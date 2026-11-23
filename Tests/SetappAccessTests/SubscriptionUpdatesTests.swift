import Foundation
import Testing

@testable import SetappAccess

private final class TrackingCenter: NotificationCenter, @unchecked Sendable {
  private let cancelDuringRegistration: Bool
  private let lock = NSLock()
  private var removals = 0

  init(cancelDuringRegistration: Bool = false) {
    self.cancelDuringRegistration = cancelDuringRegistration
    super.init()
  }

  var removedCount: Int { lock.withLock { removals } }

  override func addObserver(
    forName name: Notification.Name?, object: Any?, queue: OperationQueue?,
    using block: @escaping @Sendable (Notification) -> Void
  ) -> any NSObjectProtocol {
    let token = super.addObserver(forName: name, object: object, queue: queue, using: block)
    if cancelDuringRegistration { withUnsafeCurrentTask { $0?.cancel() } }
    return token
  }

  override func removeObserver(_ observer: Any) {
    lock.withLock { removals += 1 }
    super.removeObserver(observer)
  }
}

@MainActor
private final class Subscription {
  var isActive: Bool?
  var expirationDate: Date?
  var onRead: (() -> Void)?
  private(set) var reads = 0

  init(isActive: Bool? = nil) { self.isActive = isActive }

  func read() -> SetappAccessSnapshot {
    reads += 1
    let snapshot = SetappAccessSnapshot(
      subscriptionIsActive: isActive, expirationDate: expirationDate)
    onRead?()
    return snapshot
  }
}

@Test @MainActor func streamReadsFreshInitialSubscriptionAndRevocation() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription()
  let stream = SubscriptionUpdates.make(
    center: center, name: name, readSnapshot: { subscription.read() })
  var iterator = stream.makeAsyncIterator()
  #expect(await iterator.next()?.status == .unavailable)

  subscription.isActive = true
  subscription.expirationDate = .distantPast
  center.post(name: name, object: nil)
  #expect(
    await iterator.next()
      == SetappAccessSnapshot(subscriptionIsActive: true, expirationDate: .distantPast))

  subscription.isActive = false
  subscription.expirationDate = .distantFuture
  center.post(name: name, object: nil)
  #expect(
    await iterator.next()
      == SetappAccessSnapshot(subscriptionIsActive: false, expirationDate: .distantFuture))

  subscription.isActive = nil
  center.post(name: name, object: nil)
  #expect(await iterator.next() == SetappAccessSnapshot(subscriptionIsActive: nil))
  #expect(subscription.reads == 4)
}

@Test @MainActor func observerIsInstalledBeforeInitialRead() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  let (rereads, continuation) = AsyncStream<Int>.makeStream()
  subscription.onRead = {
    if subscription.reads == 1 {
      subscription.isActive = false
      center.post(name: name, object: nil)
    } else {
      continuation.yield(subscription.reads)
    }
  }
  let stream = SubscriptionUpdates.make(
    center: center, name: name, readSnapshot: { subscription.read() })
  var readIterator = rereads.makeAsyncIterator()
  #expect(await readIterator.next() == 2)
  var iterator = stream.makeAsyncIterator()
  #expect(await iterator.next()?.status == .inactive)
  subscription.onRead = nil
  continuation.finish()
}

@Test @MainActor func streamBuffersOnlyLatestSnapshot() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  let stream = SubscriptionUpdates.make(
    center: center, name: name, readSnapshot: { subscription.read() })
  let (reads, continuation) = AsyncStream<Int>.makeStream()
  var readIterator = reads.makeAsyncIterator()
  subscription.onRead = { continuation.yield(subscription.reads) }

  subscription.isActive = false
  center.post(name: name, object: nil)
  #expect(await readIterator.next() == 2)
  subscription.isActive = nil
  center.post(name: name, object: nil)
  #expect(await readIterator.next() == 3)

  var iterator = stream.makeAsyncIterator()
  #expect(await iterator.next()?.status == .unavailable)
  subscription.onRead = nil
  continuation.finish()
}

@Test func refreshAdmissionCoalescesPendingNotificationsAndStopsAfterCancellation() {
  let observation = SubscriptionObservation(center: TrackingCenter())
  #expect(observation.requestRefresh())
  for _ in 0..<64 {
    #expect(!observation.requestRefresh())
  }

  #expect(observation.beginRefresh())
  #expect(observation.requestRefresh())
  #expect(!observation.requestRefresh())

  observation.cancel()
  #expect(!observation.beginRefresh())
  #expect(!observation.requestRefresh())
}

@Test @MainActor func notificationDuringRefreshSchedulesFollowUp() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  let stream = SubscriptionUpdates.make(
    center: center, name: name, readSnapshot: { subscription.read() })
  var iterator = stream.makeAsyncIterator()
  #expect(await iterator.next()?.status == .active)

  let (reads, continuation) = AsyncStream<Int>.makeStream()
  subscription.onRead = {
    if subscription.reads == 2 {
      subscription.isActive = true
      center.post(name: name, object: nil)
    }
    continuation.yield(subscription.reads)
  }
  subscription.isActive = false
  center.post(name: name, object: nil)

  var readIterator = reads.makeAsyncIterator()
  #expect(await readIterator.next() == 2)
  #expect(await readIterator.next() == 3)
  #expect(await iterator.next()?.status == .active)
  subscription.onRead = nil
  continuation.finish()
}

@Test @MainActor func cancellingConsumerRemovesObserverAndStopsQueuedReads() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  let stream = SubscriptionUpdates.make(
    center: center, name: name, readSnapshot: { subscription.read() })
  let (received, continuation) = AsyncStream<Void>.makeStream()
  let task = Task {
    for await _ in stream { continuation.yield(()) }
  }
  var iterator = received.makeAsyncIterator()
  _ = await iterator.next()
  // Queue a main-actor re-read, then cancel before it can run.
  center.post(name: name, object: nil)
  task.cancel()
  await task.value
  #expect(center.removedCount == 1)
  center.post(name: name, object: nil)
  await Task.yield()
  #expect(subscription.reads == 1)
  continuation.finish()
}

@Test @MainActor func droppingUnconsumedStreamRemovesObserver() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  do {
    let stream = SubscriptionUpdates.make(
      center: center, name: name, readSnapshot: { subscription.read() })
    withExtendedLifetime(stream) {
      #expect(center.removedCount == 0)
      #expect(subscription.reads == 1)
      center.post(name: name, object: nil)
    }
  }
  #expect(center.removedCount == 1)
  center.post(name: name, object: nil)
  await Task.yield()
  #expect(subscription.reads == 1)
}

@Test @MainActor func cancellingObservationRemovesObserverWhileHandlerIsSuspended() async {
  let center = TrackingCenter()
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  let (paused, signal) = AsyncStream<CheckedContinuation<Void, Never>>.makeStream()
  var received: [SetappAccessStatus] = []
  let task = Task { @MainActor in
    await SubscriptionUpdates.observe(
      center: center, name: name, readSnapshot: { subscription.read() }
    ) { snapshot in
      received.append(snapshot.status)
      if received.count == 1 {
        await withCheckedContinuation { signal.yield($0) }
      }
    }
  }
  var pauseIterator = paused.makeAsyncIterator()
  let suspendedHandler = await pauseIterator.next()
  #expect(received == [.active])
  // Buffer an update while the handler is suspended, then enqueue one more read.
  let (rereads, rereadSignal) = AsyncStream<Void>.makeStream()
  subscription.onRead = { rereadSignal.yield(()) }
  subscription.isActive = false
  center.post(name: name, object: nil)
  var rereadIterator = rereads.makeAsyncIterator()
  _ = await rereadIterator.next()
  center.post(name: name, object: nil)
  task.cancel()
  #expect(center.removedCount == 1)
  center.post(name: name, object: nil)
  suspendedHandler?.resume()
  await task.value
  #expect(received == [.active])
  #expect(subscription.reads == 2)
  #expect(center.removedCount == 1)
  signal.finish()
  rereadSignal.finish()
}

private enum StartupCancellation: CaseIterable {
  case beforeRegistration, duringRegistration, duringRead
}

@Test(arguments: StartupCancellation.allCases, [false, true])
@MainActor private func cancellationDuringStartupEndsObservationBeforeDelivery(
  cancellation: StartupCancellation, useHandler: Bool
) async {
  let center = TrackingCenter(cancelDuringRegistration: cancellation == .duringRegistration)
  let name = Notification.Name("subscription")
  let subscription = Subscription(isActive: true)
  if cancellation == .duringRead {
    subscription.onRead = { withUnsafeCurrentTask { $0?.cancel() } }
  }
  let expectedRemovals = cancellation == .beforeRegistration ? 0 : 1

  let producer = Task { @MainActor () -> AsyncStream<SetappAccessSnapshot>? in
    if cancellation == .beforeRegistration { withUnsafeCurrentTask { $0?.cancel() } }
    if useHandler {
      await SubscriptionUpdates.observe(
        center: center, name: name, readSnapshot: { subscription.read() }
      ) { _ in
        Issue.record("An observation cancelled at startup delivered a snapshot.")
      }
      #expect(Task.isCancelled)
      return nil
    }
    let stream = SubscriptionUpdates.make(
      center: center, name: name, readSnapshot: { subscription.read() })
    #expect(Task.isCancelled)
    #expect(center.removedCount == expectedRemovals)
    return stream
  }
  if let stream = await producer.value {
    // Observe completion from a different task so cancellation cannot mask a buffered value.
    var iterator = stream.makeAsyncIterator()
    #expect(await iterator.next() == nil)
  }

  center.post(name: name, object: nil)
  await Task.yield()
  #expect(subscription.reads == (cancellation == .duringRead ? 1 : 0))
  #expect(center.removedCount == expectedRemovals)
}
