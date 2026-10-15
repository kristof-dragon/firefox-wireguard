import XCTest
import Darwin
@testable import TunnelCore

final class MemoryVault: SecretVault {
    var values: [String: String] = [:]
    func read(_ id: String) throws -> String { guard let value = values[id] else { throw UserError("Missing key.") }; return value }
    func write(_ value: String, id: String) throws { values[id] = value }
    func remove(_ id: String) throws { values.removeValue(forKey: id) }
}

final class CoreTests: XCTestCase {
    // Synthetic, generated-at-test-time bytes. No deployment profiles or keys.
    func fixture(_ extra: String = "") -> String {
        """
        [Interface]
        PrivateKey = \(Data(repeating: 7, count: 32).base64EncodedString())
        Address = 192.0.2.2/32
        DNS = 192.0.2.1
        \(extra)
        [Peer]
        PublicKey = \(Data(repeating: 9, count: 32).base64EncodedString())
        Endpoint = vpn.example.invalid:51820
        AllowedIPs = 0.0.0.0/0
        """
    }
    func testCanonicalImportAndNoExtraSections() throws {
        let config = try TunnelConfiguration(fixture("# ignored comment"))
        XCTAssertFalse(config.supportsIPv6)
        XCTAssertEqual(config.clientIPs, ["192.0.2.2"])
        XCTAssertEqual(config.dnsServers, ["192.0.2.1"])
        XCTAssertFalse(config.canonical.contains("ignored comment"))
        XCTAssertTrue(config.canonical.contains("PersistentKeepalive = 25"))
        let output = config.backendConfig(proxyPort: 9999, healthPort: 9998)
        XCTAssertTrue(output.contains("BindAddress = 127.0.0.1:9999"))
        XCTAssertFalse(output.contains("TunnelDomains"))
        for extra in ["PostUp = unsafe-command", "Table = off", "DNS = 192.0.2.4", "WGConfig = external-file", "PrivateKey = $SECRET"] {
            XCTAssertThrowsError(try TunnelConfiguration(fixture(extra)))
        }
        XCTAssertThrowsError(try TunnelConfiguration(fixture() + "\n[http]\nBindAddress = 0.0.0.0:8080"))
        XCTAssertThrowsError(try TunnelConfiguration(fixture() + "\n[Peer]\n"))
    }
    func testDNSAndRoutingCannotSilentlyBypassTunnel() throws {
        XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "DNS = 192.0.2.1", with: "")))
        XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "DNS = 192.0.2.1", with: "DNS = search.example.invalid")))
        XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "0.0.0.0/0", with: "192.0.2.0/24")))
        XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "0.0.0.0/0", with: "0.0.0.0/0, ::/0")))
        let dual = fixture().replacingOccurrences(of: "192.0.2.2/32", with: "192.0.2.2/32, 2001:db8::2/128")
            .replacingOccurrences(of: "0.0.0.0/0", with: "0.0.0.0/0, ::/0")
        XCTAssertTrue(try TunnelConfiguration(dual).supportsIPv6)
    }
    func testInterfaceAddressesAcceptBareAndPrefixedForms() throws {
        for address in ["192.0.2.2", "192.0.2.2/32", "192.0.2.2/24"] {
            let config = try TunnelConfiguration(fixture().replacingOccurrences(of: "192.0.2.2/32", with: address))
            XCTAssertFalse(config.supportsIPv6)
            XCTAssertTrue(config.backendConfig(proxyPort: 9999, healthPort: 9998).contains("Address = \(address)\n"))
        }
        for addresses in ["192.0.2.2, 2001:db8::2", "192.0.2.2/32, 2001:db8::2", "192.0.2.2, 2001:db8::2/64"] {
            let text = fixture().replacingOccurrences(of: "192.0.2.2/32", with: addresses)
                .replacingOccurrences(of: "0.0.0.0/0", with: "0.0.0.0/0, ::/0")
            let config = try TunnelConfiguration(text)
            XCTAssertTrue(config.supportsIPv6)
            XCTAssertEqual(config.clientIPs, ["192.0.2.2", "2001:db8::2"])
            XCTAssertTrue(config.canonical.contains("Address = \(addresses)\n"))
        }
    }
    func testOptionalInterfacePrefixesDoNotAdmitMalformedAddressesOrRoutes() throws {
        for address in ["192.0.2.999", "192.0.2.2/", "192.0.2.2/-1", "192.0.2.2/33", "192.0.2.2/32/1", "192.0.2.2, 2001:db8::2/129", "host.example.invalid"] {
            XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "192.0.2.2/32", with: address)))
        }
        XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "0.0.0.0/0", with: "0.0.0.0")))
        XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: "0.0.0.0/0", with: "0.0.0.0/0, 192.0.2.1")))
    }
    func testParserRejectsInvalidValuesWithoutReflectingSecrets() throws {
        let secret = "NOT-A-REAL-KEY-DO-NOT-REFLECT"
        let text = fixture().replacingOccurrences(of: Data(repeating: 7, count: 32).base64EncodedString(), with: secret)
        XCTAssertThrowsError(try TunnelConfiguration(text)) { error in XCTAssertFalse(error.localizedDescription.contains(secret)) }
        for (old, replacement) in [("192.0.2.2/32", "192.0.2.2/99"), ("51820", "99999"), ("vpn.example.invalid:51820", "bad host:51820")] {
            XCTAssertThrowsError(try TunnelConfiguration(fixture().replacingOccurrences(of: old, with: replacement)))
        }
        XCTAssertThrowsError(try TunnelConfiguration(String(repeating: "x", count: 33_000)))
    }
    func testProfileIndexDoesNotContainConfigurationAndReloads() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let vault = MemoryVault(), store = try ProfileStore(directory: directory, vault: vault)
        let profile = try store.save(name: "Test profile", configuration: fixture())
        let index = try String(contentsOf: directory.appendingPathComponent("profiles.json"))
        for forbidden in ["PrivateKey", "Endpoint", "vpn.example.invalid", "192.0.2."] { XCTAssertFalse(index.contains(forbidden)) }
        XCTAssertEqual(try ProfileStore(directory: directory, vault: vault).profiles, [profile])
        XCTAssertFalse(try store.configuration(profile.id).supportsIPv6)
        XCTAssertEqual((try FileManager.default.attributesOfItem(atPath: directory.path)[.posixPermissions] as? NSNumber)?.intValue, 0o700)
        XCTAssertEqual((try FileManager.default.attributesOfItem(atPath: directory.appendingPathComponent("profiles.json").path)[.posixPermissions] as? NSNumber)?.intValue, 0o600)
        try store.remove(profile.id)
        XCTAssertTrue(vault.values.isEmpty)
        XCTAssertTrue(store.profiles.isEmpty)
    }
    func testCorruptIndexIsNotSilentlyOverwritten() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try SecureFiles.directory(directory)
        try SecureFiles.write(Data("broken".utf8), to: directory.appendingPathComponent("profiles.json"))
        XCTAssertThrowsError(try ProfileStore(directory: directory, vault: MemoryVault()))
        XCTAssertEqual(try String(contentsOf: directory.appendingPathComponent("profiles.json")), "broken")
    }
    func testFramesRejectTruncationAndOversize() throws {
        XCTAssertThrowsError(try Frames.encode(Data()))
        XCTAssertThrowsError(try Frames.encode(Data(repeating: 0, count: Integration.maxFrame + 1)))
        let pipe = Pipe()
        try pipe.fileHandleForWriting.write(contentsOf: Data([2, 0, 0, 0, 123]))
        try pipe.fileHandleForWriting.close()
        XCTAssertThrowsError(try Frames.read(fd: pipe.fileHandleForReading.fileDescriptor))
    }
    func testControlValidationAndFramedRoundTrip() throws {
        let request = ControlRequest(id: "test", command: "status", clientID: UUID().uuidString)
        try request.validate()
        XCTAssertThrowsError(try ControlRequest(id: "test", command: "exec", clientID: request.clientID).validate())
        XCTAssertThrowsError(try ControlRequest(version: 2, id: "test", command: "status", clientID: request.clientID).validate())
        XCTAssertThrowsError(try ControlRequest(id: "test", command: "connect", clientID: request.clientID, profileID: "../secret").validate())
        let pipe = Pipe(), data = try JSONEncoder().encode(request)
        try Frames.write(data, fd: pipe.fileHandleForWriting.fileDescriptor)
        XCTAssertEqual(try Frames.read(fd: pipe.fileHandleForReading.fileDescriptor), data)
    }
    func testPrivateSocketRoundTrip() throws {
        // Use a short per-test path to stay within macOS sockaddr_un's path limit.
        let directory = URL(fileURLWithPath: "/tmp/fwgt-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let path = directory.appendingPathComponent("control.sock").path
        let server = try ControlServer(path: path) { request in ControlResponse(id: request.id, ok: true, profiles: [Profile(name: "Fixture")]) }
        defer { withExtendedLifetime(server) {} }
        let request = ControlRequest(id: "roundtrip", command: "status", clientID: UUID().uuidString)
        let response = try JSONDecoder().decode(ControlResponse.self, from: LocalSocket.exchange(JSONEncoder().encode(request), path: path))
        XCTAssertTrue(response.ok); XCTAssertEqual(response.id, request.id); XCTAssertEqual(response.profiles.first?.name, "Fixture")
        XCTAssertEqual((try FileManager.default.attributesOfItem(atPath: path)[.posixPermissions] as? NSNumber)?.intValue, 0o600)
    }
    func testRealKeychainRoundTripWhenRequested() throws {
        guard ProcessInfo.processInfo.environment["FWG_TEST_KEYCHAIN"] == "1" else {
            throw XCTSkip("Set FWG_TEST_KEYCHAIN=1 to exercise a temporary, isolated Keychain item.")
        }
        let vault = KeychainVault(service: "org.firefoxwireguard.tests.\(UUID().uuidString)")
        let id = UUID().uuidString
        defer { try? vault.remove(id) }
        try vault.write("temporary integration-test value", id: id)
        XCTAssertEqual(try vault.read(id), "temporary integration-test value")
        try vault.write("updated integration-test value", id: id)
        XCTAssertEqual(try vault.read(id), "updated integration-test value")
        try vault.remove(id)
        XCTAssertThrowsError(try vault.read(id))
    }
}
