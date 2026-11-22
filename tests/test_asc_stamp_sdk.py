"""stamp-sdk: the device path writes the real SDK version into LC_BUILD_VERSION.

Issue 170: the Linux link writes the deployment target into LC_BUILD_VERSION's
sdk field, so iOS 26+ runs a --device build in compatibility mode. Before the
fix the device path never patched that field, so this test fails on it: the
binary's sdk still reads the deployment target (16.0.0) instead of the SDK the
build actually used.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ASC = Path(__file__).resolve().parents[1] / "tools/asc.py"
XTOOL_SDK = "Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
SDK_VERSION = "27.1"


def macho(minos, sdk):
    """Thin arm64 MH_EXECUTE with one iOS LC_BUILD_VERSION (platform 2)."""
    return (struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 1, 24, 0, 0)
            + struct.pack("<6I", 0x32, 24, 2, minos, sdk, 0))


def read_lc_build_version(data):
    """(minos, sdk) raw fields of the first iOS LC_BUILD_VERSION, or None."""
    if data[:4] != b"\xcf\xfa\xed\xfe":
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        if cmd == 0x32 and struct.unpack_from("<I", data, off + 8)[0] == 2:
            return struct.unpack_from("<2I", data, off + 12)
        off += size
    return None


class StampSdkTest(unittest.TestCase):
    def run_stamp_sdk(self, extra_files=()):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            sdk = home / "sdk" / XTOOL_SDK
            sdk.mkdir(parents=True)
            (sdk / "SDKSettings.json").write_text(json.dumps({
                "Version": SDK_VERSION, "CanonicalName": "iphoneos" + SDK_VERSION,
            }))
            app = home / "Example.app"
            app.mkdir()
            # Deployment target 16.0.0 written into BOTH fields, as the Linux
            # link leaves a build against the 27.1 SDK (issue 170's dump).
            binary = app / "Example"
            binary.write_bytes(macho(0x00100000, 0x00100000))
            extra = []
            for name in extra_files:
                path = app / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(macho(0x00100000, 0x00100000))
                extra.append(path)
            # env inherits PYTHONPATH: run the suite with a cryptography that
            # imports cleanly (a venv) - this host has a rogue typing.py in
            # the user site that breaks cryptography under swapped HOME.
            env = dict(os.environ, HOME=tmp, DARWIN_SDK=str(home / "sdk"))
            done = subprocess.run(
                [sys.executable, str(ASC), "stamp-sdk", str(app)],
                env=env, capture_output=True, text=True, timeout=20, check=False,
            )
            raw = read_lc_build_version(binary.read_bytes())
            extras = [read_lc_build_version(p.read_bytes()) for p in extra]
            return done, raw, extras

    def test_device_binary_gets_the_real_sdk_version(self):
        """The sdk field moves from the deployment target to the SDK; minos stays.

        Before the fix this fails: the device path never patched the field, so
        sdk still read 16.0.0 and iOS 26 kept the compatibility-mode design.
        """
        done, raw, _ = self.run_stamp_sdk()
        self.assertEqual(done.returncode, 0, done.stderr)
        major, minor = (int(p) for p in SDK_VERSION.split("."))
        expected = major << 16 | minor << 8
        minos, sdk = raw
        self.assertEqual(minos, 0x00100000, "deployment target must stay 16.0.0")
        self.assertEqual(sdk, expected, f"sdk field must read {SDK_VERSION}")

    def test_every_macho_in_the_bundle_is_patched(self):
        """Extensions ship their own binaries; each one carries the mode switch."""
        done, raw, extras = self.run_stamp_sdk(
            extra_files=("PlugIns/Widget.appex/Widget",))
        self.assertEqual(done.returncode, 0, done.stderr)
        major, minor = (int(p) for p in SDK_VERSION.split("."))
        expected = major << 16 | minor << 8
        for minos, sdk in [raw, *extras]:
            self.assertEqual(minos, 0x00100000)
            self.assertEqual(sdk, expected)

    def test_non_macho_files_are_left_alone(self):
        """A plist or asset catalog in the bundle must not be rewritten."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            sdk = home / "sdk" / XTOOL_SDK
            sdk.mkdir(parents=True)
            (sdk / "SDKSettings.json").write_text(json.dumps({
                "Version": SDK_VERSION, "CanonicalName": "iphoneos" + SDK_VERSION,
            }))
            app = home / "Example.app"
            app.mkdir()
            payload = b"Bplist00-not-a-mach-o-payload"
            (app / "Info.plist").write_bytes(payload)
            # env inherits PYTHONPATH: run the suite with a cryptography that
            # imports cleanly (a venv) - this host has a rogue typing.py in
            # the user site that breaks cryptography under swapped HOME.
            env = dict(os.environ, HOME=tmp, DARWIN_SDK=str(home / "sdk"))
            done = subprocess.run(
                [sys.executable, str(ASC), "stamp-sdk", str(app)],
                env=env, capture_output=True, text=True, timeout=20, check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((app / "Info.plist").read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
