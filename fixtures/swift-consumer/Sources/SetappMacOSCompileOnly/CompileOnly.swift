import SetappAccess
import SetappAccessMacOS

// These declarations are compiled only. The snapshot executable never imports this target.
@MainActor
public func makeSession() -> SetappSession {
  SetappSession()
}

@MainActor
public func snapshot(from session: SetappSession) -> SetappAccessSnapshot {
  session.snapshot
}

@MainActor
public func updates(from session: SetappSession) -> AsyncStream<SetappAccessSnapshot> {
  session.updates()
}

@MainActor
public func observeUpdates(
  from session: SetappSession, receive: @MainActor (SetappAccessSnapshot) async -> Void
) async {
  await session.observeUpdates(receive)
}

@MainActor
public func reportUserInteraction(to session: SetappSession) {
  session.reportUserInteraction()
}
