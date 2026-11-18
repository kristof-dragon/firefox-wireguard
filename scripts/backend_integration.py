#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""A local encrypted WireGuard round trip; no system VPN or real credentials.

Requires the packaged app, Python 3, and OpenSSL with X25519 support. All keys
are generated in memory for this test and never printed or written to disk.
"""
import base64
import http.server
import os
import platform
from pathlib import Path
import socket
import struct
import subprocess
import threading
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
contents = Path(os.environ.get("FWG_TEST_APP", root / "dist" / "Firefox WireGuard.app")) / "Contents"
backend = contents / "Resources" / "wireproxy"
supervisor = contents / "MacOS" / "firefox-wireguard-bridge"
if platform.system() == "Linux":
    bundle = Path(os.environ.get("FWG_TEST_APP", root / "dist/firefox-wireguard-linux"))
    backend, supervisor = bundle / "wireproxy", bundle / "firefox-wireguard-bridge"
if not backend.is_file() or not supervisor.is_file():
    raise SystemExit("Build the app with scripts/build.sh first.")


def keys():
    private = subprocess.run(["openssl", "genpkey", "-algorithm", "X25519", "-outform", "DER"], check=True, capture_output=True).stdout
    public = subprocess.run(["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"], input=private, check=True, capture_output=True).stdout
    assert len(private) == 48 and len(public) == 44, "Unexpected X25519 encoding"
    return base64.b64encode(private[-32:]).decode(), base64.b64encode(public[-32:]).decode()


def free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def receive(sock, count):
    data = b""
    while len(data) < count:
        block = sock.recv(count - len(data))
        if not block:
            raise ConnectionError("Unexpected EOF")
        data += block
    return data


def through_proxy(port, address, destination_port):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        sock.settimeout(3)
        sock.sendall(bytes([5, 1, 0]))
        assert receive(sock, 2) == bytes([5, 0]), "SOCKS negotiation failed"
        sock.sendall(bytes([5, 1, 0, 1]) + socket.inet_aton(address) + struct.pack("!H", destination_port))
        reply = receive(sock, 4)
        if reply[1] != 0:
            raise ConnectionError("SOCKS connection rejected")
        assert reply[3] == 1
        receive(sock, 6)
        sock.sendall(b"GET / HTTP/1.0\r\nHost: fixture.example.invalid\r\n\r\n")
        data = b""
        while True:
            block = sock.recv(4096)
            if not block:
                return data
            data += block


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"encrypted-wireguard-roundtrip"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


processes = []
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def start(command, configuration):
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes.append(proc)
    proc.stdin.write(configuration.encode())
    proc.stdin.close()
    return proc


try:
    server_private, server_public = keys()
    client_private, client_public = keys()
    udp_port, proxy_port, health_port = free_port(socket.SOCK_DGRAM), free_port(), free_port()
    server_config = f"""[Interface]
PrivateKey = {server_private}
Address = 192.0.2.1/32
ListenPort = {udp_port}
DNS = 192.0.2.1
[Peer]
PublicKey = {client_public}
AllowedIPs = 192.0.2.2/32
[TCPServerTunnel]
ListenPort = 8080
Target = 127.0.0.1:{httpd.server_port}
"""
    client_config = f"""[Interface]
PrivateKey = {client_private}
Address = 192.0.2.2/32
DNS = 192.0.2.1
[Peer]
PublicKey = {server_public}
Endpoint = 127.0.0.1:{udp_port}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
[Socks5]
BindAddress = 127.0.0.1:{proxy_port}
"""
    server = start([str(backend), "-c", "/dev/stdin", "-s"], server_config)
    client = start([str(supervisor), "--run-backend", str(health_port), str(os.getpid())], client_config)
    deadline = time.monotonic() + 20
    while True:
        try:
            response = through_proxy(proxy_port, "192.0.2.1", 8080)
            assert b"encrypted-wireguard-roundtrip" in response
            break
        except (OSError, AssertionError):
            if time.monotonic() >= deadline or client.poll() is not None or server.poll() is not None:
                raise AssertionError("Local WireGuard round trip did not complete") from None
            time.sleep(0.2)
    print("PASS: SOCKS request crossed a real encrypted WireGuard session to the local test peer.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{health_port}/metrics", timeout=2) as result:
        metrics = result.read(65_536).decode()
    stamps = [int(line.split("=", 1)[1]) for line in metrics.splitlines() if line.startswith("last_handshake_time_sec=")]
    assert stamps and max(stamps) > time.time() - 30
    assert client_private not in metrics and "private_key=REDACTED" in metrics
    print("PASS: backend reports a recent handshake and redacts private keys from metrics.")
    # The same numerical destination exists on this machine, but through SOCKS
    # loopback refers to the peer's userspace network, not the host's TCP listener.
    try:
        through_proxy(proxy_port, "127.0.0.1", httpd.server_port)
        raise AssertionError("The backend unexpectedly dialled the host directly")
    except OSError:
        pass
    print("PASS: proxy failure did not fall back to a direct host connection.")
    client.terminate()
    client.wait(timeout=5)
    time.sleep(0.3)
    with socket.socket() as sock:
        sock.settimeout(1)
        assert sock.connect_ex(("127.0.0.1", proxy_port)) != 0, "Orphan backend still listening"
    print("PASS: stopping the supervisor terminates its backend and closes the proxy.")
    if platform.system() == "Linux":
        # Exercise the actual Linux app runtime as well as its standalone
        # supervisor. Memory-only vault; no desktop wallet/profile is touched.
        import sys
        import uuid
        from unittest.mock import patch
        sys.path.insert(0, str(root / "linux"))
        from firefox_wireguard.runtime import Runtime
        from firefox_wireguard.protocol import connect, frame, read_frame
        import json
        class MemoryVault:
            def __init__(self):
                self.values = {}
            def read(self, key, timeout=60):
                return self.values[key]
            def write(self, key, value):
                self.values[key] = value
        with tempfile.TemporaryDirectory(prefix="fwg-engine-") as temporary:
            directory = Path(temporary)
            runtime = Runtime(supervisor, directory, MemoryVault(), directory / "control.sock", directory / "manifest.json")
            try:
                profile = runtime.save(None, "Local encrypted fixture", client_config.split("[Socks5]")[0])
                owner, other = str(uuid.uuid4()), str(uuid.uuid4())
                def command(name, client=owner):
                    # Use the real server: connect is handled on a short-lived
                    # thread. The supervisor must survive that thread's exit.
                    with connect(directory / "control.sock") as control:
                        control.sendall(frame(json.dumps({"version": 1, "id": "fixture", "command": name,
                                                          "clientID": client, "profileID": profile["id"]}).encode()))
                        return json.loads(read_frame(control.recv))
                # Do not call an Internet IP provider from this local fixture.
                with patch.object(runtime.tunnel, "_update_exit"):
                    assert command("connect")["state"]["phase"] == "connecting"
                    deadline = time.monotonic() + 15
                    while command("status")["state"]["phase"] != "connected":
                        assert time.monotonic() < deadline, "Linux runtime did not observe the handshake"
                        time.sleep(0.2)
                    state = command("status")["state"]
                    assert state["details"]["downloadedBytes"] >= 0
                    assert b"encrypted-wireguard-roundtrip" in through_proxy(state["proxyPort"], "192.0.2.1", 8080)
                    assert command("status", other)["busy"] is True
                    assert command("connect", other)["ok"] is False
                    assert command("disconnect", other)["ok"] is False
                    assert command("disconnect")["state"]["phase"] == "idle"
                print("PASS: Linux runtime connects only after a handshake, exposes counters, isolates owners, and disconnects.")
            finally:
                runtime.close()
finally:
    for proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
    httpd.shutdown()
