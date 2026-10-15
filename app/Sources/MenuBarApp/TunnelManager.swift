import Foundation
import Darwin
import TunnelCore

@MainActor final class TunnelManager: ObservableObject {
    @Published private(set) var state = TunnelState()
    private var process: Process?
    private var healthPort: UInt16?
    private var generation = UUID()
    private var started = Date()
    private var timer: Timer?
    private var polling = false
    private var owner: String?
    private var lastLease = Date()
    private let session: URLSession
    private let helperURL: URL

    init(helperURL: URL? = nil) {
        self.helperURL = helperURL ?? Bundle.main.executableURL!.deletingLastPathComponent().appendingPathComponent("firefox-wireguard-bridge")
        let config = URLSessionConfiguration.ephemeral
        config.connectionProxyDictionary = [:]
        config.timeoutIntervalForRequest = 2
        session = URLSession(configuration: config)
        timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.poll() }
        }
    }
    func owns(_ client: String) -> Bool { owner == nil || owner == client }
    func renew(_ client: String) { if owner == client { lastLease = Date() } }

    func connect(profile: Profile, configuration: TunnelConfiguration, client: String) throws {
        guard owns(client) else { throw UserError("Another Firefox profile owns the active tunnel. Disconnect it first.") }
        stop(reason: nil)
        let helper = helperURL
        let backend = helper.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Resources/wireproxy")
        guard FileManager.default.isExecutableFile(atPath: helper.path), FileManager.default.isExecutableFile(atPath: backend.path) else {
            throw UserError("The packaged WireGuard backend is missing. Rebuild the app with the backend download step.")
        }
        var reservations: [Int32] = []
        defer { reservations.forEach { Darwin.close($0) } }
        let (proxyPort, proxyFD) = try reservePort(); reservations.append(proxyFD)
        let (metricsPort, metricsFD) = try reservePort(); reservations.append(metricsFD)
        let task = Process(), input = Pipe(), token = UUID()
        generation = token
        task.executableURL = helper
        task.arguments = ["--run-backend", String(metricsPort), String(getpid())]
        task.standardInput = input
        task.standardOutput = FileHandle.nullDevice; task.standardError = FileHandle.nullDevice
        task.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, self.generation == token else { return }
                self.state.phase = "blocked"
                self.state.error = "The WireGuard backend stopped. Check the profile and reconnect."
                self.state.proxyPort = nil
            }
        }
        // Release reservations immediately before spawn. If another process wins
        // the bind race, backend startup fails instead of selecting a new route.
        reservations.forEach { Darwin.close($0) }; reservations.removeAll()
        do { try task.run() } catch { throw UserError("Unable to start the WireGuard backend.") }
        process = task; owner = client; lastLease = Date(); healthPort = metricsPort; started = Date()
        state = TunnelState()
        state.phase = "connecting"; state.profileID = profile.id
        state.proxyPort = proxyPort; state.supportsIPv6 = configuration.supportsIPv6
        let bytes = Data(configuration.backendConfig(proxyPort: proxyPort, healthPort: metricsPort).utf8)
        // Avoid blocking the menu bar if a child exits before consuming the input.
        DispatchQueue.global(qos: .userInitiated).async {
            try? input.fileHandleForWriting.write(contentsOf: bytes)
            try? input.fileHandleForWriting.close()
        }
    }

    func stop(reason: String?) {
        generation = UUID()
        if let old = process, old.isRunning {
            old.terminate()
            // The supervisor handles its own child. Never SIGKILL the supervisor
            // before it has had a chance to terminate the WireGuard process.
        }
        process = nil; healthPort = nil; owner = nil
        state = TunnelState()
        if let reason { state.phase = "blocked"; state.error = reason }
    }

    private func poll() async {
        guard let process, process.isRunning else { return }
        if Date().timeIntervalSince(lastLease) > 12 {
            stop(reason: "Firefox is no longer responding. Reconnect from the extension.")
            return
        }
        guard !polling, let healthPort else { return }
        polling = true; defer { polling = false }
        let token = generation
        do {
            let (data, response) = try await session.data(from: URL(string: "http://127.0.0.1:\(healthPort)/metrics")!)
            guard generation == token else { return }
            guard (response as? HTTPURLResponse)?.statusCode == 200, data.count < 65_536 else { throw UserError("Invalid backend response.") }
            let text = String(decoding: data, as: UTF8.self)
            let handshakes = text.components(separatedBy: .newlines).compactMap { line -> TimeInterval? in
                guard line.hasPrefix("last_handshake_time_sec=") else { return nil }
                return TimeInterval(line.dropFirst("last_handshake_time_sec=".count))
            }
            let age = handshakes.filter { $0 > 0 }.map { max(0, Int(Date().timeIntervalSince1970 - $0)) }.min()
            state.handshakeAge = age
            if let age, age < 180 {
                state.phase = "connected"; state.error = nil
            } else if Date().timeIntervalSince(started) > 30 {
                state.phase = "blocked"
                state.error = "No recent WireGuard handshake. Check the server, endpoint, and keys."
            }
        } catch {
            guard generation == token else { return }
            if Date().timeIntervalSince(started) > 5 {
                state.phase = "blocked"; state.error = "The WireGuard backend is not responding. Reconnect to retry."
            }
        }
    }

    private func reservePort() throws -> (UInt16, Int32) {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw UserError("Unable to allocate a local proxy port.") }
        var address = sockaddr_in()
        address.sin_family = sa_family_t(AF_INET); address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_addr.s_addr = inet_addr("127.0.0.1"); address.sin_port = 0
        let result = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
        var size = socklen_t(MemoryLayout<sockaddr_in>.size)
        let named = withUnsafeMutablePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &size) } }
        guard result == 0, named == 0 else { Darwin.close(fd); throw UserError("Unable to allocate a local proxy port.") }
        return (UInt16(bigEndian: address.sin_port), fd)
    }
}
