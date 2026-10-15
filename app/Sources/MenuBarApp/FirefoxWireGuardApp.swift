// SPDX-License-Identifier: MPL-2.0
import SwiftUI
import AppKit
import UniformTypeIdentifiers
import TunnelCore

final class AppDelegate: NSObject, NSApplicationDelegate {
    var onQuit: (() -> Void)?
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
    }
    func applicationWillTerminate(_ notification: Notification) { onQuit?() }
}

@main struct FirefoxWireGuardApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var model = AppModel()
    var body: some Scene {
        MenuBarExtra("Firefox WireGuard", systemImage: "shield.lefthalf.filled") {
            MenuPanel(model: model, tunnel: model.tunnel)
                .onAppear { delegate.onQuit = { model.shutdown() } }
        }.menuBarExtraStyle(.window)
        Window("WireGuard Profiles", id: "profiles") {
            ProfileWindow(model: model, editor: model.editor)
                .frame(minWidth: 660, minHeight: 500)
                .onAppear { delegate.onQuit = { model.shutdown() } }
        }.defaultSize(width: 760, height: 580)
    }
}

struct MenuPanel: View {
    @ObservedObject var model: AppModel
    @ObservedObject var tunnel: TunnelManager
    @Environment(\.openWindow) var openWindow
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Firefox WireGuard", systemImage: "shield.lefthalf.filled").font(.headline)
            Label(status, systemImage: tunnel.state.phase == "connected" ? "checkmark.circle.fill" : "circle.dotted")
                .foregroundStyle(tunnel.state.phase == "connected" ? .green : .secondary)
            if let id = tunnel.state.profileID, let profile = model.profiles.first(where: { $0.id == id }) {
                Text(profile.name).font(.subheadline)
            }
            if let error = model.error ?? tunnel.state.error { Text(error).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            if let error = model.integrationError { Text(error).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            if !model.ready { Button("Retry Startup") { model.retryStartup() } }
            if let details = tunnel.state.details {
                ConnectionPanel(details: details, connected: tunnel.state.phase == "connected")
            }
            Divider()
            Button("Manage Profiles…") { openWindow(id: "profiles"); NSApp.activate(ignoringOtherApps: true) }
                .disabled(!model.ready)
            Button(model.integrationInstalled ? "Repair Firefox Integration" : "Install Firefox Integration") { model.installIntegration() }
                .help("Registers this copy's helper with Firefox, even if another copy is running. Reload the extension after repairing an older version's registration.")
            if tunnel.state.profileID != nil {
                Button("Stop Tunnel") { model.tunnel.stop(reason: "Tunnel stopped in the app. Reconnect or disconnect from Firefox.") }
                    .help("Stops the connection. Firefox blocks covered requests if its kill switch is on, or returns to normal browsing if it is off.")
            }
            Divider()
            if model.ready { Text("\(model.profiles.count) configured profile\(model.profiles.count == 1 ? "" : "s")").font(.caption).foregroundStyle(.secondary) }
            if let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String {
                Text("Version \(version)").font(.caption).foregroundStyle(.secondary)
            }
            Button("Quit") { model.shutdown(); NSApp.terminate(nil) }
        }.padding(16).frame(width: 350)
    }
    var status: String {
        guard model.ready else { return "Startup needs attention" }
        switch tunnel.state.phase {
        case "connected": return "Tunnel ready"
        case "connecting": return "Waiting for handshake…"
        case "blocked": return "Connection unavailable"
        default: return model.profiles.isEmpty ? "Add a WireGuard profile" : "Ready for Firefox"
        }
    }
}

struct ConnectionPanel: View {
    let details: ConnectionDetails
    let connected: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            row("Public IP", value: publicIP)
                .help("Exit address checked through this tunnel using ipwho.is at connection and every five minutes. Country is approximate geolocation. The service sees your exit IP; no keys or profile details are sent.")
            HStack {
                row("↓ Downloaded", value: ConnectionDetails.byteLabel(details.statsUpdatedAt == nil ? nil : details.downloadedBytes))
                Spacer(minLength: 12)
                row("↑ Uploaded", value: ConnectionDetails.byteLabel(details.statsUpdatedAt == nil ? nil : details.uploadedBytes))
            }.help("WireGuard totals for this connection, including the exit-IP check and other tunnel traffic. Reset on reconnect; excludes localhost bypass traffic.")
            row("Tunnel DNS", value: details.dnsServers.joined(separator: ", "))
                .help("DNS servers configured for the active tunnel. This is not a DNS leak test or a measurement of Firefox DNS-over-HTTPS.")
            row("WireGuard IP", value: details.clientIPs.joined(separator: ", "))
                .help("Client addresses inside this WireGuard tunnel.")
        }.font(.caption)
    }
    private var publicIP: String {
        guard connected else { return "—" }
        if details.exitStatus == "ready", let ip = details.publicIP { return "\(details.countryFlag) \(ip)" }
        return details.exitStatus == "unavailable" ? "Unavailable" : "Checking…"
    }
    private func row(_ title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).foregroundStyle(.secondary)
            Text(value.isEmpty ? "—" : value).monospacedDigit().textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct ProfileWindow: View {
    @ObservedObject var model: AppModel
    @ObservedObject var editor: ProfileEditor
    @State private var confirmDelete = false
    @State private var confirmNavigation = false
    var body: some View {
        HSplitView {
            VStack(alignment: .leading) {
                Text("Profiles").font(.title2.bold()).padding(.horizontal)
                List(model.profiles, selection: Binding(get: { editor.draft.id }, set: selectProfile)) { profile in
                    Label(profile.name, systemImage: "network").tag(profile.id)
                }
                HStack {
                    Button { navigate(.new) } label: { Image(systemName: "plus") }.help("Start a new profile. You will be asked to save or discard unsaved changes.")
                    Button { confirmDelete = true } label: { Image(systemName: "minus") }.disabled(editor.draft.id == nil).help("Remove selected profile")
                    Spacer()
                    Button("Import…", action: importFile)
                }.padding()
            }.frame(minWidth: 200, idealWidth: 230)
            VStack(alignment: .leading, spacing: 12) {
                Text(editor.draft.id == nil ? "New Profile" : "Edit Profile").font(.title2.bold())
                TextField("Profile name", text: $editor.draft.name)
                Text("WireGuard configuration").font(.headline)
                TextEditor(text: $editor.draft.configuration).font(.system(.body, design: .monospaced))
                    .border(Color.secondary.opacity(0.3)).accessibilityLabel("WireGuard configuration")
                    .help("Paste a single-peer, full-tunnel configuration. DNS IPs are required. Keys and configuration are stored in Keychain; editing reveals them here.")
                if let error = model.profileError ?? (model.ready ? nil : model.error) { Text(error).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
                HStack {
                    Image(systemName: "key.fill").foregroundStyle(.secondary)
                    Text(editor.isDirty ? "Unsaved changes" : editor.draft.id == nil ? "Save to macOS Keychain" : "Stored in macOS Keychain").font(.caption).foregroundStyle(.secondary)
                        .help("Save Profile stores the configuration in macOS Keychain. Unsaved text stays in memory until the app quits.")
                    Spacer()
                    Button("Save Profile") {
                        editor.save(using: persist)
                    }.keyboardShortcut("s", modifiers: .command).disabled(!model.ready || editor.draft.configuration.isEmpty || editor.draft.name.isEmpty)
                }
            }.padding(20).frame(minWidth: 420)
        }.padding(.vertical, 16)
            .onDisappear { editor.cancel(); confirmNavigation = false }
            .onChange(of: editor.draft.name) { _ in model.profileError = nil }
            .onChange(of: editor.draft.configuration) { _ in model.profileError = nil }
            .alert("Save changes to this profile?", isPresented: $confirmNavigation) {
                Button("Save") { editor.save(using: persist) }.keyboardShortcut(.defaultAction)
                Button("Discard Changes", role: .destructive) { editor.discard(); model.profileError = nil }
                Button("Cancel", role: .cancel) { editor.cancel() }
            } message: {
                Text("Save this profile before continuing, discard the changes, or cancel to keep editing.")
            }
            .confirmationDialog("Remove this profile, its Keychain configuration, and any unsaved changes?", isPresented: $confirmDelete) {
                Button("Remove Profile", role: .destructive) {
                    if let profile = model.profiles.first(where: { $0.id == editor.draft.id }) {
                        model.remove(profile)
                        if model.profileError == nil { editor.resetAfterDeletion() }
                    }
                }
            }
    }
    private func persist(_ draft: ProfileEditor.Draft) -> Profile? {
        model.save(id: draft.id, name: draft.name, text: draft.configuration)
    }
    private func navigate(_ destination: ProfileEditor.Destination) {
        if editor.request(destination) { model.profileError = nil }
        else { confirmNavigation = true }
    }
    private func selectProfile(_ id: String?) {
        guard let id, id != editor.draft.id,
              let profile = model.profiles.first(where: { $0.id == id }),
              let text = model.text(for: profile) else { return }
        navigate(.profile(profile, text))
    }
    private func importFile() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText, UTType(filenameExtension: "conf") ?? .data]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
            guard size <= 32_768 else { throw UserError("Configuration exceeds the supported size.") }
            let text = try String(contentsOf: url, encoding: .utf8)
            _ = try TunnelConfiguration(text)
            navigate(.imported(name: url.deletingPathExtension().lastPathComponent, configuration: text))
        } catch { model.profileError = (error as? UserError)?.message ?? "Could not read this configuration file." }
    }
}
