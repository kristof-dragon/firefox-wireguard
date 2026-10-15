# Privacy and data transmission

Updated 2026-10-15. Applies to WireGuard for Firefox extension 0.2.1 and
Firefox WireGuard macOS companion 0.2.1.

## What leaves the browser

When you choose **Connect**, Firefox sends covered browsing traffic through
the local companion and your chosen WireGuard server. This includes destination
domains and IP addresses and the requests and responses needed to load websites.
The tunnel encrypts traffic between your Mac and that server. HTTPS remains
encrypted between Firefox and the destination website. The server operator can
observe connection metadata and any traffic not separately protected by HTTPS.
Choose a server you trust. This project does not operate a VPN service.

The extension sends connection commands, a random local client identifier, and
the selected profile identifier to the companion through native messaging. The
companion returns profile names and identifiers, connection state, and the
connection details displayed in the popup. Website contents are not sent in
these control messages. Keys and complete configurations never reach the
extension; the companion uses them to establish the WireGuard connection.

## Public IP and country lookup

After a healthy handshake and approximately every five minutes while connected,
the companion makes an HTTPS request through the tunnel to
`https://ipwho.is/?fields=success,ip,country_code`. This obtains the public exit
IP and its approximate country for both interfaces. The service receives that
exit IP and ordinary request metadata, such as timing and the HTTP user-agent.
It does not receive your WireGuard keys, profile name, configured client/DNS
addresses, or browsing history from this lookup. There is no direct-network
fallback for the lookup. Failure displays **Unavailable**.

The service has its own [privacy policy](https://ipwhois.io/privacy) and
[terms](https://ipwhois.io/terms), including possible request logging. The
project does not control that service's retention or availability. The country
describes the exit IP, not GPS or a measurement of your physical location.

## What stays on your Mac

- Complete tunnel configurations are stored in macOS Keychain. Profile names
  and identifiers are stored in the companion's per-user application folder.
- Firefox local extension storage retains a random client identifier, the
  selected profile identifier, desired connection state, and kill-switch choice.
- Public IP, country, tunnel DNS/client addresses, and connection byte counters
  are held in memory. The product does not save these details as history.
- The product does not record browsing history, website content, or private
  browsing activity. It has no analytics, advertising, or remote error reporting.

The project maintainers receive no automatic reports from the product. Your
chosen server, DNS provider, websites, and the IP lookup provider process
requests according to their own policies. Normal WireGuard endpoint resolution
and encrypted tunnel transport use the Mac's ordinary network.

## Controls and limits

Firefox's installation prompt declares **browsing activity**, **website content**,
and **location information** because traffic is forwarded and the exit IP is
geolocated. This is a declaration of transmission for the connection features,
not a claim that the project stores these categories or runs an analytics
service. Firefox 140 or later is required for the built-in consent prompt.

**Disconnect** stops tunnelling and returns to ordinary browsing. With the kill
switch on, detected failures block covered requests; switching it off permits
ordinary browsing during an outage. Localhost bypasses the tunnel. Disabling or
removing the extension ends its enforcement. This is a browser proxy control,
not an operating-system firewall; see [validation limits](validation.md).

Delete profiles in the companion to remove their Keychain entries. Uninstalling
the extension removes its local extension storage. Deleting the companion alone
does not delete saved Keychain entries; see [removal](installation.md#updates-and-removal).

For questions, use the project's issue tracker linked from the add-on listing.
Do not post keys, real configurations, private endpoints, or unredacted screenshots.
