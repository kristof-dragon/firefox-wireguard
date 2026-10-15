# References and distribution notes

These links are design inputs. Their code, binaries, and instructions are not automatically approved for inclusion or execution. Recheck current documentation and licences when implementing or packaging.

## Userspace WireGuard

- [wireproxy](https://github.com/windtf/wireproxy): candidate userspace WireGuard backend exposing a local proxy.
- [WireGuard](https://www.wireguard.com/): protocol and configuration background.
- [Wireguard-Browser-Extension prototype](https://github.com/Nope-im-not-pro/Wireguard-Browser-Extension): a related Firefox/native-host design considered during exploration.

No implementation has been copied from the prototype. Its public availability is not a substitute for confirming a source licence. Evaluate each component's maintenance, security, macOS support, and licence independently.

## Firefox integration

- [Proxy settings API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/proxy/settings)
- [Network privacy controls](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/privacy/network)
- [Native messaging](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging)

Browser-wide proxy settings and native messaging are the proposed integration points. Verify current permission requirements, API behaviour, and browser-version support before implementation.

## Private extension installation

- [Temporary development installation](https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/)
- [Signing and distribution](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)
- [Installing a self-distributed extension](https://extensionworkshop.com/documentation/publish/install-self-distributed/)

A public add-on listing is not required for self-distribution. Ordinary release Firefox requires a signed extension for persistent installation. Temporary development installations are removed on browser restart. Native app/helper installation is separate from the extension package.

Use a stable project-owned extension ID and matching native host allowlist. Signing accounts, tokens, and personal tunnel configurations must never be bundled with the extension.
