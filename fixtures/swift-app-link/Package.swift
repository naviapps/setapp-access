// swift-tools-version: 6.3
import PackageDescription

let package = Package(
  name: "SetappAppLinkFixture",
  platforms: [.macOS(.v26)],
  dependencies: [.package(name: "setapp-access", path: "../sdk")],
  targets: [
    .executableTarget(
      name: "SetappLinkProbe",
      dependencies: [
        .product(name: "SetappAccessMacOS", package: "setapp-access")
      ])
  ]
)
