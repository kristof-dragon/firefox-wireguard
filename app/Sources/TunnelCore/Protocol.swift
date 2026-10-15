import Foundation
import Darwin

public enum Integration {
    public static let extensionID = "firefox-wireguard@local.invalid"
    public static let hostName = "org.firefoxwireguard.bridge"
    public static let protocolVersion = 1
    public static let maxFrame = 65_536
    public static var socketPath: String { SecureFiles.support.appendingPathComponent("control.sock").path }
}

public struct ControlRequest: Codable {
    public let version: Int
    public let id: String
    public let command: String
    public let clientID: String
    public let profileID: String?
    public init(version: Int = 1, id: String, command: String, clientID: String, profileID: String? = nil) {
        self.version = version; self.id = id; self.command = command; self.clientID = clientID; self.profileID = profileID
    }
    public func validate() throws {
        guard version == Integration.protocolVersion, id.count <= 80,
              UUID(uuidString: clientID) != nil, ["status", "connect", "disconnect"].contains(command),
              profileID == nil || UUID(uuidString: profileID!) != nil else {
            throw UserError("Unsupported or invalid control request.")
        }
    }
}

public struct TunnelState: Codable {
    public var phase: String = "idle"
    public var profileID: String?
    public var proxyPort: UInt16?
    public var error: String?
    public var handshakeAge: Int?
    public var supportsIPv6 = false
    public init() {}
}

public struct ControlResponse: Codable {
    public var version = Integration.protocolVersion
    public var id: String
    public var ok: Bool
    public var profiles: [Profile]
    public var state: TunnelState
    public var error: String?
    public var busy = false
    public init(id: String, ok: Bool, profiles: [Profile] = [], state: TunnelState = TunnelState(), error: String? = nil, busy: Bool = false) {
        self.id = id; self.ok = ok; self.profiles = profiles; self.state = state; self.error = error; self.busy = busy
    }
}

public enum Frames {
    public static func encode(_ data: Data) throws -> Data {
        guard !data.isEmpty, data.count <= Integration.maxFrame else { throw UserError("Invalid message size.") }
        var size = UInt32(data.count).littleEndian
        var result = withUnsafeBytes(of: &size) { Data($0) }
        result.append(data); return result
    }
    public static func read(fd: Int32) throws -> Data? {
        guard let header = try exact(fd: fd, count: 4, allowEOF: true) else { return nil }
        let size = header.enumerated().reduce(UInt32(0)) { $0 | UInt32($1.element) << (8 * $1.offset) }
        guard size > 0, size <= Integration.maxFrame else { throw UserError("Invalid message size.") }
        return try exact(fd: fd, count: Int(size), allowEOF: false)
    }
    private static func exact(fd: Int32, count: Int, allowEOF: Bool) throws -> Data? {
        var data = Data(count: count), offset = 0
        while offset < count {
            let length = data.withUnsafeMutableBytes { Darwin.read(fd, $0.baseAddress!.advanced(by: offset), count - offset) }
            if length == 0 && offset == 0 && allowEOF { return nil }
            if length < 0 && errno == EINTR { continue }
            guard length > 0 else { throw UserError("The local connection ended unexpectedly.") }
            offset += length
        }
        return data
    }
    public static func write(_ data: Data, fd: Int32) throws {
        let frame = try encode(data)
        var offset = 0
        while offset < frame.count {
            let n = frame.withUnsafeBytes { Darwin.write(fd, $0.baseAddress!.advanced(by: offset), frame.count - offset) }
            if n < 0 && errno == EINTR { continue }
            guard n > 0 else { throw UserError("Unable to write to the local connection.") }
            offset += n
        }
    }
}

public enum LocalSocket {
    public static func address(_ path: String) throws -> sockaddr_un {
        var value = sockaddr_un(); value.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8CString)
        guard bytes.count <= MemoryLayout.size(ofValue: value.sun_path) else { throw UserError("The application storage path is too long for the local control socket.") }
        withUnsafeMutableBytes(of: &value.sun_path) { raw in
            bytes.withUnsafeBytes { raw.copyBytes(from: $0) }
        }
        value.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        return value
    }
    public static func configure(_ fd: Int32) {
        var timeout = timeval(tv_sec: 5, tv_usec: 0), yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &yes, socklen_t(MemoryLayout.size(ofValue: yes)))
        _ = fcntl(fd, F_SETFD, FD_CLOEXEC)
    }
    public static func sameUser(_ fd: Int32) -> Bool {
        var uid: uid_t = 0, gid: gid_t = 0
        return getpeereid(fd, &uid, &gid) == 0 && uid == getuid()
    }
    public static func connect(path: String = Integration.socketPath) throws -> Int32 {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw UserError("Unable to open the local control connection.") }
        configure(fd)
        do {
            var a = try address(path)
            let result = withUnsafePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
            guard result == 0, sameUser(fd) else { throw UserError("Open the Firefox WireGuard menu-bar app, then retry.") }
            return fd
        } catch { Darwin.close(fd); throw error }
    }
    public static func exchange(_ data: Data, path: String = Integration.socketPath) throws -> Data {
        let fd = try connect(path: path); defer { Darwin.close(fd) }
        try Frames.write(data, fd: fd)
        guard let response = try Frames.read(fd: fd) else { throw UserError("The companion app did not respond.") }
        return response
    }
}

public final class ControlServer {
    private let fd: Int32
    private let path: String
    public init(path: String = Integration.socketPath, handler: @escaping (ControlRequest) -> ControlResponse) throws {
        self.path = path
        try SecureFiles.directory(URL(fileURLWithPath: path).deletingLastPathComponent())
        if let live = try? LocalSocket.connect(path: path) { Darwin.close(live); throw UserError("Another copy of Firefox WireGuard is already running.") }
        if FileManager.default.fileExists(atPath: path) {
            let attributes = try FileManager.default.attributesOfItem(atPath: path)
            guard attributes[.type] as? FileAttributeType == .typeSocket else { throw UserError("Unexpected file at the local control socket path.") }
            try FileManager.default.removeItem(atPath: path)
        }
        fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw UserError("Unable to create local control socket.") }
        LocalSocket.configure(fd)
        var a = try LocalSocket.address(path)
        let bound = withUnsafePointer(to: &a) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
        guard bound == 0, chmod(path, 0o600) == 0, listen(fd, 8) == 0 else { Darwin.close(fd); throw UserError("Unable to start the local control server.") }
        let listener = fd
        DispatchQueue(label: "org.firefoxwireguard.control").async {
            while true {
                let client = accept(listener, nil, nil)
                if client < 0 { if errno == EINTR || errno == EAGAIN { continue }; break }
                LocalSocket.configure(client)
                defer { Darwin.close(client) }
                guard LocalSocket.sameUser(client) else { continue }
                do {
                    guard let data = try Frames.read(fd: client) else { continue }
                    let request = try JSONDecoder().decode(ControlRequest.self, from: data)
                    try request.validate()
                    let response = handler(request)
                    try Frames.write(JSONEncoder().encode(response), fd: client)
                } catch { /* Invalid local requests are closed without reflecting data. */ }
            }
        }
    }
    deinit { Darwin.close(fd); unlink(path) }
}
