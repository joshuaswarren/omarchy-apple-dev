import SwiftUI

@main
enum LayoutProbe {
  static var sink = (0, 0, 0, 0, 0, 0, 0, 0, 0)
  static func main() {
    sink.0 = MemoryLayout<HorizontalAlignment>.size
    sink.1 = MemoryLayout<Text>.size
    sink.2 = MemoryLayout<TupleView<(Text, Text)>>.size
    sink.3 = MemoryLayout<Color>.size
    sink.4 = MemoryLayout<Font>.size
    sink.5 = MemoryLayout<Image>.size
    sink.6 = MemoryLayout<State<String>>.size
    sink.7 = MemoryLayout<Optional<Color>>.size
    sink.8 = MemoryLayout<Optional<Font>>.size
  }
}
