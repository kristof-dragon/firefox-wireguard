#!/usr/bin/python3
"""Disposable browser-test host. Synthetic display data only; no real tunnel."""
import json
import struct
import sys

PROFILE = "11111111-1111-4111-8111-111111111111"
state = {"phase": "idle", "supportsIPv6": False}
while True:
    header = sys.stdin.buffer.read(4)
    if not header:
        break
    if len(header) != 4:
        break
    size = struct.unpack("<I", header)[0]
    if not 0 < size <= 65536:
        break
    request = json.loads(sys.stdin.buffer.read(size))
    command = request.get("command")
    if command == "disconnect":
        state = {"phase": "idle", "supportsIPv6": False}
    elif command == "connect":
        if request.get("profileID") == PROFILE:
            state = {"phase": "connected", "profileID": PROFILE, "proxyPort": 9, "supportsIPv6": True,
                     "details": {"connectionID": "fixture", "clientIPs": ["192.0.2.2", "2001:db8::2"],
                                 "dnsServers": ["192.0.2.1"], "downloadedBytes": 123456789, "uploadedBytes": 8765432,
                                 "statsUpdatedAt": 100, "publicIP": "203.0.113.8", "countryCode": "GB", "exitStatus": "ready"}}
        else:
            state = {"phase": "blocked", "supportsIPv6": False, "error": "Test profile unavailable."}
    response = json.dumps({"version": 1, "id": request["id"], "ok": True, "busy": False,
                           "profiles": [{"id": PROFILE, "name": "Example tunnel"}], "state": state}).encode()
    sys.stdout.buffer.write(struct.pack("<I", len(response)) + response)
    sys.stdout.buffer.flush()
