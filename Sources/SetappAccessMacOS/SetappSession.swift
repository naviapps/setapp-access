import Setapp
import SetappAccess

/// Main-actor access to the official macOS SDK. Link only in the Setapp app build.
@MainActor
public final class SetappSession {
  public init() {}

  public var snapshot: SetappAccessSnapshot {
    let subscription = SetappManager.shared.subscription
    return SetappAccessSnapshot(
      subscriptionIsActive: subscription?.isActive,
      expirationDate: subscription?.expirationDate)
  }

  /// Yields fresh access immediately, then on subscription notifications.
  /// Cancelling a task awaiting an update removes its observer. Check cancellation
  /// before acting on a buffered snapshot.
  public func updates() -> AsyncStream<SetappAccessSnapshot> {
    SubscriptionUpdates.make(
      center: .default, name: SetappManager.didChangeSubscriptionNotification,
      readSnapshot: { self.snapshot })
  }

  /// Delivers the current snapshot and subsequent updates until the task is cancelled.
  /// Cancellation removes the observer even while the handler is suspended.
  public func observeUpdates(_ receive: @MainActor (SetappAccessSnapshot) async -> Void) async {
    await SubscriptionUpdates.observe(
      center: .default, name: SetappManager.didChangeSubscriptionNotification,
      readSnapshot: { self.snapshot }, receive: receive)
  }

  /// Call for meaningful user activity according to the host's usage policy.
  public func reportUserInteraction() {
    SetappManager.shared.reportUsageEvent(.userInteraction)
  }
}
