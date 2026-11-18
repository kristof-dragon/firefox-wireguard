# SPDX-License-Identifier: MPL-2.0
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .configuration import UserError
from .engine import idle, terminate
from .protocol import EXTENSION_ID, connect, frame, read_frame, registration_matches, validate


def parent_death(expected, death_signal):
    # Linux PR_SET_PDEATHSIG plus a post-prctl parent check closes the fork race.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, death_signal, 0, 0, 0) != 0 or os.getppid() != expected:
        raise UserError("The supervising process is unavailable.")


def supervise(helper, port, parent):
    stopping = False
    def stop(_number, _frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    # The app spawns us from a short-lived control thread. PR_SET_PDEATHSIG
    # tracks the creating *thread*, so using it here would kill a healthy tunnel
    # when that request completes. Monitor the app process's parentage instead.
    # Our own single-threaded child below can safely use a parent-death signal.
    if os.getppid() != parent:
        return 1
    if stopping:
        return 1
    child = subprocess.Popen([str(helper), "--exec-backend", str(port), str(os.getpid())],
                             stdin=sys.stdin.buffer, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while not stopping and os.getppid() == parent and child.poll() is None:
            time.sleep(0.1)
        return child.returncode or 0
    finally:
        terminate(child)


def open_companion(command, helper, connector=connect, launch=None, pause=time.sleep):
    try:
        return connector()
    except (OSError, UserError):
        if command != "connect":
            raise UserError("Open Firefox WireGuard to load profiles.") from None
    if launch is None:
        def launch():
            subprocess.Popen([str(helper.parent / "firefox-wireguard"), "--background"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    launch()
    for _ in range(15):
        pause(0.1)
        try:
            return connector()
        except (OSError, UserError):
            pass
    raise UserError("Open Firefox WireGuard and retry.")


def main(helper):
    args = sys.argv[1:]
    try:
        if len(args) == 3 and args[0] in ("--run-backend", "--exec-backend"):
            port, parent = int(args[1]), int(args[2])
            if not 0 < port <= 65535 or parent <= 1:
                return 1
            if args[0] == "--run-backend":
                return supervise(helper, port, parent)
            parent_death(parent, signal.SIGKILL)
            backend = str(helper.parent / "wireproxy")
            os.execv(backend, [backend, "-c", "/dev/stdin", "-s", "-i", f"127.0.0.1:{port}"])
        if len(args) != 2 or args[1] != EXTENSION_ID:
            return 1
        manifest = Path(args[0])
        while True:
            data = read_frame(sys.stdin.buffer.read)
            if data is None:
                return 0
            request = validate(json.loads(data))
            if not registration_matches(helper, manifest):
                return 1
            try:
                with open_companion(request["command"], helper) as sock:
                    # Retry establishing a socket only, never replay a mutation.
                    sock.sendall(frame(data))
                    response = read_frame(sock.recv)
                    if response is None:
                        raise UserError("No response")
            except (OSError, UserError):
                response = json.dumps({"version": 1, "id": request["id"], "ok": False,
                                       "profiles": [], "state": idle(), "busy": False,
                                       "error": "Companion unavailable. Open Firefox WireGuard, unlock KWallet, and retry."}).encode()
            sys.stdout.buffer.write(frame(response))
            sys.stdout.buffer.flush()
    except (OSError, UserError, ValueError, TypeError, RecursionError):
        return 1  # stdout is exclusively framed JSON; no inputs are logged.
