import Foundation
import SetappAccess

let active = SetappAccessSnapshot(subscriptionIsActive: true, expirationDate: .distantPast)
precondition(active.status == .active)
precondition(active.expirationDate == .distantPast)

let inactive = SetappAccessSnapshot(subscriptionIsActive: false, expirationDate: .distantFuture)
precondition(inactive.status == .inactive)
precondition(inactive.expirationDate == .distantFuture)

let unavailable = SetappAccessSnapshot(subscriptionIsActive: nil, expirationDate: .distantFuture)
precondition(unavailable.status == .unavailable)
precondition(unavailable.expirationDate == nil)
precondition(unavailable != inactive)
precondition(SetappAccessSnapshot(subscriptionIsActive: true).expirationDate == nil)

print("External vendor-free Setapp snapshot consumer passed.")
