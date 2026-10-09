import SwiftUI

@main
struct HelloSwiftUIApp: App {
  var body: some Scene {
    WindowGroup {
      ContentView()
    }
  }
}

struct ContentView: View {
  @State private var count = 0
  var body: some View {
    VStack(alignment: .center, spacing: 16) {
      Text("taps: \(count)")
      Button("tap me") { count += 1 }
    }
  }
}
