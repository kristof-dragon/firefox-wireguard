# SPDX-License-Identifier: MPL-2.0
import copy
import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import uuid

from .configuration import UserError, ip


def idle():
    return {"phase": "idle", "supportsIPv6": False}


def metrics(data):
    if len(data) > 65536:
        raise UserError("Invalid backend metrics.")
    values = {}
    try:
        for line in data.decode("utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in ("rx_bytes", "tx_bytes", "last_handshake_time_sec"):
                if key in values or not re.fullmatch(r"[0-9]+", value) or int(value) > 2**64 - 1:
                    raise ValueError()
                values[key] = int(value)
        if len(values) != 3:
            raise ValueError()
    except (UnicodeError, ValueError):
        raise UserError("Invalid or incomplete backend metrics.") from None
    return values


def public_exit(data):
    try:
        if len(data) > 16384:
            raise ValueError()
        result = json.loads(data)
        if result.get("success") is not True or not isinstance(result.get("ip"), str):
            raise ValueError()
        ip(result["ip"])
        code = result.get("country_code")
        code = code.upper() if isinstance(code, str) else ""
        return {"publicIP": result["ip"], **({"countryCode": code} if re.fullmatch(r"[A-Z]{2}", code) else {})}
    except (ValueError, AttributeError, TypeError):
        raise UserError("Public IP lookup unavailable.") from None


def exit_arguments(port):
    return ["/usr/bin/curl", "--disable", "--proxy", f"socks5h://127.0.0.1:{port}", "--noproxy", "",
            "--proto", "=https", "--connect-timeout", "5", "--max-time", "10", "--max-filesize", "16384",
            "--silent", "--fail", "--header", "Accept: application/json",
            "--url", "https://ipwho.is/?fields=success,ip,country_code"]


def terminate(process):
    if process is not None:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


class Tunnel:
    def __init__(self, helper, poll_interval=2):
        self.helper = Path(helper)
        self.lock = threading.RLock()
        self.state = idle()
        self.process = None
        self.owner = None
        self.health_port = None
        self.started = self.last_lease = time.monotonic()
        self.generation = 0
        self.exit_generation = 0
        self.exit_process = None
        self.next_lookup = 0
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(poll_interval,), daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def owns(self, client):
        with self.lock:
            return self.owner is None or self.owner == client

    def renew(self, client):
        with self.lock:
            if self.owner == client:
                self.last_lease = time.monotonic()

    def connect(self, profile, configuration, client):
        with self.lock:
            if not self.owns(client):
                raise UserError("Another Firefox profile owns the active tunnel. Disconnect it first.")
            if self.closed.is_set():
                raise UserError("Companion app is closing.")
            self.stop()
            backend = self.helper.parent / "wireproxy"
            if not os.access(self.helper, os.X_OK) or not os.access(backend, os.X_OK):
                raise UserError("The packaged WireGuard backend is missing. Rebuild the Linux companion.")
            reservations = [socket.socket(), socket.socket()]
            try:
                for sock in reservations:
                    sock.bind(("127.0.0.1", 0))
                proxy_port, self.health_port = [s.getsockname()[1] for s in reservations]
            finally:
                for sock in reservations:
                    sock.close()
            # A bind race fails startup; it must never choose a direct route.
            try:
                process = subprocess.Popen([str(self.helper), "--run-backend", str(self.health_port), str(os.getpid())],
                                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                raise UserError("Unable to start the WireGuard backend.") from None
            self.process, self.owner = process, client
            self.started = self.last_lease = time.monotonic()
            self.state = {"phase": "connecting", "profileID": profile["id"], "proxyPort": proxy_port,
                          "supportsIPv6": configuration.supports_ipv6,
                          "details": {"connectionID": str(uuid.uuid4()), "clientIPs": configuration.client_ips,
                                      "dnsServers": configuration.dns_servers, "exitStatus": "waiting"}}
            data = configuration.backend_config(proxy_port).encode()
            def send_config():
                try:
                    with process.stdin:
                        process.stdin.write(data)
                except OSError:
                    pass
            threading.Thread(target=send_config, daemon=True).start()

    def _invalidate_exit(self):
        self.exit_generation += 1
        if self.exit_process is not None and self.exit_process.poll() is None:
            self.exit_process.terminate()
        self.exit_process = None
        self.next_lookup = 0
        details = self.state.get("details", {})
        for key in ("publicIP", "countryCode", "exitCheckedAt"):
            details.pop(key, None)
        details["exitStatus"] = "waiting"

    def stop(self, reason=None):
        with self.lock:
            self.generation += 1
            self._invalidate_exit()
            process, self.process = self.process, None
            # The supervisor stops its child; its child also has a kernel parent-death signal.
            terminate(process)
            self.owner, self.health_port = None, None
            self.state = idle()
            if reason:
                self.state.update(phase="blocked", error=reason)

    def _run(self, interval):
        while not self.closed.wait(interval):
            self.poll()

    def poll(self):
        with self.lock:
            if self.process is None:
                return
            if time.monotonic() - self.last_lease > 12:
                self.stop("Firefox is no longer responding. Reconnect from the extension.")
                return
            if self.process.poll() is not None:
                self.state.update(phase="blocked", error="The WireGuard backend stopped. Reconnect to retry.")
                self.state.pop("proxyPort", None)
                self.state.get("details", {}).pop("statsUpdatedAt", None)
                self._invalidate_exit()
                return
            token, port = self.generation, self.health_port
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                connection.request("GET", "/metrics")
                response = connection.getresponse()
                if response.status != 200:
                    raise UserError("Invalid backend response.")
                value = metrics(response.read(65537))
            finally:
                connection.close()
            with self.lock:
                if token != self.generation:
                    return
                self.state["details"].update(downloadedBytes=value["rx_bytes"], uploadedBytes=value["tx_bytes"],
                                             statsUpdatedAt=time.time())
                stamp = value["last_handshake_time_sec"]
                age = max(0, int(time.time() - stamp)) if stamp else None
                self.state["handshakeAge"] = age
                if age is not None and age < 180:
                    self.state.update(phase="connected")
                    self.state.pop("error", None)
                    self._update_exit()
                elif time.monotonic() - self.started > 30:
                    self.state.update(phase="blocked", error="No recent WireGuard handshake. Check the server, endpoint, and keys.")
                    self._invalidate_exit()
        except (OSError, http.client.HTTPException, UserError):
            with self.lock:
                if token == self.generation and time.monotonic() - self.started > 5:
                    self.state.update(phase="blocked", error="The WireGuard backend is not responding. Reconnect to retry.")
                    self.state["details"].pop("statsUpdatedAt", None)
                    self._invalidate_exit()

    def _update_exit(self):
        if self.exit_process is not None or time.monotonic() < self.next_lookup:
            return
        self.next_lookup = time.monotonic() + 300
        self.state["details"]["exitStatus"] = "checking"
        self.exit_generation += 1
        token = self.exit_generation
        try:
            process = subprocess.Popen(exit_arguments(self.state["proxyPort"]), env={}, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.state["details"]["exitStatus"] = "unavailable"
            return
        self.exit_process = process
        def lookup():
            result = None
            try:
                # Curl enforces response and time limits, including chunked responses.
                data, _ = process.communicate(timeout=12)
                if process.returncode == 0:
                    result = public_exit(data)
            except (OSError, UserError, subprocess.TimeoutExpired):
                terminate(process)
            with self.lock:
                if token != self.exit_generation or self.state["phase"] != "connected":
                    return
                self.exit_process = None
                details = self.state["details"]
                for key in ("publicIP", "countryCode"):
                    details.pop(key, None)
                details.update(result or {})
                details.update(exitStatus="ready" if result else "unavailable", exitCheckedAt=time.time())
        threading.Thread(target=lookup, daemon=True).start()

    def close(self):
        self.closed.set()
        self.stop("Companion app stopped.")
        self.thread.join(timeout=3)
