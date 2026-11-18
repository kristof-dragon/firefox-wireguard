# Validation record

## Linux development preview — 2026-11-18

Checked on the Kubuntu 26.04 target machine (Ubuntu 26.04.1 x86_64 base), Python
3.14.4, Qt/PyQt6 6.10.2, KDE KSecretD as the active Secret Service provider,
native Firefox 160.0, geckodriver 0.37.1 and wireproxy 1.1.3. The existing macOS record below remains separate; Swift tests were not
rerun on Linux.

| Check | Evidence |
| --- | --- |
| Linux build | Pinned Linux/amd64 archive verified, relocatable Python/Qt companion built, unsigned shared XPI packaged |
| Automated suites | 21 Linux tests and all 23 existing extension tests pass; optional backend and Secret Service tests enabled |
| Configuration/storage | Strict full-tunnel policy, bare/prefixed addresses, IPv6 pairing, unsafe field rejection, private secret-free metadata, corruption/symlink rejection and failed-save rollback |
| Desktop wallet | Disposable Secret Service item written, read, updated with a multiline synthetic configuration, and deleted; no real profile accessed |
| Native protocol | Real bridge subprocess and private Unix socket exchange; origin, frame limits, foreign UID, stale registration, and startup ownership checks |
| Quit/relaunch | Packaged app remains stopped on status/disconnect; explicit Connect launches it; app termination removes its socket |
| Backend lifecycle | Killing the app parent or supervisor closes the real backend's SOCKS listener; stale browser lease and unhealthy metrics block the modeled connection |
| Encrypted transport | HTTP crosses SOCKS and a real encrypted loopback WireGuard peer; failed destination does not fall back to the host; metrics redact private keys |
| Real companion engine | Connect over the threaded control server survives handler exit, waits for a handshake, publishes counters, isolates browser ownership and disconnects cleanly |
| Real Firefox | Disposable browser reaches both the isolated fixture host and actual packaged Qt companion/bridge with empty isolated app storage |
| Firefox behavior | Failed connection blocks external-looking fixture requests, keeps localhost accessible, enables proxy DNS, disables WebRTC; kill-switch toggle and explicit disconnect restore/block as expected |
| Qt editor | Offscreen test checks Cancel, failed Save preservation, Save before New, Discard and selection; synthetic details render without clipping in a visually inspected screenshot |
| Installation | Isolated install, replacement and removal preserve metadata and register the expected helper; no real installation is changed by that test |

Reproduce with `scripts/build.sh`,
`FWG_TEST_BACKEND=1 FWG_TEST_SECRET_SERVICE=1 scripts/test.sh`, and
`python3 scripts/backend_integration.py`. The real-bridge browser check launches
the packaged Qt app with temporary XDG data/runtime directories and runs the
existing Firefox smoke script in that environment. Build outputs and synthetic
screenshots stay in ignored directories.

Remaining Linux validation: interactive Plasma/Wayland tray and wallet-prompt
UX, Snap/Flatpak Firefox, Linux arm64, other desktops, real remote-peer DNS/IPv6
and the wider browser leak matrix below. The exit provider has no live remote
test here. Public Linux binary redistribution needs its own dependency/licence
audit. This preview does not claim complete browser or OS traffic containment.

On 2026-11-18, the user imported a profile in the installed Kubuntu companion
and reported successful Firefox connectivity, matching their macOS experience.
The active published 0.2.1 extension was checked to have the same controller and
protocol as this checkout. This records a manual success report, not a packet
capture or a complete DNS/IPv6 leak test. Extension 0.2.2 changes only platform
wording and release metadata; the installed signed 0.2.1 package is not modified
in place.

For the 0.2.2 source update, the 21 Linux and 23 extension tests passed again,
with the lifecycle fixture's registration isolated from the live desktop
installation. The live native-host manifest checksum was unchanged after the
suite. Mozilla web-ext 10.8.0 reported zero errors, zero notices and the existing
Android-only minimum-version warning; this add-on targets desktop Firefox.

## macOS 0.2.1 record

Native app 0.2.1 / extension 0.2.1, checked 2026-10-15 on Apple Silicon, macOS 27, Swift 6.4, Firefox 157.0.1, and wireproxy 1.1.3. This is a development milestone, not a complete traffic-containment certification.

## Passed

| Check | Evidence |
| --- | --- |
| Native release build and bundle | Swift compilation, app packaging, nested ad-hoc signatures, strict signature verification |
| Native suite | 29 passing tests (including optional synthetic UI rendering) covering profile draft navigation, bare/prefixed interface addresses, configuration rejection, secret-free metadata, corrupt indexes, framing, socket exchange, Keychain, and real engine lifecycle |
| Upgrade lifecycle | Five regression tests cover failed-startup ownership release, second-copy repair and retry without altering stored metadata, registration refresh after ownership, no relaunch for status/disconnect, and bounded explicit-connect startup. The packaged helper also exits quietly on a changed registration before forwarding status or connect |
| Profile editor state | Six tests cover Cancel preservation, failed Save preservation, Save before New, switching profiles only after Save, explicit Discard of imported drafts, and retaining selection after Save |
| Keychain | Disposable entry written, read, updated, deleted; no real profile used |
| Engine readiness | Temporary WireGuard peers establish a real handshake with a bare client interface address; app manager reports ready only afterwards; another client cannot take over; stop clears the port |
| Extension suite | 23 passing tests covering startup guards, localhost, connection ordering, private-window permission, failure, stale readiness, settings conflicts/restoration, and helper timeout recovery |
| Encrypted backend path | Packaged supervisor and wireproxy send an HTTP request through SOCKS and an encrypted loopback WireGuard peer to a virtual destination |
| Backend failure | Unreachable proxy destination does not use the host's direct listener; stopping supervisor closes the backend proxy |
| Health data | Recent handshake observed; backend metrics redact private keys |
| Real Firefox integration | Temporary extension in a disposable Firefox profile communicates with the running packaged app through the real native bridge |
| Real Firefox failure handling | Nonexistent profile blocks an external-looking fixture URL; localhost remains reachable; proxy DNS is enabled and WebRTC disabled |
| Kill switch | Controller tests cover defaults, persistence, startup, recovery, and failures while saving/restoring settings. Real Firefox fixture verifies off permits direct requests and on blocks them again, with localhost accessible |
| Connection details | Native/JavaScript tests validate metrics, flags, addresses, reset and stale-result handling; provider failure leaves a healthy tunnel connected. Real Firefox renders synthetic details from an isolated native host; native SwiftUI card rendered and visually checked |
| Exit lookup path | A local SOCKS fixture receives the provider hostname and HTTPS port; a proxy refusal fails the lookup. No external service or deployment keys are used by automated tests |
| Real Firefox disconnect | Explicit disconnect restores access to the same directly reachable fixture |
| Publication package | Exact ten-file XPI contents checked; web-ext 10.8.0 reports zero errors and one Android-only minimum-version warning. Submission targets macOS desktop. MPL notices, privacy declaration, and synthetic preview verified; see [publication audit](publication-audit.md) |
| Downloadable Mac app | Source-built wireproxy with pinned module/licence inventory; no home-directory paths; system-library dependencies only. Final ZIP re-extracted and signatures verified; its actual engine/helper passed encrypted transport and failure/cleanup checks. Anonymous GitHub downloads matched SHA-256 values; see [release evidence](macos-releases.md#published-021-preview) |

The browser failure fixture uses a reserved hostname mapped locally by the test profile. It proves request blocking/restoration, not remote DNS or Internet routing. The browser and encrypted backend paths have been tested separately. Manual browser-to-remote-server use has been reported working; it has not been independently verified with traffic captures. The new public-IP display has synthetic response and SOCKS transport coverage, but a live provider response through a remote tunnel remains to be checked.

## Repeat the checks

```sh
scripts/build.sh
FWG_TEST_KEYCHAIN=1 FWG_TEST_BACKEND=1 FWG_PREVIEW_PATH="$PWD/dist/native-connection-preview.png" scripts/test.sh
python3 scripts/backend_integration.py
```

Without the environment flags, the Keychain, engine, and optional UI-render tests are skipped. Opt-in tests generate temporary credentials in memory and clean up their own Keychain entries and processes. They do not import a real profile or change system routing.

To test the display and kill switch without touching the live app/integration, provide a Mozilla geckodriver executable:

```sh
python3 scripts/firefox_smoke.py /path/to/geckodriver --launch-services --fixture-native
```

This uses an isolated disposable browser profile, temporary add-on with a unique ID, separate synthetic native host, and local HTTP fixture. It does not modify the real integration manifest or contact the real app. The fixture supplies reserved IPs and counters for UI testing; it does not implement a tunnel. Logs and a popup screenshot remain in ignored build/output directories.

Omit `--fixture-native` only to test the real bridge with the packaged app already running and idle. That mode temporarily installs the companion's native-host manifest, then restores any previous file and permissions. It never selects a real profile, but should not be run while another Firefox session owns the tunnel.

The `--launch-services` option works around Firefox profile-launch trouble on macOS 27 by opening the disposable instance through LaunchServices. geckodriver 0.37.1 was used. The script grants test-only privileged automation to that disposable instance for extension setup; this is not a product runtime requirement.

## Known limitations and remaining validation

- Remote browsing is reported working manually; production DNS, remote private subnets, and complete routing/containment have not been independently measured. Use a dedicated test peer for captures.
- Handshake readiness does not prove DNS/Internet reachability; failures are detected on polling and timeout intervals.
- IPv6, DNS-over-HTTPS, HTTP/3, WebSockets, service workers, downloads, Firefox-created background connections, and private-window requests need live path/capture tests.
- Existing sockets may survive proxy changes. Close tabs and downloads before connecting. A running or removed extension is not an OS-level containment boundary.
- Extension removal/disable and temporary-extension removal at browser restart end enforcement. Persistent signed-install startup/restart behaviour is unverified.
- Real app crashes, sleep/wake, interface changes, stale leases, and profile switching need broader browser-level testing. Supervisor stop and modeled controller failures were tested.
- Other local processes may connect to the unauthenticated loopback SOCKS listener. Same-user processes are not isolated by the control socket's UID check.
- Endpoint hostname resolution and WireGuard transport setup use the host network. Proxy destination DNS is intended to use configured tunnel DNS; comprehensive leakage measurements remain pending.
- Intel, macOS 13–26, and Firefox 140–156 are declared targets but have not been tested here.
- The native UI compiles and the app launches; the full profile editor workflow has not been exercised through UI automation. Profile persistence/parser/Keychain operations have automated coverage.
- Public-IP provider availability, country accuracy, and shared-exit rate limiting need live verification. Lookup failure does not imply tunnel failure.
- No notarization, Mozilla signing, automatic updates, or login startup is included. MPL-2.0 covers the original source.
