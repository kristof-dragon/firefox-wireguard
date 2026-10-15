import Foundation

/// Non-secret connection information. Kept in memory, never persisted or logged.
public struct ConnectionDetails: Codable, Equatable {
    public var connectionID: String
    public var clientIPs: [String]
    public var dnsServers: [String]
    public var downloadedBytes: UInt64?
    public var uploadedBytes: UInt64?
    public var statsUpdatedAt: TimeInterval?
    public var publicIP: String?
    public var countryCode: String?
    public var exitStatus = "waiting"
    public var exitCheckedAt: TimeInterval?

    public init(connectionID: String, clientIPs: [String], dnsServers: [String]) {
        self.connectionID = connectionID; self.clientIPs = clientIPs; self.dnsServers = dnsServers
    }
    public var countryFlag: String {
        guard let code = countryCode, code.utf8.count == 2,
              code.utf8.allSatisfy({ (65...90).contains($0) }) else { return "🌐" }
        return String(String.UnicodeScalarView(code.unicodeScalars.compactMap { UnicodeScalar($0.value + 127397) }))
    }
    public static func byteLabel(_ bytes: UInt64?) -> String {
        guard let bytes else { return "—" }
        var value = Double(bytes), unit = 0
        let units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
        while value >= 1000 && unit < units.count - 1 { value /= 1000; unit += 1 }
        return "\(value.formatted(.number.precision(.fractionLength(0...1)))) \(units[unit])"
    }
}

/// wireproxy /metrics uses WireGuard UAPI counters, not Prometheus text.
public struct WireGuardMetrics {
    public let downloadedBytes: UInt64
    public let uploadedBytes: UInt64
    public let handshakeTime: TimeInterval?
    public init(_ data: Data) throws {
        guard data.count <= 65_536, let text = String(data: data, encoding: .utf8) else { throw UserError("Invalid backend metrics.") }
        var values: [String: UInt64] = [:]
        for line in text.components(separatedBy: .newlines) {
            let pair = line.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: false)
            guard pair.count == 2 else { continue }
            let key = String(pair[0])
            guard ["rx_bytes", "tx_bytes", "last_handshake_time_sec"].contains(key) else { continue }
            guard values[key] == nil, let value = UInt64(pair[1]) else { throw UserError("Invalid backend metrics.") }
            values[key] = value
        }
        guard let rx = values["rx_bytes"], let tx = values["tx_bytes"], let stamp = values["last_handshake_time_sec"] else { throw UserError("Incomplete backend metrics.") }
        downloadedBytes = rx; uploadedBytes = tx
        handshakeTime = stamp > 0 ? TimeInterval(stamp) : nil
    }
}

public struct PublicExit: Equatable, Sendable {
    public let ip: String
    public let countryCode: String?
    public init(data: Data) throws {
        struct Response: Decodable { let success: Bool; let ip: String?; let country_code: String? }
        guard data.count <= 16_384, let response = try? JSONDecoder().decode(Response.self, from: data),
              response.success, let ip = response.ip, TunnelConfiguration.isIP(ip) else {
            throw UserError("Public IP lookup unavailable.")
        }
        self.ip = ip
        if let code = response.country_code?.uppercased(), code.utf8.count == 2,
           code.utf8.allSatisfy({ (65...90).contains($0) }) { countryCode = code }
        else { countryCode = nil }
    }
}
