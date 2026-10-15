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

The behaviour for destinations outside a profile's routes is not yet selected. Before implementation, choose and expose one explicit policy: direct access or blocking. Never infer that policy from a failed proxy connection.

Do not assume standard WireGuard configuration fields automatically enforce browser-level split routing. The proxy and userspace backend need tested, compatible routing behaviour.

### Tunnel failure and explicit disconnect

- Distinguish desired protection state from backend health.
- Establish the protected browser state before sending traffic through a newly selected connection.
- Unexpected loss of the app, bridge, backend, network, or tunnel must not intentionally restore direct browsing.
- A failed health check must not be shown as a successful connection merely because a process or local port exists.
- An explicit Disconnect action ends protection and restores the Firefox settings previously controlled by the product.
- Browser startup, restart, extension update, and crash behaviour are release gates. Any unavoidable gaps must be documented.
- Switching profiles must not introduce a temporary direct connection.

## User interface

### Menu-bar app

Profile list, active profile, connection state, import/edit/remove controls, and useful errors. Show advanced or first-use explanations in contextual help rather than permanent instructions on every screen.

### Firefox extension

A compact profile selector, Connect/Disconnect control, status, and an actionable error when the companion app is unavailable. Keep implementation details out of the normal user flow.

Changing Firefox-wide proxy settings may require the extension to be allowed in private windows. Detect this prerequisite and explain it before claiming protection is active.

## Initial exclusions

- System-wide VPN operation.
- A browser-hosted WireGuard implementation without a native companion.
- Multi-browser support, container-specific routing, or simultaneous tunnels.
- A hosted account service or remote configuration control plane.
- Docker or a Linux virtual machine as a required runtime.

## Decisions still required

- Minimum supported macOS and Firefox versions, and initial CPU architectures.
- Out-of-route policy for split-tunnel profiles.
- WebRTC policy and supported browser calling behaviour.
- Multiple Firefox profiles and concurrent client ownership.
- App launch, quit, login startup, and protection persistence behaviour.
- Backend version, supply-chain verification, and redistribution approach.
- Public project licence and optional update hosting.
