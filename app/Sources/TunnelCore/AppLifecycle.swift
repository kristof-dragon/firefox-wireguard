// SPDX-License-Identifier: MPL-2.0
import Foundation
import Darwin

/// Keep the ownership descriptor scoped to the instance that acquired it.
public final class AppInstanceLock {
    private let fd: Int32
    public init(directory: URL) throws {
        try SecureFiles.directory(directory)
        let descriptor = Darwin.open(directory.appendingPathComponent("app.lock").path,
                                     O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0o600)
        guard descriptor >= 0 else { throw UserError("Unable to open the application lock.") }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else {
            Darwin.close(descriptor)
            throw UserError("Another copy of Firefox WireGuard is running. Quit that copy, then choose Retry Startup.")
        }
        fd = descriptor
    }
    deinit { Darwin.close(fd) }
}

public enum NativeHostRegistration {
    public static var defaultURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Mozilla/NativeMessagingHosts/\(Integration.hostName).json")
    }
    public static func matches(helper: URL, manifest: URL) -> Bool {
        struct Entry: Decodable { let path: String }
        guard let data = try? Data(contentsOf: manifest), let entry = try? JSONDecoder().decode(Entry.self, from: data) else { return false }
        return URL(fileURLWithPath: entry.path).standardizedFileURL == helper.standardizedFileURL
    }
    public static func install(helper: URL, manifest: URL) throws {
        guard FileManager.default.isExecutableFile(atPath: helper.path) else { throw UserError("Use the packaged app to install Firefox integration.") }
        try FileManager.default.createDirectory(at: manifest.deletingLastPathComponent(), withIntermediateDirectories: true)
        let entry: [String: Any] = ["name": Integration.hostName, "description": "Firefox WireGuard companion",
                                  "path": helper.path, "type": "stdio", "allowed_extensions": [Integration.extensionID]]
        try SecureFiles.write(JSONSerialization.data(withJSONObject: entry, options: [.prettyPrinted, .sortedKeys]), to: manifest)
    }
}

public enum CompanionConnection {
    public static func open(command: String, connect: () throws -> Int32, launch: () throws -> Void,
                            pause: () -> Void = { Thread.sleep(forTimeInterval: 0.1) }) throws -> Int32 {
        if let fd = try? connect() { return fd }
        // Background polling and Disconnect must respect an intentional app Quit.
        // Only an explicit Connect may launch the registered companion.
        guard command == "connect" else { throw UserError("Open the Firefox WireGuard app to load profiles.") }
        try launch()
        for _ in 0..<15 {
            pause()
            if let fd = try? connect() { return fd }
        }
        throw UserError("Open the Firefox WireGuard app and try again.")
    }
}
