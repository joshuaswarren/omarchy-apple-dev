import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xcodeproj2xtool as xt

TOOL = Path(__file__).resolve().parent / "xcodeproj2xtool.py"


class SelfTestGate(unittest.TestCase):
    def test_the_modules_own_self_test_battery_still_passes(self):
        r = subprocess.run([sys.executable, str(TOOL), "--self-test"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("self-test passed", r.stdout)


class Helpers(unittest.TestCase):
    def test_c99_identifier(self):
        self.assertEqual(xt.c99_identifier("My-App"), "My_App")
        self.assertEqual(xt.c99_identifier("3d"), "_3d")
        self.assertEqual(xt.c99_identifier("a b.c"), "a_b_c")

    def test_bump_minor(self):
        self.assertEqual(xt.bump_minor("1.2.3"), "1.3.0")
        self.assertEqual(xt.bump_minor("1.9"), "1.10.0")
        self.assertEqual(xt.bump_minor("noversion"), "noversion")

    def test_package_label(self):
        self.assertEqual(xt.package_label("https://example.com/org/Repo.git"), "Repo")
        self.assertEqual(xt.package_label("https://example.com/org/Repo/"), "Repo")
        self.assertEqual(xt.package_label("local/pkg-name"), "pkg-name")

    def test_sw_sy_matches_swift_string_literal_rules(self):
        self.assertEqual(xt.sw_sy('a"b\\c'), '"a\\"b\\\\c"')


class AssetSymbolName(unittest.TestCase):
    def test_actool_word_rules(self):
        self.assertEqual(xt.asset_symbol_name("brand-blue"), "brandBlue")
        self.assertEqual(xt.asset_symbol_name("URL"), "url")
        self.assertEqual(xt.asset_symbol_name("Icons/Star"), "iconsStar")
        self.assertEqual(xt.asset_symbol_name("Café"), "café")
        self.assertEqual(xt.asset_symbol_name("2fast"), "_2fast")
        self.assertEqual(xt.asset_symbol_name("---"), "_")

    def test_unsure_codepoints_raise_with_the_rename_hint(self):
        with self.assertRaises(ValueError):
            xt.asset_symbol_name("́name")  # leading combining mark: Swift reads a property unicodedata lacks


class DirScans(unittest.TestCase):
    def test_dir_resource_kind_processes_only_known_subtrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertEqual(xt.dir_resource_kind(d), ".copy")
            (d / "x.txt").write_text("")
            self.assertEqual(xt.dir_resource_kind(d), ".copy")
            (d / "en.lproj").mkdir()
            (d / "en.lproj" / "Main.strings").write_text("")  # a .strings file is processable
            self.assertEqual(xt.dir_resource_kind(d), ".process")

    def test_dir_has_ib_and_has_swift(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertFalse(xt.dir_has_ib(d))
            self.assertFalse(xt.has_swift(d))
            (d / "Main.storyboard").write_text("")
            (d / "App.swift").write_text("")
            self.assertTrue(xt.dir_has_ib(d))
            self.assertTrue(xt.has_swift(d))


class LoadXcconfig(unittest.TestCase):
    def test_assignments_comments_and_includes_in_file_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "base.xcconfig").write_text(
                "// comment\nA = one\nB = two;\n#include \"child.xcconfig\"\nC = three\n")
            (d / "child.xcconfig").write_text("B = override\nD = four\n")
            s = xt.load_xcconfig(d / "base.xcconfig")
            self.assertEqual(s, {"A": "one", "B": "override", "D": "four", "C": "three"})

    def test_include_cycles_terminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.xcconfig").write_text('#include "b.xcconfig"\nA = 1')
            (d / "b.xcconfig").write_text('#include "a.xcconfig"\nB = 2')
            self.assertEqual(xt.load_xcconfig(d / "a.xcconfig"), {"B": "2", "A": "1"})


class ParsePbxproj(unittest.TestCase):
    def test_openstep_plist_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "project.pbxproj"
            p.write_text("""{
\trootObject = ABCDEF0123456789ABCDEF01;
\tobjects = {
\t\tABCDEF0123456789ABCDEF01 = {
\t\t\tisa = PBXProject;
\t\t\tname = "Demo App";
\t\t\ttargets = (ABCDEF0123456789ABCDEF02, );
\t\t};
\t};
\tarchiveVersion = 1;
\tobjectVersion = 56;
}""")
            doc = xt.parse_pbxproj(p)
            self.assertEqual(doc["rootObject"], "ABCDEF0123456789ABCDEF01")
            obj = doc["objects"]["ABCDEF0123456789ABCDEF01"]
            self.assertEqual((obj["isa"], obj["name"]), ("PBXProject", "Demo App"))
            self.assertEqual(obj["targets"], ["ABCDEF0123456789ABCDEF02"])
            self.assertEqual(doc["objectVersion"], "56")  # unquoted tokens stay strings


if __name__ == "__main__":
    unittest.main()
