import Foundation
import SetappAccess

let active = SetappAccessSnapshot(subscriptionIsActive: true, expirationDate: .distantPast)
precondition(active.status == .active)
precondition(active.expirationDate == .distantPast)

print("External vendor-free Setapp snapshot consumer passed.")
