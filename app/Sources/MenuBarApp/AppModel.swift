// SPDX-License-Identifier: MPL-2.0
import AppKit
import Foundation
import TunnelCore

@MainActor final class AppModel: ObservableObject {
    @Published var profiles: [Profile] = []
    @Published var error: String?
    @Published var profileError: String?
    @Published var integrationInstalled = false
    @Published var integrationError: String?
    @Published private(set) var ready = false
    let tunnel = TunnelManager()
    let editor = ProfileEditor()
    private var store: ProfileStore?
    private var server: ControlServer?
    private var appLock: AppInstanceLock?
    private let directory: URL
    private let manifestURL: URL
    private let helperURL: URL
    private let vault: SecretVault

    init(directory: URL = SecureFiles.support, manifestURL: URL = NativeHostRegistration.defaultURL,
         helperURL: URL? = nil, vault: SecretVault = KeychainVault()) {
        self.directory = directory; self.manifestURL = manifestURL; self.vault = vault
        self.helperURL = helperURL ?? Bundle.main.executableURL!.deletingLastPathComponent().appendingPathComponent("firefox-wireguard-bridge")
        integrationInstalled = FileManager.default.fileExists(atPath: manifestURL.path)
        retryStartup()
    }
    func retryStartup() {
        guard !ready else { return }
        do {
            let ownership = try AppInstanceLock(directory: directory)
            let loadedStore = try ProfileStore(directory: directory, vault: vault)
            let control = try ControlServer(path: directory.appendingPathComponent("control.sock").path) { [weak self] request in
                DispatchQueue.main.sync {
                    self?.handle(request) ?? ControlResponse(id: request.id, ok: false, error: "Companion app is closing.")
                }
            }
            appLock = ownership; store = loadedStore; server = control
            profiles = loadedStore.profiles; ready = true; error = nil
            integrationInstalled = FileManager.default.fileExists(atPath: manifestURL.path)
            // An explicitly opened replacement app refreshes an existing
            // registration after obtaining ownership. First install stays explicit.
            if integrationInstalled && !NativeHostRegistration.matches(helper: helperURL, manifest: manifestURL) {
                installIntegration()
            }
        } catch { self.error = (error as? UserError)?.message ?? "Unable to initialise private application storage." }
    }
    func installIntegration() {
        do {
            try NativeHostRegistration.install(helper: helperURL, manifest: manifestURL)
            integrationInstalled = true; integrationError = nil
        } catch { integrationError = (error as? UserError)?.message ?? "Could not install Firefox integration." }
    }
    func text(for profile: Profile) -> String? {
        do { return try store?.configuration(profile.id).canonical }
        catch { profileError = (error as? UserError)?.message ?? "Could not read the profile."; return nil }
    }
    func save(id: String?, name: String, text: String) -> Profile? {
        guard let store, ready else { profileError = "Profile storage is unavailable. Check the app's menu-bar status."; return nil }
        do {
            guard tunnel.state.profileID != id || id == nil else { throw UserError("Disconnect this profile in Firefox before editing it.") }
            let profile = try store.save(id: id, name: name, configuration: text)
            profiles = store.profiles; profileError = nil; return profile
        } catch { profileError = (error as? UserError)?.message ?? "Could not save the profile."; return nil }
    }
    func remove(_ profile: Profile) {
        guard let store else { return }
        do {
            guard tunnel.state.profileID != profile.id else { throw UserError("Disconnect this profile in Firefox before removing it.") }
            try store.remove(profile.id); profiles = store.profiles; profileError = nil
        } catch { profileError = (error as? UserError)?.message ?? "Could not remove the profile." }
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
    func shutdown() {
        tunnel.stop(reason: "Companion app stopped.")
        ready = false; server = nil; store = nil; appLock = nil
    }
}
