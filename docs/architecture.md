# Architecture

This document describes a proposed architecture, not an implemented or verified system.

## Components

### macOS menu-bar application

Prefer a native Swift/SwiftUI application. Confirm the deployment target before selecting the exact menu-bar API. Package it as a menu-bar accessory application without a Dock icon.

The app owns:

- Profile metadata and configuration validation.
- macOS Keychain references for private and preshared keys.
- The single active tunnel and its lifecycle.
- The userspace backend process and loopback proxy endpoint.
- Connection status and health information shared with Firefox.
- Installation and registration of the Firefox native messaging bridge.

Store mutable application data in per-user application storage. Do not put runtime data inside the source checkout. Do not invoke arbitrary WireGuard PostUp, PostDown, PreUp, or PreDown shell hooks from imported profiles. Unsupported fields must produce an explicit validation result.

### Firefox WebExtension

The extension provides selection and connection controls and applies browser-level proxy and privacy settings. It obtains profile summaries through native messaging; it does not import or store WireGuard keys.

Record the desired protected state separately from observed connection health. Inspect whether other extensions or browser policy control the relevant settings. Refuse to claim protection if the required settings cannot be applied.

The extension must preserve and correctly restore user settings, account for private-window permission, and handle existing network connections when enabling protection or changing profiles. Manifest version and minimum browser version remain implementation decisions.

### Native messaging bridge

Use Firefox native messaging to communicate with a narrowly scoped native executable registered for the extension's exact ID. The bridge is a control channel; browsing data does not flow through native messaging.

The bridge forwards allowlisted, versioned commands to the app through an authenticated local channel. Evaluate XPC or a per-user Unix socket with restricted permissions and peer validation. Avoid a general-purpose unauthenticated HTTP control server.

Planned operations: list profiles, read state, connect using a profile ID, disconnect, and subscribe to state changes. Do not offer arbitrary command execution, arbitrary file reads, or secret export to the extension.

### Userspace WireGuard backend

Evaluate wireproxy as the initial backend. It establishes a separate WireGuard session and exposes a proxy on a loopback address. It does not attach to an existing tunnel managed by the official Mac app.

Use a dedicated peer identity when the browser connection may run alongside another WireGuard client. Validate configuration compatibility and the remote server's intended routing.

Keep the proxy loopback-only. Loopback binding does not itself prevent another local application from using the proxy; evaluate per-session authentication and available Firefox support if that isolation is required. The routing scope means the product configures Firefox to use the proxy; it is not automatically a process-level firewall.

Pin and verify the selected backend version. Check available macOS builds, relevant licences, executable verification, update behaviour, DNS handling, and routing semantics before bundling it. A running backend process or listening socket is not sufficient evidence of a working tunnel.

## Data and secret handling

- Profile summaries contain opaque IDs, display names, and non-secret status only.
- Private and preshared keys are stored through macOS Keychain.
- Keep tunnel endpoints, addresses, and other profile metadata out of routine logs.
- If the backend requires a temporary plaintext configuration, minimize its lifetime and restrict file and directory permissions. Keychain storage does not eliminate this runtime exposure.
- Do not place secrets in process arguments, exception messages, browser storage, telemetry, build artifacts, or repository files.
- Log only what is needed to diagnose lifecycle failures; any diagnostic export must be deliberate and sanitized.

## Connection lifecycle

The initial design needs explicit idle, preparing, connecting, connected, blocked, and disconnecting states. The desired protection state is independent of these observed states.

Before reporting Connected:

1. Verify that the extension can control the necessary browser settings.
2. Establish a browser state that blocks direct external browsing during connection setup.
3. Start or select the configured backend and verify readiness.
4. Apply the tunnel's proxy and privacy settings.
5. Confirm the expected network path using an appropriate health check.

Unexpected failures while protection is desired enter Blocked. Explicit disconnect restores the user's prior browser configuration. Profile switching, process crashes, stale messages, app termination, and browser restart need defined transitions and testing.

Native messaging connections may end with Firefox or the extension. Do not implicitly couple backend lifetime or the app's protected state to the bridge process without testing the resulting failure behaviour.

## Browser coverage

Test DNS and DNS-over-HTTPS, IPv4 and IPv6, WebRTC, HTTP protocol fallback, downloads, WebSockets, service workers, background requests, private windows, and browser-created connections. Validate both tunnel health and absence of unintended direct traffic.

An extension can lose control if removed, disabled, or overridden. If the product later requires a stronger containment guarantee, that is a separate operating-system enforcement design with its own permissions and validation requirements.
