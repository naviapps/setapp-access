// swift-tools-version: 6.3
import PackageDescription

let package = Package(
  name: "SetappAccess",
  platforms: [.macOS(.v26)],
  products: [
    .library(name: "SetappAccess", targets: ["SetappAccess"]),
    .library(name: "SetappAccessMacOS", targets: ["SetappAccessMacOS"]),
  ],
  dependencies: [
    .package(url: "https://github.com/MacPaw/Setapp-framework.git", exact: "5.5.5")
  ],
  targets: [
    .target(name: "SetappAccess"),
    .target(
      name: "SetappAccessMacOS",
      dependencies: [
        "SetappAccess",
        .product(name: "Setapp", package: "Setapp-framework"),
      ]),
    .testTarget(
      name: "SetappAccessTests", dependencies: ["SetappAccess"]),
  ]
)
