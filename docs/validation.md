# Validation record

Native app 0.1.1 / extension 0.1.0, checked 2026-10-15 on Apple Silicon, macOS 27, Swift 6.4, Firefox 157.0.1, and wireproxy 1.1.3. This is a development milestone, not a complete traffic-containment certification.

## Passed

| Check | Evidence |
| --- | --- |
| Native release build and bundle | Swift compilation, app packaging, nested ad-hoc signatures, strict signature verification |
| Native suite | 18 passing tests covering profile draft navigation, bare/prefixed interface addresses, configuration rejection, secret-free metadata, corrupt indexes, framing, socket exchange, Keychain, and real engine lifecycle |
| Profile editor state | Six tests cover Cancel preservation, failed Save preservation, Save before New, switching profiles only after Save, explicit Discard of imported drafts, and retaining selection after Save |
| Keychain | Disposable entry written, read, updated, deleted; no real profile used |
| Engine readiness | Temporary WireGuard peers establish a real handshake with a bare client interface address; app manager reports ready only afterwards; another client cannot take over; stop clears the port |
| Extension suite | 15 passing tests covering startup guards, localhost, connection ordering, private-window permission, failure, stale readiness, settings conflicts/restoration, and helper timeout recovery |
| Encrypted backend path | Packaged supervisor and wireproxy send an HTTP request through SOCKS and an encrypted loopback WireGuard peer to a virtual destination |
| Backend failure | Unreachable proxy destination does not use the host's direct listener; stopping supervisor closes the backend proxy |
| Health data | Recent handshake observed; backend metrics redact private keys |
| Real Firefox integration | Temporary extension in a disposable Firefox profile communicates with the running packaged app through the real native bridge |
| Real Firefox failure handling | Nonexistent profile blocks an external-looking fixture URL; localhost remains reachable; proxy DNS is enabled and WebRTC disabled |
| Real Firefox disconnect | Explicit disconnect restores access to the same directly reachable fixture |

The browser failure fixture uses a reserved hostname mapped locally by the test profile. It proves request blocking/restoration, not remote DNS or Internet routing. The browser and encrypted backend paths have been tested separately; a successful browser-to-remote-server session with a real deployment is still pending.

## Repeat the checks

```sh
scripts/build.sh
FWG_TEST_KEYCHAIN=1 FWG_TEST_BACKEND=1 scripts/test.sh
python3 scripts/backend_integration.py
```

Without the environment flags, the Keychain and engine tests are skipped. Opt-in tests generate temporary credentials in memory and clean up their own Keychain entries and processes. They do not import a real profile or change system routing.

To test Firefox, start the packaged app and provide a Mozilla geckodriver executable:

```sh
python3 scripts/firefox_smoke.py /path/to/geckodriver --launch-services
```

This uses an isolated disposable browser profile, temporary add-on, and local HTTP fixture. It temporarily installs the companion's native-host manifest and restores any previous file and its permissions. The ordinary Firefox profile is not used. Logs and a popup screenshot remain in ignored build/output directories.

The `--launch-services` option works around Firefox profile-launch trouble on macOS 27 by opening the disposable instance through LaunchServices. geckodriver 0.37.1 was used. The script grants test-only privileged automation to that disposable instance for extension setup; this is not a product runtime requirement.

## Known limitations and remaining validation

- No real remote server, Internet egress, production DNS, or remote private subnet has been tested. Use a dedicated test peer first.
- Handshake readiness does not prove DNS/Internet reachability; failures are detected on polling and timeout intervals.
- IPv6, DNS-over-HTTPS, HTTP/3, WebSockets, service workers, downloads, Firefox-created background connections, and private-window requests need live path/capture tests.
- Existing sockets may survive proxy changes. Close tabs and downloads before connecting. A running or removed extension is not an OS-level containment boundary.
- Extension removal/disable and temporary-extension removal at browser restart end enforcement. Persistent signed-install startup/restart behaviour is unverified.
- Real app crashes, sleep/wake, interface changes, stale leases, and profile switching need broader browser-level testing. Supervisor stop and modeled controller failures were tested.
- Other local processes may connect to the unauthenticated loopback SOCKS listener. Same-user processes are not isolated by the control socket's UID check.
- Endpoint hostname resolution and WireGuard transport setup use the host network. Proxy destination DNS is intended to use configured tunnel DNS; comprehensive leakage measurements remain pending.
- Intel, macOS 13–26, and Firefox 128–156 are declared targets but have not been tested here.
- The native UI compiles and the app launches; the full profile editor workflow has not been exercised through UI automation. Profile persistence/parser/Keychain operations have automated coverage.
- No notarization, Mozilla signing, automatic updates, login startup, or public licence decision is included.
