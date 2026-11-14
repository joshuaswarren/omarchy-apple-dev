"""Stamp the real app plist with either SDK layout; no SDK download or device needed."""
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ASC = Path(__file__).resolve().parents[1] / "tools/asc.py"
XTOOL = "Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"


class StampLayouts(unittest.TestCase):
    def run_stamp(self, layouts):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            sdk_root = home / "sdk"
            sdk_root.mkdir()
            for layout in layouts:
                sdk = sdk_root / (XTOOL if layout.startswith("xtool") else "iPhoneOS.sdk")
                sdk.mkdir(parents=True)
                if layout == "xtool-broken":
                    continue
                version, build = ("27.1", "XTOOL1") if layout == "xtool" else ("27.2", "FLAT1")
                (sdk / "SDKSettings.json").write_text(json.dumps({
                    "Version": version, "CanonicalName": "iphoneos" + version,
                }))
                core = sdk / "System/Library/CoreServices"
                core.mkdir(parents=True)
                (core / "SystemVersion.plist").write_bytes(plistlib.dumps({
                    "ProductBuildVersion": build,
                }))
            app = home / "Example.app"
            app.mkdir()
            info_path = app / "Info.plist"
            original = plistlib.dumps({
                "CFBundleIdentifier": "org.example.stamp",
                "CFBundleShortVersionString": "1.2.3",
                "UnrelatedKey": "preserved",
            })
            info_path.write_bytes(original)
            env = dict(os.environ, HOME=tmp, DARWIN_SDK=str(sdk_root),
                       XCODE_VERSION="27.0", XCODE_BUILD="27A266a")
            done = subprocess.run(
                [sys.executable, str(ASC), "stamp", str(app), "42"],
                env=env, capture_output=True, text=True, timeout=20, check=False,
            )
            return done, info_path.read_bytes(), original

    def assert_stamp(self, layouts, version, build):
        done, raw, _ = self.run_stamp(layouts)
        self.assertEqual(done.returncode, 0, done.stderr)
        info = plistlib.loads(raw)
        expected = {
            "CFBundleVersion": "42",
            "DTPlatformVersion": version,
            "DTPlatformBuild": build,
            "DTSDKName": "iphoneos" + version,
            "DTSDKBuild": build,
            "DTXcode": "2700",
            "DTXcodeBuild": "27A266a",
            "UnrelatedKey": "preserved",
            "CFBundleIdentifier": "org.example.stamp",
            "CFBundleShortVersionString": "1.2.3",
        }
        for key, value in expected.items():
            self.assertEqual(info[key], value, key)

    def test_xtool_layout(self):
        self.assert_stamp(("xtool",), "27.1", "XTOOL1")

    def test_flat_layout(self):
        self.assert_stamp(("flat",), "27.2", "FLAT1")

    def test_xtool_wins_when_both_exist(self):
        self.assert_stamp(("xtool", "flat"), "27.1", "XTOOL1")

    def test_broken_xtool_does_not_silently_use_flat(self):
        done, raw, original = self.run_stamp(("xtool-broken", "flat"))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SDKSettings.json", done.stderr)
        self.assertIn(XTOOL, done.stderr)
        self.assertEqual(raw, original)

    def test_missing_layout_does_not_modify_app(self):
        done, raw, original = self.run_stamp(())
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SDKSettings.json", done.stderr)
        self.assertEqual(raw, original)


if __name__ == "__main__":
    unittest.main()
