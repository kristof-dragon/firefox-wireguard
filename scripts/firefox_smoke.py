#!/usr/bin/env python3
"""Exercise the actual extension in a disposable Firefox profile.

Pass the path to a Mozilla geckodriver executable. Start the packaged companion
first. This temporarily registers its native host and restores any prior entry.
It never selects a real tunnel and never modifies the normal Firefox profile.
"""
import argparse
import http.server
import json
import os
import shutil
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("geckodriver", type=Path)
parser.add_argument("--firefox", default="/Applications/Firefox.app/Contents/MacOS/firefox")
parser.add_argument("--launch-services", action="store_true", help="Launch via macOS LaunchServices (needed for Firefox on macOS 27)")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
helper = root / "dist/Firefox WireGuard.app/Contents/MacOS/firefox-wireguard-bridge"
extension = root / "dist/firefox-wireguard-0.1.0-unsigned.xpi"
extension_id = "firefox-wireguard@local.invalid"
extension_uuid = str(uuid.uuid4())
host = "org.firefoxwireguard.bridge"
manifest = Path.home() / f"Library/Application Support/Mozilla/NativeMessagingHosts/{host}.json"
prior = manifest.read_bytes() if manifest.exists() else None
prior_mode = manifest.stat().st_mode & 0o777 if manifest.exists() else None
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
session = None
driver = None
browser_pid = None
launched_profile = None
driver_log = (root / ".build/firefox-smoke.log").open("w")


def api(path, data=None, method=None, timeout=40):
    payload = None if data is None else json.dumps(data).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=payload, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            result = json.load(response)["value"]
    except urllib.error.HTTPError as error:
        result = json.load(error)["value"]
        raise RuntimeError(f"WebDriver failed: {result.get('error')}: {result.get('message')}") from None
    return result


def execute(script, arguments=None, asynchronous=False):
    return api(f"/session/{session}/execute/{'async' if asynchronous else 'sync'}",
               {"script": script, "args": arguments or []})


def message(command, **values):
    return execute("const done = arguments[arguments.length - 1]; browser.runtime.sendMessage(arguments[0]).then(done, e => done({failure:String(e)}));",
                   [{"command": command, **values}], asynchronous=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"local-browser-test")

    def log_message(self, *args):
        pass


httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
try:
    assert helper.is_file() and extension.is_file(), "Build the app and extension first"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"name": host, "description": "Firefox WireGuard companion", "path": str(helper), "type": "stdio", "allowed_extensions": [extension_id]}))
    os.chmod(manifest, 0o600)
    profile_root = root / ".build/browser-profiles"
    profile_root.mkdir(parents=True, exist_ok=True)
    preferences = {
        "extensions.webextensions.uuids": json.dumps({extension_id: extension_uuid}),
        "extensions.allowPrivateBrowsingByDefault": True,
        "network.dns.localDomains": "fixture.example.invalid",
        "browser.startup.homepage": "about:blank",
        "browser.startup.homepage_override.mstone": "ignore",
        "browser.newtabpage.enabled": False,
        "network.captive-portal-service.enabled": False,
        "network.connectivity-service.enabled": False,
        "datareporting.healthreport.uploadEnabled": False,
        "toolkit.telemetry.enabled": False
    }
    driver_command = [str(args.geckodriver.resolve()), "--allow-system-access", "--host", "127.0.0.1", "--port", str(port), "--profile-root", str(profile_root)]
    if args.launch_services:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            marionette_port = sock.getsockname()[1]
        launched_profile = profile_root / str(uuid.uuid4())
        launched_profile.mkdir(mode=0o700)
        preferences["marionette.port"] = marionette_port
        preferences["marionette.enabled"] = True
        preferences["browser.shell.checkDefaultBrowser"] = False
        preferences["browser.startup.firstrunSkipsHomepage"] = True
        (launched_profile / "user.js").write_text("\n".join(f"user_pref({json.dumps(key)}, {json.dumps(value)});" for key, value in preferences.items()))
        app = Path(args.firefox).parents[2]
        subprocess.run(["/usr/bin/open", "-n", "-g", "-a", str(app), "--args", "--marionette", "--remote-allow-system-access", "-headless", "--no-remote", "--profile", str(launched_profile)], check=True)
        driver_command += ["--connect-existing", "--marionette-port", str(marionette_port)]
    driver = subprocess.Popen(driver_command, stdout=driver_log, stderr=driver_log)
    for _ in range(100):
        try:
            api("/status", timeout=1)
            break
        except (OSError, RuntimeError):
            time.sleep(0.1)
    value = api("/session", {"capabilities": {"alwaysMatch": {"browserName": "firefox", "moz:firefoxOptions": {
        "binary": args.firefox, "args": ["-headless", "--no-remote"], "prefs": preferences
    }}}})
    session = value["sessionId"]
    browser_pid = value.get("capabilities", {}).get("moz:processID")
    api(f"/session/{session}/timeouts", {"script": 20000, "pageLoad": 20000})
    installed = api(f"/session/{session}/moz/addon/install", {"path": str(extension), "temporary": True})
    assert installed == extension_id
    # Current Firefox restricts direct WebDriver navigation to extension URLs.
    # Use its explicitly enabled test-only chrome context in this disposable
    # browser, then return to the extension document for the actual assertions.
    api(f"/session/{session}/moz/context", {"context": "chrome"})
    granted = execute("""
        const done = arguments[arguments.length - 1], id = arguments[0];
        (async () => {
          const {ExtensionPermissions} = ChromeUtils.importESModule('resource://gre/modules/ExtensionPermissions.sys.mjs');
          const {AddonManager} = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
          await ExtensionPermissions.add(id, {permissions: ['internal:privateBrowsingAllowed'], origins: []});
          const addon = await AddonManager.getAddonByID(id);
          await addon.reload();
          done(true);
        })().catch(error => done({error: String(error)}));
    """, [extension_id], asynchronous=True)
    assert granted is True, granted
    extension_uuid = execute("return JSON.parse(Services.prefs.getStringPref('extensions.webextensions.uuids'))[arguments[0]];", [extension_id])
    execute("gBrowser.selectedBrowser.loadURI(Services.io.newURI(arguments[0]), {triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal()});", [f"moz-extension://{extension_uuid}/popup.html"])
    api(f"/session/{session}/moz/context", {"context": "content"})
    for _ in range(30):
        if execute("return document.querySelector('h1')?.textContent") == "Firefox WireGuard":
            break
        time.sleep(0.1)
    assert execute("return document.querySelector('h1').textContent") == "Firefox WireGuard"
    state = message("refresh")
    assert state and state["ready"] and not state["desired"] and not state["error"], state
    print("PASS: actual Firefox extension loaded and reached the real companion through native messaging.", flush=True)
    result = execute("const done=arguments[arguments.length-1]; browser.extension.isAllowedIncognitoAccess().then(done);", asynchronous=True)
    assert result is True, "Disposable profile did not grant private-window access"

    def fetch(url):
        return execute("const done=arguments[arguments.length-1]; fetch(arguments[0], {cache:'no-store'}).then(r=>r.text()).then(t=>done({ok:true,text:t}),()=>done({ok:false}));", [url], asynchronous=True)

    remote_url = f"http://fixture.example.invalid:{httpd.server_port}/"
    local_url = f"http://127.0.0.1:{httpd.server_port}/"
    assert fetch(remote_url)["ok"] is True
    # A syntactically valid, nonexistent profile must fail closed, never start a
    # real tunnel, and never fall back to the direct connection that just worked.
    state = message("connect", profileID=str(uuid.uuid4()))
    assert state["desired"] and state["blocked"], state
    assert fetch(remote_url)["ok"] is False
    assert fetch(local_url)["ok"] is True
    network = execute("const done=arguments[arguments.length-1]; Promise.all([browser.proxy.settings.get({}), browser.privacy.network.peerConnectionEnabled.get({})]).then(done);", asynchronous=True)
    assert network[0]["value"]["proxyDNS"] is True
    assert network[1]["value"] is False
    print("PASS: failed connection blocks external requests, preserves localhost, uses proxy DNS, and disables WebRTC.", flush=True)
    state = message("disconnect")
    assert state["desired"] is False
    assert fetch(remote_url)["ok"] is True
    print("PASS: explicit Disconnect restores ordinary browsing in the disposable Firefox profile.", flush=True)
    # A screenshot is a generated local artifact; it is never committed.
    import base64
    image = api(f"/session/{session}/screenshot")
    (root / "dist/firefox-extension-preview.png").write_bytes(base64.b64decode(image))
finally:
    if session:
        try:
            api(f"/session/{session}", method="DELETE", timeout=10)
        except Exception:
            pass
    if driver:
        driver.terminate()
        try:
            driver.wait(timeout=5)
        except subprocess.TimeoutExpired:
            driver.kill()
            driver.wait(timeout=3)
    if args.launch_services and not browser_pid and launched_profile:
        for line in subprocess.check_output(["ps", "-axo", "pid=,args="], text=True).splitlines():
            fields = line.strip().split(maxsplit=1)
            if len(fields) == 2 and fields[1].startswith(args.firefox + " ") and str(launched_profile) in fields[1]:
                browser_pid = int(fields[0])
                break
    if args.launch_services and browser_pid:
        # Only the process ID returned for this isolated WebDriver session.
        try:
            os.kill(browser_pid, 15)
        except ProcessLookupError:
            pass
        for _ in range(30):
            try:
                os.kill(browser_pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
    if launched_profile:
        shutil.rmtree(launched_profile, ignore_errors=True)
    if prior is None:
        manifest.unlink(missing_ok=True)
    else:
        manifest.write_bytes(prior)
        os.chmod(manifest, prior_mode)
    httpd.shutdown()
    driver_log.close()
