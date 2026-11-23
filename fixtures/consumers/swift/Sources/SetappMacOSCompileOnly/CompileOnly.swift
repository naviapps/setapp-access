import SetappAccess
import SetappAccessMacOS

// The standalone snapshot executable does not link this target.
@MainActor
func checkAdapterAPI(
  receive: @MainActor (SetappAccessSnapshot) async -> Void
) async {
  let session = SetappSession()
  let _: SetappAccessSnapshot = session.snapshot
  let _: AsyncStream<SetappAccessSnapshot> = session.updates()
  session.reportUserInteraction()
  await session.observeUpdates(receive)
}
