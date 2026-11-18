# SPDX-License-Identifier: MPL-2.0
import threading

from .configuration import UserError
from .engine import Tunnel, idle
from .protocol import ControlServer, InstanceLock, manifest_path, register, registration_matches, validate
from .storage import ProfileStore, data_directory


class Runtime:
    def __init__(self, helper, directory=None, vault=None, path=None, manifest=None):
        self.helper = helper
        self.mutations = threading.Lock()
        self.closing = threading.Event()
        self.stop_generation = 0
        self.ownership = self.server = self.tunnel = None
        try:
            self.ownership = InstanceLock(directory or data_directory())
            self.store = ProfileStore(directory or data_directory(), vault)
            self.tunnel = Tunnel(helper)
            self.server = ControlServer(self.handle, path)
            existing = manifest or manifest_path()
            if existing.exists() and not registration_matches(helper, existing):
                register(helper, existing)
        except Exception:
            self.close()
            raise

    def handle(self, request):
        validate(request)
        reply = {"version": 1, "id": request["id"], "ok": False, "profiles": [], "state": idle(), "busy": False}
        try:
            if self.closing.is_set():
                raise UserError("Companion app is closing.")
            client, command = request["clientID"], request["command"]
            if command == "status":
                self.tunnel.renew(client)
            else:
                if not self.mutations.acquire(blocking=False):
                    raise UserError("A profile operation is in progress. Retry when it finishes.")
                try:
                    if not self.tunnel.owns(client):
                        raise UserError("Another Firefox profile owns the tunnel. Disconnect it first.")
                    if command == "disconnect":
                        self.tunnel.stop()
                    else:
                        profile_id = request.get("profileID")
                        profile = next((p for p in self.store.profiles if p["id"] == profile_id), None)
                        if profile is None:
                            raise UserError("Choose an existing profile.")
                        generation = self.stop_generation
                        configuration = self.store.configuration(profile_id, timeout=4)
                        if self.closing.is_set():
                            raise UserError("Companion app is closing.")
                        with self.tunnel.lock:
                            if generation != self.stop_generation:
                                raise UserError("Connection cancelled in the companion.")
                            self.tunnel.connect(profile, configuration, client)
                finally:
                    self.mutations.release()
            reply.update(ok=True, busy=not self.tunnel.owns(client))
            reply["state"] = idle() if reply["busy"] else self.tunnel.snapshot()
        except UserError as error:
            reply["error"] = str(error)
        except Exception:
            reply["error"] = "The requested operation could not be completed."
        reply["profiles"] = self.store.profiles
        return reply

    def save(self, profile_id, name, text):
        with self.mutations:
            if self.closing.is_set():
                raise UserError("Companion app is closing.")
            if profile_id and self.tunnel.snapshot().get("profileID") == profile_id:
                raise UserError("Disconnect this profile before editing it.")
            return self.store.save(profile_id, name, text)

    def remove(self, profile_id):
        with self.mutations:
            if self.closing.is_set():
                raise UserError("Companion app is closing.")
            if self.tunnel.snapshot().get("profileID") == profile_id:
                raise UserError("Disconnect this profile before removing it.")
            self.store.remove(profile_id)

    def close(self):
        self.closing.set()
        if self.server:
            self.server.close()
            self.server = None
        if self.tunnel:
            self.tunnel.close()
        # A pending vault lookup cannot start a tunnel after closing is set.
        if self.ownership:
            with self.mutations:
                self.ownership.close()
                self.ownership = None

    def stop(self):
        with self.tunnel.lock:
            self.stop_generation += 1
            self.tunnel.stop("Tunnel stopped in the companion. Reconnect from Firefox.")
