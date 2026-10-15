import Foundation
import TunnelCore

/// Unsaved configuration stays in memory. Navigation must be resolved before
/// replacing it; a failed save never discards the draft or changes selection.
@MainActor final class ProfileEditor: ObservableObject {
    struct Draft: Equatable {
        var id: String?
        var name = ""
        var configuration = ""
    }
    enum Destination {
        case new
        case profile(Profile, String)
        case imported(name: String, configuration: String)
    }
    @Published var draft = Draft()
    @Published private(set) var pending: Destination?
    private var saved = Draft()

    var isDirty: Bool { draft != saved }

    /// True means navigation completed; false means the UI must ask first.
    @discardableResult func request(_ destination: Destination) -> Bool {
        if isDirty { pending = destination; return false }
        apply(destination)
        return true
    }
    func cancel() { pending = nil }
    func discard() {
        guard let destination = pending else { return }
        apply(destination)
    }
    @discardableResult func save(using persist: (Draft) -> Profile?) -> Bool {
        guard let profile = persist(draft) else { pending = nil; return false }
        draft.id = profile.id; draft.name = profile.name
        saved = draft
        if let destination = pending { apply(destination) }
        return true
    }
    func resetAfterDeletion() { apply(.new) }

    private func apply(_ destination: Destination) {
        pending = nil
        switch destination {
        case .new:
            draft = Draft(); saved = draft
        case let .profile(profile, text):
            draft = Draft(id: profile.id, name: profile.name, configuration: text)
            saved = draft
        case let .imported(name, configuration):
            // An imported file is a new, unsaved profile even before typing.
            draft = Draft(name: name, configuration: configuration)
            saved = Draft()
        }
    }
}
