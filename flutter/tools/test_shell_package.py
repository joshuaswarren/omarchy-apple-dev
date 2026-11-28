import json
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TOOL = TOOLS / "gen-shell-package.py"


def fixture(root, plugins_spec):
    """Build an app dir + plugin roots under root; return (app, out)."""
    app = Path(root) / "App"
    runner = app / "ios" / "Runner"
    runner.mkdir(parents=True)
    (runner / "AppDelegate.swift").write_text(
        "import UIKit\n@main class AppDelegate { /* GeneratedPluginRegistrant.register */ }\n")
    (runner / "Plain.swift").write_text("struct Plain {}\n")
    (runner / "GeneratedPluginRegistrant.h").write_text("// reg header\n")
    (runner / "GeneratedPluginRegistrant.m").write_text(
        "#import \"GeneratedPluginRegistrant.h\"\n"
        "#if __has_include(<keep_plug/KeepPlugPlugin.h>)\n"
        "#import <keep_plug/KeepPlugPlugin.h>\n"
        "#endif\n"
        "#if __has_include(<dev_plug/DevPlugPlugin.h>)\n"
        "#import <dev_plug/DevPlugPlugin.h>\n"
        "#endif\n"
        "@implementation GeneratedPluginRegistrant\n"
        "+ (void)registerWithRegistry {\n"
        "  [KeepPlugPlugin registerWithRegistrar:reg];\n"
        "  [DevPlugPlugin registerWithRegistrar:reg];\n"
        "}\n@end\n")
    deps = {"plugins": {"ios": plugins_spec}}
    (app / ".flutter-plugins-dependencies").write_text(json.dumps(deps))
    return app, Path(root) / "Out"


def plugin_root(root, name, manifest_body=None):
    pkg = Path(root) / "pkgsrc" / name / "darwin" / name
    pkg.mkdir(parents=True)
    body = manifest_body if manifest_body is not None else (
        "// swift-tools-version: 5.9\n"
        "import PackageDescription\n"
        "let package = Package(\n"
        f'  name: "{name}",\n'
        '  dependencies: [.package(name: "FlutterFramework", path: "../FlutterFramework")],\n'
        f'  products: [.library(name: "{name}Lib", targets: ["{name}"])],\n'
        f'  targets: [.target(name: "{name}", dependencies: [.product(name: "FlutterFramework", package: "FlutterFramework")])]\n'
        ")\n")
    (pkg / "Package.swift").write_text(body)
    return str(Path(root) / "pkgsrc" / name)


def run(app, out, min_ios="15.0"):
    return subprocess.run(["python3", str(TOOL), str(app), str(out), min_ios],
                          capture_output=True, text=True)


class ShellPackage(unittest.TestCase):
    def test_dev_and_pods_plugins_drop_out_of_the_registrant(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = plugin_root(tmp, "keep_plug")
            dev = plugin_root(tmp, "dev_plug")
            app, out = fixture(tmp, [
                {"name": "keep_plug", "path": keep},
                {"name": "dev_plug", "path": dev, "dev_dependency": True},
                {"name": "pod_plug", "path": "/nonexistent", "native_build": False},
            ])
            r = run(app, out)
            self.assertEqual(r.returncode, 0, r.stderr)
            reg = (out / "Sources/PluginRegistrant/GeneratedPluginRegistrant.m").read_text()
            self.assertIn("<keep_plug/KeepPlugPlugin.h>", reg)          # kept plugin's block stays
            self.assertIn("[KeepPlugPlugin registerWithRegistrar", reg)
            self.assertNotIn("dev_plug", reg)                            # dev plugin's block + call drop
            self.assertNotIn("DevPlugPlugin register", reg)

    def test_runner_sources_copy_and_swift_gets_the_module_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = plugin_root(tmp, "keep_plug")
            app, out = fixture(tmp, [{"name": "keep_plug", "path": keep}])
            self.assertEqual(run(app, out).returncode, 0)
            src = out / "Sources/Runner"
            self.assertTrue((src / "AppDelegate.swift").read_text().startswith("import PluginRegistrant\n"))
            self.assertFalse((src / "Plain.swift").read_text().startswith("import PluginRegistrant"))
            self.assertTrue((out / "Sources/PluginRegistrant/include/GeneratedPluginRegistrant.h").is_file())

    def test_flutter_framework_refs_scrub_from_the_copied_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = plugin_root(tmp, "keep_plug")
            app, out = fixture(tmp, [{"name": "keep_plug", "path": keep}])
            self.assertEqual(run(app, out).returncode, 0)
            scrubbed = (out / "Packages/keep_plug/Package.swift").read_text()
            self.assertNotIn("FlutterFramework", scrubbed)
            self.assertIn('.target(name: "keep_plug"', scrubbed)  # the target line survives
            self.assertTrue((out / "Packages/FlutterFramework/Package.swift").is_file())

    def test_generated_manifest_links_kept_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = plugin_root(tmp, "keep_plug")
            app, out = fixture(tmp, [{"name": "keep_plug", "path": keep}])
            self.assertEqual(run(app, out, "16.0").returncode, 0)
            manifest = (out / "Package.swift").read_text()
            self.assertIn('.iOS("16.0")', manifest)
            self.assertIn('.package(path: "Packages/keep_plug")', manifest)
            self.assertIn('.product(name: "keep_plugLib", package: "keep_plug")', manifest)

    def test_a_plugin_with_no_swift_package_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app, out = fixture(tmp, [{"name": "bare", "path": str(Path(tmp) / "pkgsrc/bare")}])
            r = run(app, out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("needs CocoaPods", r.stderr)

    def test_a_manifest_without_a_library_product_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plugin_root(tmp, "nolib", manifest_body="let package = Package(name: \"nolib\")\n")
            app, out = fixture(tmp, [{"name": "nolib", "path": root}])
            r = run(app, out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("no .library product", r.stderr)

    def test_an_unsupported_flutterframework_form_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = plugin_root(tmp, "split", manifest_body=(
                "let package = Package(\n"
                '  dependencies: [.product(name:\n    "FlutterFramework", package: "FF")],\n'
                '  products: [.library(name: "splitLib", targets: ["split"])],\n'
                ")\n"))
            app, out = fixture(tmp, [{"name": "split", "path": root}])
            r = run(app, out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("unsupported FlutterFramework reference", r.stderr)


class MachoAlignGate(unittest.TestCase):
    def test_self_test(self):
        r = subprocess.run(["python3", str(TOOLS / "macho-align.py"), "--self-test"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("self-test: ok", r.stdout)


if __name__ == "__main__":
    unittest.main()
