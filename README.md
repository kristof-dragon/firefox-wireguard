# Firefox WireGuard

A native macOS menu-bar app and Firefox extension that send Firefox browsing through a selected WireGuard connection. No Docker, system VPN routes, or system DNS changes.

## Native app 0.2.1 / extension 0.2.0

Both interfaces show the public exit IP and country flag, current-connection download/upload totals, tunnel DNS servers, and WireGuard client addresses. Firefox has a persistent **Kill switch**, on by default: detected failures block covered requests; switching it off permits normal browsing while the tunnel is unavailable. Direct browsing is clearly labelled.

Native 0.2.1 fixes app relaunch after Quit and recovery when another copy is running. Background status checks do not launch the app; an explicit Firefox Connect can. A replacement app updates an existing Firefox registration after acquiring ownership.

The development version is implemented and builds locally. It includes profile import/editing, Keychain storage, a native messaging bridge, a userspace WireGuard backend, and the Firefox profile picker. The encrypted proxy path and browser failure handling have been exercised locally. Manual remote browsing has been reported working; the full browser leak-testing matrix remains to be validated. See [test evidence and limitations](docs/validation.md).

This is a private development repository. Keep all commits suitable for possible public release: no personal references, real profiles, credentials, or machine-specific paths.

## Try it

1. Run `scripts/build.sh` on a Mac with a Swift toolchain and Python 3.
2. Open `dist/Firefox WireGuard.app`. Its shield icon appears in the menu bar.
3. Choose **Install Firefox Integration**, then **Manage Profiles…** to import a supported full-tunnel configuration.
4. Temporarily load `extension/manifest.json` using Firefox's `about:debugging` page. Allow the extension in private windows.
5. Close existing tabs and downloads, then select a profile and **Connect** in the extension.

[Installation, supported configurations, updates, and removal](docs/installation.md) has the complete steps. The local app is ad-hoc signed; the extension package is unsigned. Persistent installation in ordinary Firefox needs Mozilla signing, but no public add-on listing.

## Behaviour

- Multiple stored profiles; one Firefox profile owns one active tunnel at a time.
- Localhost stays local. Other private addresses use the tunnel, subject to remote routing.
- With **Kill switch** on (default), new covered requests are blocked during connection setup and detected failures. With it off, an unavailable tunnel permits normal browsing. **Disconnect** explicitly returns to ordinary browsing.
- Public exit lookup uses HTTPS through the tunnel; see [connection details and privacy](docs/installation.md#connection-details).
- Proxied DNS uses the tunnel. WebRTC and network prediction are disabled while protected.
- The official WireGuard Mac app is not required. This creates its own connection; use a separate server peer if another client will run simultaneously.

```mermaid
flowchart LR
    Firefox --> Proxy[Loopback SOCKS5 proxy]
    Proxy --> Tunnel[Userspace WireGuard connection]
    Tunnel --> Destination[Internet or remote private network]
    Extension[Firefox extension] --> Bridge[Native messaging bridge]
    Bridge --> App[macOS menu-bar app]
    App --> Tunnel
```

The extension controls browser requests and settings; this is not an operating-system firewall. Existing connections, browser-internal traffic, extension removal, and several network/browser combinations have not been proven contained. Temporary extensions disappear on browser restart. Do not treat this development build as a complete privacy boundary.

## Development

```sh
scripts/build.sh
scripts/test.sh
FWG_TEST_KEYCHAIN=1 FWG_TEST_BACKEND=1 scripts/test.sh
python3 scripts/backend_integration.py
```

Opt-in tests use disposable Keychain entries and locally generated WireGuard peers. Backend downloads are pinned to wireproxy 1.1.3 with verified archive and licence checksums. Build products, logs, and browser profiles are ignored by Git.

Declared minimums are macOS 13 and Firefox 128. The build was tested on Apple Silicon with macOS 27 and Firefox 157. Intel backend download support is included, but an Intel build has not been tested.

## Project documents

- [Installation](docs/installation.md)
- [Requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [Validation evidence and known limits](docs/validation.md)
- [Remaining roadmap](docs/roadmap.md)
- [Upstream references and distribution](docs/references.md)
- [Contribution and publication hygiene](CONTRIBUTING.md)
- [Third-party provenance](THIRD_PARTY.md)

The app and extension are original code. No code was copied from the referenced browser-extension prototype. A public project licence and binary redistribution review remain release decisions.
