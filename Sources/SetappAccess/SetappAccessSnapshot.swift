import Foundation

/// The official framework's current subscription state, without host product policy.
public enum SetappAccessStatus: Equatable, Sendable {
  /// The framework currently has no subscription information.
  case unavailable
  case active
  case inactive
}

/// A point-in-time projection of the vendor subscription, never a persisted grant.
public struct SetappAccessSnapshot: Equatable, Sendable {
  public let status: SetappAccessStatus

  /// Vendor metadata only. The vendor's active flag remains the authority for access.
  public let expirationDate: Date?

  public init(subscriptionIsActive: Bool?, expirationDate: Date? = nil) {
    switch subscriptionIsActive {
    case true?: status = .active
    case false?: status = .inactive
    case nil: status = .unavailable
    }
    self.expirationDate = subscriptionIsActive == nil ? nil : expirationDate
  }
}
