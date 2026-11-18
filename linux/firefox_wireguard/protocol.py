# SPDX-License-Identifier: MPL-2.0
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import struct
import threading

from .configuration import UserError
from .storage import atomic_write, private_directory, runtime_directory, valid_uuid

EXTENSION_ID = "firefox-wireguard@local.invalid"
HOST_NAME = "org.firefoxwireguard.bridge"
MAX_FRAME = 65536


def socket_path():
    path = runtime_directory() / "control.sock"
    if len(os.fsencode(path)) >= 108:
        raise UserError("Application storage path is too long for the control socket. Set XDG_RUNTIME_DIR.")
    return path


def manifest_path():
    return Path.home() / ".mozilla/native-messaging-hosts" / f"{HOST_NAME}.json"


def registration_matches(helper, manifest):
    try:
        entry = json.loads(manifest.read_bytes())
        return (entry.get("path") == str(helper.resolve()) and entry.get("name") == HOST_NAME
                and entry.get("type") == "stdio" and entry.get("allowed_extensions") == [EXTENSION_ID])
    except (OSError, ValueError, AttributeError):
        return False


def register(helper, manifest=None):
    manifest = manifest or manifest_path()
    if not helper.is_file() or not os.access(helper, os.X_OK):
        raise UserError("Use the packaged companion to install Firefox integration.")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(manifest, json.dumps({"name": HOST_NAME, "description": "Firefox WireGuard companion",
                                     "path": str(helper.resolve()), "type": "stdio",
                                     "allowed_extensions": [EXTENSION_ID]}, indent=2).encode())


def validate(request):
    if (not isinstance(request, dict) or type(request.get("version")) is not int or request["version"] != 1
            or not isinstance(request.get("id"), str) or len(request["id"]) > 80
            or request.get("command") not in ("status", "connect", "disconnect")
            or not valid_uuid(request.get("clientID"))
            or (request.get("profileID") is not None and not valid_uuid(request["profileID"]))):
        raise UserError("Unsupported or invalid control request.")
    return request


def read_frame(read):
    def exact(count, allow_eof=False):
        data = bytearray()
        while len(data) < count:
            block = read(count - len(data))
            if not block:
                if not data and allow_eof:
                    return None
                raise UserError("The local connection ended unexpectedly.")
            data.extend(block)
        return bytes(data)
    header = exact(4, True)
    if header is None:
        return None
    size, = struct.unpack("<I", header)
    if not 0 < size <= MAX_FRAME:
        raise UserError("Invalid message size.")
    return exact(size)


def frame(data):
    if not 0 < len(data) <= MAX_FRAME:
        raise UserError("Invalid message size.")
    return struct.pack("<I", len(data)) + data


def same_user(sock):
    _, uid, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    return uid == os.getuid()


def connect(path=None):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect(str(path or socket_path()))
        if not same_user(sock):
            raise UserError("The companion must run as the current user.")
        return sock
    except Exception:
        sock.close()
        raise


class InstanceLock:
    def __init__(self, directory):
        private_directory(directory)
        self.fd = os.open(directory / "app.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise OSError()
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise UserError("Another companion may be running. Quit it, then retry startup.") from None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class ControlServer:
    def __init__(self, handler, path=None):
        self.path = path or socket_path()
        self.handler = handler
        self.stopped = threading.Event()
        self.slots = threading.BoundedSemaphore(8)
        private_directory(self.path.parent)
        if self.path.exists() or self.path.is_symlink():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise UserError("Unexpected file at the control socket path.")
            try:
                live = connect(self.path)
            except OSError:
                self.path.unlink()
            else:
                live.close()
                raise UserError("Another companion is already running.")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.bind(str(self.path))
            self.path.chmod(0o600)
            self.sock.listen(8)
            self.sock.settimeout(0.5)
        except Exception:
            self.sock.close()
            raise
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not self.slots.acquire(blocking=False):
                client.close()
                continue
            threading.Thread(target=self._client, args=(client,), daemon=True).start()

    def _client(self, client):
        try:
            with client:
                client.settimeout(5)
                if not same_user(client):
                    return
                data = read_frame(client.recv)
                if data is None or self.stopped.is_set():
                    return
                request = validate(json.loads(data))
                response = self.handler(request)
                client.sendall(frame(json.dumps(response).encode()))
        except (OSError, UserError, ValueError, TypeError, RecursionError):
            pass  # Neither malformed input nor secrets are reflected or logged.
        finally:
            self.slots.release()

    def close(self):
        self.stopped.set()
        self.sock.close()
        self.thread.join(timeout=1)
        self.path.unlink(missing_ok=True)
