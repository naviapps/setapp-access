import Foundation
import os

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
final class SubscriptionObservation: Sendable {
  private enum Refresh { case idle, pending, cancelled }

  private struct State {
    var token: (any NSObjectProtocol)?
    var refresh = Refresh.idle
  }

  // Foundation's opaque token is only stored here and passed back to the same center.
  private let state = OSAllocatedUnfairLock(uncheckedState: State())
  private let center: NotificationCenter

  init(center: NotificationCenter) { self.center = center }

  func requestRefresh() -> Bool {
    state.withLock {
      guard $0.refresh == .idle else { return false }
      $0.refresh = .pending
      return true
    }
  }

  func beginRefresh() -> Bool {
    state.withLock {
      guard $0.refresh == .pending else { return false }
      // Allow a follow-up if the snapshot read itself triggers another notification.
      $0.refresh = .idle
      return true
    }
  }

  func install(_ token: any NSObjectProtocol) {
    let installed = state.withLockUnchecked {
      guard $0.refresh != .cancelled else { return false }
      $0.token = token
      return true
    }
    if !installed { center.removeObserver(token) }
  }

  func cancel() {
    let removed = state.withLockUnchecked {
      $0.refresh = .cancelled
      defer { $0.token = nil }
      return $0.token
    }
    if let removed { center.removeObserver(removed) }
  }

  deinit { cancel() }
}
