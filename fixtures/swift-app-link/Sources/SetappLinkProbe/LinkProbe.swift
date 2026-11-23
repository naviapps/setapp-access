import SetappAccessMacOS

@main
enum SetappLinkProbe {
  static func main() {
    fatalError("\(SetappSession.self) is a link-only probe. Never launch this executable.")
  }
}
