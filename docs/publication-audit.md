# Public-source audit

Checked 2026-10-15 before the first public-source release.

## Scope and findings

- All six pre-publication commits and every reachable file version were checked,
  including local branches and checkpoint refs: 99 distinct historical file
  blobs, all text. Current release changes were checked again before commit.
- File names, source, comments, documentation, tests, commit messages, authors,
  and committers were reviewed. No real configurations, deployment endpoints,
  keys, tokens, personal email addresses, user home paths, or private notes were
  found. Commit authorship uses the neutral project contributor identity.
- Historical URLs, domain names, IP addresses, and long token-like strings were
  inventoried. They resolve to public upstream references, loopback addresses,
  synthetic test destinations, code identifiers, and pinned download checksums.
  Test keys are generated at runtime. No history rewrite was necessary.
- The GitHub repository had only its main branch, no tags, releases, issues,
  pull requests, issue/PR/commit comments, or Actions runs. Wiki, discussions,
  and Pages were disabled. The repository owner's public account name remains
  visible through GitHub; this audit does not make repository ownership anonymous.
- Local build products, browser profiles, logs, native binaries, and screenshots
  are excluded from Git. No local runtime profiles or Keychain items were read
  for this publication audit.

## Distribution checks

Original code, documentation, and assets use MPL-2.0. Source files carry SPDX
notices where practical; README and LICENSE cover files without inline comments.
Upstream attribution and licences remain intact.

The Firefox 0.2.1 XPI uses an explicit ten-file allowlist and was compared byte
for byte with its intended source files. It includes the complete MPL text and
a source notice, contains no native binaries or private files, and has no
third-party JavaScript or remote code. The accompanying source archive is made
from the reviewed Git commit, not the working directory.

Mozilla web-ext 10.8.0 reports zero errors and zero notices. It emits one Android
minimum-version warning for built-in data consent; this companion-dependent
extension is submitted for macOS desktop only. Firefox desktop 140+ is required.

The native release build and signatures, 29 native tests, 23 JavaScript tests,
and the disposable Firefox fixture checks passed after the release changes.
The popup preview uses only synthetic data. Broader network-validation limits
remain in [validation.md](validation.md).

This records the checks performed, not a guarantee that automated pattern scans
can identify every possible secret. Keep the same review boundary for future
changes and releases. Native binary distribution remains separate work.
