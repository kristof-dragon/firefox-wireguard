# Install and try the development build

Current native app: 0.1.1. Firefox extension: 0.1.0. The native app version appears near the bottom of its menu-bar panel.

## Build

Use a Mac with Swift 5.9 or later, the macOS SDK, and Python 3. Xcode or compatible command-line developer tools must be selected. Node.js 20 or later is needed for tests, not for running the app.

From the checkout:

```sh
scripts/build.sh
```

This downloads checksum-verified wireproxy 1.1.3, builds the native programs, applies local ad-hoc signatures, and creates:

- `dist/Firefox WireGuard.app`
- `dist/firefox-wireguard-0.1.0-unsigned.xpi`

The package declares macOS 13 as its minimum. Apple Silicon/macOS 27 with Swift 6.4 was tested. Intel and older versions remain unverified. The scripts use SwiftPM's legacy native build system because the default service stalled in the tested toolchain; this deprecated flag may need updating in future toolchains.

## Set up the app

1. Put the app where you want to keep it, then open it. The shield icon appears in the menu bar. A locally built copy needs no Apple signing account; this is not a notarized downloadable release.
2. Choose **Install Firefox Integration** to register the helper for your macOS user.
3. Choose **Manage Profiles…**, then **Import…**, or paste a configuration into a new profile and save it. Approve a Keychain prompt if shown.

The app registers its current path. After moving it, reopen it and choose **Repair Firefox Integration**. Disconnect and quit before moving or replacing an app.

The **+** button starts a new profile; **Save Profile** saves the text currently being edited and keeps it selected. If there are unsaved changes, starting a new profile, switching to another profile, or importing asks **Save / Discard Changes / Cancel** first. A failed save leaves the current draft intact. Cancelling the file picker or choosing an invalid import also leaves the draft intact. Validation errors stay in the profile editor and clear when its name or configuration changes.

Drafts remain in memory when the profile window closes and reopens, but are not automatically saved when the app quits. Save before quitting.

## Supported profiles

Use a WireGuard server you control or are authorised to use. Internet browsing requires server routing and Internet egress. This creates a separate session, not a connection to a tunnel in the official WireGuard app. Give simultaneous clients separate peer keys.

Version 0.1 supports:

- Exactly one `[Interface]` and one `[Peer]`.
- Required interface `PrivateKey`, `Address`, and `DNS`: an IPv4 address and one or more IP-literal DNS servers. Interface addresses may be bare IPs or include a valid prefix, for example `192.0.2.2` or `192.0.2.2/32`. `AllowedIPs` still requires routing prefixes.
- Required peer `PublicKey`, `Endpoint`, and `AllowedIPs`, including `0.0.0.0/0`.
- Optional `PresharedKey` and `MTU` (1280–9000).
- Optional IPv6 only with both an IPv6 interface address and `::/0`. Live IPv6 testing is pending.

`PersistentKeepalive` is accepted and normalized to 25 seconds to provoke a handshake before browsing is allowed. `ListenPort` is accepted but omitted from the saved configuration; the backend chooses its local UDP port. Comments are removed. The imported source file is never edited.

Split tunnels, multiple peers, DNS search domains, shell hooks, `Table`, proxy sections, environment variables, and unknown fields are rejected. No real profile or keys are included in the repository.

## Load the development extension

1. Visit `about:debugging` in Firefox.
2. Choose **This Firefox → Load Temporary Add-on…**.
3. Select `extension/manifest.json` in this checkout.
4. In `about:addons`, find **Firefox WireGuard**, and set **Run in Private Windows → Allow**. This permission is needed for the browser-wide proxy setting even if you use only ordinary windows.
5. Open the extension from Firefox's extensions menu; pin it if desired.
6. Close existing tabs and downloads. Choose a profile and **Connect**. A recent handshake and verified settings produce **Connected**.

Localhost remains reachable. Other private IPs use the tunnel. WebRTC calling is disabled while protected. **Disconnect** restores underlying Firefox settings; **Stop Tunnel** in the Mac app intentionally leaves covered browsing blocked.

If the list is empty, create a profile in the app and click **Refresh**. If the helper is unavailable, open the app and repair integration. If a Keychain prompt delayed a request, answer it and reconnect. Other proxy/privacy extensions or managed browser policies may prevent necessary settings from being applied.

Temporary add-ons disappear on Firefox restart. The unsigned XPI cannot be permanently installed in standard release Firefox. Mozilla supports signed, unlisted self-distribution, requiring an AMO account and submission but no public listing. Signing has not been performed. See Mozilla's [temporary installation](https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/) and [signing and distribution](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/) instructions.

## Updates and removal

To update locally: disconnect in Firefox, quit the app, rebuild, and reopen. Reload the temporary extension in `about:debugging`; repair integration if the app moved. Ad-hoc signed rebuilds may prompt for Keychain access again. No automatic updater or login startup is implemented.

To remove: disconnect, delete profiles in the app to remove Keychain entries, quit, and remove the app and extension. These per-user files can then be removed:

- `~/Library/Application Support/Mozilla/NativeMessagingHosts/org.firefoxwireguard.bridge.json`
- `~/Library/Application Support/FirefoxWireGuard/`

Deleting the app alone does not delete its Keychain entries. Removing/disabling the extension releases its settings and ends protection.

This version is ready for controlled testing, not certified containment. Read [validation.md](validation.md) before relying on its traffic separation.
