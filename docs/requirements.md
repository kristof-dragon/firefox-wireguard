# Requirements

## Accepted product scope

- A native macOS app owns WireGuard profiles and connection state.
- The app is accessed through the menu bar, without a Dock icon or Docker dependency.
- Profiles can be added, imported from supported WireGuard configuration files, edited, renamed, and removed.
- The Firefox extension lists profiles configured in the app and selects one to connect.
- The extension can request connection, disconnection, and current status.
- The first version has one active browser tunnel at a time. Multiple stored profiles are supported.
- Secrets remain in native storage, with private and preshared keys protected using macOS Keychain. Firefox receives profile identifiers and display names, not key material.
- The app does not create system-wide VPN routes or change system DNS settings.
- Neither the official WireGuard Mac app nor Docker is a prerequisite.

## Traffic policy

### Full-tunnel profiles

The intended scope is the external network traffic of the Firefox profile using the extension, including ordinary browsing, resources, downloads, and WebSockets. Requests must use the selected tunnel or be blocked while protection is enabled.

- Localhost and loopback destinations remain local.
- Private IP addresses are not automatically exempted. They may traverse the tunnel when covered by the peer's routes and reachable from the remote network.
- IPv4 and IPv6 handling must follow an explicit policy. Unsupported or unconfigured address families must not silently fall back to the normal network while protection is enabled.
- A profile covering all IPv4 destinations does not by itself establish equivalent IPv6 coverage.
- DNS for proxied destinations must follow a tested tunnel path. Firefox DNS-over-HTTPS, speculative lookups, and cached results need explicit treatment.
- Transport setup needed to reach the WireGuard server is outside the tunnel by necessity. Endpoint hostname resolution and its privacy boundary must be documented.
- Browser network features that cannot safely use the proxy must be restricted or disabled while protection is enabled. Any functional effects must be visible to the user.

A Firefox proxy setting is not a claim that every packet from every Firefox-related process is contained under all conditions. Browser updater processes, native helpers, external applications opened by Firefox, extension removal, and other escape paths require separate assessment. Do not advertise operating-system-level containment without implementing and validating it.

### Split-tunnel profiles

Version 0.1 rejects split-tunnel profiles. Before adding support, choose and expose one explicit policy for destinations outside the routes: direct access or blocking. Never infer that policy from a failed proxy connection.

Do not assume standard WireGuard configuration fields automatically enforce browser-level split routing. The proxy and userspace backend need tested, compatible routing behaviour.

### Tunnel failure and explicit disconnect

- Distinguish desired protection state from backend health.
- Establish the protected browser state before sending traffic through a newly selected connection.
- The Firefox kill switch defaults to on and persists per browser profile. With it on, unexpected app, bridge, backend, network, or tunnel loss must not intentionally restore direct browsing. Explicitly switching it off permits normal browsing after failure detection, with a direct-browsing warning.
- A failed health check must not be shown as a successful connection merely because a process or local port exists.
- An explicit Disconnect action ends protection and restores the Firefox settings previously controlled by the product.
- Browser startup, restart, extension update, and crash behaviour are release gates. Any unavoidable gaps must be documented.
- Switching profiles must not introduce a temporary direct connection.

## User interface

### Menu-bar app

Profile list, active profile, connection state, import/edit/remove controls, and useful errors. Show advanced or first-use explanations in contextual help rather than permanent instructions on every screen.

### Firefox extension

A compact profile selector, Connect/Disconnect control, persistent Kill switch toggle, status, and an actionable error when the companion app is unavailable. Keep implementation details out of the normal user flow.

Changing Firefox-wide proxy settings may require the extension to be allowed in private windows. Detect this prerequisite and explain it before claiming protection is active.

Both interfaces show public exit IP with an approximate country flag, downloaded/uploaded byte totals for the current connection, configured tunnel DNS IPs, and client WireGuard IPs. Public-IP checks must use the tunnel and never bypass it when unavailable. Details must not persist in logs, files, or browser storage. Reset totals on a new connection and discard stale lookup responses.

## Initial exclusions

- System-wide VPN operation.
- A browser-hosted WireGuard implementation without a native companion.
- Multi-browser support, container-specific routing, or simultaneous tunnels.
- A hosted account service or remote configuration control plane.
- Docker or a Linux virtual machine as a required runtime.

## Version 0.1 decisions

- Declared minimum macOS 13 and Firefox 128; tested on Apple Silicon/macOS 27/Firefox 157. Intel and older versions remain unverified.
- Full-tunnel IPv4 is required. Optional IPv6 needs both an interface address and default route; its live path is unverified. Split profiles are rejected.
- WebRTC is disabled while protected, so WebRTC calls will not work in that state.
- One Firefox profile owns the tunnel, with a renewable 12-second lease. Other profiles cannot take over.
- The bridge launches the app on demand. App quit/stop leaves covered Firefox requests blocked when the kill switch is on. Login startup is deferred.
- wireproxy 1.1.3 archives and licence are checksum-pinned. Local app builds use ad-hoc signing; the extension is unsigned and temporarily loaded.
- A recent handshake is the readiness signal, not proof of Internet reachability or complete containment.

The public project licence, signed extension distribution, binary redistribution review, split-routing policy, and update hosting remain open. These requirements describe intended protection scope; [validation.md](validation.md) distinguishes tested checks from unverified release gates.
