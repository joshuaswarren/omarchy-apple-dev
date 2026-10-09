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

public struct HorizontalAlignment {
  public static var center: HorizontalAlignment { fatalError() }
  public static var leading: HorizontalAlignment { fatalError() }
  public static var trailing: HorizontalAlignment { fatalError() }
}

public struct VStack<Content: View>: View {
  public init(alignment: HorizontalAlignment = .center, spacing: CGFloat? = nil,
              @ViewBuilder content: () -> Content) { fatalError() }
  public var body: some View { EmptyView() }
}

public struct Text: View {
  public init<S: StringProtocol>(_ content: S) { fatalError() }
  public var body: some View { EmptyView() }
}

public struct Button<Label: View>: View {
  public init(action: @escaping () -> Void, @ViewBuilder label: () -> Label) { fatalError() }
  public var body: some View { EmptyView() }
}

extension Button where Label == Text {
  public init<S: StringProtocol>(_ title: S, action: @escaping () -> Void) { fatalError() }
}

@propertyWrapper
public struct State<Value> {
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
