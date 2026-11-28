#!/usr/bin/env python3
"""The sdk-free shims that parse real files: lipo/otool read Mach-O headers
and load commands, xcrun translates SDK queries, and the small sdk-free tools
(fixplist, setmin, features) rewrite plists and CMake text."""
import json
import os
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHIMS = ROOT / "shims"
FAT, MH_MAGIC_64 = 0xCAFEBABE, 0xFEEDFACF
ARM64, X86_64 = 0x0100000C, 0x01000007


def run(path, *args, env=None, cwd=None):
    merged = {**os.environ, **(env or {})}
    return subprocess.run([str(path), *map(str, args)],
                          capture_output=True, text=True, env=merged, cwd=cwd)


def dylib_command(cmd, name):
    blob = struct.pack("<IIIIII", cmd, 0, 24, 0, 0, 0) + name.encode() + b"\0"
    blob = blob[:4] + struct.pack("<I", len(blob)) + blob[8:]
    return blob


def thin_macho(cpu=ARM64, commands=()):
    body = b"".join(commands)
    header = struct.pack("<IIIIIIII", MH_MAGIC_64, cpu, 0, 2,
                         len(commands), len(body), 0, 0)
    return header + body


def fat_macho(slices):
    """slices: [(cpu, bytes)]. Returns the fat file's bytes."""
    header = struct.pack(">II", FAT, len(slices))
    entries, offset = b"", 8 + 20 * len(slices)
    for cpu, data in slices:
        entries += struct.pack(">iiIII", cpu, 0, offset, len(data), 0)
        offset += len(data)
    return header + entries + b"".join(data for _c, data in slices)


class LipoShim(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.arm = thin_macho(ARM64)
        self.x86 = thin_macho(X86_64)
        self.fat = self.dir / "fat.dylib"
        self.fat.write_bytes(fat_macho([(X86_64, self.x86),
                                        (ARM64, self.arm)]))

    def test_info_and_archs(self):
        r = run(SHIMS / "lipo", "-info", self.fat)
        self.assertEqual(r.returncode, 0)
        self.assertIn("x86_64 arm64", r.stdout)
        r = run(SHIMS / "lipo", "-archs", self.fat)
        self.assertEqual(r.stdout.strip(), "x86_64 arm64")

    def test_verify_arch(self):
        r = run(SHIMS / "lipo", self.fat, "-verify_arch", "arm64")
        self.assertEqual(r.returncode, 0)
        r = run(SHIMS / "lipo", self.fat, "-verify_arch", "armv7")
        self.assertEqual(r.returncode, 1)

    def test_thin_extracts_its_slice(self):
        out = self.dir / "thin.dylib"
        r = run(SHIMS / "lipo", "-thin", "arm64", "-output", out, self.fat)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out.read_bytes(), self.arm)
        r = run(SHIMS / "lipo", "-thin", "armv7", "-output", out, self.fat)
        self.assertNotEqual(r.returncode, 0)

    def test_thin_input_and_non_macho(self):
        thin = self.dir / "thin.dylib"
        thin.write_bytes(self.arm)
        r = run(SHIMS / "lipo", "-info", thin)
        self.assertIn("Non-fat file", r.stdout)
        bad = self.dir / "junk.bin"
        bad.write_bytes(b"not a macho")
        r = run(SHIMS / "lipo", "-info", bad)
        self.assertNotEqual(r.returncode, 0)


class OtoolShim(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.lib = thin_macho(ARM64, [
            dylib_command(0xD, "/usr/lib/libmine.dylib"),      # LC_ID_DYLIB
            dylib_command(0xC, "/usr/lib/libdep.dylib"),       # LC_LOAD_DYLIB
            dylib_command(0x80000018, "/usr/lib/libweak.dylib"),
        ])
        self.thin = self.dir / "libmine.dylib"
        self.thin.write_bytes(self.lib)

    def test_d_install_name(self):
        r = run(SHIMS / "otool", "-D", self.thin)
        self.assertEqual(r.returncode, 0)
        self.assertIn("/usr/lib/libmine.dylib", r.stdout)

    def test_L_lists_load_commands(self):
        r = run(SHIMS / "otool", "-L", self.thin)
        self.assertEqual(r.returncode, 0)
        for name in ("libmine", "libdep", "libweak"):
            self.assertIn(name, r.stdout)

    def test_fat_reads_the_arm64_slice(self):
        x86 = thin_macho(X86_64, [dylib_command(0xD, "x86-lib")])
        arm = thin_macho(ARM64, [dylib_command(0xD, "arm64-lib")])
        fat = self.dir / "fat.dylib"
        fat.write_bytes(fat_macho([(X86_64, x86), (ARM64, arm)]))
        r = run(SHIMS / "otool", "-D", fat)
        self.assertEqual(r.returncode, 0)
        self.assertIn("arm64-lib", r.stdout)
        self.assertNotIn("x86-lib", r.stdout)


class XcrunShim(unittest.TestCase):
    def test_show_sdk_path(self):
        r = run(SHIMS / "xcrun", "--sdk", "iphoneos", "--show-sdk-path",
                env={"NOSDK_SYSROOT": "/tmp/fake-sysroot"})
        self.assertEqual(r.stdout.strip(), "/tmp/fake-sysroot")

    def test_find_prefers_shim_sibling(self):
        r = run(SHIMS / "xcrun", "--find", "clang")
        self.assertEqual(Path(r.stdout.strip()).name, "clang-darwin")
        r = run(SHIMS / "xcrun", "--find", "no-such-tool-xyz")
        self.assertNotEqual(r.returncode, 0)

    def test_shim_log(self):
        log = Path(tempfile.mkdtemp()) / "calls.log"
        run(SHIMS / "xcrun", "--find", "clang",
            env={"XCRUN_SHIM_LOG": str(log)})
        self.assertIn("xcrun --find clang", log.read_text())

    def test_codesign_is_a_noop(self):
        r = run(SHIMS / "xcrun", "codesign", "--sign", "-", "app")
        self.assertEqual(r.returncode, 0)


class SmallTools(unittest.TestCase):
    def test_fixplist_strips_module_name(self):
        tmp = Path(tempfile.mkdtemp())
        src, out = tmp / "in.plist", tmp / "out.plist"
        src.write_bytes(plistlib.dumps({
            "UIMainStoryboardFile": "Main",
            "CFBundleDocumentTypes": [{"CFBundleTypeRole": "Editor",
                                       "LSItemContentTypes": ["$(PRODUCT_MODULE_NAME).doc"]}],
            "NSPrincipalClass": "$(PRODUCT_MODULE_NAME).App",
        }))
        r = subprocess.run([sys.executable, str(ROOT / "fixplist.py"),
                            src, out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        fixed = plistlib.loads(out.read_bytes())
        self.assertEqual(fixed["NSPrincipalClass"], "App")
        self.assertEqual(fixed["CFBundleDocumentTypes"][0]
                         ["LSItemContentTypes"], ["doc"])
        self.assertEqual(fixed["UIMainStoryboardFile"], "Main")

    def test_setmin_sets_minimum_version(self):
        root = Path(tempfile.mkdtemp())
        for name in ("One", "Two"):
            fw = root / f"{name}.framework"
            fw.mkdir()
            with open(fw / "Info.plist", "wb") as f:
                plistlib.dump({"CFBundleName": name}, f)
        r = subprocess.run([sys.executable, str(ROOT / "setmin.py"),
                            root, "13.0"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("One", "Two"):
            info = plistlib.loads(
                (root / f"{name}.framework" / "Info.plist").read_bytes())
            self.assertEqual(info["MinimumOSVersion"], "13.0")

    def test_features_reads_cmake_flags(self):
        src = Path(tempfile.mkdtemp())
        (src / "stdlib").mkdir()
        (src / "stdlib" / "a.cmake").write_text(
            'list(APPEND flags "-enable-experimental-feature" "NewThing")\n'
            '"-enable-upcoming-feature" "OtherThing" '
            '"-enable-experimental-feature" "Embedded" '
            '"-enable-library-evolution"\n')
        r = subprocess.run([sys.executable,
                            str(ROOT / "swift" / "features.py"), src,
                            "a.cmake"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        lines = r.stdout.splitlines()
        pairs = list(zip(lines[::2], lines[1::2]))
        self.assertIn(("-enable-experimental-feature", "NewThing"), pairs)
        self.assertIn(("-enable-upcoming-feature", "OtherThing"), pairs)
        self.assertNotIn("Embedded", r.stdout)  # Embedded is filtered out
        self.assertNotIn("library-evolution", r.stdout)


if __name__ == "__main__":
    unittest.main()
