import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent.parent / "tools"))

import importlib.util

import xcode_settings as xs

_spec = importlib.util.spec_from_file_location("gen_extensions", TOOLS / "gen-extensions.py")
ge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ge)


class FakeSettings:
    def __init__(self, values):
        self.values = values
    def raw(self, name):
        return self.values.get(name)
    def value(self, name):
        return self.values.get(name, "")


class Expand(unittest.TestCase):
    def test_names_expand_recursively_through_lookup(self):
        lookup = lambda n: {"A": "x", "B": "$(A)-y", "C": ""}[n]
        self.assertEqual(xs.expand("pre $(B) post", lookup), "pre x-y post")
        self.assertEqual(xs.expand("$(C)", lookup), "")

    def test_self_reference_substitutes_empty_with_a_warning(self):
        lookup = lambda n: {"A": "$(A)", "B": "$(B)$(A)"}[n]
        self.assertEqual(xs.expand("$(A)", lookup), "")
        self.assertEqual(xs.expand("$(B)", lookup), "")


class ReadXcconfig(unittest.TestCase):
    def test_settings_include_and_inherited_stripping(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.xcconfig").write_text(
                "// comment\nA = one // trailing\nB = $(inherited) two\n#include \"b.xcconfig\"\n")
            (d / "b.xcconfig").write_text("C = $() three\n")
            s = xs.read_xcconfig(str(d / "a.xcconfig"), {})
            self.assertEqual(s, {"A": "one", "B": "two", "C": "three"})


class Schemes(unittest.TestCase):
    def test_shared_and_user_schemes_or_the_runner_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "Runner.xcodeproj"
            self.assertEqual(xs.schemes(tmp), ["Runner"])
            (proj / "xcshareddata" / "xcschemes").mkdir(parents=True)
            (proj / "xcshareddata" / "xcschemes" / "App.xcscheme").write_text("")
            (proj / "xcuserdata" / "u.xcuserdatad" / "xcschemes").mkdir(parents=True)
            (proj / "xcuserdata" / "u.xcuserdatad" / "xcschemes" / "Dev.xcscheme").write_text("")
            self.assertEqual(xs.schemes(tmp), ["App", "Dev"])


class SettingsValue(unittest.TestCase):
    def test_an_unresolved_setting_exits_rather_than_ship_a_lie(self):
        self.assertEqual(ge.settings_value(FakeSettings({"X": "v"}), "X", "ext"), "v")
        with self.assertRaises(SystemExit):
            ge.settings_value(FakeSettings({"X": "$(UNSET)-v"}), "X", "ext")
        with self.assertRaises(SystemExit):
            ge.settings_value(FakeSettings({}), "X", "ext")


class VersionKey(unittest.TestCase):
    def test_numeric_components_or_zero(self):
        self.assertEqual(ge.version_key("26.1.2"), [26, 1, 2])
        self.assertEqual(ge.version_key("beta3"), [3])
        self.assertEqual(ge.version_key("noversion"), [0])


class ExpandPlist(unittest.TestCase):
    def test_nested_values_expand_from_settings_then_defaults(self):
        settings = FakeSettings({"PRODUCT_NAME": "WidgetExt"})
        defaults = {"EXECUTABLE_NAME": "WidgetExt", "CFBundleVersion": "1"}
        plist = {"CFBundleExecutable": "$(EXECUTABLE_NAME)",
                 "NSExtension": {"NSExtensionPrincipalClass": "$(PRODUCT_NAME).Widget",
                                 "NSExtensionAttributes": ["$(CFBundleVersion)", 7, True]}}
        out = ge.expand_plist(plist, settings, "WidgetExt", defaults)
        self.assertEqual(out["CFBundleExecutable"], "WidgetExt")
        self.assertEqual(out["NSExtension"]["NSExtensionPrincipalClass"], "WidgetExt.Widget")
        self.assertEqual(out["NSExtension"]["NSExtensionAttributes"], ["1", 7, True])

    def test_team_prefixes_survive_expansion_untouched(self):
        out = ge.expand_plist("$(AppIdentifierPrefix)net.x.app", FakeSettings({}), "e", {})
        self.assertEqual(out, "$(AppIdentifierPrefix)net.x.app")

    def test_an_undefined_variable_stops_the_build(self):
        with self.assertRaises(SystemExit):
            ge.expand_plist("$(MISSING)", FakeSettings({}), "e", {})


class PlistDefaults(unittest.TestCase):
    def test_xcodes_own_set_for_an_extension_target(self):
        gen = type("G", (), {"project": {"developmentRegion": "en"}})()
        d = ge.plist_defaults(gen, "My-Ext")
        self.assertEqual(d["PRODUCT_MODULE_NAME"], "My_Ext")
        self.assertEqual(d["PRODUCT_BUNDLE_PACKAGE_TYPE"], "XPC!")


class FixPlist(unittest.TestCase):
    def test_module_prefixes_strip_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.plist"
            with open(src, "wb") as f:
                plistlib.dump({"NSPrincipalClass": "$(PRODUCT_MODULE_NAME).App",
                               "List": ["$(PRODUCT_MODULE_NAME).X", "keep"],
                               "Nested": {"V": "$(PRODUCT_MODULE_NAME).Y", "N": 3}}, f)
            out = Path(tmp) / "out.plist"
            r = subprocess.run([sys.executable, str(TOOLS.parent.parent / "sdk-free/fixplist.py"),
                                str(src), str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as f:
                got = plistlib.load(f)
            self.assertEqual(got["NSPrincipalClass"], "App")
            self.assertEqual(got["List"], ["X", "keep"])
            self.assertEqual(got["Nested"], {"V": "Y", "N": 3})


class SetMin(unittest.TestCase):
    def test_every_framework_info_plist_gets_the_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("A.framework", "B.framework"):
                (root / name).mkdir()
                with open(root / name / "Info.plist", "wb") as f:
                    plistlib.dump({"CFBundleName": name.split(".")[0]}, f)
            r = subprocess.run([sys.executable, str(TOOLS.parent.parent / "sdk-free/setmin.py"),
                                str(root), "15.0"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for name in ("A.framework", "B.framework"):
                with open(root / name / "Info.plist", "rb") as f:
                    self.assertEqual(plistlib.load(f)["MinimumOSVersion"], "15.0")
            self.assertIn("A.framework", r.stdout)


if __name__ == "__main__":
    unittest.main()
