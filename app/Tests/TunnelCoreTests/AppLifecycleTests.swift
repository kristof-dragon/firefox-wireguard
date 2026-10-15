import XCTest
@testable import TunnelCore
@testable import MenuBarApp

final class AppLifecycleTests: XCTestCase {
    private func fixture() throws -> (root: URL, directory: URL, manifest: URL, helper: URL) {
        let root = URL(fileURLWithPath: "/tmp/fwg-\(UUID().uuidString)")
        try SecureFiles.directory(root)
        let helper = root.appendingPathComponent("test-helper")
        try Data("fixture only".utf8).write(to: helper)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: helper.path)
        return (root, root.appendingPathComponent("data"), root.appendingPathComponent("host.json"), helper)
    }
    @MainActor func testSecondCopyCanRepairAndRecoverExistingProfilesAfterOwnerQuits() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        var owner: AppInstanceLock? = try AppInstanceLock(directory: f.directory)
        let profiles = [Profile(name: "Example profile")]
        let index = f.directory.appendingPathComponent("profiles.json")
        let bytes = try JSONEncoder().encode(profiles)
        try SecureFiles.write(bytes, to: index)
        let model = AppModel(directory: f.directory, manifestURL: f.manifest, helperURL: f.helper, vault: MemoryVault())
        defer { model.shutdown() }
        XCTAssertNotNil(owner); XCTAssertFalse(model.ready)
        XCTAssertTrue(model.error?.contains("Another copy") == true)
        model.installIntegration()
        XCTAssertNil(model.integrationError)
        XCTAssertTrue(NativeHostRegistration.matches(helper: f.helper, manifest: f.manifest))
        XCTAssertFalse(model.ready); XCTAssertNotNil(model.error)
        owner = nil
        model.retryStartup()
        XCTAssertTrue(model.ready); XCTAssertNil(model.error)
        XCTAssertEqual(model.profiles, profiles)
        XCTAssertEqual(try Data(contentsOf: index), bytes)
    }
    @MainActor func testFailedStartupReleasesOwnershipAndCanRetry() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        try SecureFiles.directory(f.directory)
        let index = f.directory.appendingPathComponent("profiles.json")
        try SecureFiles.write(Data("invalid".utf8), to: index)
        let model = AppModel(directory: f.directory, manifestURL: f.manifest, helperURL: f.helper, vault: MemoryVault())
        defer { model.shutdown() }
        XCTAssertFalse(model.ready)
        // A failed initializer must not leave a descriptor holding the lock.
        var ownership: AppInstanceLock? = try AppInstanceLock(directory: f.directory)
        XCTAssertNotNil(ownership); ownership = nil
        try SecureFiles.write(Data("[]".utf8), to: index)
        model.retryStartup()
        XCTAssertTrue(model.ready)
        XCTAssertFalse(FileManager.default.fileExists(atPath: f.manifest.path)) // First install remains explicit.
    }
    @MainActor func testReplacementRefreshesExistingRegistrationOnlyAfterAcquiringOwnership() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.root) }
        let previous = f.root.appendingPathComponent("previous-helper")
        try FileManager.default.copyItem(at: f.helper, to: previous)
        try NativeHostRegistration.install(helper: previous, manifest: f.manifest)
        var owner: AppInstanceLock? = try AppInstanceLock(directory: f.directory)
        let model = AppModel(directory: f.directory, manifestURL: f.manifest, helperURL: f.helper, vault: MemoryVault())
        defer { model.shutdown() }
        XCTAssertNotNil(owner)
        XCTAssertTrue(NativeHostRegistration.matches(helper: previous, manifest: f.manifest))
        owner = nil; model.retryStartup()
        XCTAssertTrue(model.ready)
        XCTAssertTrue(NativeHostRegistration.matches(helper: f.helper, manifest: f.manifest))
        XCTAssertFalse(NativeHostRegistration.matches(helper: previous, manifest: f.manifest))
    }
    func testStatusAndDisconnectNeverRelaunchAClosedApp() throws {
        for command in ["status", "disconnect"] {
            var launches = 0, attempts = 0
            XCTAssertThrowsError(try CompanionConnection.open(command: command, connect: {
                attempts += 1; throw UserError("No app")
            }, launch: { launches += 1 }, pause: { XCTFail("Read-only requests must not wait for launch") }))
            XCTAssertEqual(launches, 0); XCTAssertEqual(attempts, 1)
            XCTAssertEqual(try CompanionConnection.open(command: command, connect: { 42 }, launch: { XCTFail("Already running") }), 42)
        }
    }
    func testExplicitConnectLaunchesOnceAndBoundsConnectionRetries() throws {
        var launches = 0, attempts = 0, pauses = 0
        let fd = try CompanionConnection.open(command: "connect", connect: {
            attempts += 1
            if attempts < 3 { throw UserError("Starting") }
            return 42
        }, launch: { launches += 1 }, pause: { pauses += 1 })
        XCTAssertEqual(fd, 42); XCTAssertEqual(launches, 1)
        XCTAssertEqual(attempts, 3); XCTAssertEqual(pauses, 2)
        attempts = 0; launches = 0; pauses = 0
        XCTAssertThrowsError(try CompanionConnection.open(command: "connect", connect: {
            attempts += 1; throw UserError("Unavailable")
        }, launch: { launches += 1 }, pause: { pauses += 1 }))
        XCTAssertEqual(attempts, 16); XCTAssertEqual(launches, 1); XCTAssertEqual(pauses, 15)
    }
}
