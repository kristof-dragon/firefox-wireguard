# Architecture

This describes native app 0.1.1 and extension 0.1.0. Validation scope is recorded separately in [validation.md](validation.md).

## Native app and secrets

The SwiftUI app uses `MenuBarExtra` and runs as an accessory without a Dock icon. It owns profile management, Keychain access, backend lifecycle, and native-host registration. It requires no privileged access and configures no OS network interfaces, routes, or DNS.

Profile IDs and names are in a mode-0600 JSON index inside a mode-0700 per-user application-support directory. Complete normalized configurations are in macOS Keychain, accessible when the device is unlocked. Editing reveals keys in the native editor. Corrupt metadata is reported rather than overwritten. Configuration contents never reach Firefox or routine logs.

The app owns an in-memory editor draft independently of window lifetime. Dirty drafts require Save, Discard, or Cancel before new-profile, selection, or import navigation. A failed save cancels navigation and preserves the draft. Editor errors are separate from application/tunnel status. No draft contents are written to disk or automatically saved on app quit.

A strict parser supports one interface and peer, an IPv4 full tunnel, IP-literal DNS, and optional paired IPv6 address/default route. It rejects unknown fields, shell hooks, backend sections, and environment substitutions. Keepalive is normalized to 25 seconds; a fixed client listening port is omitted. See [installation.md](installation.md) for compatibility.

## Control channel

The extension ID is `firefox-wireguard@local.invalid`. Firefox starts `org.firefoxwireguard.bridge`, whose native-host manifest allows only that ID. The helper also checks Firefox's origin argument.

The bridge forwards bounded, length-prefixed JSON to a mode-0600 Unix socket in the private application directory. Both ends validate the peer UID. An advisory lock prevents duplicate app ownership. Failed startup releases its descriptor, and **Retry Startup** can acquire ownership after another copy quits. Profile management stays unavailable until startup succeeds; registration repair remains usable independently. A successfully started replacement updates an existing registration to its own helper. These controls isolate other users, not hostile software already running as the same user.

Protocol version 1 allows only `status`, `connect`, and `disconnect`. Commands carry a client UUID; connect adds a profile UUID. Replies contain profile summaries, state, and a loopback proxy port when appropriate. No arbitrary commands, paths, configurations, or secret exports are supported. Frames are limited to 64 KiB.

The bridge can launch its containing app only for an explicit `connect` request. Background `status` polling and `disconnect` never relaunch it after Quit. Before forwarding each request, the helper checks that its manifest still points to its executable; a stale helper exits, letting Firefox start the newly registered one on the next request. It retries socket connection establishment, never a mutating request whose response may have been lost. A timeout advises checking the app and any Keychain prompt. The extension reopens failed native ports on later requests.

## Backend lifecycle

The build downloads pinned wireproxy 1.1.3 for the host architecture and verifies archive and licence SHA-256 digests. Configuration goes through stdin, absent from command arguments and temporary files. The backend and its licence are packaged in the app.

A supervisor watches its parent app and terminates wireproxy when the app exits. SOCKS5 and metrics bind separately allocated IPv4 loopback ports. No direct-routing backend option is admitted.

Health is polled every two seconds. A handshake less than 180 seconds old permits `connected`; a listening port alone does not. Startup without a handshake becomes blocked after 30 seconds; missing health responses become blocked after five seconds. These are detection intervals, not instant network-loss detection. A handshake proves peer contact, not DNS or Internet reachability.

One Firefox client UUID owns the tunnel. Status requests renew a 12-second lease; lease loss stops the backend. Other clients cannot take over or stop it. App quit or **Stop Tunnel** leaves the extension blocked when its kill switch is on; an explicitly disabled kill switch permits normal browsing after failure detection. Login startup is not implemented.

The SOCKS endpoint is unauthenticated. Other local processes can opt into using it. This product selects Firefox's route rather than enforcing exclusive Firefox use.

## Extension lifecycle

The Manifest V2 extension has a persistent background page. Synchronous request and proxy handlers register before storage is read. Desired tunnel state, selected profile, and kill-switch preference persist separately from observed health. The kill switch defaults to on. A new installation starts idle; saved protected intent starts blocked.

Connect persists intent, closes the request guard, verifies private-window permission and control of settings, disables WebRTC/network prediction, and installs a dead proxy. It then asks the app to connect. A recent handshake for the selected profile and verified settings enable its SOCKS5 port with proxy DNS. Proxy results end with `null` to prohibit direct failover.

Localhost names and loopback IPs bypass the tunnel. Other private addresses follow the proxy. An unsupported IPv6 destination does not get a direct fallback.

Transport loss, conflicting settings, mismatched profiles, missing readiness, and startup failures close the guard. Stale transport responses cannot reopen it. With the kill switch explicitly off, failure handling releases owned settings before permitting normal browsing and labels that state as direct fallback. Turning it back on closes the synchronous guard before saving or applying proxy changes. Failed persistence or settings restoration cannot enable direct fallback. Polls may recover a still-running healthy tunnel; a stopped/idle app requires reconnect.

**Disconnect** releases only settings controlled by this extension, restoring the underlying Firefox settings, even with the companion unavailable. Disabling/removing the extension also removes its enforcement; it is not an OS-level kill switch.

Proxy changes do not guarantee closure of existing connections. Close existing tabs and downloads before connecting. Full startup, browser-internal, DNS-over-HTTPS, HTTP/3, IPv6, and socket-lifecycle coverage remain validation work.

## Connection observations

`TunnelState.details` is optional under protocol version 1, so older peers remain usable. Each backend start gets a fresh connection UUID and empty counters. The existing local metrics poll reads WireGuard UAPI `rx_bytes`, `tx_bytes`, and `last_handshake_time_sec`. The parser rejects missing, duplicate, malformed, or overflowing counters without logging the metrics body.

The app owns a single public-IP lookup task per connection. After a healthy handshake and every five minutes, fixed system curl requests `https://ipwho.is/?fields=success,ip,country_code` through `socks5h://127.0.0.1:<session-port>`. Curl configuration files and environment proxy overrides are disabled; bypass lists are empty, HTTPS/TLS verification is required, redirects are not followed, and response/time limits apply. No direct/system-resolver fallback is configured. Stop, reconnect, and unhealthy state cancel the task and invalidate its result generation. A provider failure affects only the display.

DNS/client addresses come from the validated configuration without keys or endpoint information. Public response IPs and country codes are validated; flags are generated locally without remote images. All display fields remain in memory, shared through the existing native channel. Firefox copies only known display fields and clears them on transport loss, disconnect, or profile change. No new extension permissions, analytics, or persistent IP history were added.

Public distribution should review provider terms, availability, shared-exit rate limits, and Mozilla privacy disclosures. The free service is an external dependency; there is no private API credential in the app.
