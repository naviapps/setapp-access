import Foundation
import SetappAccess
import Testing

@Test func unavailableSubscriptionIsDistinctFromExplicitInactivity() {
  let expiration = Date(timeIntervalSince1970: 1000)
  let unavailable = SetappAccessSnapshot(subscriptionIsActive: nil, expirationDate: expiration)
  let inactive = SetappAccessSnapshot(subscriptionIsActive: false, expirationDate: expiration)

  #expect(unavailable.status == .unavailable)
  #expect(unavailable.expirationDate == nil)
  #expect(inactive.status == .inactive)
  #expect(inactive.expirationDate == expiration)
  #expect(unavailable != inactive)
}

@Test func expirationMetadataDoesNotDetermineAccess() {
  let past = Date.distantPast
  let future = Date.distantFuture
  let active = SetappAccessSnapshot(subscriptionIsActive: true, expirationDate: past)
  let inactive = SetappAccessSnapshot(subscriptionIsActive: false, expirationDate: future)

  #expect(active.status == .active)
  #expect(active.expirationDate == past)
  #expect(inactive.status == .inactive)
  #expect(inactive.expirationDate == future)
  #expect(SetappAccessSnapshot(subscriptionIsActive: true).expirationDate == nil)
}
