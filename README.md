# SetappAccess

Setapp access snapshots and observation for macOS 26 and Swift 6.3 or newer.

Start with [installation](#installation), then choose
[snapshot-only use](#snapshot-only-use) or [app integration](#app-integration).
[Development](#development) describes safe tests, compile checks and the
separate opt-in app link probe. The package's two public products are
`SetappAccess` and `SetappAccessMacOS`; neither is a SoftwareLicensing provider.

`SetappAccess` contains the native Swift value contract and
Foundation observation mechanics. It has no dependency on the generic
SoftwareLicensing core, native Rust artifacts or the vendor runtime. The package
introduces no Rust crate, Windows emulation, receipt validator, persistence or
app-owned grace policy.

`SetappAccessMacOS` adds `@MainActor SetappSession` using the official
[MacPaw Setapp framework](https://github.com/MacPaw/Setapp-framework) pinned exactly
to 5.5.5. Setapp is the sole authority for subscription access. Only the Setapp app
build should link this product. The vendor-free product can be used by ordinary
host tests without linking or initializing the vendor framework.

The native adapter targets the macOS distribution channel. Windows is outside
the [Setapp Marketplace platform requirements](https://docs.setapp.com/docs/setapp-marketplace-overview).

## Access contract

`SetappAccessSnapshot` projects the vendor's optional subscription into
`SetappAccessStatus`:

| Vendor subscription | Snapshot status |
| ------------------- | --------------- |
| Unavailable (`nil`) | `.unavailable`  |
| `isActive == true`  | `.active`       |
| `isActive == false` | `.inactive`     |

The snapshot's optional `expirationDate` copies only vendor-provided metadata.
Unavailable subscription information has no expiration metadata. A past date
does not override an active vendor status, and a future date does not grant
access to an inactive subscription. There is no local expiry timer or clock-based
authority. Re-read the current subscription when making an access decision;
previous snapshots never establish continuing access on their own.

The SDK has no activation, validation, deactivation, key or plan-management API.
The host owns its product model, source identity and free-versus-paid policy.
Unavailable and inactive states remain distinct even if the host denies access
for both. No snapshot is adopted into a generic license manager or persisted as
a license grant.

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

Replace `<full-40-character-commit>` with an actual published 40-character commit.
The Setapp app target can select `SetappAccessMacOS` and must follow the vendor
configuration and linking requirements below. The snapshot product does not link or initialize
Setapp. SwiftPM still resolves the official framework as a package dependency,
so a fresh resolution needs access to its repository even for snapshot-only
use. Developer tooling is not part of installation.

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

These are host-supplied test values. The live app obtains vendor-authoritative
snapshots from `SetappSession` in the macOS product.

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

`session.snapshot` synchronously reads the current vendor subscription on the
main actor. Both `observeUpdates(_:)` and `updates()` install the observer before
reading the initial snapshot, then re-read on subscription notifications on the
main actor. Notifications that arrive before a pending read starts share one refresh. A
notification during that read can schedule a follow-up. Each stream buffers only
its latest value. Consumers making a later access decision should use
`session.snapshot` again, including when handling a buffered update that may
predate revocation.

Use `observeUpdates(_:)` when the handler can suspend. Cancelling the observation
task removes its observer immediately, suppresses queued reads and stops later
handler calls. A handler already running still has to cooperate with cancellation.
With `updates()`, cancelling while the loop awaits its next snapshot or releasing
an unconsumed stream removes the observer. Check cancellation before acting on a
buffered value from that stream. A task already cancelled skips registration, and
cancellation during registration skips the initial read. Cancellation during the
initial read ends observation without delivering that snapshot. Foundation-only
tests cover these mechanics without linking Setapp.

The Setapp Launch Agent controls macOS app launch. The vendor's
[subscription monitoring guide](https://docs.setapp.com/docs/monitor-subscription-status)
describes iOS behavior. If your macOS app gates features on subscription values,
verify the initial read and status changes in the signed app against its actual
Setapp configuration before release.

Call `reportUserInteraction()` explicitly for meaningful user activity according
to the host's usage policy. Snapshot reads, subscription observation and refresh
do not report usage. The access adapter does not present release notes; a host
that needs vendor presentation can call the official framework directly.

The official macOS framework initializes before `main`. The host must provide
Setapp's key/configuration/resources and the official force-load linker setting:
`-force_load "$(BUILT_PRODUCTS_DIR)/libSetapp.a"` (adjust the archive path for the
host's build layout). Command-line SwiftPM stages `libSetapp.a` in its build
products; force-load that same archive. For direct archive linking, use
`Setapp.xcframework/macos-arm64_x86_64/libSetapp.a`. This SDK supplies
no host-specific unsafe linker flags. Preserve the unmodified
[official Setapp license](Notices/Setapp.txt) in the Setapp app's bundled notices,
including when distributing only compiled binaries. App bundle configuration,
release notes, linking and runtime acceptance belong to the host app.

## Development

An ordinary consumer resolves the package and uses its Swift products without a
developer bootstrap. There is no generic core source pin, local core path override
or core artifact preparation in this package.

Use Xcode 27 or later for the full maintainer checks. From the
repository root, review `mise.toml`, trust only that configuration and install its
declared tools:

```sh
mise trust mise.toml
mise install
mise exec -- make check
```

Individual checks are `mise exec -- make test` (snapshots and Foundation
observation), `make build-macos` (compile the official adapter),
`make test-consumer` (run the external snapshot executable and compile the
adapter), and `make test-fixtures` (portable fixture-boundary checks). Run each
through `mise exec --`; none executes a vendor-linked executable.

Maintainer lint, format and consumer checks use the public SDK Tooling revision in
`mise.toml`. Run
`make lint` to check source or `make format` to apply formatting. GitHub Actions
runs the Swift tests and the same external consumer on macOS 26 with Xcode 26.6
and macOS 27 with Xcode 27.2. The external consumer compiles the macOS adapter
on both. Lint and maintainer tooling checks run once on Xcode 27.2.

`make test-consumer` copies `Package.swift`, `Sources`, `Tests`, `Notices` and
`LICENSE` into a disposable SDK beside the external
`fixtures/swift-consumer/` package. `Tests` preserves the manifest's source layout;
the external package imports only public products. The check isolates SwiftPM
state and runs Swift Build with strict concurrency and warnings as errors.
The Make targets allow compiler warnings with Swift 6.3 to accommodate flags
from the Setapp framework. Supply private dependency configuration directly to
`mise run sdk-tooling -- swift-consumer` with `--git-config` and `--mirror-config`.

The `SetappSnapshotConsumer` executable depends only on the vendor-free product.
It checks active, inactive and unavailable snapshots, including expiration metadata
that must not change vendor access. A separate `SetappMacOSCompileOnly` ordinary
target imports the public macOS adapter and references `SetappSession`, `snapshot`,
`updates()`, `observeUpdates(_:)` and `reportUserInteraction()` in functions that
are never called. Its automatic library product participates in the helper's default build without
creating a dynamic library or executable. Only the core dependency is reachable
from the snapshot executable; the compile-only target is never linked into or
invoked by that executable. No vendor-linked executable runs; the framework's before-main
initialization therefore stays outside this runtime check.

A separate, opt-in app link probe checks the final executable and copied
resources without running the vendor. It requires an existing owned ARM64 macOS
VM lease, rather than an ordinary host checkout: the SDK must be beneath
`/tmp/workspace-<workspace-uuid>` in the guest, that directory must be private to
the non-root user, and its `lease.json` must be exactly
`{"lease":"<workspace-uuid>"}` with the matching UUID.
Its `gitconfig` must map the official repository to a file-only Git mirror
containing the pinned 5.5.5 revision and tag. The probe enforces these prerequisites
and does not provision a VM or lease. From that SDK checkout, run
`mise exec -- python3 -B fixtures/swift-app-link/check-link.py --lease <workspace-uuid>`. It builds only
the external `SetappLinkProbe` product, force-loads SwiftPM's staged macOS
archive, and inspects a temporary unsigned app. It checks the linked Setapp
version marker and adapter symbols, and compares the staged archive, resources
and license with the pinned inputs. If Swift Build signs the resource wrapper
ad hoc, the probe verifies its exact metadata paths and resource seal. It needs
no key. It removes the app and build tree and emits only inspection metadata. The probe does not verify runtime
resource lookup or vendor initialization. Do not run its executable.

This is local source consumption, not remote installation or host-app acceptance.
Setapp bundle configuration, vendor initialization, subscription reads, observation
and usage reporting still require separate host-owned runtime acceptance.

## License

SetappAccess is available under the [MIT License](LICENSE).
The official framework and its dependencies retain their
[upstream notices](Notices/Setapp.txt).
