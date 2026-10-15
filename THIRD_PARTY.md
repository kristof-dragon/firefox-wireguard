# Third-party components

## wireproxy 1.1.3

The local development build downloads an upstream macOS executable from the
[v1.1.3 release](https://github.com/windtf/wireproxy/releases/tag/v1.1.3).
The archive SHA-256 values are pinned in `scripts/fetch_backend.py`, checked
before extraction, and matched to the release asset digests.

wireproxy is ISC-licensed. The build retains its original licence and copyright
notice in the app's `Contents/Resources/wireproxy-LICENSE`. Do not remove or edit
that notice. The source repository and upstream licence are available at
[wireproxy](https://github.com/windtf/wireproxy/tree/v1.1.3) and
[LICENSE](https://github.com/windtf/wireproxy/blob/v1.1.3/LICENSE).

### Downloadable Apple Silicon app

Public Mac release packaging builds the unmodified **v1.1.3 source** with Go
**1.26.5**, `CGO_ENABLED=0`, `-trimpath`, and `-buildvcs=false`. It does not reuse
the upstream executable, which contains build-machine paths. The module ZIP is
verified against Go's checksum database, a pinned module sum, and SHA-256
`0c3ab6f2943515a2bcd6d3662804941c1f1fca6192502facfedef26ab0ae34d4`.

[backend-release.json](packaging/backend-release.json) records all thirteen
compiled dependency modules, their exact versions and sums, and hashes of the
bundled notices. The release build refuses an inventory mismatch. Source is
available from [wireproxy v1.1.3](https://github.com/windtf/wireproxy/tree/v1.1.3)
and the versioned Go modules; upstream `go.mod` and `go.sum` are unchanged.

The Darwin/arm64 dependency graph was inspected with `go-licenses` 2.0.1 and
`go list -deps`. It uses ISC, MIT, BSD-3-Clause, and Apache-2.0 licences. The
Linux-only libcap/psx and Windows-only wintun modules are not linked in this
binary. Assembly inputs use the corresponding Go/BSD or gVisor/Apache notices
and system calls; no additional linked third-party library was found. The Go
standard-library and vendored notices, patent grants, and source-level
attributions are included alongside the module licences. The compiled modules
contain no separate NOTICE files.

These unchanged upstream texts are in [packaging/third-party](packaging/third-party)
and, in the downloadable app, `Contents/Resources/ThirdPartyLicenses`.
Copyright holders and upstream contact references in legal notices are retained
as required attribution. They are not project-user information. This review is
specific to the pinned Darwin/arm64 build; dependency or architecture changes
require a fresh review.

## Original application and extension

The Swift application, messaging bridge, and Firefox extension were written for
this project. No code from the related Wireguard-Browser-Extension prototype has
been copied. The original project source, documentation, and assets are licensed under
MPL-2.0; see LICENSE. This does not change the licences of wireproxy or its
dependencies. The Firefox XPI contains no third-party code or native binaries.

The downloadable app includes MPL-2.0 and `Contents/Resources/SOURCE.txt`, which
identifies the exact source commit. Its GitHub release includes matching source
and checksums. No additional restriction is placed on recipients' source-code
rights. Apple system frameworks are dynamically linked and are not redistributed.
