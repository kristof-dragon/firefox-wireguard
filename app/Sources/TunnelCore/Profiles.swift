import Foundation
import Security

public struct Profile: Codable, Identifiable, Equatable {
    public let id: String
    public var name: String
    public init(id: String = UUID().uuidString, name: String) { self.id = id; self.name = name }
}

public protocol SecretVault {
    func read(_ id: String) throws -> String
    func write(_ value: String, id: String) throws
    func remove(_ id: String) throws
}

public struct KeychainVault: SecretVault {
    private let service: String
    public init(service: String = "org.firefoxwireguard.profiles") { self.service = service }
    private func query(_ id: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: id]
    }
    public func read(_ id: String) throws -> String {
        var q = query(id)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data, let text = String(data: data, encoding: .utf8) else {
            throw UserError("Unable to read this profile from Keychain. Unlock the login keychain and allow access, then try again.")
        }
        return text
    }
    public func write(_ value: String, id: String) throws {
        let data = Data(value.utf8), q = query(id)
        var status = SecItemUpdate(q as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = q
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            status = SecItemAdd(item as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw UserError("Unable to save the profile in Keychain. No configuration was saved to disk.") }
    }
    public func remove(_ id: String) throws {
        let result = SecItemDelete(query(id) as CFDictionary)
        guard result == errSecSuccess || result == errSecItemNotFound else { throw UserError("Unable to remove the profile from Keychain.") }
    }
}

public final class ProfileStore {
    public private(set) var profiles: [Profile]
    private let directory: URL
    private let vault: SecretVault
    public init(directory: URL, vault: SecretVault = KeychainVault()) throws {
        self.directory = directory; self.vault = vault
        try SecureFiles.directory(directory)
        let index = directory.appendingPathComponent("profiles.json")
        if FileManager.default.fileExists(atPath: index.path) {
            do { profiles = try JSONDecoder().decode([Profile].self, from: Data(contentsOf: index)) }
            catch { throw UserError("Profile list could not be read. Restore its backup before making changes.") }
            guard Set(profiles.map(\.id)).count == profiles.count, profiles.allSatisfy({ UUID(uuidString: $0.id) != nil }) else {
                throw UserError("Profile list is invalid; refusing to overwrite it.")
            }
        } else { profiles = [] }
    }
    public func configuration(_ id: String) throws -> TunnelConfiguration {
        guard profiles.contains(where: { $0.id == id }) else { throw UserError("Profile not found.") }
        return try TunnelConfiguration(vault.read(id))
    }
    @discardableResult public func save(id: String? = nil, name: String, configuration: String) throws -> Profile {
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, clean.count <= 80, !clean.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else {
            throw UserError("Use a profile name between 1 and 80 characters without control characters.")
        }
        let config = try TunnelConfiguration(configuration)
        if let id { guard profiles.contains(where: { $0.id == id }) else { throw UserError("Profile not found.") } }
        let profile = Profile(id: id ?? UUID().uuidString, name: clean)
        let previous = id == nil ? nil : try vault.read(profile.id)
        try vault.write(config.canonical, id: profile.id)
        var next = profiles.filter { $0.id != profile.id }; next.append(profile)
        next.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        do { try persist(next) } catch {
            if let previous { try? vault.write(previous, id: profile.id) } else { try? vault.remove(profile.id) }
            throw UserError("Could not save the profile list.")
        }
        profiles = next
        return profile
    }
    public func remove(_ id: String) throws {
        let next = profiles.filter { $0.id != id }
        // Remove the secret first: a failed metadata write leaves a recoverable
        // missing-key entry rather than an unlisted secret that cannot be deleted.
        try vault.remove(id)
        try persist(next); profiles = next
    }
    private func persist(_ profiles: [Profile]) throws {
        try SecureFiles.write(JSONEncoder().encode(profiles), to: directory.appendingPathComponent("profiles.json"))
    }
}

public enum SecureFiles {
    public static var support: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/FirefoxWireGuard", isDirectory: true)
    }
    public static func directory(_ url: URL) throws {
        let manager = FileManager.default
        if !manager.fileExists(atPath: url.path) {
            try manager.createDirectory(at: url, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        }
        let attributes = try manager.attributesOfItem(atPath: url.path)
        guard attributes[.type] as? FileAttributeType == .typeDirectory,
              (attributes[.ownerAccountID] as? NSNumber)?.uint32Value == getuid() else {
            throw UserError("Application storage must be a directory owned by the current user.")
        }
        try manager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: url.path)
    }
    public static func write(_ data: Data, to url: URL) throws {
        try data.write(to: url, options: [.atomic])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}
