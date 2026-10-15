import Foundation
import Darwin

public struct UserError: LocalizedError, Equatable {
    public let message: String
    public init(_ message: String) { self.message = message }
    public var errorDescription: String? { message }
}

/// Parse only the configuration subset we can safely reproduce. Never forward
/// arbitrary imported sections, shell hooks, file includes, or environment values.
public struct TunnelConfiguration {
    public let canonical: String
    public let supportsIPv6: Bool
    public let clientIPs: [String]
    public let dnsServers: [String]

    public init(_ text: String) throws {
        guard text.utf8.count <= 32_768, !text.contains("\0") else {
            throw UserError("Configuration is too large or contains invalid characters.")
        }
        let allowed = [
            "Interface": Set(["PrivateKey", "Address", "DNS", "MTU", "ListenPort"]),
            "Peer": Set(["PublicKey", "PresharedKey", "Endpoint", "AllowedIPs", "PersistentKeepalive"])
        ]
        var values: [String: [String: String]] = [:]
        var section = ""
        for raw in text.components(separatedBy: .newlines) {
            let line = raw.components(separatedBy: "#")[0].trimmingCharacters(in: .whitespaces)
            if line.isEmpty { continue }
            if line.hasPrefix("[") {
                guard ["[Interface]", "[Peer]"].contains(line) else {
                    throw UserError("Only one [Interface] and one [Peer] are supported. Hooks and proxy sections are not accepted.")
                }
                section = String(line.dropFirst().dropLast())
                guard values[section] == nil else { throw UserError("Duplicate sections are not supported.") }
                values[section] = [:]
                continue
            }
            let pair = line.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard pair.count == 2, let keys = allowed[section] else { throw UserError("Invalid WireGuard configuration structure.") }
            let key = pair[0].trimmingCharacters(in: .whitespaces)
            let value = pair[1].trimmingCharacters(in: .whitespaces)
            guard keys.contains(key) else { throw UserError("Unsupported configuration field. Remove shell hooks, search domains, and custom backend options.") }
            guard !value.isEmpty, !value.contains("$"), values[section]?[key] == nil else {
                throw UserError("Empty, duplicate, or environment-based configuration fields are not supported.")
            }
            values[section]?[key] = value
        }
        let interface = values["Interface"] ?? [:], peer = values["Peer"] ?? [:]
        func require(_ fields: [String: String], _ key: String) throws -> String {
            guard let value = fields[key] else { throw UserError("Missing required field: \(key).") }
            return value
        }
        func validateKey(_ value: String) throws {
            guard let bytes = Data(base64Encoded: value), bytes.count == 32,
                  bytes.contains(where: { $0 != 0 }) else { throw UserError("A WireGuard key is invalid. Keys must encode 32 bytes and cannot be all zeros.") }
        }
        try validateKey(require(interface, "PrivateKey"))
        try validateKey(require(peer, "PublicKey"))
        if let key = peer["PresharedKey"] { try validateKey(key) }
        let addresses = try Self.list(require(interface, "Address"))
        // WireGuard's Apple client and wireproxy both accept bare interface IPs.
        // Preserve the input form; explicit prefixes must still be valid. This
        // does not relax AllowedIPs, which remains a routing-prefix list below.
        for address in addresses {
            guard Self.isIP(address) || Self.validCIDR(address) else {
                throw UserError("Address must contain valid IP addresses, optionally followed by /prefix (IPv4: 0–32; IPv6: 0–128).")
            }
        }
        let has4 = addresses.contains { !$0.contains(":") }, has6 = addresses.contains { $0.contains(":") }
        guard has4 else { throw UserError("This first version requires an IPv4 interface address.") }
        let dns = try Self.list(require(interface, "DNS"))
        guard dns.allSatisfy(Self.isIP) else { throw UserError("DNS must contain IP addresses only. A tunnel DNS server is required.") }
        let routes = try Self.list(require(peer, "AllowedIPs"))
        guard routes.allSatisfy(Self.validCIDR), routes.contains("0.0.0.0/0") else {
            throw UserError("Only full-tunnel profiles are supported: AllowedIPs must include 0.0.0.0/0. Split routing is not yet supported.")
        }
        let route6 = routes.contains("::/0") || routes.contains("0:0:0:0:0:0:0:0/0")
        guard has6 == route6 else { throw UserError("IPv6 requires both an IPv6 interface address and ::/0. Otherwise remove IPv6 addresses and routes.") }
        guard has6 || !dns.contains(where: { $0.contains(":") }) else { throw UserError("An IPv6 DNS server requires IPv6 tunnel support.") }
        let endpoint = try require(peer, "Endpoint")
        let pattern = #"^(\[[0-9a-fA-F:]+\]|[A-Za-z0-9][A-Za-z0-9.-]*):([0-9]{1,5})$"#
        guard endpoint.range(of: pattern, options: .regularExpression) != nil,
              let port = Int(endpoint.split(separator: ":").last ?? ""), (1...65535).contains(port) else {
            throw UserError("Endpoint must be a hostname or IP address followed by a valid port.")
        }
        for (fields, key, range) in [(interface, "MTU", 1280...9000), (interface, "ListenPort", 0...65535), (peer, "PersistentKeepalive", 0...65535)] {
            if let raw = fields[key] { guard let number = Int(raw), range.contains(number) else { throw UserError("Invalid numeric field: \(key).") } }
        }
        // A small keepalive provokes a handshake even before the browser is allowed
        // to send traffic. Do not open a local listening WireGuard port explicitly.
        var output = "[Interface]\n"
        for key in ["PrivateKey", "Address", "DNS", "MTU"] {
            if let value = interface[key] { output += "\(key) = \(value)\n" }
        }
        output += "\n[Peer]\n"
        for key in ["PublicKey", "PresharedKey", "Endpoint", "AllowedIPs"] {
            if let value = peer[key] { output += "\(key) = \(value)\n" }
        }
        output += "PersistentKeepalive = 25\n"
        canonical = output
        supportsIPv6 = has6
        clientIPs = addresses.map { String($0.split(separator: "/")[0]) }
        dnsServers = dns
    }

    public func backendConfig(proxyPort: UInt16, healthPort: UInt16) -> String {
        // No TunnelDomains or other direct-routing option is admitted by the parser.
        canonical + "\n[Socks5]\nBindAddress = 127.0.0.1:\(proxyPort)\n"
    }

    private static func list(_ value: String) throws -> [String] {
        let items = value.split(separator: ",", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) }
        guard !items.isEmpty, items.allSatisfy({ !$0.isEmpty }) else { throw UserError("Invalid empty list entry.") }
        return items
    }
    public static func isIP(_ value: String) -> Bool {
        var a4 = in_addr(), a6 = in6_addr()
        return value.withCString { inet_pton(AF_INET, $0, &a4) == 1 || inet_pton(AF_INET6, $0, &a6) == 1 }
    }
    private static func validCIDR(_ value: String) -> Bool {
        let parts = value.split(separator: "/", omittingEmptySubsequences: false)
        guard parts.count == 2, isIP(String(parts[0])), let prefix = Int(parts[1]) else { return false }
        return (0...(parts[0].contains(":") ? 128 : 32)).contains(prefix)
    }
}
