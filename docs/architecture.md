# Architecture

This describes native app 0.1.1 and extension 0.1.0. Validation scope is recorded separately in [validation.md](validation.md).

## Native app and secrets

The SwiftUI app uses `MenuBarExtra` and runs as an accessory without a Dock icon. It owns profile management, Keychain access, backend lifecycle, and native-host registration. It requires no privileged access and configures no OS network interfaces, routes, or DNS.

Profile IDs and names are in a mode-0600 JSON index inside a mode-0700 per-user application-support directory. Complete normalized configurations are in macOS Keychain, accessible when the device is unlocked. Editing reveals keys in the native editor. Corrupt metadata is reported rather than overwritten. Configuration contents never reach Firefox or routine logs.

The app owns an in-memory editor draft independently of window lifetime. Dirty drafts require Save, Discard, or Cancel before new-profile, selection, or import navigation. A failed save cancels navigation and preserves the draft. Editor errors are separate from application/tunnel status. No draft contents are written to disk or automatically saved on app quit.

A strict parser supports one interface and peer, an IPv4 full tunnel, IP-literal DNS, and optional paired IPv6 address/default route. It rejects unknown fields, shell hooks, backend sections, and environment substitutions. Keepalive is normalized to 25 seconds; a fixed client listening port is omitted. See [installation.md](installation.md) for compatibility.

## Control channel

The extension ID is `firefox-wireguard@local.invalid`. Firefox starts `org.firefoxwireguard.bridge`, whose native-host manifest allows only that ID. The helper also checks Firefox's origin argument.

The bridge forwards bounded, length-prefixed JSON to a mode-0600 Unix socket in the private application directory. Both ends validate the peer UID. An advisory lock prevents duplicate app ownership. These controls isolate other users, not hostile software already running as the same user.

Protocol version 1 allows only `status`, `connect`, and `disconnect`. Commands carry a client UUID; connect adds a profile UUID. Replies contain profile summaries, state, and a loopback proxy port when appropriate. No arbitrary commands, paths, configurations, or secret exports are supported. Frames are limited to 64 KiB.

The bridge can launch its containing app. It retries socket connection establishment, never a mutating request whose response may have been lost. A timeout advises checking the app and any Keychain prompt. The extension reopens failed native ports on later requests.

## Backend lifecycle

The build downloads pinned wireproxy 1.1.3 for the host architecture and verifies archive and licence SHA-256 digests. Configuration goes through stdin, absent from command arguments and temporary files. The backend and its licence are packaged in the app.

A supervisor watches its parent app and terminates wireproxy when the app exits. SOCKS5 and metrics bind separately allocated IPv4 loopback ports. No direct-routing backend option is admitted.

Health is polled every two seconds. A handshake less than 180 seconds old permits `connected`; a listening port alone does not. Startup without a handshake becomes blocked after 30 seconds; missing health responses become blocked after five seconds. These are detection intervals, not instant network-loss detection. A handshake proves peer contact, not DNS or Internet reachability.

One Firefox client UUID owns the tunnel. Status requests renew a 12-second lease; lease loss stops the backend. Other clients cannot take over or stop it. App quit or **Stop Tunnel** leaves a protected extension blocked. Login startup is not implemented.

The SOCKS endpoint is unauthenticated. Other local processes can opt into using it. This product selects Firefox's route rather than enforcing exclusive Firefox use.

## Extension lifecycle

The Manifest V2 extension has a persistent background page. Synchronous request and proxy handlers register before storage is read. Desired protection and selected profile persist separately from observed health. A new installation starts idle; saved protected intent starts blocked.

Connect persists intent, closes the request guard, verifies private-window permission and control of settings, disables WebRTC/network prediction, and installs a dead proxy. It then asks the app to connect. A recent handshake for the selected profile and verified settings enable its SOCKS5 port with proxy DNS. Proxy results end with `null` to prohibit direct failover.

Localhost names and loopback IPs bypass the tunnel. Other private addresses follow the proxy. An unsupported IPv6 destination does not get a direct fallback.

Transport loss, conflicting settings, mismatched profiles, missing readiness, and startup failures close the guard. Stale transport responses cannot reopen it. Polls may recover a still-running healthy tunnel; a stopped/idle app requires reconnect.

**Disconnect** releases only settings controlled by this extension, restoring the underlying Firefox settings, even with the companion unavailable. Disabling/removing the extension also removes its enforcement; it is not an OS-level kill switch.

Proxy changes do not guarantee closure of existing connections. Close existing tabs and downloads before connecting. Full startup, browser-internal, DNS-over-HTTPS, HTTP/3, IPv6, and socket-lifecycle coverage remain validation work.
