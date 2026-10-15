# Third-party components

## wireproxy 1.1.3

The build downloads an unmodified upstream macOS executable from the
[v1.1.3 release](https://github.com/windtf/wireproxy/releases/tag/v1.1.3).
The archive SHA-256 values are pinned in `scripts/fetch_backend.py`, checked
before extraction, and matched to the release asset digests.

wireproxy is ISC-licensed. The build retains its original licence and copyright
notice in the app's `Contents/Resources/wireproxy-LICENSE`. Do not remove or edit
that notice. The source repository and upstream licence are available at
[wireproxy](https://github.com/windtf/wireproxy/tree/v1.1.3) and
[LICENSE](https://github.com/windtf/wireproxy/blob/v1.1.3/LICENSE).

The upstream executable also includes Go dependencies, including WireGuard's Go
implementation and gVisor. Their source revisions are recorded by upstream in
[go.mod](https://github.com/windtf/wireproxy/blob/v1.1.3/go.mod) and `go.sum`.
This repository does not commit or publish native binary releases. A complete
transitive notice/source-offer review is required before redistributing binaries
outside local development.

## Original application and extension

The Swift application, messaging bridge, and Firefox extension were written for
this project. No code from the related Wireguard-Browser-Extension prototype has
been copied. A licence for this project's original code remains a public-release
decision.
