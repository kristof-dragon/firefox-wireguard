# Firefox listing and reviewer information

## Submission record

Version 0.2.1 was submitted to Mozilla on 2026-10-15 for a public AMO listing.
The submission is **Awaiting Review**; submission is not approval or publication.
Mozilla will notify the publisher when review/publication completes.

- Listing slug: `wireguard-for-firefox`
- Intended public listing: <https://addons.mozilla.org/firefox/addon/wireguard-for-firefox/>
- AMO version ID: `6581988`; file ID: `5126120`
- Submitted source commit: `94d9ef6641b231890d991abff362b4123bf5d1e0`
- Unsigned XPI SHA-256: `1eec5df25711b62df085db7582a97a29366f53e5d3f9a3b4929132928d28e4ab`
- Readable extension source is included in the XPI. The audited full-project
  source archive was also attached for reviewers, with version notes and test
  instructions. No native binary or real profile was uploaded.
- Desktop Firefox 140+ was selected; Android was not. The listing explicitly
  describes the macOS-only companion requirement and experimental status.
- Public support uses the project's issue tracker; no personal support email
  is published. The listing uses the project icon and a synthetic-data screenshot.

Check the Developer Hub for current status; the record above describes the
submission date and does not imply subsequent approval.

On 2026-10-15, after publishing the Apple Silicon companion to GitHub, the AMO
description, version notes, and reviewer notes were updated with the download
link, macOS requirements, and ad-hoc/non-notarized signing status. The saved
version page still showed **Awaiting Review**. The XPI and attached original
source were not replaced; all ten XPI file contents match the original submission
source. See [Mac release verification](macos-releases.md#published-021-preview).

## Listing

- Name: **WireGuard for Firefox**
- Version: **0.2.1**
- Distribution: public listing on addons.mozilla.org
- Platform: macOS desktop only
- Minimum Firefox: 140
- Licence: Mozilla Public License 2.0
- Category: Privacy & Security
- Experimental: yes
- Payment: the extension and companion source are free; users supply their own
  authorised WireGuard server. No VPN subscription is included or sold.
- Homepage/support: the public project repository and its Issues page.
- Privacy policy: [privacy.md](privacy.md).

### Summary

Route Firefox browsing through your own WireGuard tunnel using a macOS menu-bar
companion. Includes profile selection, connection details, and a kill switch.

### Description

WireGuard for Firefox connects Firefox to profiles configured in the separate
Firefox WireGuard menu-bar app for macOS. It leaves the Mac's system routes and
DNS settings unchanged. No Docker or official WireGuard app is needed.

**Requires macOS, the separate native companion, and a supported full-tunnel
WireGuard configuration.** Download the ready-to-run Apple Silicon companion
from the [0.2.1 GitHub release](https://github.com/kristof-dragon/firefox-wireguard/releases/tag/v0.2.1).
No developer tools are needed. The app requires macOS 13 or later and is ad-hoc
signed, not notarized by Apple; macOS may require Privacy & Security → Open Anyway
on first launch. Intel users must build from source; Intel builds are untested.
This is not a VPN service and no server or subscription is included.

Select a profile, connect, and see the public exit IP with country flag, uploaded
and downloaded session totals, configured tunnel DNS, and client WireGuard IPs.
The kill switch is on by default and blocks covered requests during connection
setup and detected failures. Turning it off permits ordinary browsing during an
outage. Disconnect explicitly returns to ordinary browsing. Localhost remains
local; other private addresses use the tunnel when remotely reachable.

While protected, WebRTC calls and network prediction are disabled. Allow the
extension in private windows so it can control Firefox's browser-wide proxy.
Close existing tabs and downloads before connecting. This preview is not an
operating-system firewall: existing connections, browser-internal traffic,
IPv6, DNS-over-HTTPS, and HTTP/3 still need broader testing. Disabling or removing
the extension ends protection.

Browsing requests and responses pass through your selected WireGuard server.
An HTTPS request through that tunnel to ipwho.is obtains the exit IP and country
on connection and approximately every five minutes. That provider sees the
exit IP and normal request metadata. The project has no analytics or browsing
history storage. Read the linked privacy policy for details.

This independent project is not affiliated with Mozilla or the WireGuard project.

## Reviewer notes

The XPI contains original, readable JavaScript/HTML/CSS and SVG. There is no
transpilation, minification, remote code, or third-party JavaScript. Reproduce the
XPI with `python3 scripts/package_extension.py`; it contains eight runtime files,
LICENSE, and SOURCE.txt. Native binaries are not inside the XPI.

The native host name is `org.firefoxwireguard.bridge`; the stable add-on ID is
`firefox-wireguard@local.invalid`. The `.invalid` suffix is an identifier, not an
email service or a network destination. The bridge accepts only status, connect,
and disconnect with bounded messages and validates the Firefox origin and local
UID. Configurations and keys never pass through the extension.

Permissions are used as follows:

- `proxy`: loopback SOCKS routing with remote DNS and no direct failover.
- `privacy`: disable WebRTC and network prediction while protection is active.
- `storage`: persist desired protection, selected profile ID, random local client
  ID, and the kill-switch preference.
- `nativeMessaging`: communicate with the separately installed macOS companion.
- `webRequest`, `webRequestBlocking`, `<all_urls>`: synchronously block covered
  requests during startup and failures. Localhost remains exempt.
- Required data categories: browsingActivity and websiteContent for forwarding
  browsing traffic; locationInfo for the public exit IP/country lookup. The
  lookup has no direct fallback. No analytics are collected.

### Testing without private credentials

No hosted account or private testing credentials are required. The repository
contains local fixtures that generate disposable peers rather than committing
keys or using a real deployment. On macOS:

1. Run `scripts/build.sh` and `scripts/test.sh` using the requirements in
   [installation.md](installation.md).
2. Run `FWG_TEST_BACKEND=1 scripts/test.sh` for an encrypted local peer handshake
   and app lifecycle tests; `python3 scripts/backend_integration.py` checks an
   actual SOCKS-to-WireGuard HTTP exchange.
3. With Mozilla geckodriver installed, run
   `python3 scripts/firefox_smoke.py /path/to/geckodriver --launch-services --fixture-native`.
   This opens a separate disposable Firefox profile and synthetic native host.
   It exercises request blocking, localhost bypass, settings restoration, the
   kill switch, and display fields. It does not touch an existing app/profile.

The browser fixture and real encrypted backend checks are separate; the fixture
does not itself establish a WireGuard tunnel. To test remote browsing, download/open
the companion, install its Firefox integration, import a dedicated authorised
full-tunnel peer, allow the add-on in private windows, and connect. See the
complete installation and validation documents for coverage and limitations.

The Apple Silicon native app is downloadable from the public repository's
0.2.1 release, with matching source, checksums, and third-party notices. It is
ad-hoc signed and not notarized. The XPI remains extension-only; its contents
have not changed since submission. The full-project archive originally attached
to Mozilla describes the pre-download packaging; the native release includes
its own exact source revision.
