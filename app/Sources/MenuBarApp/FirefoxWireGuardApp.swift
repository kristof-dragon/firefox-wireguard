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
            ProfileWindow(model: model)
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
            Divider()
            Button("Manage Profiles…") { openWindow(id: "profiles"); NSApp.activate(ignoringOtherApps: true) }
            Button(model.integrationInstalled ? "Repair Firefox Integration" : "Install Firefox Integration") { model.installIntegration() }
                .help("Registers this app's helper with Firefox. Install the extension separately. Repeat after moving the app.")
                .disabled(!model.ready)
            if tunnel.state.profileID != nil {
                Button("Stop Tunnel") { model.tunnel.stop(reason: "Tunnel stopped in the app. Reconnect or disconnect from Firefox.") }
                    .help("Stops the connection. Firefox stays blocked until you reconnect or explicitly disconnect in the extension.")
            }
            Divider()
            Text("\(model.profiles.count) configured profile\(model.profiles.count == 1 ? "" : "s")").font(.caption).foregroundStyle(.secondary)
            Button("Quit") { model.shutdown(); NSApp.terminate(nil) }
        }.padding(16).frame(width: 300)
    }
    var status: String {
        switch tunnel.state.phase {
        case "connected": return "Tunnel ready"
        case "connecting": return "Waiting for handshake…"
        case "blocked": return "Connection unavailable"
        default: return "Ready for Firefox"
        }
    }
}

struct ProfileWindow: View {
    @ObservedObject var model: AppModel
    @State private var selected: String?
    @State private var name = ""
    @State private var configuration = ""
    @State private var editingID: String?
    @State private var confirmDelete = false
    var body: some View {
        HSplitView {
            VStack(alignment: .leading) {
                Text("Profiles").font(.title2.bold()).padding(.horizontal)
                List(model.profiles, selection: $selected) { profile in
                    Label(profile.name, systemImage: "network").tag(profile.id)
                }.onChange(of: selected) { value in
                    guard let profile = model.profiles.first(where: { $0.id == value }), let text = model.text(for: profile) else { return }
                    editingID = profile.id; name = profile.name; configuration = text
                }
                HStack {
                    Button { clear() } label: { Image(systemName: "plus") }.help("Add a profile")
                    Button { confirmDelete = true } label: { Image(systemName: "minus") }.disabled(editingID == nil).help("Remove selected profile")
                    Spacer()
                    Button("Import…", action: importFile)
                }.padding()
            }.frame(minWidth: 200, idealWidth: 230)
            VStack(alignment: .leading, spacing: 12) {
                Text(editingID == nil ? "New Profile" : "Edit Profile").font(.title2.bold())
                TextField("Profile name", text: $name)
                Text("WireGuard configuration").font(.headline)
                TextEditor(text: $configuration).font(.system(.body, design: .monospaced))
                    .border(Color.secondary.opacity(0.3)).accessibilityLabel("WireGuard configuration")
                    .help("Paste a single-peer, full-tunnel configuration. DNS IPs are required. Keys and configuration are stored in Keychain; editing reveals them here.")
                if let error = model.error { Text(error).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
                HStack {
                    Image(systemName: "key.fill").foregroundStyle(.secondary)
                    Text("Stored in macOS Keychain").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("Save Profile") {
                        if model.save(id: editingID, name: name, text: configuration) { clear() }
                    }.keyboardShortcut("s", modifiers: .command).disabled(!model.ready || configuration.isEmpty || name.isEmpty)
                }
            }.padding(20).frame(minWidth: 420)
        }.padding(.vertical, 16)
            .confirmationDialog("Remove this profile and its Keychain configuration?", isPresented: $confirmDelete) {
                Button("Remove Profile", role: .destructive) {
                    if let profile = model.profiles.first(where: { $0.id == editingID }) { model.remove(profile); if model.error == nil { clear() } }
                }
            }
    }
    private func clear() { selected = nil; editingID = nil; name = ""; configuration = "" }
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
            clear(); configuration = text; name = url.deletingPathExtension().lastPathComponent; model.error = nil
        } catch { model.error = (error as? UserError)?.message ?? "Could not read this configuration file." }
    }
}
