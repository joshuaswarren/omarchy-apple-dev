import AssetKit
import Foundation

/// Prepare actool's input catalogs for AssetKit: AssetKit compiles one catalog, knows imagesets,
/// colorsets and one appiconset, and rejects anything else. Copy every catalog side by side into
/// one temporary catalog, keeping only what AssetKit can compile and listing what was left out.
public enum CatalogMerge {
    public struct DuplicateEntry: Error, CustomStringConvertible {
        public let name: String
        public var description: String { "\(name) is defined in more than one asset catalog" }
    }

    public struct FolderConflict: Error, CustomStringConvertible {
        public let name: String
        public var description: String { "\(name) is a folder in more than one asset catalog with different properties" }
    }

    public struct Prepared {
        /// The merged catalog, inside its own temporary directory.
        public let catalog: URL
        /// Entries left out, as "<catalog>/<relative path>: <reason>".
        /// Only genuinely unsupported content; deselected app icon sets are
        /// dropped silently, like Apple's actool.
        public let skipped: [String]
        /// The --app-icon Icon Composer source, compiled layered by
        /// XCAssetCompiler instead of through the appiconset path.
        public let iconComposer: IconComposerCompiler.Input?
        /// Alternate .icon sources (--alternate-app-icon matches, or every
        /// .icon with --include-all-app-icons), compiled layered as
        /// alternate icons.
        public let alternateIconComposers: [IconComposerCompiler.Input]
    }

    /// - Parameters:
    ///   - appIcon: the primary .appiconset / .icon name (actool's --app-icon).
    ///   - alternateAppIcons: --alternate-app-icon names.
    ///   - includeAllAppIcons: --include-all-app-icons; every app icon asset
    ///     is kept. Apple 27.0 compiles deselected icon sets with no warning
    ///     (IceCubes oracle: catalog with 30 unselected appiconsets, empty
    ///     stdout), so only unsupported content lands in `skipped`.
    public static func prepare(
        _ catalogs: [URL], appIcon: String?,
        alternateAppIcons: Set<String> = [], includeAllAppIcons: Bool = false
    ) throws -> Prepared {
        let fm = FileManager.default
        let merged = fm.temporaryDirectory
            .appendingPathComponent("actool-\(UUID().uuidString)")
            .appendingPathComponent("Merged.xcassets")
        try fm.createDirectory(at: merged, withIntermediateDirectories: true)
        try Data(#"{"info":{"author":"xcode","version":1}}"#.utf8)
            .write(to: merged.appendingPathComponent("Contents.json"))
        var skipped: [String] = []
        var iconComposer: IconComposerCompiler.Input? = nil
        var alternateIconComposers: [IconComposerCompiler.Input] = []

        func copy(_ dir: URL, into dest: URL, catalog: URL) throws {
            for child in try fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.isDirectoryKey])
                .sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
            where child.lastPathComponent != "Contents.json" {
                let target = dest.appendingPathComponent(child.lastPathComponent)
                let where_ = "\(catalog.path)/\(child.path.dropFirst(catalog.path.count + 1))"
                let isDir = (try? child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
                switch child.pathExtension {
                case "imageset":
                    if let format = unsupportedImageFormat(child) {
                        skipped.append("\(where_): .\(format) images are not supported by AssetKit")
                    } else {
                        try place(child, at: target)
                        try keyBitmapsAtOneX(target)
                    }
                case "colorset":
                    if try !copyColorSet(child, to: target) {
                        skipped.append("\(where_): no color defined")
                    }
                case "symbolset":
                    try place(child, at: target)
                case "appiconset":
                    let name = child.deletingPathExtension().lastPathComponent
                    if name == appIcon || includeAllAppIcons || alternateAppIcons.contains(name) {
                        try place(child, at: target)
                    }
                    // Deselected icon sets drop silently, like Apple's.
                case "icon":
                    // Icon Composer source: the one matching --app-icon is
                    // compiled layered as the primary; named alternates and,
                    // with --include-all-app-icons, every .icon compile as
                    // alternate icons. Others drop silently.
                    let name = child.deletingPathExtension().lastPathComponent
                    if name == appIcon {
                        iconComposer = recordIconComposerIcon(child, appIcon: appIcon)
                    } else if includeAllAppIcons || alternateAppIcons.contains(name) {
                        alternateIconComposers.append(
                            IconComposerCompiler.Input(name: name, directory: child, idioms: []))
                    }
                case "solidimagestack":
                    // visionOS-only: actool 27.0 drops it silently for iphoneos.
                    continue
                case "" where isDir:
                    try fm.createDirectory(at: target, withIntermediateDirectories: true)
                    let folderContents = child.appendingPathComponent("Contents.json")
                    let targetContents = target.appendingPathComponent("Contents.json")
                    // A folder of the same name in two catalogs merges, as in Apple's actool: the first Contents.json stays.
                    // Different properties (provides-namespace) would change what one catalog meant: refused.
                    if fm.fileExists(atPath: folderContents.path) {
                        if !fm.fileExists(atPath: targetContents.path) {
                            try fm.copyItem(at: folderContents, to: targetContents)
                        } else if folderProperties(folderContents) != folderProperties(targetContents) {
                            throw FolderConflict(name: child.lastPathComponent)
                        }
                    }
                    try copy(child, into: target, catalog: catalog)
                default:
                    skipped.append("\(where_): \(child.pathExtension.isEmpty ? "not an asset" : ".\(child.pathExtension) is not supported by AssetKit")")
                }
            }
        }

        func place(_ source: URL, at target: URL) throws {
            guard !fm.fileExists(atPath: target.path) else { throw DuplicateEntry(name: target.lastPathComponent) }
            try fm.copyItem(at: source, to: target)
        }

        /// A folder Contents.json's "properties", empty when it has none.
        func folderProperties(_ contents: URL) -> NSDictionary {
            guard let data = try? Data(contentsOf: contents),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let properties = json["properties"] as? [String: Any] else { return [:] }
            return properties as NSDictionary
        }

        /// The first source file extension AssetKit cannot read (it reads PNG, JPEG, SVG and PDF).
        func unsupportedImageFormat(_ imageSet: URL) -> String? {
            guard let data = try? Data(contentsOf: imageSet.appendingPathComponent("Contents.json")),
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let images = json["images"] as? [[String: Any]] else { return nil }
            return images.compactMap { ($0["filename"] as? String).map { URL(fileURLWithPath: $0).pathExtension.lowercased() } }
                // HEIC/HEIF decode through libheif's heif-convert.
                .first { !["png", "jpg", "jpeg", "svg", "pdf", "heic", "heif"].contains($0) }
        }

        /// A bitmap entry with no scale (Xcode's "Single Scale" set) gets "1x", as Apple's actool keys it: AssetKit
        /// keys it at scale 0, which UIKit never matches ("No image named ..."). Vector sources stay scale-free.
        func keyBitmapsAtOneX(_ imageSet: URL) throws {
            let url = imageSet.appendingPathComponent("Contents.json")
            guard var contents = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any],
                  var images = contents["images"] as? [[String: Any]] else { return }
            var changed = false
            for i in images.indices where images[i]["scale"] == nil {
                guard let name = images[i]["filename"] as? String,
                      ["png", "jpg", "jpeg", "heic", "heif"].contains(URL(fileURLWithPath: name).pathExtension.lowercased())
                else { continue }
                images[i]["scale"] = "1x"
                changed = true
            }
            guard changed else { return }
            contents["images"] = images
            try JSONSerialization.data(withJSONObject: contents).write(to: url)
        }

        /// Copies a colorset without its color-less entries (Xcode's empty AccentColor placeholder).
        func copyColorSet(_ source: URL, to target: URL) throws -> Bool {
            let json = try JSONSerialization.jsonObject(with: Data(contentsOf: source.appendingPathComponent("Contents.json")))
            guard var contents = json as? [String: Any], let colors = contents["colors"] as? [[String: Any]] else {
                try place(source, at: target)
                return true
            }
            let defined = colors.filter { $0["color"] != nil }
            guard !defined.isEmpty else { return false }
            try place(source, at: target)
            contents["colors"] = defined
            try JSONSerialization.data(withJSONObject: contents).write(to: target.appendingPathComponent("Contents.json"))
            return true
        }

        for catalog in catalogs {
            if catalog.pathExtension == "icon" {
                // An Icon Composer .icon passed as its own catalog input
                // (SwiftBuild passes folder.iconcomposer.icon paths through).
                let name = catalog.deletingPathExtension().lastPathComponent
                if name == appIcon {
                    iconComposer = recordIconComposerIcon(catalog, appIcon: appIcon)
                } else if includeAllAppIcons || alternateAppIcons.contains(name) {
                    alternateIconComposers.append(
                        IconComposerCompiler.Input(name: name, directory: catalog, idioms: []))
                }
                continue
            }
            try copy(catalog, into: merged, catalog: catalog)
        }
        return Prepared(catalog: merged, skipped: skipped, iconComposer: iconComposer,
                        alternateIconComposers: alternateIconComposers)
    }

    /// Records an Icon Composer `.icon` as the layered app-icon input when
    /// `--app-icon` is set; the caller has already matched the name.
    /// Idioms are filled in by the caller from actool's --target-device flags.
    static func recordIconComposerIcon(
        _ icon: URL, appIcon: String?
    ) -> IconComposerCompiler.Input? {
        guard let appIcon else { return nil }
        return IconComposerCompiler.Input(name: appIcon, directory: icon, idioms: [])
    }
}
