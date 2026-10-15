// SPDX-License-Identifier: MPL-2.0
import XCTest
@testable import MenuBarApp
import TunnelCore

final class ProfileEditorTests: XCTestCase {
    @MainActor func testNewProfileRequiresDecisionAndCancelPreservesDraft() async {
        let editor = ProfileEditor()
        editor.draft.name = "Unsaved profile"
        editor.draft.configuration = "Unsaved configuration fixture"
        let before = editor.draft
        XCTAssertFalse(editor.request(.new))
        XCTAssertEqual(editor.draft, before)
        editor.cancel()
        XCTAssertNil(editor.pending)
        XCTAssertEqual(editor.draft, before)
        XCTAssertTrue(editor.isDirty)
    }

    @MainActor func testFailedSavePreservesDraftAndDoesNotNavigate() async {
        let editor = ProfileEditor()
        editor.draft.name = "Incomplete profile"
        let before = editor.draft
        XCTAssertFalse(editor.request(.imported(name: "Imported", configuration: "Imported fixture")))
        XCTAssertFalse(editor.save { _ in nil })
        XCTAssertEqual(editor.draft, before)
        XCTAssertNil(editor.pending)
        XCTAssertTrue(editor.isDirty)
        XCTAssertFalse(editor.request(.new))
    }

    @MainActor func testSaveBeforeNewPersistsCurrentDraftThenClears() async {
        let editor = ProfileEditor()
        editor.draft.name = "New profile"
        editor.draft.configuration = "Configuration fixture"
        let before = editor.draft
        XCTAssertFalse(editor.request(.new))
        var saved: ProfileEditor.Draft?
        XCTAssertTrue(editor.save { draft in
            saved = draft
            return Profile(name: draft.name)
        })
        XCTAssertEqual(saved, before)
        XCTAssertEqual(editor.draft, ProfileEditor.Draft())
        XCTAssertFalse(editor.isDirty)
    }

    @MainActor func testProfileSwitchKeepsSelectionUntilSaveSucceeds() async {
        let editor = ProfileEditor(), first = Profile(name: "First"), second = Profile(name: "Second")
        XCTAssertTrue(editor.request(.profile(first, "Original fixture")))
        editor.draft.configuration = "Edited fixture"
        XCTAssertFalse(editor.request(.profile(second, "Second fixture")))
        XCTAssertEqual(editor.draft.id, first.id)
        XCTAssertTrue(editor.save { draft in
            XCTAssertEqual(draft.id, first.id)
            XCTAssertEqual(draft.configuration, "Edited fixture")
            return first
        })
        XCTAssertEqual(editor.draft.id, second.id)
        XCTAssertEqual(editor.draft.configuration, "Second fixture")
        XCTAssertFalse(editor.isDirty)
    }

    @MainActor func testImportIsUnsavedAndDiscardIsExplicit() async {
        let editor = ProfileEditor()
        XCTAssertTrue(editor.request(.imported(name: "Imported", configuration: "Imported fixture")))
        XCTAssertTrue(editor.isDirty)
        XCTAssertFalse(editor.request(.new))
        XCTAssertEqual(editor.draft.configuration, "Imported fixture")
        editor.discard()
        XCTAssertEqual(editor.draft, ProfileEditor.Draft())
        XCTAssertFalse(editor.isDirty)
    }

    @MainActor func testSaveKeepsProfileSelectedAndRevertedEditsNeedNoPrompt() async {
        let editor = ProfileEditor(), profile = Profile(name: "Saved")
        editor.draft.name = "Saved"
        editor.draft.configuration = "Configuration fixture"
        XCTAssertTrue(editor.save { _ in profile })
        XCTAssertEqual(editor.draft.id, profile.id)
        XCTAssertEqual(editor.draft.configuration, "Configuration fixture")
        XCTAssertFalse(editor.isDirty)
        editor.draft.name = "Changed"
        XCTAssertTrue(editor.isDirty)
        editor.draft.name = "Saved"
        XCTAssertFalse(editor.isDirty)
        XCTAssertTrue(editor.request(.new))
        XCTAssertNil(editor.pending)
    }
}
