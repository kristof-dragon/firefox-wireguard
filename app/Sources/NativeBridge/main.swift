import Foundation
import Darwin
import TunnelCore

signal(SIGPIPE, SIG_IGN)
let executable = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
let contents = executable.deletingLastPathComponent().deletingLastPathComponent()

if CommandLine.arguments.count == 4, CommandLine.arguments[1] == "--run-backend",
   let healthPort = UInt16(CommandLine.arguments[2]), let parent = Int32(CommandLine.arguments[3]), parent > 1 {
    // Supervise the backend so a killed/crashed app cannot leave an orphan tunnel.
    // The config travels down stdin, never through arguments or a plaintext file.
    guard getppid() == parent else { exit(1) }
    signal(SIGTERM, SIG_IGN); signal(SIGINT, SIG_IGN)
    let child = Process()
    child.executableURL = contents.appendingPathComponent("Resources/wireproxy")
    child.arguments = ["-c", "/dev/stdin", "-s", "-i", "127.0.0.1:\(healthPort)"]
    child.standardInput = FileHandle.standardInput
    child.standardOutput = FileHandle.nullDevice
    child.standardError = FileHandle.nullDevice
    func stop() {
        if child.isRunning {
            child.terminate()
            for _ in 0..<20 where child.isRunning { Thread.sleep(forTimeInterval: 0.05) }
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
        }
        exit(0)
    }
    let term = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
    term.setEventHandler { stop() }; term.resume()
    let interrupt = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    interrupt.setEventHandler { stop() }; interrupt.resume()
    do { try child.run() } catch { exit(1) }
    let timer = DispatchSource.makeTimerSource(queue: .main)
    timer.schedule(deadline: .now(), repeating: 0.5)
    timer.setEventHandler {
        if getppid() != parent { stop() }
        if !child.isRunning { exit(child.terminationStatus) }
    }
    timer.resume()
    dispatchMain()
}

// Firefox passes the native manifest path and the requesting extension ID.
guard CommandLine.arguments.count == 3, CommandLine.arguments[2] == Integration.extensionID else { exit(1) }
while true {
    do {
        guard let data = try Frames.read(fd: STDIN_FILENO) else { break }
        let request = try JSONDecoder().decode(ControlRequest.self, from: data)
        try request.validate()
        let response: Data
        do {
            var connected = try? LocalSocket.connect()
            if connected == nil {
                // Retry connection establishment only. Never replay a mutating
                // request whose response may have been lost or delayed by Keychain.
                let app = contents.deletingLastPathComponent()
                if app.pathExtension == "app" {
                    let launch = Process()
                    launch.executableURL = URL(fileURLWithPath: "/usr/bin/open")
                    launch.arguments = ["-g", app.path]
                    launch.standardOutput = FileHandle.nullDevice; launch.standardError = FileHandle.nullDevice
                    try? launch.run()
                    for _ in 0..<15 {
                        Thread.sleep(forTimeInterval: 0.1)
                        connected = try? LocalSocket.connect()
                        if connected != nil { break }
                    }
                }
            }
            guard let fd = connected else { throw UserError("Open the Firefox WireGuard app and try again.") }
            defer { Darwin.close(fd) }
            try Frames.write(data, fd: fd)
            guard let answer = try Frames.read(fd: fd) else { throw UserError("The companion app did not respond.") }
            response = answer
        } catch {
            response = try JSONEncoder().encode(ControlResponse(id: request.id, ok: false, error: "The companion app did not respond. Open it, check for a Keychain prompt, and retry."))
        }
        try Frames.write(response, fd: STDOUT_FILENO)
    } catch {
        // stdout is exclusively the native messaging transport. Do not print requests,
        // profile data, or system error descriptions to stderr either.
        break
    }
}
