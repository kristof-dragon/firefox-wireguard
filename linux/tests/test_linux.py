# SPDX-License-Identifier: MPL-2.0
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from firefox_wireguard.configuration import Configuration, UserError
from firefox_wireguard.storage import ProfileStore, SecretVault, private_directory, atomic_write
from firefox_wireguard.protocol import (EXTENSION_ID, HOST_NAME, ControlServer, InstanceLock, connect,
                                        frame, read_frame, register, registration_matches, same_user, validate)
from firefox_wireguard.engine import Tunnel, metrics, public_exit, exit_arguments
from firefox_wireguard.bridge import open_companion
from firefox_wireguard.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "linux/firefox-wireguard-bridge"
BUNDLE = ROOT / "dist/firefox-wireguard-linux"


def fixture():
    # Deterministic synthetic bytes, no deployment key or real endpoint.
    return (f"[Interface]\nPrivateKey = {base64.b64encode(bytes([7]) * 32).decode()}\n"
            "Address = 192.0.2.2/32\nDNS = 192.0.2.1\n[Peer]\n"
            f"PublicKey = {base64.b64encode(bytes([9]) * 32).decode()}\n"
            "Endpoint = vpn.example.invalid:51820\nAllowedIPs = 0.0.0.0/0\n")


class MemoryVault:
    def __init__(self):
        self.values = {}

    def read(self, key, timeout=60):
        if key not in self.values:
            raise UserError("Missing secret")
        return self.values[key]

    def write(self, key, value):
        self.values[key] = value

    def remove(self, key):
        self.values.pop(key, None)


def request(command="status", client=None, profile=None):
    value = {"version": 1, "id": "test", "command": command, "clientID": client or str(uuid.uuid4())}
    if profile is not None:
        value["profileID"] = profile
    return value


class ConfigurationTests(unittest.TestCase):
    def test_normalization_and_bare_addresses_match_macos(self):
        for address in ("192.0.2.2", "192.0.2.2/32", "192.0.2.2/24"):
            text = fixture().replace("192.0.2.2/32", address).replace("DNS =", "ListenPort = 51820\nDNS =")
            config = Configuration(text + "PersistentKeepalive = 0\n")
            self.assertEqual(config.client_ips, ["192.0.2.2"])
            self.assertEqual(config.dns_servers, ["192.0.2.1"])
            self.assertFalse(config.supports_ipv6)
            self.assertNotIn("ListenPort", config.canonical)
            self.assertIn("PersistentKeepalive = 25", config.canonical)
            self.assertIn("BindAddress = 127.0.0.1:1234", config.backend_config(1234))
            self.assertEqual(Configuration(config.canonical).canonical, config.canonical)

    def test_rejects_hooks_includes_environment_and_proxy_sections(self):
        for extra in ("PostUp = command", "WGConfig = path", "Table = off", "PrivateKey = $KEY", "DNS = 192.0.2.4"):
            with self.subTest(extra=extra), self.assertRaises(UserError):
                Configuration(fixture().replace("[Peer]", extra + "\n[Peer]"))
        for extra in ("[Peer]", "[Socks5]\nBindAddress = 0.0.0.0:1234", "TunnelDomains = example.invalid"):
            with self.subTest(extra=extra), self.assertRaises(UserError):
                Configuration(fixture() + extra)

    def test_dns_and_full_tunnel_policy(self):
        for old, new in (("DNS = 192.0.2.1", ""), ("192.0.2.1", "search.example.invalid"),
                         ("0.0.0.0/0", "192.0.2.0/24"), ("0.0.0.0/0", "0.0.0.0"),
                         ("0.0.0.0/0", "0.0.0.0/0, ::/0"), ("DNS = 192.0.2.1", "DNS = 2001:db8::1")):
            with self.subTest(new=new), self.assertRaises(UserError):
                Configuration(fixture().replace(old, new))
        dual = fixture().replace("192.0.2.2/32", "192.0.2.2, 2001:db8::2").replace("0.0.0.0/0", "0.0.0.0/0, ::/0")
        self.assertTrue(Configuration(dual).supports_ipv6)

    def test_invalid_values_and_nonreflecting_errors(self):
        for old, new in (("192.0.2.2/32", "192.0.2.2/33"), ("192.0.2.2/32", "192.0.2.999"),
                         ("192.0.2.2/32", "192.0.2.2/32/1"), ("51820", "65536"),
                         ("vpn.example.invalid", "bad host"), ("192.0.2.1", "fe80::1%eth0")):
            with self.subTest(new=new), self.assertRaises(UserError):
                Configuration(fixture().replace(old, new))
        secret = "DO-NOT-REFLECT"
        with self.assertRaises(UserError) as failure:
            Configuration(fixture().replace(base64.b64encode(bytes([7]) * 32).decode(), secret))
        self.assertNotIn(secret, str(failure.exception))
        for text in ("x" * 32769, fixture() + "\0"):
            with self.assertRaises(UserError):
                Configuration(text)


class StorageTests(unittest.TestCase):
    def test_profile_lifecycle_private_metadata_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory, vault = Path(tmp) / "data", MemoryVault()
            store = ProfileStore(directory, vault)
            p = store.save(None, "Fixture", fixture())
            saved = store.index.read_bytes()
            for private in (b"PrivateKey", b"Endpoint", b"vpn.example.invalid", b"192.0.2."):
                self.assertNotIn(private, saved)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            self.assertEqual(store.index.stat().st_mode & 0o777, 0o600)
            self.assertEqual(ProfileStore(directory, vault).profiles, [p])
            self.assertEqual(store.configuration(p["id"]).canonical, Configuration(fixture()).canonical)
            with patch.object(vault, "write", side_effect=UserError("Locked")):
                with self.assertRaises(UserError):
                    store.save(p["id"], "Changed", fixture())
                with self.assertRaises(UserError):
                    store.save(None, "New", fixture())
            self.assertEqual(store.index.read_bytes(), saved)
            store.remove(p["id"])
            self.assertFalse(store.profiles)
            self.assertFalse(vault.values)

    def test_corruption_symlinks_and_invalid_metadata_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            index = directory / "profiles.json"
            for value in (b"broken", b"{}", b'[{"id":"../bad","name":"name"}]',
                          json.dumps([{"id": str(uuid.uuid4()), "name": "name", "secret": "bad"}]).encode()):
                index.write_bytes(value)
                with self.assertRaises(UserError):
                    ProfileStore(directory, MemoryVault())
                self.assertEqual(index.read_bytes(), value)
            index.unlink()
            target = directory / "target"
            target.write_text("untouched")
            index.symlink_to(target)
            with self.assertRaises(UserError):
                ProfileStore(directory, MemoryVault())
            with self.assertRaises(UserError):
                atomic_write(index, b"replacement")
            self.assertEqual(target.read_text(), "untouched")

    def test_vault_passes_secrets_only_over_stdin_and_fails_closed(self):
        vault, profile_id = SecretVault(), str(uuid.uuid4())
        with patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
            vault.write(profile_id, "private-value")
            self.assertNotIn("private-value", repr(run.call_args.args))
            self.assertEqual(run.call_args.kwargs["input"], b"private-value")
            run.return_value = subprocess.CompletedProcess([], 1, b"", b"locked")
            with self.assertRaises(UserError):
                vault.read(profile_id)
            with self.assertRaises(UserError):
                vault.remove(profile_id)
            run.return_value = subprocess.CompletedProcess([], 1, b"", b"")
            vault.remove(profile_id)  # Removing an already absent secret is idempotent.

    @unittest.skipUnless(os.environ.get("FWG_TEST_SECRET_SERVICE") == "1", "Opt-in disposable Secret Service entry")
    def test_real_secret_service(self):
        vault, key = SecretVault("org.firefoxwireguard.tests." + str(uuid.uuid4())), str(uuid.uuid4())
        try:
            vault.write(key, "temporary fixture")
            self.assertEqual(vault.read(key).rstrip("\n"), "temporary fixture")
            vault.write(key, "updated fixture")
            self.assertEqual(vault.read(key).rstrip("\n"), "updated fixture")
            config = Configuration(fixture()).canonical
            vault.write(key, config)
            self.assertEqual(Configuration(vault.read(key)).canonical, config)
        finally:
            vault.remove(key)


class ProtocolTests(unittest.TestCase):
    def test_framing_and_validation(self):
        data = json.dumps(request()).encode()
        self.assertEqual(read_frame(io.BytesIO(frame(data)).read), data)
        for raw in (b"\x01", struct.pack("<I", 65537), struct.pack("<I", 0), struct.pack("<I", 2) + b"x"):
            with self.assertRaises(UserError):
                read_frame(io.BytesIO(raw).read)
        for changes in ({"command": "exec"}, {"version": True}, {"version": 2}, {"clientID": "bad"},
                        {"profileID": "../secret"}, {"id": "x" * 81}):
            with self.assertRaises(UserError):
                validate(request() | changes)

    def test_private_socket_roundtrip_and_peer_identity(self):
        with tempfile.TemporaryDirectory(prefix="fwgt-") as tmp:
            path = Path(tmp) / "control.sock"
            server = ControlServer(lambda r: {"id": r["id"], "ok": True}, path)
            try:
                with connect(path) as sock:
                    self.assertTrue(same_user(sock))
                    sock.sendall(frame(json.dumps(request()).encode()))
                    self.assertTrue(json.loads(read_frame(sock.recv))["ok"])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            finally:
                server.close()
            self.assertFalse(path.exists())

    def test_failed_startup_releases_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "profiles.json").write_text("broken")
            with self.assertRaises(UserError):
                Runtime(HELPER, directory, MemoryVault(), directory / "control.sock", directory / "manifest.json")
            lock = InstanceLock(directory)
            try:
                with self.assertRaises(UserError):
                    InstanceLock(directory)
            finally:
                lock.close()

    def test_only_connect_launches_and_retry_is_bounded(self):
        helper, calls = HELPER, []
        def unavailable():
            raise OSError()
        for command in ("status", "disconnect"):
            with self.assertRaises(UserError):
                open_companion(command, helper, unavailable, lambda: calls.append(1), lambda _: None)
        self.assertFalse(calls)
        with self.assertRaises(UserError):
            open_companion("connect", helper, unavailable, lambda: calls.append(1), lambda _: None)
        self.assertEqual(calls, [1])

    def test_real_bridge_origin_framing_stale_registration_and_runtime(self):
        with tempfile.TemporaryDirectory(prefix="fwgt-") as tmp:
            directory = Path(tmp)
            env = dict(os.environ, XDG_DATA_HOME=tmp, XDG_RUNTIME_DIR=tmp)
            path = directory / "firefox-wireguard/control.sock"
            manifest = directory / "manifest.json"
            register(HELPER, manifest)
            runtime = Runtime(HELPER, directory / "data", MemoryVault(), path, manifest)
            try:
                profile = runtime.save(None, "Synthetic fixture", fixture())
                def run(origin=EXTENSION_ID):
                    return subprocess.run([str(HELPER), str(manifest), origin], input=frame(json.dumps(request()).encode()),
                                          capture_output=True, env=env, timeout=5)
                result = run()
                self.assertEqual(result.stderr, b"")
                answer = json.loads(read_frame(io.BytesIO(result.stdout).read))
                self.assertTrue(answer["ok"])
                self.assertEqual(answer["profiles"], [profile])
                self.assertNotIn(b"PrivateKey", result.stdout)
                self.assertEqual(run("wrong@origin.invalid").stdout, b"")
                manifest.write_text(json.dumps({"path": "/another/bridge"}))
                self.assertEqual(run().stdout, b"")
            finally:
                runtime.close()

    @unittest.skipUnless(os.environ.get("FWG_TEST_BACKEND") == "1", "Opt-in packaged companion lifecycle")
    def test_packaged_companion_quit_and_explicit_connect_launch(self):
        with tempfile.TemporaryDirectory(prefix="fwgt-") as tmp:
            directory = Path(tmp)
            bundle = directory / "bundle"
            shutil.copytree(BUNDLE, bundle)
            helper = bundle / "firefox-wireguard-bridge"
            manifest = directory / "manifest.json"
            # XDG isolation alone is insufficient: native Firefox registration
            # lives under ~/.mozilla. Inject a private registration path into
            # this packaged-app test, so automatic repair cannot change a live
            # user's manifest while their tunnel is running.
            launcher = bundle / "firefox-wireguard"
            launcher.write_text(
                "#!/usr/bin/python3 -I\n"
                "import sys\nfrom pathlib import Path\nfrom unittest.mock import patch\n"
                "bundle = Path(__file__).resolve().parent\n"
                "sys.path.insert(0, str(bundle))\n"
                "from firefox_wireguard.app import main\n"
                "with patch('firefox_wireguard.runtime.manifest_path', return_value=bundle.parent / 'manifest.json'):\n"
                "    sys.exit(main(bundle))\n")
            register(helper, manifest)
            path = directory / "firefox-wireguard/control.sock"
            env = dict(os.environ, XDG_DATA_HOME=tmp, XDG_RUNTIME_DIR=tmp, QT_QPA_PLATFORM="offscreen")
            pid = None
            def run(command):
                result = subprocess.run([str(helper), str(manifest), EXTENSION_ID],
                                        input=frame(json.dumps(request(command, profile=str(uuid.uuid4()))).encode()),
                                        capture_output=True, env=env, timeout=8)
                self.assertEqual(result.stderr, b"")
                return json.loads(read_frame(io.BytesIO(result.stdout).read))
            try:
                for command in ("status", "disconnect"):
                    self.assertFalse(run(command)["ok"])
                    self.assertFalse(path.exists(), "Polling must respect Quit")
                self.assertFalse(run("connect")["ok"])  # A nonexistent profile, but the app must launch.
                with connect(path) as control:
                    pid, _, _ = struct.unpack("3i", control.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                self.assertTrue(run("status")["ok"])
            finally:
                if pid is not None:
                    os.kill(pid, 15)
                    deadline = time.monotonic() + 5
                    while path.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertFalse(path.exists(), "Companion did not shut down")

    def test_foreign_uid_is_rejected(self):
        class ForeignSocket:
            def getsockopt(self, *_):
                return struct.pack("3i", 123, os.getuid() + 1, 123)
        self.assertFalse(same_user(ForeignSocket()))


class EngineTests(unittest.TestCase):
    def test_metrics_and_public_response_validation(self):
        valid = b"rx_bytes=123\ntx_bytes=42\nlast_handshake_time_sec=100\nprivate_key=REDACTED\n"
        self.assertEqual(metrics(valid)["rx_bytes"], 123)
        for bad in (valid + b"rx_bytes=1\n", valid.replace(b"123", b"-1"), valid.replace(b"123", str(2**64).encode()), b"rx_bytes=1"):
            with self.assertRaises(UserError):
                metrics(bad)
        self.assertEqual(public_exit(b'{"success":true,"ip":"203.0.113.8","country_code":"gb"}'),
                         {"publicIP": "203.0.113.8", "countryCode": "GB"})
        for bad in (b"{}", b"[]", b'{"success":true,"ip":"not-an-ip"}'):
            with self.assertRaises(UserError):
                public_exit(bad)
        args = exit_arguments(1234)
        self.assertEqual(args[1], "--disable")
        self.assertIn("socks5h://127.0.0.1:1234", args)
        self.assertEqual(args[args.index("--noproxy") + 1], "")

    def test_owner_lease_failure_and_health_readiness(self):
        tunnel = Tunnel(HELPER, poll_interval=3600)
        class Process:
            def poll(self):
                return None
        try:
            tunnel.process, tunnel.owner = Process(), "owner"
            tunnel.state = {"phase": "connecting", "proxyPort": 1234, "details": {"connectionID": "fixture"}}
            self.assertFalse(tunnel.owns("other"))
            with self.assertRaises(UserError):
                tunnel.connect({"id": "fixture"}, Configuration(fixture()), "other")
            class Response:
                status = 200
                def read(self, _limit):
                    return f"rx_bytes=10\ntx_bytes=20\nlast_handshake_time_sec={int(time.time())}\n".encode()
            with patch("http.client.HTTPConnection") as http, patch.object(tunnel, "_update_exit"):
                http.return_value.getresponse.return_value = Response()
                tunnel.poll()
            self.assertEqual(tunnel.snapshot()["phase"], "connected")
            tunnel.started = time.monotonic() - 31
            with patch("http.client.HTTPConnection", side_effect=OSError()):
                tunnel.poll()
            self.assertEqual(tunnel.snapshot()["phase"], "blocked")
            self.assertNotIn("statsUpdatedAt", tunnel.snapshot()["details"])
            tunnel.last_lease = time.monotonic() - 13
            with patch("firefox_wireguard.engine.terminate"):
                tunnel.poll()
            self.assertIsNone(tunnel.owner)
            self.assertNotIn("proxyPort", tunnel.snapshot())
        finally:
            tunnel.process = None
            tunnel.close()

    def test_stop_cancels_a_pending_secret_lookup(self):
        with tempfile.TemporaryDirectory(prefix="fwgt-") as tmp:
            directory, vault = Path(tmp), MemoryVault()
            runtime = Runtime(HELPER, directory, vault, directory / "control.sock", directory / "manifest.json")
            try:
                profile = runtime.save(None, "Fixture", fixture())
                original = vault.read
                def read(key, timeout=60):
                    runtime.stop()
                    return original(key, timeout)
                with patch.object(vault, "read", side_effect=read):
                    answer = runtime.handle(request("connect", profile=profile["id"]))
                self.assertFalse(answer["ok"])
                self.assertIsNone(runtime.tunnel.process)
            finally:
                runtime.close()

    @unittest.skipUnless(os.environ.get("FWG_TEST_BACKEND") == "1", "Opt-in packaged backend tests")
    def test_packaged_backend_parent_death_closes_proxy(self):
        self.assertTrue((BUNDLE / "wireproxy").is_file(), "Build first")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            health = sock.getsockname()[1]
        # Parent forwards in-memory configuration, then is killed. Supervisor must
        # observe parent death; wireproxy must also die if the supervisor is killed.
        code = ("import subprocess,sys,os,time; p=subprocess.Popen([sys.argv[1],'--run-backend',sys.argv[2],str(os.getpid())],"
                "stdin=sys.stdin,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); print(p.pid,flush=True); time.sleep(60)")
        for kill_supervisor in (False, True):
            parent = subprocess.Popen([sys.executable, "-c", code, str(BUNDLE / "firefox-wireguard-bridge"), str(health)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            supervisor = int(parent.stdout.readline())
            try:
                config = Configuration(fixture().replace("vpn.example.invalid", "127.0.0.1"))
                parent.stdin.write(config.backend_config(port).encode())
                parent.stdin.close()
                deadline = time.monotonic() + 5
                while True:
                    try:
                        socket.create_connection(("127.0.0.1", port), 0.2).close()
                        break
                    except OSError:
                        self.assertLess(time.monotonic(), deadline, "Backend never listened")
                        time.sleep(0.05)
                if kill_supervisor:
                    os.kill(supervisor, 9)
                else:
                    parent.kill()
                deadline = time.monotonic() + 5
                while True:
                    try:
                        socket.create_connection(("127.0.0.1", port), 0.2).close()
                        self.assertLess(time.monotonic(), deadline, "Orphan backend still listening")
                        time.sleep(0.05)
                    except OSError:
                        break
            finally:
                parent.kill()
                parent.wait(timeout=5)
                parent.stdout.close()
                try:
                    os.kill(supervisor, 15)
                except ProcessLookupError:
                    pass


class InstallerTests(unittest.TestCase):
    def test_isolated_install_update_uninstall_preserves_profiles(self):
        spec = importlib.util.spec_from_file_location("installer", ROOT / "linux/install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory(prefix="fwg space-") as tmp:
            home = Path(tmp)
            bundle = home / "bundle"
            bundle.mkdir()
            for name in ("firefox-wireguard", "firefox-wireguard-bridge", "wireproxy", "icon.svg"):
                (bundle / name).write_text("fixture")
                (bundle / name).chmod(0o755)
            manifest = home / ".mozilla/native-messaging-hosts" / f"{HOST_NAME}.json"
            data = home / "data"
            private_directory(data)
            (data / "profiles.json").write_text("[]")
            with (patch.object(installer, "BUNDLE", bundle), patch.object(Path, "home", return_value=home),
                  patch.object(installer, "data_directory", return_value=data),
                  patch.object(installer, "manifest_path", return_value=manifest),
                  patch.object(installer, "xdg_path", return_value=home / "share"), patch("os.getuid", return_value=os.getuid()),
                  patch("sys.argv", ["install.py"])):
                installer.main()
                destination = home / ".local/lib/firefox-wireguard"
                self.assertTrue(registration_matches(destination / "firefox-wireguard-bridge", manifest))
                installer.main()  # Replace the recognised installation.
                with patch("sys.argv", ["install.py", "--uninstall"]):
                    installer.main()
                self.assertFalse(destination.exists())
                self.assertFalse(manifest.exists())
                self.assertEqual((data / "profiles.json").read_text(), "[]")


if __name__ == "__main__":
    unittest.main()
