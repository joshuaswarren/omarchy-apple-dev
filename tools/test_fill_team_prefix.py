import importlib.util
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TOOL = TOOLS / "fill-team-prefix.py"
_spec = importlib.util.spec_from_file_location("fill_team_prefix", TOOL)
ftp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ftp)


def plist(path, data):
    with open(path, "wb") as f:
        plistlib.dump(data, f)


def profile(tmp, prefix="ABCDE12345"):
    inner = plistlib.dumps({"ApplicationIdentifierPrefix": [prefix],
                            "TeamIdentifier": [prefix]})
    p = Path(tmp) / "dev.mobileprovision"
    p.write_bytes(b"CMS-HEADER" + inner + b"CMS-SIG")
    return p


class FillPlist(unittest.TestCase):
    def test_both_placeholders_nested_and_key_paths_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Info.plist"
            plist(p, {
                "CFBundleURLTypes": [{"CFBundleURLSchemes": ["$(AppIdentifierPrefix)app"]}],
                "Entitlements": {"keychain-access-groups": ["$(TeamIdentifierPrefix)shared"],
                                 "other": 3},
                "Plain": "untouched",
            })
            filled = ftp.fill_plist(p, "Z6P74P6T99")
            with open(p, "rb") as f:
                got = plistlib.load(f)
            self.assertEqual(got["CFBundleURLTypes"][0]["CFBundleURLSchemes"],
                             ["Z6P74P6T99.app"])
            self.assertEqual(got["Entitlements"]["keychain-access-groups"],
                             ["Z6P74P6T99.shared"])
            self.assertEqual(got["Plain"], "untouched")
            self.assertIn("CFBundleURLTypes[0].CFBundleURLSchemes[0]", filled)
            self.assertIn("Entitlements.keychain-access-groups[0]", filled)

    def test_no_placeholder_leaves_the_file_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "Info.plist"
            plist(p, {"A": "$(NotAPlaceholder)x"})
            before = p.read_bytes()
            self.assertEqual(ftp.fill_plist(p, "Z6P74P6T99"), [])
            self.assertEqual(p.read_bytes(), before)


class TeamFromProfile(unittest.TestCase):
    def test_reads_the_embedded_plist(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ftp.team_from_profile(profile(tmp)), "ABCDE12345")
            p = Path(tmp) / "empty.mobileprovision"
            inner = plistlib.dumps({"Name": "no team"})
            p.write_bytes(b"H" + inner + b"S")
            with self.assertRaises(SystemExit):
                ftp.team_from_profile(p)


class BundlePlists(unittest.TestCase):
    def test_bundle_plus_appex(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "App.app"
            appex = bundle / "PlugIns" / "W.appex"
            appex.mkdir(parents=True)
            plist(bundle / "Info.plist", {"A": 1})
            plist(appex / "Info.plist", {"B": 2})
            got = ftp.bundle_plists(bundle)
            self.assertEqual(len(got), 2)
            self.assertTrue(got[0].name == "Info.plist")

    def test_xtool_adapter_lists_info_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "App.app"
            ext = bundle / "Ext.appex"
            ext.mkdir(parents=True)
            plist(bundle / "Info.plist", {"A": 1})
            plist(ext / "Info.plist", {"B": 2})
            (bundle / "xtool.yml").write_text(
                "extensions:\ninfoPath: Ext.appex/Info.plist\n")
            got = ftp.bundle_plists(bundle)
            self.assertIn(bundle / "Info.plist", got)
            self.assertIn(bundle / "Ext.appex/Info.plist", got)


class Cli(unittest.TestCase):
    def test_team_flag_fills_the_whole_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "App.app"
            appex = bundle / "PlugIns" / "W.appex"
            appex.mkdir(parents=True)
            plist(bundle / "Info.plist", {"K": "$(AppIdentifierPrefix)a"})
            plist(appex / "Info.plist", {"K": "$(TeamIdentifierPrefix)b"})
            r = subprocess.run([sys.executable, str(TOOL), str(bundle), "--team", "Z6P74P6T99"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(bundle / "Info.plist", "rb") as f:
                self.assertEqual(plistlib.load(f)["K"], "Z6P74P6T99.a")
            with open(appex / "Info.plist", "rb") as f:
                self.assertEqual(plistlib.load(f)["K"], "Z6P74P6T99.b")

    def test_profile_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "App.app"
            bundle.mkdir()
            plist(bundle / "Info.plist", {"K": "$(AppIdentifierPrefix)a"})
            r = subprocess.run([sys.executable, str(TOOL), str(bundle),
                                "--profile", str(profile(tmp))],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(bundle / "Info.plist", "rb") as f:
                self.assertEqual(plistlib.load(f)["K"], "ABCDE12345.a")


if __name__ == "__main__":
    unittest.main()
