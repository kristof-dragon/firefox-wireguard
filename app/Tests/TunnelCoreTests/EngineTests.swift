// SPDX-License-Identifier: MPL-2.0
import XCTest
import CryptoKit
import Darwin
@testable import MenuBarApp
@testable import TunnelCore

private actor ControlledExitLookup: ExitIPLookingUp {
    var requests: [CheckedContinuation<PublicExit, Error>] = []
    func lookup(proxyPort: UInt16) async throws -> PublicExit {
        try await withCheckedThrowingContinuation { requests.append($0) }
    }
    func count() -> Int { requests.count }
    func complete(_ index: Int, result: Result<PublicExit, Error>) { requests[index].resume(with: result) }
}

final class EngineTests: XCTestCase {
    @MainActor func testManagerWaitsForRealHandshakeAndOwnsOneClient() async throws {
        guard ProcessInfo.processInfo.environment["FWG_TEST_BACKEND"] == "1" else {
            throw XCTSkip("Build the app and set FWG_TEST_BACKEND=1 to run the local WireGuard engine test.")
        }
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let contents = root.appendingPathComponent("dist/Firefox WireGuard.app/Contents")
        let backend = contents.appendingPathComponent("Resources/wireproxy")
        let helper = contents.appendingPathComponent("MacOS/firefox-wireguard-bridge")
        guard FileManager.default.isExecutableFile(atPath: backend.path) else { return XCTFail("Build the app first.") }
        let serverKey = Curve25519.KeyAgreement.PrivateKey(), clientKey = Curve25519.KeyAgreement.PrivateKey()
        let fd = socket(AF_INET, SOCK_DGRAM, 0)
        XCTAssertGreaterThanOrEqual(fd, 0)
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET); address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        let bound = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
        XCTAssertEqual(bound, 0)
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) } }
        let port = UInt16(bigEndian: address.sin_port)
        Darwin.close(fd)
        let server = Process(), pipe = Pipe()
        server.executableURL = backend; server.arguments = ["-s", "-c", "/dev/stdin"]
        server.standardInput = pipe; server.standardOutput = FileHandle.nullDevice; server.standardError = FileHandle.nullDevice
        try server.run()
        defer { if server.isRunning { server.terminate(); server.waitUntilExit() } }
        let serverConfig = """
        [Interface]
        PrivateKey = \(serverKey.rawRepresentation.base64EncodedString())
        Address = 192.0.2.1/32
        ListenPort = \(port)
        DNS = 192.0.2.1
        [Peer]
        PublicKey = \(clientKey.publicKey.rawRepresentation.base64EncodedString())
        AllowedIPs = 192.0.2.2/32
        """
        try pipe.fileHandleForWriting.write(contentsOf: Data(serverConfig.utf8))
        try pipe.fileHandleForWriting.close()
        let config = try TunnelConfiguration("""
        [Interface]
        PrivateKey = \(clientKey.rawRepresentation.base64EncodedString())
        Address = 192.0.2.2
        DNS = 192.0.2.1
        [Peer]
        PublicKey = \(serverKey.publicKey.rawRepresentation.base64EncodedString())
        Endpoint = 127.0.0.1:\(port)
        AllowedIPs = 0.0.0.0/0
        """)
        let lookup = ControlledExitLookup()
        let manager = TunnelManager(helperURL: helper, exitLookup: lookup), owner = UUID().uuidString, profile = Profile(name: "Local engine fixture")
        defer { manager.stop(reason: nil) }
        try manager.connect(profile: profile, configuration: config, client: owner)
        XCTAssertEqual(manager.state.phase, "connecting")
        XCTAssertFalse(manager.owns(UUID().uuidString))
        XCTAssertThrowsError(try manager.connect(profile: profile, configuration: config, client: UUID().uuidString))
        for _ in 0..<30 {
            manager.renew(owner)
            if manager.state.phase == "connected", await lookup.count() == 1 { break }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        XCTAssertEqual(manager.state.phase, "connected", manager.state.error ?? "No handshake observed")
        XCTAssertNotNil(manager.state.handshakeAge)
        XCTAssertNotNil(manager.state.proxyPort)
        XCTAssertEqual(manager.state.details?.clientIPs, ["192.0.2.2"])
        XCTAssertEqual(manager.state.details?.dnsServers, ["192.0.2.1"])
        XCTAssertNotNil(manager.state.details?.downloadedBytes)
        XCTAssertNotNil(manager.state.details?.uploadedBytes)
        let firstConnection = manager.state.details?.connectionID
        let exit = try PublicExit(data: Data(#"{"success":true,"ip":"203.0.113.8","country_code":"GB"}"#.utf8))
        // Hold the old lookup across reconnect; its late result must not appear
        // on the new connection, even when a provider ignores cancellation.
        try manager.connect(profile: profile, configuration: config, client: owner)
        XCTAssertNotEqual(manager.state.details?.connectionID, firstConnection)
        XCTAssertNil(manager.state.details?.downloadedBytes)
        XCTAssertNil(manager.state.details?.publicIP)
        guard await lookup.count() == 1 else { return XCTFail("First lookup did not start") }
        await lookup.complete(0, result: .success(exit))
        for _ in 0..<30 {
            manager.renew(owner)
            if await lookup.count() == 2 { break }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        XCTAssertNil(manager.state.details?.publicIP)
        guard await lookup.count() == 2 else { return XCTFail("Second lookup did not start") }
        await lookup.complete(1, result: .failure(UserError("Fixture provider unavailable")))
        for _ in 0..<10 {
            if manager.state.details?.exitStatus == "unavailable" { break }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        XCTAssertEqual(manager.state.phase, "connected")
        XCTAssertEqual(manager.state.details?.exitStatus, "unavailable")
        try manager.connect(profile: profile, configuration: config, client: owner)
        for _ in 0..<30 {
            manager.renew(owner)
            if await lookup.count() == 3 { break }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        guard await lookup.count() == 3 else { return XCTFail("Third lookup did not start") }
        await lookup.complete(2, result: .success(exit))
        for _ in 0..<10 {
            if manager.state.details?.exitStatus == "ready" { break }
            try await Task.sleep(nanoseconds: 50_000_000)
        }
        XCTAssertEqual(manager.state.details?.publicIP, "203.0.113.8")
        XCTAssertEqual(manager.state.details?.countryFlag, "🇬🇧")
        manager.stop(reason: "Fixture stopped")
        XCTAssertEqual(manager.state.phase, "blocked")
        XCTAssertNil(manager.state.proxyPort)
        XCTAssertNil(manager.state.details)
    }
}
