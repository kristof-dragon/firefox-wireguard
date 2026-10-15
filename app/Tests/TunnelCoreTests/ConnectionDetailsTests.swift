import XCTest
import Darwin
import SwiftUI
@testable import TunnelCore
@testable import MenuBarApp

final class ConnectionDetailsTests: XCTestCase {
    func testExitLookupSendsHostnameToSOCKSAndFailsWhenProxyRejects() async throws {
        let listener = socket(AF_INET, SOCK_STREAM, 0)
        guard listener >= 0 else { return XCTFail("No fixture socket") }
        defer { Darwin.close(listener) }
        LocalSocket.configure(listener)
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET); address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        let bound = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(listener, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
        XCTAssertEqual(bound, 0); XCTAssertEqual(listen(listener, 1), 0)
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(listener, $0, &length) } }
        let port = UInt16(bigEndian: address.sin_port), received = expectation(description: "SOCKS domain request")
        DispatchQueue.global().async {
            defer { received.fulfill() }
            let fd = accept(listener, nil, nil)
            guard fd >= 0 else { return XCTFail("No SOCKS connection") }
            defer { Darwin.close(fd) }
            LocalSocket.configure(fd)
            func read(_ count: Int) -> [UInt8] {
                var bytes = [UInt8](repeating: 0, count: count), offset = 0
                while offset < count {
                    let n = bytes.withUnsafeMutableBytes { Darwin.read(fd, $0.baseAddress!.advanced(by: offset), count - offset) }
                    guard n > 0 else { return [] }
                    offset += n
                }
                return bytes
            }
            let greeting = read(2)
            guard greeting.count == 2 else { return XCTFail("Missing SOCKS greeting") }
            XCTAssertEqual(greeting[0], 5); _ = read(Int(greeting[1]))
            _ = [UInt8(5), 0].withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
            XCTAssertEqual(read(4), [5, 1, 0, 3]) // A hostname, not an OS-resolved IP.
            guard let count = read(1).first else { return XCTFail("Missing hostname") }
            XCTAssertEqual(String(bytes: read(Int(count)), encoding: .utf8), "ipwho.is")
            XCTAssertEqual(read(2), [1, 187]) // HTTPS port 443.
            _ = [UInt8(5), 5, 0, 1, 0, 0, 0, 0, 0, 0].withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
        }
        do { _ = try await SOCKSExitIPLookup().lookup(proxyPort: port); XCTFail("Rejected proxy must fail the lookup") }
        catch { XCTAssertEqual(error.localizedDescription, "Public IP lookup unavailable.") }
        await fulfillment(of: [received], timeout: 12)
    }

    @MainActor func testRenderConnectionPanelWhenRequested() throws {
        guard let path = ProcessInfo.processInfo.environment["FWG_PREVIEW_PATH"] else {
            throw XCTSkip("Set FWG_PREVIEW_PATH to render synthetic connection details.")
        }
        var details = ConnectionDetails(connectionID: "fixture", clientIPs: ["192.0.2.2", "2001:db8::2"], dnsServers: ["192.0.2.1"])
        details.downloadedBytes = 123_456_789; details.uploadedBytes = 8_765_432; details.statsUpdatedAt = 100
        details.publicIP = "203.0.113.8"; details.countryCode = "GB"; details.exitStatus = "ready"
        let content = VStack(alignment: .leading, spacing: 12) {
            Label("Firefox WireGuard", systemImage: "shield.lefthalf.filled").font(.headline)
            Label("Tunnel ready", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
            Text("Example tunnel").font(.subheadline)
            ConnectionPanel(details: details, connected: true)
        }.padding(16).frame(width: 350).background(Color(nsColor: .windowBackgroundColor)).environment(\.colorScheme, .light)
        let renderer = ImageRenderer(content: content); renderer.scale = 2
        let image = try XCTUnwrap(renderer.cgImage)
        let bitmap = NSBitmapImageRep(cgImage: image)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: URL(fileURLWithPath: path))
        XCTAssertGreaterThan(image.height, 200)
    }
    func testMetricsMapDirectionsAndRejectIncompleteOrMalformedCounters() throws {
        let text = "private_key=(redacted)\nrx_bytes=12345\ntx_bytes=678\nlast_handshake_time_sec=100\n"
        let metrics = try WireGuardMetrics(Data(text.utf8))
        XCTAssertEqual(metrics.downloadedBytes, 12345)
        XCTAssertEqual(metrics.uploadedBytes, 678)
        XCTAssertEqual(metrics.handshakeTime, 100)
        for invalid in [text + "rx_bytes=1\n", text.replacingOccurrences(of: "678", with: "-1"),
                        text.replacingOccurrences(of: "678", with: "18446744073709551616"),
                        "rx_bytes=1\ntx_bytes=2\n", text.replacingOccurrences(of: "12345", with: "NaN")] {
            XCTAssertThrowsError(try WireGuardMetrics(Data(invalid.utf8)))
        }
        XCTAssertNil(try WireGuardMetrics(Data(text.replacingOccurrences(of: "sec=100", with: "sec=0").utf8)).handshakeTime)
    }
    func testPublicExitRejectsFailedOversizedAndNonIPResponses() throws {
        let result = try PublicExit(data: Data(#"{"success":true,"ip":"203.0.113.8","country_code":"gb"}"#.utf8))
        XCTAssertEqual(result.ip, "203.0.113.8"); XCTAssertEqual(result.countryCode, "GB")
        let ipv6 = try PublicExit(data: Data(#"{"success":true,"ip":"2001:db8::1","country_code":"unknown"}"#.utf8))
        XCTAssertNil(ipv6.countryCode)
        for invalid in [#"{"success":false,"ip":"203.0.113.8"}"#, #"{"success":true,"ip":"example.invalid"}"#,
                        #"{"success":true}"#, "{}", String(repeating: " ", count: 16_385)] {
            XCTAssertThrowsError(try PublicExit(data: Data(invalid.utf8)))
        }
    }
    func testDisplayHasOnlyAddressesAndCountersAndSupportsOldProtocol() throws {
        var details = ConnectionDetails(connectionID: "fixture", clientIPs: ["192.0.2.2"], dnsServers: ["192.0.2.1"])
        details.countryCode = "GB"
        XCTAssertEqual(details.countryFlag, "🇬🇧")
        details.countryCode = "<invalid>"
        XCTAssertEqual(details.countryFlag, "🌐")
        XCTAssertEqual(ConnectionDetails.byteLabel(nil), "—")
        XCTAssertEqual(ConnectionDetails.byteLabel(0), "0 B")
        XCTAssertEqual(ConnectionDetails.byteLabel(1_000_000), "1 MB")
        let data = try JSONEncoder().encode(details)
        XCTAssertEqual(try JSONDecoder().decode(ConnectionDetails.self, from: data), details)
        let oldState = Data(#"{"phase":"connected","supportsIPv6":false}"#.utf8)
        XCTAssertNil(try JSONDecoder().decode(TunnelState.self, from: oldState).details)
    }
    func testExitLookupAlwaysUsesRemoteDNSProxyAndIgnoresCurlPreferences() {
        let args = SOCKSExitIPLookup.arguments(proxyPort: 34567)
        XCTAssertEqual(args.first, "--disable")
        for (option, value) in [("--proxy", "socks5h://127.0.0.1:34567"), ("--noproxy", ""),
                                ("--proto", "=https"), ("--max-time", "10"), ("--max-filesize", "16384"),
                                ("--url", "https://ipwho.is/?fields=success,ip,country_code")] {
            XCTAssertEqual(args[args.firstIndex(of: option)! + 1], value)
        }
        XCTAssertFalse(args.contains("--insecure")); XCTAssertFalse(args.contains("--location"))
    }
}
