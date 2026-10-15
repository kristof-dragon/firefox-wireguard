# Implementation roadmap

## 0. Project foundation

Status: repository setup and design documentation only.

- Record the accepted app/extension experience and unresolved choices.
- Keep personal references, live configuration, and credentials out of Git.
- Establish a private repository with project-only commit metadata.

## 1. Backend feasibility

- Select and verify a wireproxy version for the supported Mac architectures.
- Use a dedicated test peer with credentials stored outside the checkout.
- Validate basic browsing through a loopback proxy without modifying system routes or system DNS.
- Check remote DNS, private destinations, IPv4, IPv6, unsupported configuration fields, and backend failure behaviour.
- Confirm an unrelated application continues to use its expected network path.

Exit criterion: measured evidence of the basic traffic path and its limitations. No claim of complete Firefox containment at this stage.

## 2. Native application

- Create the menu-bar app and profile model.
- Implement safe configuration import, editing, validation, and Keychain storage.
- Implement backend lifecycle management and status based on useful health evidence.
- Define app quit, login startup, and single-instance behaviour.
- Keep logs and runtime files outside the repository and scrub diagnostics.

Exit criterion: profiles and lifecycle work locally with verified secret handling and no system networking changes.

## 3. Native messaging and Firefox extension

- Install an allowlisted native messaging host.
- Implement a versioned, constrained local control protocol.
- Build the profile picker, Connect/Disconnect control, and status view.
- Handle private-window permission and conflicts with other proxy settings.
- Coordinate browser protection state with app and backend health.

Exit criterion: Firefox can select and operate app-managed profiles without receiving WireGuard keys.

## 4. Routing and failure validation

Test the actual network path, including:

- Full-tunnel browsing, resources, downloads, WebSockets, service workers, and background requests.
- Localhost remaining local and reachable private destinations using the selected tunnel.
- DNS, DNS-over-HTTPS, speculative requests, and supported address families.
- WebRTC and any deliberately restricted browser features.
- Initial connection, failed connection, tunnel loss, helper loss, app crash, reconnect, and profile changes.
- Browser startup/restart, private windows, extension update, extension disable/removal, and competing settings.
- Sleep/wake and changes between network interfaces.
- Explicit disconnect restoring the prior Firefox settings.

Capture evidence outside Git, publish only sanitized summaries, and label untested paths. Select the split-tunnel out-of-route policy before adding that feature.

Exit criterion: supported behaviour and known limitations documented from repeatable tests. No release based only on unit tests or a changed public-IP page.

## 5. Private installation and distribution

- Produce installable Mac and Firefox artifacts.
- Verify fresh installation, native host registration, upgrades, and removal.
- Use a signed, unlisted extension for persistent installation in ordinary Firefox.
- Keep signing credentials and WireGuard configurations out of source and artifacts.
- Document manual updates first; hosted updates are optional.

## 6. Public release readiness

Public release is a separate decision. Before changing visibility:

- Review the entire published history and release artifacts for private material.
- Select the project licence and document third-party licences and provenance.
- Verify backend checksums and the reproducibility of published builds.
- Document supported versions, installation, traffic scope, failure behaviour, and limitations.
- Confirm that readme claims match measured behaviour.
