import AppKit
import Foundation
import TunnelCore

@MainActor final class AppModel: ObservableObject {
    @Published var profiles: [Profile] = []
    @Published var error: String?
    @Published var integrationInstalled = false
    let tunnel = TunnelManager()
    private var store: ProfileStore?
    private var server: ControlServer?
    private var lockFD: Int32 = -1

    init() {
        do {
            try SecureFiles.directory(SecureFiles.support)
            let path = SecureFiles.support.appendingPathComponent("app.lock").path
            lockFD = Darwin.open(path, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0o600)
            guard lockFD >= 0, flock(lockFD, LOCK_EX | LOCK_NB) == 0 else {
                throw UserError("Another copy of Firefox WireGuard is already running.")
            }
            store = try ProfileStore(directory: SecureFiles.support)
            profiles = store!.profiles
            server = try ControlServer { [weak self] request in
                DispatchQueue.main.sync {
                    self?.handle(request) ?? ControlResponse(id: request.id, ok: false, error: "Companion app is closing.")
                }
            }
            integrationInstalled = FileManager.default.fileExists(atPath: manifestURL.path)
        } catch { self.error = (error as? UserError)?.message ?? "Unable to initialise private application storage." }
    }
    var ready: Bool { store != nil && server != nil }
    private var manifestURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Mozilla/NativeMessagingHosts/\(Integration.hostName).json")
    }
    func installIntegration() {
        do {
            let helper = Bundle.main.executableURL!.deletingLastPathComponent().appendingPathComponent("firefox-wireguard-bridge")
            guard FileManager.default.isExecutableFile(atPath: helper.path) else { throw UserError("Use the packaged app to install Firefox integration.") }
            try FileManager.default.createDirectory(at: manifestURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            let manifest: [String: Any] = ["name": Integration.hostName, "description": "Firefox WireGuard companion", "path": helper.path, "type": "stdio", "allowed_extensions": [Integration.extensionID]]
            try SecureFiles.write(JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys]), to: manifestURL)
            integrationInstalled = true; error = nil
        } catch { self.error = (error as? UserError)?.message ?? "Could not install Firefox integration." }
    }
    func text(for profile: Profile) -> String? {
        do { return try store?.configuration(profile.id).canonical }
        catch { self.error = (error as? UserError)?.message ?? "Could not read the profile."; return nil }
    }
    func save(id: String?, name: String, text: String) -> Bool {
        guard let store, ready else { return false }
        do {
            guard tunnel.state.profileID != id || id == nil else { throw UserError("Disconnect this profile in Firefox before editing it.") }
            try store.save(id: id, name: name, configuration: text)
            profiles = store.profiles; error = nil; return true
        } catch { self.error = (error as? UserError)?.message ?? "Could not save the profile."; return false }
    }
    func remove(_ profile: Profile) {
        guard let store else { return }
        do {
            guard tunnel.state.profileID != profile.id else { throw UserError("Disconnect this profile in Firefox before removing it.") }
            try store.remove(profile.id); profiles = store.profiles; error = nil
        } catch { self.error = (error as? UserError)?.message ?? "Could not remove the profile." }
    }
    private func handle(_ request: ControlRequest) -> ControlResponse {
        guard let store else { return ControlResponse(id: request.id, ok: false, error: "The companion app is unavailable. Check its menu-bar status.") }
        do {
            try request.validate()
            if request.command != "status" && !tunnel.owns(request.clientID) {
                throw UserError("Another Firefox profile owns the tunnel. Disconnect it first.")
            }
            switch request.command {
            case "connect":
                guard let id = request.profileID, let profile = profiles.first(where: { $0.id == id }) else { throw UserError("Choose an existing profile.") }
                try tunnel.connect(profile: profile, configuration: store.configuration(id), client: request.clientID)
            case "disconnect": tunnel.stop(reason: nil)
            default: tunnel.renew(request.clientID)
            }
            let busy = !tunnel.owns(request.clientID)
            return ControlResponse(id: request.id, ok: true, profiles: profiles, state: busy ? TunnelState() : tunnel.state, busy: busy)
        } catch {
            return ControlResponse(id: request.id, ok: false, profiles: profiles, error: (error as? UserError)?.message ?? "The requested operation could not be completed.")
        }
    }
    func shutdown() { tunnel.stop(reason: "Companion app stopped. Firefox remains blocked until you disconnect.") }
}
