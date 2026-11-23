import Foundation

/// Native observation mechanics, isolated from the auto-initializing vendor framework.
package enum SubscriptionUpdates {
  @MainActor
  package static func make(
    center: NotificationCenter, name: Notification.Name,
    readSnapshot: @escaping @MainActor @Sendable () -> SetappAccessSnapshot
  ) -> AsyncStream<SetappAccessSnapshot> {
    let (stream, continuation) = AsyncStream<SetappAccessSnapshot>.makeStream(
      bufferingPolicy: .bufferingNewest(1))
    register(
      center: center, name: name, readSnapshot: readSnapshot,
      observation: SubscriptionObservation(center: center), continuation: continuation)
    return stream
  }

  @MainActor
  package static func observe(
    center: NotificationCenter, name: Notification.Name,
    readSnapshot: @escaping @MainActor @Sendable () -> SetappAccessSnapshot,
    receive: @MainActor (SetappAccessSnapshot) async -> Void
  ) async {
    let (stream, continuation) = AsyncStream<SetappAccessSnapshot>.makeStream(
      bufferingPolicy: .bufferingNewest(1))
    let observation = SubscriptionObservation(center: center)
    await withTaskCancellationHandler {
      register(
        center: center, name: name, readSnapshot: readSnapshot,
        observation: observation, continuation: continuation)
      for await snapshot in stream {
        guard !Task.isCancelled else { break }
        await receive(snapshot)
      }
    } onCancel: {
      observation.cancel()
      continuation.finish()
    }
  }

  @MainActor
  private static func register(
    center: NotificationCenter, name: Notification.Name,
    readSnapshot: @escaping @MainActor @Sendable () -> SetappAccessSnapshot,
    observation: SubscriptionObservation,
    continuation: AsyncStream<SetappAccessSnapshot>.Continuation
  ) {
    guard !Task.isCancelled else {
      continuation.finish()
      return
    }
    continuation.onTermination = { _ in observation.cancel() }
    let token = center.addObserver(forName: name, object: nil, queue: nil) { _ in
      guard observation.requestRefresh() else { return }
      Task { @MainActor in
        guard observation.beginRefresh() else { return }
        continuation.yield(readSnapshot())
      }
    }
    observation.install(token)
    guard !Task.isCancelled else {
      continuation.finish()
      return
    }
    // Register first, then read. Notifications always re-read on the main actor.
    let snapshot = readSnapshot()
    guard !Task.isCancelled else {
      continuation.finish()
      return
    }
    continuation.yield(snapshot)
  }
}

// The lock covers observer lifetime and admission of one pending main-actor read.
// Removing observers, reading subscriptions, and yielding snapshots happen outside it.
final class SubscriptionObservation: @unchecked Sendable {
  private let lock = NSLock()
  private let center: NotificationCenter
  private var token: (any NSObjectProtocol)?
  private var cancelled = false
  private var refreshPending = false

  init(center: NotificationCenter) { self.center = center }

  func requestRefresh() -> Bool {
    lock.withLock {
      guard !cancelled, !refreshPending else { return false }
      refreshPending = true
      return true
    }
  }

  func beginRefresh() -> Bool {
    lock.withLock {
      guard !cancelled, refreshPending else { return false }
      // Allow a follow-up if the snapshot read itself triggers another notification.
      refreshPending = false
      return true
    }
  }

  func install(_ token: any NSObjectProtocol) {
    let remove = lock.withLock {
      if cancelled { return true }
      self.token = token
      return false
    }
    if remove { center.removeObserver(token) }
  }

  func cancel() {
    let removed = lock.withLock {
      cancelled = true
      refreshPending = false
      let removed = token
      token = nil
      return removed
    }
    if let removed { center.removeObserver(removed) }
  }

  deinit { cancel() }
}
