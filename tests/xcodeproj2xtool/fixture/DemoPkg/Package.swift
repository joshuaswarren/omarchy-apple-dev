// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DemoPkg",
    products: [.library(name: "DemoKit", targets: ["DemoKit"])],
    targets: [.target(name: "DemoKit")]
)
