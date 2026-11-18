# SPDX-License-Identifier: MPL-2.0
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import threading
import uuid

from .configuration import Configuration, UserError


def xdg_path(variable, fallback):
    value = os.environ.get(variable, "")
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def data_directory():
    return xdg_path("XDG_DATA_HOME", ".local/share") / "firefox-wireguard"


def runtime_directory():
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    return Path(runtime) / "firefox-wireguard" if runtime and Path(runtime).is_absolute() else data_directory()


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise UserError("Application storage must be a directory owned by the current user.")
    path.chmod(0o700)


def atomic_write(path, data):
    """Create private before writing, then atomically replace; never follow a leaf symlink."""
    if path.is_symlink():
        raise UserError("Refusing to replace a symbolic link in application storage.")
    fd, temporary = tempfile.mkstemp(prefix=".fwg-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def valid_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


class SecretVault:
    """libsecret talks to KDE's KSecretD/KWallet (or another Secret Service).

    No plaintext fallback. Values travel over stdin/stdout, never argv or logs.
    Lookup has a shorter deadline for Firefox's seven-second request timeout.
    """
    def __init__(self, service="org.firefoxwireguard.profiles"):
        self.service = service

    def _run(self, operation, profile_id, value=None, timeout=60):
        arguments = ["/usr/bin/secret-tool", operation]
        if operation == "store":
            arguments += ["--label=Firefox WireGuard profile"]
        arguments += ["application", self.service, "profile", profile_id]
        try:
            result = subprocess.run(arguments, input=value.encode() if value is not None else b"",
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise UserError("Secret storage is unavailable. Unlock KWallet, then retry; libsecret-tools is required.") from None
        # secret-tool clear returns 1 without diagnostics if no item matches.
        # Errors from a locked/unavailable service include diagnostics, which we
        # inspect only for presence, never display or log.
        if operation == "clear" and result.returncode == 1 and not result.stderr:
            return ""
        if result.returncode != 0:
            raise UserError("Could not access the profile in Secret Service. Unlock KWallet and retry.")
        if len(result.stdout) > 32769:
            raise UserError("Invalid profile in secret storage.")
        return result.stdout.decode("utf-8")

    def read(self, profile_id, timeout=60):
        return self._run("lookup", profile_id, timeout=timeout)

    def write(self, profile_id, value):
        self._run("store", profile_id, value)

    def remove(self, profile_id):
        self._run("clear", profile_id)


class ProfileStore:
    def __init__(self, directory, vault=None):
        self.directory, self.vault = directory, vault or SecretVault()
        self.lock = threading.RLock()
        self.writes = threading.Lock()
        private_directory(directory)
        self.index = directory / "profiles.json"
        self._profiles = []
        if self.index.exists() or self.index.is_symlink():
            try:
                fd = os.open(self.index, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 32768:
                        raise ValueError()
                    os.fchmod(stream.fileno(), 0o600)
                    profiles = json.load(stream)
                if not isinstance(profiles, list) or len(profiles) > 100:
                    raise ValueError()
                seen = set()
                for p in profiles:
                    if (not isinstance(p, dict) or set(p) != {"id", "name"} or not valid_uuid(p["id"])
                            or p["id"].lower() in seen or not self.valid_name(p["name"])):
                        raise ValueError()
                    seen.add(p["id"].lower())
                self._profiles = profiles
            except (OSError, ValueError, TypeError):
                raise UserError("Profile metadata is unreadable or corrupt. It has not been overwritten.") from None

    @staticmethod
    def valid_name(name):
        return isinstance(name, str) and 0 < len(name.strip()) <= 80 and not any(ord(c) < 32 for c in name)

    @property
    def profiles(self):
        with self.lock:
            return [dict(p) for p in self._profiles]

    def _persist(self, profiles):
        data = json.dumps(profiles, ensure_ascii=True).encode()
        if len(data) > 32768:
            raise UserError("Profile metadata is too large. Shorten profile names or remove unused profiles.")
        atomic_write(self.index, data)
        with self.lock:
            self._profiles = profiles

    def configuration(self, profile_id, timeout=60):
        if not any(p["id"] == profile_id for p in self.profiles):
            raise UserError("Choose an existing profile.")
        return Configuration(self.vault.read(profile_id, timeout=timeout))

    def save(self, profile_id, name, text):
        if not self.valid_name(name):
            raise UserError("Enter a profile name of 1–80 characters without control characters.")
        config = Configuration(text)
        with self.writes:
            if profile_id is not None and not any(p["id"] == profile_id for p in self._profiles):
                raise UserError("Choose an existing profile.")
            if profile_id is None and len(self._profiles) >= 100:
                raise UserError("A maximum of 100 profiles is supported.")
            profile = {"id": profile_id or str(uuid.uuid4()), "name": name.strip()}
            # Reserve an index entry before writing the secret. If the vault fails,
            # restore the index; a failed rollback still leaves a removable entry.
            previous = self._profiles
            next_profiles = [profile if p["id"] == profile_id else p for p in previous]
            if profile_id is None:
                next_profiles.append(profile)
            self._persist(next_profiles)
            try:
                self.vault.write(profile["id"], config.canonical)
            except Exception:
                self._persist(previous)
                raise
            return profile

    def remove(self, profile_id):
        with self.writes:
            self.vault.remove(profile_id)
            self._persist([p for p in self._profiles if p["id"] != profile_id])
