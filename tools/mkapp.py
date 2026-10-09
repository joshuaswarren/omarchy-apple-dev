"""Wrap an SDK-free executable into an .app. usage: mkapp.py BINARY OUT.app BUNDLE-ID [EXECUTABLE-NAME]"""
import plistlib
import shutil
import sys
from pathlib import Path

binary, out, bundle_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
name = sys.argv[4] if len(sys.argv) > 4 else "HelloNoSDK"
out.mkdir(parents=True, exist_ok=True)
shutil.copy2(binary, out / name)
info = {
    "CFBundleExecutable": name,
    "CFBundleIdentifier": bundle_id,
    "CFBundleName": name,
    "CFBundleDisplayName": name,
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "1.0",
    "CFBundleVersion": "1",
    "CFBundleInfoDictionaryVersion": "6.0",
    "CFBundleSupportedPlatforms": ["iPhoneOS"],
    "MinimumOSVersion": "17.0",
    "UIDeviceFamily": [1],
    "UIRequiredDeviceCapabilities": ["arm64"],
    "UILaunchScreen": {},
    "UISupportedInterfaceOrientations": ["UIInterfaceOrientationPortrait"],
    "LSRequiresIPhoneOS": True,
}
with open(out / "Info.plist", "wb") as f:
    plistlib.dump(info, f)
(out / "PkgInfo").write_bytes(b"APPL????")
print(f"wrote {out}")
