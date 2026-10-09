// Minimal SwiftUI module interface for the no-xcode mode.
//
// These are our own declarations of the public SwiftUI surface, written to
// compile against the Swift standard-library modules this mode already builds.
// The module is built with library evolution on. Result-builder static methods
// are marked @inlinable so the client inlines them at compile time and does not
// emit runtime references to them; everything else stays in the SwiftUI binary
// on the iPhone and is reached through the link stubs. The link check in
// swiftui-build.sh proves every referenced symbol exists in the stubs cut
// from the connected iPhone.
//
// Deliberately out: MainActor isolation (the app compiles in Swift 5 mode),
// LocalizedStringKey overloads (string literals bind to the StringProtocol
// inits), buildIf and buildEither (no conditionals in content closures yet),
// and the builder attributes on the View, Scene and App body requirements
// (the body expressions here are single expressions; builders still apply
// inside content closures).

import CoreGraphics

@resultBuilder
public enum ViewBuilder {
  @inlinable public static func buildBlock() -> EmptyView { EmptyView() }
  @inlinable public static func buildBlock<Content: View>(_ content: Content) -> Content { content }
  @inlinable public static func buildBlock<C0: View, C1: View>(_ c0: C0, _ c1: C1)
    -> TupleView<(C0, C1)> { TupleView((c0, c1)) }
  @inlinable public static func buildBlock<C0: View, C1: View, C2: View, C3: View>(
    _ c0: C0, _ c1: C1, _ c2: C2, _ c3: C3) -> TupleView<(C0, C1, C2, C3)> {
    TupleView((c0, c1, c2, c3))
  }
  @inlinable public static func buildExpression<Content: View>(_ content: Content) -> Content { content }
}

@resultBuilder
public enum SceneBuilder {
  @inlinable public static func buildBlock<Content: Scene>(_ content: Content) -> Content { content }
  @inlinable public static func buildExpression<Content: Scene>(_ content: Content) -> Content { content }
}

public protocol View {
  associatedtype Body: View
  var body: Self.Body { get }
}

public protocol Scene {
  associatedtype Body: Scene
  var body: Self.Body { get }
}

public protocol App {
  associatedtype Body: Scene
  var body: Self.Body { get }
  init()
}

extension App {
  public static func main() { fatalError() }
}

public struct EmptyView: View {
  public init() { fatalError() }
  public var body: EmptyView { fatalError() }
}

@frozen public struct TupleView<T>: View {
  public var value: T
  @inlinable public init(_ value: T) { self.value = value }
  public var body: some View { EmptyView() }
}

public struct EmptyScene: Scene {
  public init() { fatalError() }
  public var body: some Scene { EmptyScene() }
}

public struct WindowGroup<Content: View>: Scene {
  public init(@ViewBuilder content: () -> Content) { fatalError() }
  public var body: some Scene { EmptyScene() }
}

// Device layout: HorizontalAlignment { key: AlignmentKey { bits: UInt } } —
// 8 bytes, passed in one register (SwiftUICore metadata). Resilient-empty
// here made clients pass it indirectly while VStack.init(alignment:) read a
// register.
@frozen public struct HorizontalAlignment {
  public var key: UInt
  public static var center: HorizontalAlignment { fatalError() }
  public static var leading: HorizontalAlignment { fatalError() }
  public static var trailing: HorizontalAlignment { fatalError() }
}

public struct VStack<Content: View>: View {
  public init(alignment: HorizontalAlignment = .center, spacing: CGFloat? = nil,
              @ViewBuilder content: () -> Content) { fatalError() }
  public var body: some View { EmptyView() }
}

// Device layout (iOS 27.0.1 SwiftUICore, verified by disassembly):
// Text is @frozen, 0x20 bytes, returned in x0..x3 (payload words, tag byte,
// modifiers), never through an sret. Text.init(verbatim:) (SwiftUICore
// 0x18925d224) passes the String through in x0,x1 and sets w2=0;
// Text.init(any TextStorage) (0x18925ce84) sets w2=1. A resilient Text here
// made clients call those inits with an sret the device never writes, so the
// stored value was uninitialized stack and the WindowGroup destroy released
// garbage.
@frozen public struct Text: View {
  // Tag byte at offset 0x10: 0 = string, 1 = device text storage.
  // String is the only payload our clients can produce; the second case
  // exists to occupy the payload area so the tag lands in a trailing byte
  // (offset 0x10, size 0x18) exactly like the device enum — a payload-less
  // second case lets the compiler fold the tag into String's spare bits and
  // shrink Text to 0x18, which is NOT the device layout.
  @frozen public enum Storage {
    case string(String)
    case deviceStorage(UInt64, UInt64)
  }
  public struct Modifier {}
  public var storage: Storage
  public var modifiers: [Modifier]
  public init<S: StringProtocol>(_ content: S) { fatalError() }
  public init(verbatim content: String) { fatalError() }
  public var body: some View { EmptyView() }
}

public struct Button<Label: View>: View {
  public init(action: @escaping () -> Void, @ViewBuilder label: () -> Label) { fatalError() }
  public var body: some View { EmptyView() }
}

extension Button where Label == Text {
  public init<S: StringProtocol>(_ title: S, action: @escaping () -> Void) { fatalError() }
}

// Device layout: State { _value: Value, _location: AnyLocation<Value>? } —
// the location is a one-word class existential. Resilient-empty here made
// clients store zero bytes while the device init wrote the real fields.
// AnyObject? gives the same one-word existential with the same
// retain/release semantics as the device's AnyLocation box.
@propertyWrapper
@frozen public struct State<Value> {
  public var _value: Value
  public var _location: AnyObject?
  public init(wrappedValue: Value) { fatalError() }
  public var wrappedValue: Value {
    get { fatalError() }
    nonmutating set { fatalError() }
  }
  public var projectedValue: Binding<Value> { fatalError() }
}

public struct Binding<Value> {
  public init(wrappedValue: Value) { fatalError() }
}

// Device layout (iOS 27.0.1 SwiftUICore reflection dump): Color
// { provider: AnyColorBox } — one word, a class reference; Color, Font and
// Image are @frozen in the OSS interface and the device dump fields match,
// so each passes in a single register. A resilient-empty Color here would
// make clients pass an empty value where the device init reads a register.
@frozen public struct Color {
  public var provider: AnyObject
  public static var red: Color { fatalError() }
  public static var green: Color { fatalError() }
  public static var blue: Color { fatalError() }
  public static var orange: Color { fatalError() }
  public static var gray: Color { fatalError() }
  public static var primary: Color { fatalError() }
}

// Device layout: Font { provider: AnyFontBox } — one word. The statics below
// are plain getters the device exports (Font.largeTitle etc.); no default
// arguments: the device exports no default-argument generators for these.
@frozen public struct Font {
  public var provider: AnyObject
  public static var largeTitle: Font { fatalError() }
  public static var title: Font { fatalError() }
  public static var headline: Font { fatalError() }
  public static var body: Font { fatalError() }
}

// Device layout: Image { provider: AnyImageProviderBox } — one word.
// Image(systemName:) is the device init _$s7SwiftUI5ImageV10systemNameACSS_tcfC.
@frozen public struct Image: View {
  public var provider: AnyObject
  public init(systemName: String) { fatalError() }
  public var body: some View { EmptyView() }
}

public protocol ShapeStyle {}

// Modifier methods are protocol-extension functions the device exports (the
// demangled symbols say "(extension in SwiftUI):SwiftUI.View.padding(...)
// -> some"); a non-inlinable declaration with a fatalError body links the
// device implementation. Each returns the device's opaque "some View"
// (ModifiedContent<Self, _XLayout>), whose descriptor and metadata accessor
// the device also exports under the same mangled name. The zero-argument
// padding() is unusable: the device exports no default-argument generator.
extension View {
  public func padding(_ length: CGFloat) -> some View { EmptyView() }
  public func font(_ font: Font?) -> some View { EmptyView() }
  public func foregroundColor(_ color: Color?) -> some View { EmptyView() }
  public func foregroundStyle<S: ShapeStyle>(_ style: S) -> some View { EmptyView() }
  public func navigationTitle(_ title: LocalizedStringKey) -> some View { EmptyView() }
}

// iOS 27 device shapes, read from the reflection dump and exported symbols.
// List has TWO generic parameters (Selection first), both unconstrained at
// the struct: the plain List { } initializer lives in
// `extension List where Selection == Never` and returns
// List<Never, Content> (device symbol ...4ListVAAs5NeverORszrlE7content...),
// and the View conformance is `where Content: View`. The content closure is
// @escaping in the device mangling (yXE_), a plain () -> Content would
// mangle yc_ and miss.
public struct List<Selection, Content>: View {
  public init() {}
  public var body: some View { EmptyView() }
}

extension List where Selection == Never {
  public init(@ViewBuilder content: () -> Content) { fatalError() }
}

public struct ForEach<Data, ID, Content> {
  public init() {}
}

extension ForEach: View where Content: View {
  public var body: some View { EmptyView() }
}

extension ForEach where Data == Range<Int>, ID == Int, Content: View {
  public init(_ data: Range<Int>, @ViewBuilder content: @escaping (Int) -> Content) { fatalError() }
}

// The label closure must stay UNMARKED: an unmarked () -> Label mangles
// xyXEt exactly like the device, while @escaping mangles a bare yc and
// misses the symbol (same shape as Button above).
public struct NavigationLink<Label: View, Destination: View>: View {
  public init(destination: Destination, @ViewBuilder label: () -> Label) { fatalError() }
  public var body: some View { EmptyView() }
}

// One-word-initing wrapper: the device init takes a String and copies it
// (symbol ...18LocalizedStringKeyVyACSScfC). The label parameter of
// navigationTitle is this type, not String.
public struct LocalizedStringKey {
  public init(_ value: String) { fatalError() }
}
