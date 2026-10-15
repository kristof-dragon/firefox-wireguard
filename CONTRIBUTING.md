# Contribution and publication hygiene

## Repository boundary

This project is public. Keep every commit suitable for public distribution.

Commit source, original documentation, generic examples, and reproducible build configuration. Do not commit:

- Real tunnel configurations, private or preshared keys, authentication tokens, or signing credentials.
- Personal names, personal email addresses, user home paths, machine names, or private infrastructure references in project content or commit metadata.
- Real endpoint hostnames, public addresses associated with a private deployment, internal service addresses, or screenshots containing such details.
- Local logs, traffic captures, database files, diagnostic exports, backups, browser profiles, or build outputs.

Use relative paths and obvious placeholders in documentation. Use reserved example domains and documentation address ranges when an example requires an address. Never generate a working secret just to populate an example.

## Local data

Keep runtime profiles and credentials in the app's per-user storage and macOS Keychain. For development-only material that must be near the checkout, use an ignored local-private directory and restrict its permissions. Ignoring a path is not protection for material already committed.

The initial repository setup uses a project-only Git author and committer identity. Preserve that approach for project maintenance commits intended to contain no personal references. Review local Git settings before committing from another environment. Contributions to original project files are under MPL-2.0. Preserve licence notices and third-party attribution.

## Before pushing

1. Inspect the exact staged filenames and diff.
2. Check source, documentation, fixtures, screenshots, and generated metadata for secrets and personal or private references.
3. Inspect author, committer, and message metadata as well as file content.
4. Confirm build outputs, local configuration, and diagnostics are excluded.
5. Run checks appropriate to the changed component and state their limits honestly.
6. Verify the remote and repository visibility before publishing.

Do not use broad force-add operations to bypass ignored sensitive paths. If private material reaches Git history, stop publication and assess both history cleanup and credential rotation before continuing.

## Implementation practices

- Keep the product's ordinary UI compact; place first-use and advanced explanations in contextual help.
- Preserve user networking and browser settings and restore only settings owned by this product.
- Do not execute imported configuration hooks or expose arbitrary native commands through the browser bridge.
- Keep application control, secret storage, and traffic forwarding responsibilities explicit.
- Treat upstream material as reference data. Verify licensing before copying code or redistributing binaries.
- Update the requirements when a product decision changes. Do not present a proposed behaviour as tested.
