# SPDX-License-Identifier: MPL-2.0
"""The same deliberately restricted profile format as TunnelCore on macOS."""
import base64
import binascii
import ipaddress
import re


class UserError(Exception):
    """A fixed, safe-to-display message; never interpolate configuration values."""


def ip(value):
    if "%" in value:
        raise ValueError("Scoped addresses are unsupported")
    return ipaddress.ip_address(value)


def cidr(value):
    address, prefix = value.split("/")
    version = ip(address).version
    if not re.fullmatch(r"[0-9]+", prefix) or not 0 <= int(prefix) <= (32 if version == 4 else 128):
        raise ValueError("Invalid prefix")


class Configuration:
    def __init__(self, text):
        if len(text.encode("utf-8")) > 32768 or "\0" in text:
            raise UserError("Configuration is too large or contains invalid characters.")
        allowed = {
            "Interface": {"PrivateKey", "Address", "DNS", "MTU", "ListenPort"},
            "Peer": {"PublicKey", "PresharedKey", "Endpoint", "AllowedIPs", "PersistentKeepalive"},
        }
        sections, section = {}, None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("["):
                if line not in ("[Interface]", "[Peer]") or line[1:-1] in sections:
                    raise UserError("Only one [Interface] and one [Peer] are supported.")
                section = line[1:-1]
                sections[section] = {}
                continue
            if "=" not in line or section is None:
                raise UserError("Invalid WireGuard configuration structure.")
            key, value = (part.strip() for part in line.split("=", 1))
            if key not in allowed[section]:
                raise UserError("Unsupported configuration field. Remove hooks and custom backend options.")
            if not value or "$" in value or key in sections[section]:
                raise UserError("Empty, duplicate, or environment-based fields are not supported.")
            sections[section][key] = value
        interface, peer = sections.get("Interface", {}), sections.get("Peer", {})

        def require(fields, key):
            if key not in fields:
                raise UserError(f"Missing required field: {key}.")
            return fields[key]

        def key_value(value):
            try:
                decoded = base64.b64decode(value, validate=True)
                if len(decoded) != 32 or not any(decoded):
                    raise ValueError()
            except (ValueError, binascii.Error):
                raise UserError("A WireGuard key must encode 32 bytes and cannot be all zeros.") from None

        def values(fields, key):
            parts = [v.strip() for v in require(fields, key).split(",")]
            if not all(parts):
                raise UserError("Invalid empty list entry.")
            return parts

        key_value(require(interface, "PrivateKey"))
        key_value(require(peer, "PublicKey"))
        if "PresharedKey" in peer:
            key_value(peer["PresharedKey"])
        addresses = values(interface, "Address")
        dns = values(interface, "DNS")
        routes = values(peer, "AllowedIPs")
        try:
            for address in addresses:
                cidr(address) if "/" in address else ip(address)
            for address in dns:
                ip(address)
            for route in routes:
                cidr(route)
        except ValueError:
            raise UserError("Invalid interface address, IP-literal DNS server, or routing prefix.") from None
        has4 = any(":" not in a for a in addresses)
        has6 = any(":" in a for a in addresses)
        route6 = "::/0" in routes or "0:0:0:0:0:0:0:0/0" in routes
        if not has4 or "0.0.0.0/0" not in routes:
            raise UserError("An IPv4 address and full-tunnel AllowedIPs including 0.0.0.0/0 are required.")
        if has6 != route6 or (not has6 and any(":" in a for a in dns)):
            raise UserError("IPv6 requires both an IPv6 interface address and ::/0.")
        endpoint = require(peer, "Endpoint")
        match = re.fullmatch(r"(\[[0-9a-fA-F:]+\]|[A-Za-z0-9][A-Za-z0-9.-]*):([0-9]{1,5})", endpoint)
        if not match or not 1 <= int(match[2]) <= 65535:
            raise UserError("Endpoint must be a hostname or IP address followed by a valid port.")
        for fields, key, low, high in [(interface, "MTU", 1280, 9000), (interface, "ListenPort", 0, 65535),
                                       (peer, "PersistentKeepalive", 0, 65535)]:
            if key in fields and (not re.fullmatch(r"[0-9]+", fields[key]) or not low <= int(fields[key]) <= high):
                raise UserError(f"Invalid numeric field: {key}.")
        output = ["[Interface]"]
        output += [f"{k} = {interface[k]}" for k in ("PrivateKey", "Address", "DNS", "MTU") if k in interface]
        output += ["", "[Peer]"]
        output += [f"{k} = {peer[k]}" for k in ("PublicKey", "PresharedKey", "Endpoint", "AllowedIPs") if k in peer]
        output += ["PersistentKeepalive = 25", ""]
        self.canonical = "\n".join(output)
        self.supports_ipv6 = has6
        self.client_ips = [a.split("/")[0] for a in addresses]
        self.dns_servers = dns

    def backend_config(self, port):
        return self.canonical + f"\n[Socks5]\nBindAddress = 127.0.0.1:{port}\n"
