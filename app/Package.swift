// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "FirefoxWireGuard",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "FirefoxWireGuard", targets: ["MenuBarApp"]),
        .executable(name: "firefox-wireguard-bridge", targets: ["NativeBridge"])
    ],
    targets: [
        .target(name: "TunnelCore"),
        .executableTarget(name: "MenuBarApp", dependencies: ["TunnelCore"]),
        .executableTarget(name: "NativeBridge", dependencies: ["TunnelCore"]),
        .testTarget(name: "TunnelCoreTests", dependencies: ["TunnelCore", "MenuBarApp"])
    ]
)
