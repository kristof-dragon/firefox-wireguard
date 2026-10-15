# Roadmap

## Implemented in 0.1.0

- Menu-bar app, profile management, Keychain storage, and strict configuration parsing.
- Pinned userspace backend, loopback SOCKS5, handshake health, supervision, and client ownership.
- Allowlisted native bridge and protected local control socket.
- Firefox selector, proxy DNS, WebRTC restriction, settings restoration, and blocking during setup/detected failure.
- Local app/unsigned-extension packaging, unit tests, encrypted-peer tests, and disposable-browser smoke tests.

Evidence and coverage limits are in [validation.md](validation.md).

## Implemented in 0.2.0

- Shared exit IP/country display, WireGuard session counters, tunnel DNS, and client IPs.
- Tunnel-only HTTPS exit lookup, bounded responses, cancellation, and no stale results across connections.
- Persistent Firefox kill switch, on by default, with explicit direct-browsing fallback when switched off.
- Isolated native-host browser fixture for display and real Firefox kill-switch checks without touching the live integration.

## Implemented in native 0.2.1

- Status polling respects app Quit; only explicit Connect can launch the companion.
- Retry Startup and independent integration repair recover a blocked second copy.
- A started replacement refreshes an existing registration; updated helpers exit when their registration changes.

## Next: real server and browser coverage

- Import a dedicated full-tunnel peer; verify Firefox's exit address while another app retains its original path.
- Verify remote DNS and private destinations with traffic captures.
- Exercise resources, downloads, WebSockets, service workers, background requests, and private windows.
- Test DNS-over-HTTPS, IPv6, HTTP/3, existing sockets, restart, policies, and conflicting extensions.
- Test app/backend crashes, reconnect, profile changes, sleep/wake, and interface changes.

Do not infer complete leak prevention from a public-IP page or existing automated tests.

## Installation hardening

- Obtain Mozilla unlisted signing for persistent ordinary-Firefox installation.
- Validate fresh installs, upgrades, removal, Intel, and declared minimum versions.
- Add optional login startup; consider notarization and an installer for wider distribution.
- Evaluate local SOCKS authentication if exclusive proxy access is needed.

## Later work

Choose an explicit out-of-route policy before adding split tunnels. Expand configuration compatibility without executable hooks. Add useful diagnostics without exposing profiles. Determine whether stronger containment needs separate OS enforcement.

## Public release decision

Keep the repository private until explicitly approved. Review all history for private material, choose a project licence, review transitive licences for binary redistribution, verify artifacts, and align claims with measured coverage. Signing credentials and real configurations remain outside Git.
