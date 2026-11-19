"""Stamp the real app plist with either SDK layout; no SDK download or device needed."""
import json
import os
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ASC = Path(__file__).resolve().parents[1] / "tools/asc.py"
XTOOL = "Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
# Thin arm64 MH_EXECUTE with one iOS LC_BUILD_VERSION (minos 17.0, sdk 26.0).
MACHO = (struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 1, 24, 0, 0)
         + struct.pack("<6I", 0x32, 24, 2, 0x00110000, 0x001A0000, 0))


class StampLayouts(unittest.TestCase):
    def run_stamp(self, layouts, version=None):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            sdk_root = home / "sdk"
            sdk_root.mkdir()
            for layout in layouts:
                sdk = sdk_root / (XTOOL if layout.startswith("xtool") else "iPhoneOS.sdk")
                if layout == "xtool-file":
                    sdk.parent.mkdir(parents=True)
                    sdk.write_text("not a directory")
                    continue
                if layout == "xtool-dangling":
                    sdk.parent.mkdir(parents=True)
                    sdk.symlink_to(home / "missing-sdk")
                    continue
                sdk.mkdir(parents=True)
                if layout == "xtool-broken":
                    continue
                sdk_version, build = ("27.1", "XTOOL1") if layout.startswith("xtool") else ("27.2", "FLAT1")
                if layout.endswith("-bad-version"):
                    sdk_version = "bad"
                sdk_version = version or sdk_version
                (sdk / "SDKSettings.json").write_text(json.dumps({
                    "Version": sdk_version, "CanonicalName": "iphoneos" + sdk_version,
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
            (app / "Example").write_bytes(MACHO)
            env = dict(os.environ, HOME=tmp, DARWIN_SDK=str(sdk_root),
                       XCODE_VERSION="27.0", XCODE_BUILD="27A266a")
            done = subprocess.run(
                [sys.executable, str(ASC), "stamp", str(app), "42"],
                env=env, capture_output=True, text=True, timeout=20, check=False,
            )
            return done, info_path.read_bytes(), original, (app / "Example").read_bytes()

    def assert_stamp(self, layouts, version, build):
        done, raw, _, macho = self.run_stamp(layouts)
        self.assertEqual(done.returncode, 0, done.stderr)
        major, minor = (int(p) for p in version.split("."))
        self.assertEqual(struct.unpack_from("<I", macho, 32 + 16)[0], major << 16 | minor << 8)
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
        done, raw, original, _ = self.run_stamp(("xtool-broken", "flat"))
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SDKSettings.json", done.stderr)
        self.assertIn(XTOOL, done.stderr)
        self.assertEqual(raw, original)

    def test_missing_layout_does_not_modify_app(self):
        done, raw, original, _ = self.run_stamp(())
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SDKSettings.json", done.stderr)
        self.assertEqual(raw, original)

    def test_malformed_version_does_not_modify_app(self):
        for layout in ("xtool-bad-version", "flat-bad-version"):
            with self.subTest(layout=layout):
                done, raw, original, _ = self.run_stamp((layout,))
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("ValueError", done.stderr)
                self.assertEqual(raw, original)

    def test_non_directory_xtool_does_not_silently_use_flat(self):
        for layout in ("xtool-file", "xtool-dangling"):
            with self.subTest(layout=layout):
                done, raw, original, _ = self.run_stamp((layout, "flat"))
                self.assertNotEqual(done.returncode, 0)
                self.assertIn(XTOOL, done.stderr)
                self.assertEqual(raw, original)

    def test_out_of_range_version_does_not_modify_app(self):
        for version in ("65536", "-1", "27.256", "27.1.256"):
            with self.subTest(version=version):
                done, raw, original, macho = self.run_stamp(("flat",), version)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("Version", done.stderr)
                self.assertEqual(raw, original)
                self.assertEqual(macho, MACHO)


class SdkVersionDevice(unittest.TestCase):
    """asc.py sdk-version, the device build's step: the Mach-O sdk field only, no App Store keys."""

    def run_sdk_version(self, version="27.1", with_sdk=True):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            sdk_root = home / "sdk"
            if with_sdk:
                sdk = sdk_root / XTOOL
                sdk.mkdir(parents=True)
                (sdk / "SDKSettings.json").write_text(json.dumps({
                    "Version": version, "CanonicalName": "iphoneos" + version,
                }))
            app = home / "Example.app"
            framework = app / "Frameworks/Lib.framework"
            framework.mkdir(parents=True)
            original = plistlib.dumps({"CFBundleIdentifier": "org.example.device"})
            (app / "Info.plist").write_bytes(original)
            (app / "Example").write_bytes(MACHO)
            (framework / "Lib").write_bytes(MACHO)
            (app / "notes.txt").write_text("not a Mach-O")
            # No SystemVersion.plist and no Xcode version: stamp would stop, sdk-version must not.
            env = {k: v for k, v in os.environ.items() if k not in ("XCODE_VERSION", "XCODE_BUILD")}
            env.update(HOME=tmp, DARWIN_SDK=str(sdk_root))
            done = subprocess.run(
                [sys.executable, str(ASC), "sdk-version", str(app)],
                env=env, capture_output=True, text=True, timeout=20, check=False,
            )
            return (done, (app / "Info.plist").read_bytes(), original,
                    (app / "Example").read_bytes(), (framework / "Lib").read_bytes(),
                    (app / "notes.txt").read_text())

    def test_writes_the_sdk_into_every_macho(self):
        done, raw, original, app_bin, lib_bin, notes = self.run_sdk_version()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Mach-O sdk 27.1 in 2 file(s)", done.stdout)
        for binary in (app_bin, lib_bin):
            self.assertEqual(struct.unpack_from("<I", binary, 32 + 16)[0], 27 << 16 | 1 << 8)
            # minos is left alone
            self.assertEqual(struct.unpack_from("<I", binary, 32 + 12)[0], 0x00110000)
        self.assertEqual(raw, original)
        self.assertEqual(notes, "not a Mach-O")

    def test_missing_sdk_leaves_the_app(self):
        done, raw, original, app_bin, lib_bin, _ = self.run_sdk_version(with_sdk=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SDKSettings.json", done.stderr)
        self.assertEqual((app_bin, lib_bin, raw), (MACHO, MACHO, original))

    def test_out_of_range_version_leaves_the_app(self):
        done, _, _, app_bin, lib_bin, _ = self.run_sdk_version(version="27.256")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Version", done.stderr)
        self.assertEqual((app_bin, lib_bin), (MACHO, MACHO))

    def test_ship_device_path_runs_it(self):
        ship = (Path(__file__).resolve().parents[1] / "ship.sh").read_text()
        device = ship[ship.index('if [ "$device" = 1 ]; then'):]
        device = device[:device.index("  exit 0\n")]
        self.assertIn('"$PY" "$ASC" sdk-version "$app"', device)


if __name__ == "__main__":
    unittest.main()
