// SPDX-License-Identifier: MPL-2.0
import Foundation
import TunnelCore

protocol ExitIPLookingUp {
    func lookup(proxyPort: UInt16) async throws -> PublicExit
}

struct SOCKSExitIPLookup: ExitIPLookingUp {
    // Fixed HTTPS endpoint, no user data in URL or headers. socks5h resolves the
    // service hostname through the tunnel, with no direct or system-DNS fallback.
    static func arguments(proxyPort: UInt16) -> [String] {
        ["--disable", "--proxy", "socks5h://127.0.0.1:\(proxyPort)", "--noproxy", "",
         "--proto", "=https", "--connect-timeout", "5", "--max-time", "10",
         "--max-filesize", "16384", "--silent", "--fail", "--header", "Accept: application/json",
         "--url", "https://ipwho.is/?fields=success,ip,country_code"]
    }
    func lookup(proxyPort: UInt16) async throws -> PublicExit {
        let request = CurlRequest(arguments: Self.arguments(proxyPort: proxyPort))
        let data = try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { continuation in
                DispatchQueue.global(qos: .utility).async {
                    do { continuation.resume(returning: try request.run()) }
                    catch { continuation.resume(throwing: error) }
                }
            }
        }, onCancel: { request.cancel() })
        return try PublicExit(data: data)
    }
}

private final class CurlRequest: @unchecked Sendable {
    private let lock = NSLock()
    private let process = Process()
    private let output = Pipe()
    private var cancelled = false
    init(arguments: [String]) {
        process.executableURL = URL(fileURLWithPath: "/usr/bin/curl")
        process.arguments = arguments
        process.environment = [:]
        process.standardInput = FileHandle.nullDevice
        process.standardOutput = output; process.standardError = FileHandle.nullDevice
    }
    func cancel() {
        lock.lock(); defer { lock.unlock() }
        cancelled = true
        if process.isRunning { process.terminate() }
    }
    func run() throws -> Data {
        lock.lock()
        do {
            guard !cancelled else { throw CancellationError() }
            try process.run()
            lock.unlock()
        } catch { lock.unlock(); throw error }
        defer {
            cancel()
            process.waitUntilExit()
            try? output.fileHandleForReading.close()
        }
        var data = Data()
        while let chunk = try output.fileHandleForReading.read(upToCount: 4096), !chunk.isEmpty {
            guard data.count + chunk.count <= 16_384 else { throw UserError("Public IP lookup unavailable.") }
            data.append(chunk)
        }
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { throw UserError("Public IP lookup unavailable.") }
        return data
    }
}
