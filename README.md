# SetappAccess

Setapp access snapshots and observation for macOS 26 and Swift 6.3 or newer.

- `SetappAccess` provides the vendor-free Swift snapshot contract for host code and tests.
- `SetappAccessMacOS` adds the main-actor `SetappSession` using the official
  [MacPaw Setapp framework](https://github.com/MacPaw/Setapp-framework), pinned to 5.5.5.
  Link this product in the Setapp app build only.

## Access contract

`SetappAccessSnapshot` projects the vendor's optional subscription into
`SetappAccessStatus`:

| Vendor subscription | Snapshot status |
| ------------------- | --------------- |
| Unavailable (`nil`) | `.unavailable`  |
| `isActive == true`  | `.active`       |
| `isActive == false` | `.inactive`     |

`expirationDate` is optional display metadata and is absent when the subscription
is unavailable. Setapp's current status is the authority for access. The host
uses that status to decide which features to enable and reads it again at each
access decision. Snapshots are transient values and do not grant offline access.

## Installation

Pin the repository to a published full commit in the host's `Package.swift` and
select the vendor-free product for snapshot-only use:

```swift
dependencies: [
  .package(
    url: "https://github.com/naviapps/setapp-access.git",
    revision: "<full-40-character-commit>")
],
targets: [
  .target(
    name: "MyHost",
    dependencies: [
      .product(name: "SetappAccess", package: "setapp-access")
    ])
]
```

SwiftPM resolves the official framework even for the vendor-free product, so a fresh
resolution needs access to its repository. Setapp apps can select `SetappAccessMacOS`
and follow the [app integration](#app-integration) linking instructions.

For SwiftPM command-line builds that link `SetappAccessMacOS` with Swift 6.3,
pass `--build-system swiftbuild` to `swift build` or `swift test` so SwiftPM
can load the vendor XCFramework's Swift module. Xcode uses Swift Build.

## Snapshot-only use

The vendor-free value can be constructed in host tests without importing Setapp:

```swift
import SetappAccess

let available = SetappAccessSnapshot(subscriptionIsActive: true)
precondition(available.status == .active)
let unavailable = SetappAccessSnapshot(subscriptionIsActive: nil)
precondition(unavailable.status == .unavailable)
```

## App integration

```swift
import SetappAccess
import SetappAccessMacOS

@MainActor
func observeSetapp() async {
  let session = SetappSession()

  await session.observeUpdates { snapshot in
    switch snapshot.status {
    case .active:
      // Project the host's paid plan, with optional expirationDate for display.
      break
    case .inactive, .unavailable:
      // Clear the host's current paid access without changing the vendor account.
      break
    }
  }
}
```

`session.snapshot` reads the current subscription synchronously. Both observation APIs
install the observer before the initial read and refresh on the main actor. Pending
notifications share one read, and each stream buffers only its latest snapshot. Re-read
`session.snapshot` when a buffered update could predate revocation.

Use `observeUpdates(_:)` for suspending handlers. Cancelling its task removes
the observer even while a handler is suspended; the handler cooperates with
cancellation. With `updates()`, cancellation while waiting for the next value or
releasing an unconsumed stream removes the observer. Check cancellation before
acting on a buffered value. Cancellation during startup suppresses the initial
delivery in both APIs.

The Setapp Launch Agent controls macOS app launch. The vendor's
[subscription monitoring guide](https://docs.setapp.com/docs/monitor-subscription-status)
describes iOS behavior. If your macOS app gates features on subscription values,
verify the initial read and status changes in the signed app against its actual
Setapp configuration before release.

Call `reportUserInteraction()` explicitly for meaningful user activity according
to the host's usage policy. Call the official framework for vendor release notes.

The official macOS framework initializes before `main`. The host must provide
Setapp's key/configuration/resources and the official force-load linker setting:
`-force_load "$(BUILT_PRODUCTS_DIR)/libSetapp.a"` (adjust the archive path for the
host's build layout). Command-line SwiftPM stages `libSetapp.a` in its build
products; force-load that same archive. For direct archive linking, use
`Setapp.xcframework/macos-arm64_x86_64/libSetapp.a`. This SDK supplies
no host-specific linker flags. Bundle the unmodified [official Setapp license](Notices/Setapp.txt),
including in binary-only distributions.

## Development

Use Xcode 27 or later for the full maintainer checks. From the
repository root, review `mise.toml`, trust only that configuration and install its
declared tools:

```sh
mise trust mise.toml
mise install
mise exec -- make check
```

Run focused targets with `mise exec -- make <target>`:

| Target                    | Check                                                        |
| ------------------------- | ------------------------------------------------------------ |
| `test`                    | Snapshot and observation behavior in the vendor-free product |
| `test-consumer`           | Run the external snapshot consumer and compile the macOS API |
| `test-consumer-isolation` | Inspect SwiftPM's evaluated graph for vendor isolation       |
| `build-macos`             | Compile the adapter target                                   |
| `lint`                    | Check source and configuration                               |
| `format`                  | Format owned source and configuration                        |

GitHub Actions runs the same tests and consumer on macOS 26 and 27. Maintainer
lint and tooling checks run on macOS 27. The public SDK Tooling revision in
`mise.toml` isolates the external consumer's SwiftPM state. Its vendor target is
an automatic library that compiles against the public adapter API. The snapshot
executable links only `SetappAccess`. Swift Build uses strict concurrency, with
compiler warnings allowed under Swift 6.3 for the vendor resource target.

The app link probe requires an existing owned ARM64 macOS VM lease. Place the SDK
under the non-root user's private `/tmp/workspace-<workspace-uuid>` directory.
The directory's `lease.json` must contain `{"lease":"<workspace-uuid>"}` and its
`gitconfig` must map the official repository to a file-only mirror with the 5.5.5
revision and tag. From the SDK checkout inside the guest, run:

```sh
mise exec -- python3 -B fixtures/acceptance/macos/setapp-link/verify_link.py --lease "<workspace-uuid>"
```

The probe force-loads the staged Setapp archive and inspects a temporary unsigned
app. It verifies linked symbols, the vendor version marker, the archive, resources,
resource seal when present, and the original notice. It cleans up and emits inspection
metadata. Do not launch its executable.

## License

SetappAccess is available under the [MIT License](LICENSE).
The official framework and its dependencies retain their
[upstream notices](Notices/Setapp.txt).
