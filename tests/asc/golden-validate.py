#!/usr/bin/env python3
"""Golden test for `tools/asc.py validate` on a synthetic .ipa.

Builds Payload/Fixture.app inside a temp dir (Info.plist + a hand-made thin
arm64 Mach-O, no Apple-derived data), runs validate with a stub `rcodesign` on
PATH (this fixture has no Frameworks/ and no embedded.mobileprovision, so the
stub only satisfies the which() probe and never executes), and compares the
sorted PASS/FAIL lines to golden/validate-lines.txt. Regenerate the golden with
--regen after an intentional behavior change.
"""
import os
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASC = HERE.parent.parent / "tools" / "asc.py"
GOLDEN = HERE / "golden" / "validate-lines.txt"


def macho_exe():
    """Thin arm64 MH_EXECUTE, MH_PIE, LC_BUILD_VERSION (iOS 17.0 / SDK 26.0), unsigned."""
    header = struct.pack(
        "<8I",
        0xFEEDFACF,      # magic
        0x0100000C,      # cputype arm64
        0,               # cpusubtype
        2,               # filetype MH_EXECUTE
        1,               # ncmds
        24,              # sizeofcmds
        0x200000,        # flags MH_PIE
        0,               # reserved
    )
    lc = struct.pack("<6I", 0x32, 24, 2, 0x00110000, 0x001A0000, 0)
    return header + lc


def build_ipa(path):
    info = {
        "CFBundleIdentifier": "dev.omarchy.fixture",
        "CFBundleExecutable": "Fixture",
        "CFBundleName": "Fixture",
        "CFBundleShortVersionString": "1.2",
        "CFBundleVersion": "3",
        "CFBundlePackageType": "APPL",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "CFBundleInfoDictionaryVersion": "6.0",
        "MinimumOSVersion": "17.0",
        "UIDeviceFamily": [1],
        "UIRequiredDeviceCapabilities": ["arm64"],
        "CFBundleIcons": {"CFBundlePrimaryIcon": {"CFBundleIconName": "AppIcon"}},
        "UILaunchScreen": {},
        "DTCompiler": "com.apple.compilers.llvm.clang.1_0",
        "DTPlatformBuild": "27A266a",
        "DTPlatformName": "iphoneos",
        "DTPlatformVersion": "27.0",
        "DTSDKBuild": "27A266a",
        "DTSDKName": "iphoneos27.0",
        "DTXcode": "2700",
        "DTXcodeBuild": "27A266a",
    }
    import plistlib
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Payload/", "")
        z.writestr("Payload/Fixture.app/Info.plist",
                   plistlib.dumps(info, sort_keys=True))
        z.writestr("Payload/Fixture.app/Fixture", macho_exe())


def main():
    regen = "--regen" in sys.argv
    with tempfile.TemporaryDirectory(prefix="asc-golden-") as tmp:
        ipa = Path(tmp) / "Fixture.ipa"
        build_ipa(ipa)
        stub = Path(tmp) / "bin"
        stub.mkdir()
        (stub / "rcodesign").write_text("#!/bin/sh\nexit 3\n")
        os.chmod(stub / "rcodesign", 0o755)
        env = dict(os.environ, PATH=f"{stub}:{os.environ.get('PATH', '')}")
        run = subprocess.run([sys.executable, str(ASC), "validate", str(ipa)],
                             capture_output=True, text=True, env=env, check=False)
    lines = sorted(l for l in run.stdout.splitlines() if l.startswith(("ok  ", "FAIL ")))
    if regen:
        GOLDEN.write_text("\n".join(lines) + "\n")
        print(f"golden written: {len(lines)} lines (validate exit {run.returncode})")
        return 0
    want = GOLDEN.read_text().splitlines()
    if lines != want:
        print("asc validate golden MISMATCH")
        for l in lines:
            if l not in want:
                print(f"+ {l}")
        for l in want:
            if l not in lines:
                print(f"- {l}")
        return 1
    print(f"asc validate golden OK ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
