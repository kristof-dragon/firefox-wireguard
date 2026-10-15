# Mac app releases

The 0.2.1 preview provides a self-contained **Apple Silicon** app ZIP. Its three
executables are arm64: the Swift menu-bar app, native messaging bridge, and
userspace WireGuard engine. Only macOS system libraries are dynamically linked.
The app declares macOS 13 as its minimum; testing was on macOS 27. No Intel or
universal binary is published yet.

## Signing and installation

The app and nested executables have ad-hoc signatures for local code integrity.
They do not identify an Apple-verified developer, and the app is not notarized.
Users may need **Open Anyway** in macOS Privacy & Security after their first
launch attempt. See [installation](installation.md#download-the-mac-app).
Developer ID signing and Apple notarization remain future release work.

No developer certificate, account, WireGuard configuration, private key, browser
profile, log, or Keychain contents is included in a release. The ZIP contains
only the fresh app bundle, with executable modes preserved and no extended
attributes, owner identifiers, resource forks, or Finder metadata. Swift source
prefix maps and Go `-trimpath` remove local build paths; release packaging rejects
home-directory paths. Upstream attribution is deliberately preserved.

## Prepare a release

Use an Apple Silicon Mac with the development prerequisites and **Go 1.26.5**
from the official Go distribution. Set `FWG_GO` to its executable if it is not on
PATH. The toolchain itself is not shipped or needed by users. Commit the reviewed
source first; the packager refuses a dirty working tree.

```sh
python3 scripts/release_macos.py
```

This builds the verified backend source, checks its compiled dependency versions
against `packaging/backend-release.json`, checks licence hashes, builds into a
fresh staging folder, includes all notices and exact source information, signs,
and checks the bundle. It checks architectures and system-library dependencies,
creates a metadata-free ZIP, re-extracts it with macOS `ditto`, verifies signatures,
and runs an encrypted local backend exchange using the extracted executables.
It creates these files in `dist/macos-0.2.1/` without uploading them:

- `Firefox-WireGuard-0.2.1-macOS-arm64.zip`
- `Firefox-WireGuard-0.2.1-source.zip` (tracked source at the embedded commit)
- `SHA256SUMS.txt`

Publish these together on a GitHub **pre-release**, tagging the same commit. Do
not attach the unsigned XPI as a normal Firefox installation download. The
Mozilla submission and native Mac release have separate signing/review steps.

To target a particular app bundle in the native and encrypted transport tests:

```sh
FWG_TEST_APP="/path/to/Firefox WireGuard.app" FWG_TEST_KEYCHAIN=1 FWG_TEST_BACKEND=1 scripts/test.sh
FWG_TEST_APP="/path/to/Firefox WireGuard.app" python3 scripts/backend_integration.py
```

## Dependency review

The source backend is wireproxy v1.1.3. The release lock contains the module
checksum, ZIP SHA-256, compiled dependency versions and checksums, and licence
file hashes. The Go module mirror/checksum database verifies downloads. No source
modification or dependency upgrade is performed by the release script.

For a dependency update, use `go list -deps -json ./cmd/wireproxy` with
`GOOS=darwin GOARCH=arm64 CGO_ENABLED=0` and inspect the built executable's
`go version -m` inventory. `github.com/google/go-licenses/v2@v2.0.1` was used for
the initial licence report and collection. Investigate its non-Go/assembly
warnings manually. Preserve module licence/patent/NOTICE files and source
attribution headers; also include Go standard-library/vendor notices. Regenerate
the reviewed lock only after inspecting those changes. See [THIRD_PARTY.md](../THIRD_PARTY.md).
