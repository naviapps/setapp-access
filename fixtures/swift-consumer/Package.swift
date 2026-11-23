// swift-tools-version: 6.4
import PackageDescription

let package = Package(
  name: "SetappStandaloneConsumer",
  platforms: [.macOS(.v26)],
  products: [
    .library(name: "SetappMacOSCompileOnly", targets: ["SetappMacOSCompileOnly"])
  ],
  dependencies: [.package(name: "setapp-access", path: "../sdk")],
  targets: [
    .executableTarget(
      name: "SetappSnapshotConsumer",
      dependencies: [
        .product(name: "SetappAccess", package: "setapp-access")
      ]),
    // An automatic library compiles the adapter without linking a vendor executable.
    .target(
      name: "SetappMacOSCompileOnly",
      dependencies: [
        .product(name: "SetappAccessMacOS", package: "setapp-access")
      ]),
  ]
)
