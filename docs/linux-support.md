# Linux support — Kubuntu 26.04

The Linux companion supports the published extension 0.2.1 and the pending
0.2.2 label update, using protocol version 1 and the pinned
wireproxy 1.1.3 userspace backend. It adds a Python/Qt 6 tray application for KDE
Plasma, including Wayland, without requiring Swift, Docker, root, a kernel
WireGuard interface, or changes to system routing/DNS. The current primary
target is Kubuntu 26.04 x86_64 with **native Firefox** (Debian package or Mozilla
tarball). The Linux companion is a source-built development preview.

## Implementation plan and decisions

1. Preserve the extension's existing kill switch, profile selection, native
   protocol and connection-details behavior. No Linux-specific browser fork.
2. Port the macOS companion's strict configuration policy, ownership lease,
   handshake-based readiness and backend supervision to a small Linux runtime.
3. Use Qt 6 for the Plasma tray/editor and libsecret's Secret Service interface
   for KWallet/KSecretD. Keep secrets out of metadata, argv, logs, Firefox and
   temporary configuration files. Do not add a plaintext fallback.
4. Register the existing native host at Firefox's Linux per-user location,
   package verified Linux backend assets, and provide a reversible user-local
   installer. Preserve the macOS build behavior and Swift source.
5. Exercise configuration rejection, storage, framing, client ownership,
   startup/quit, backend failure/parent death and real encrypted transport;
   adapt the existing disposable Firefox smoke check for Linux.

The plan is implemented. The validation record in
[validation.md](validation.md) separates executed checks from remaining work.

## Build and install

Install distro dependencies if absent:

```sh
sudo apt install python3 python3-pyqt6 libsecret-tools curl
```

Kubuntu's desktop must provide an unlocked Secret Service wallet (KSecretD /
KWallet). An alternative Secret Service provider can work, but other desktops
are not the primary tested target. Python 3.10 or later and Qt 6 are required.

From the repository:

```sh
scripts/build.sh
scripts/test.sh
python3 scripts/backend_integration.py
dist/firefox-wireguard-linux/install.py
```

Build downloads the upstream Linux archive, verifies its pinned SHA-256 before
extraction, and creates `dist/firefox-wireguard-linux` plus the shared,
unsigned Firefox XPI (with platform-neutral labels). `FWG_BACKEND_DIR` can supply an already reviewed backend
and `wireproxy-LICENSE` for an offline build. This override is trusted local
input; it bypasses downloading and verification.

The installer must run **without sudo**. It copies the companion to
`~/.local/lib/firefox-wireguard`, creates a desktop launcher, and installs
`~/.mozilla/native-messaging-hosts/org.firefoxwireguard.bridge.json`. Quit the
running companion before an upgrade. It retains saved profiles and secrets.

Open **Firefox WireGuard** from the application launcher. Use **Import…** or
paste a configuration, name it, then **Save Profile**. Accept/unlock the
desktop wallet prompt. Keep an existing 0.2.1 extension or install it from
[Mozilla Add-ons](https://addons.mozilla.org/firefox/addon/wireguard-for-firefox/).
Allow private-window access, then choose the profile and **Connect** in Firefox.
The old extension's “Mac app” label does not affect Linux compatibility; 0.2.2
replaces it with “companion app”. Developers can temporarily load
`extension/manifest.json` via `about:debugging` to test that update.
The [existing configuration restrictions and browser
limitations](installation.md#supported-profiles) apply on Linux too.

Closing the editor keeps the tray app running and preserves its in-memory
draft. Save/Discard/Cancel protects navigation and Quit. If no tray is available,
closing the window offers to finish editing and quits. **Stop Tunnel** stops
the backend; Firefox applies its existing kill-switch preference. Background
status checks do not relaunch a quit companion; an explicit Connect can launch
it. There is no login autostart or privileged service.

## Storage and lifecycle

- Profile names and UUIDs: `$XDG_DATA_HOME/firefox-wireguard/profiles.json`
  (default `~/.local/share/firefox-wireguard`), directory 0700 and file 0600.
- Configurations: Secret Service entries with `application` set to
  `org.firefoxwireguard.profiles` and `profile` set to the profile UUID.
  `secret-tool` receives configurations on stdin and returns them over stdout
  to the companion; neither is logged. Locked/missing storage fails closed.
- Control socket: `$XDG_RUNTIME_DIR/firefox-wireguard/control.sock`, mode 0600,
  falling back to the private data directory when no runtime directory is set.
  App and bridge must run in the same desktop/XDG environment. Both validate
  peer UID with Linux `SO_PEERCRED`; frames are limited to 64 KiB.
- An advisory lock prevents concurrent app ownership. Failed startup releases
  the lock; **Retry Startup** retries after fixing the cause. A replacement
  app repairs an existing registration after acquiring ownership. A stale
  bridge exits when its manifest points elsewhere.
- One browser client owns the active tunnel. Two-second health checks require
  a recent handshake. Thirty-second handshake startup, five-second health
  startup and twelve-second browser lease limits match macOS. Provider failure
  affects the exit-IP display only. No credentials are needed for tests.
- Configurations reach wireproxy over a pipe. A supervisor monitors the app
  process and stops the backend on termination or crash. A Linux parent-death
  signal kills the backend if its supervisor dies. The app-to-supervisor link
  deliberately monitors process parentage: Linux parent-death signals track the
  creating thread, which can be a short-lived control handler. No system routes
  or DNS settings are modified.

The same-user and browser containment limits in [architecture.md](architecture.md)
still apply. Destination DNS goes through SOCKS; WireGuard endpoint resolution
uses the host network. Public exit lookup uses the same HTTPS provider through
`socks5h`, without environment proxy overrides or a direct fallback.

## Firefox packaging

Mozilla documents the Linux manifest location in
[Native manifests](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_manifests).
The machine used for development has native Firefox. Snap/Flatpak Firefox is
not yet a validated target: it requires distribution/browser support for
launching hosts outside its sandbox. Copying the manifest into a sandbox does
not provide that support. See the upstream
[native-messaging proxy](https://github.com/flatpak/xdg-native-messaging-proxy).
Use native Firefox for this preview; the installer does not change sandbox
permissions or replace your browser.

## Diagnostics, tests and removal

```sh
~/.local/lib/firefox-wireguard/firefox-wireguard --diagnose
python3 scripts/firefox_smoke.py /path/to/geckodriver --fixture-native
```

Diagnostics report only installation availability, not secrets. The Firefox
fixture uses an isolated browser profile, separate host and synthetic display
data. For a real-bridge smoke test, open the built companion first and omit
`--fixture-native`; use it only when no browser owns an active tunnel.

Optional `FWG_TEST_SECRET_SERVICE=1 scripts/test.sh` exercises a disposable
wallet entry. It can prompt to unlock KWallet. No existing profile is read.
`FWG_TEST_BACKEND=1 scripts/test.sh` exercises the packaged backend lifecycle.

Delete profiles in the app to remove their wallet entries. Quit the app, then:

```sh
~/.local/lib/firefox-wireguard/install.py --uninstall
```

Uninstall removes only the recognised installation, launcher and its matching
native-host registration. Metadata and wallet entries are retained intentionally.
Remove the extension separately in Firefox. Linux binary redistribution still
needs its own dependency/licence inventory audit; the macOS release audit does
not cover the upstream Linux executable. System Qt, Python and libsecret are
not bundled. See [THIRD_PARTY.md](../THIRD_PARTY.md).
