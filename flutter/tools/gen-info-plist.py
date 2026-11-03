#!/usr/bin/env python3
"""Produce the app's final Info.plist the way an Xcode build would.

  gen-info-plist.py <source Info.plist> <actool partial plist> <output>
                    <bundle id> <build name> <build number> <min iOS> <iPhoneOS.sdk>
                    <device families, e.g. 1,2> [<build configuration, default Release>]

Expands the $(BUILD_SETTING) references Flutter's template uses, merges the
icon keys actool reported, and adds the platform and toolchain keys Xcode
stamps on a device build.
"""
import json
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xcode_settings import Settings, expand  # noqa: E402

src, icon, out, bundle_id, build_name, build_number, min_ios, sdk, families = sys.argv[1:10]
configuration = sys.argv[10] if len(sys.argv) > 10 else "Release"

settings = {
    "DEVELOPMENT_LANGUAGE": "en",
    "EXECUTABLE_NAME": "Runner",
    "PRODUCT_NAME": "Runner",
    "PRODUCT_MODULE_NAME": "Runner",
    "PRODUCT_BUNDLE_IDENTIFIER": bundle_id,
    "FLUTTER_BUILD_NAME": build_name,
    "FLUTTER_BUILD_NUMBER": build_number,
    "MARKETING_VERSION": build_name,
    "CURRENT_PROJECT_VERSION": build_number,
}

# Apps whose template goes beyond Flutter's own variable set (MARKETING_VERSION
# is common) define the values as build settings, in the project or in the
# configuration's xcconfig (Flutter/Release.xcconfig) and the files it includes
# (a Google client id, say): take them from the Runner target's settings in the
# configuration being built, as Xcode does.
# sdk-free/flutter-build.sh stages Info.plist under build/ios-sdkfree/<mode>, so the
# project directory cannot be derived from it; that caller sets IOS_DIR.
ios_dir = os.environ.get("IOS_DIR") or os.path.dirname(os.path.dirname(src))
build_settings = Settings(ios_dir, configuration)

def lookup(name):
    if name in settings:
        return settings[name]
    value = build_settings.raw(name) or ""
    if not value:
        print(f"warning: no value for $({name}); substituting empty", file=sys.stderr)
    return value

def expand_all(value):
    if isinstance(value, str):
        return expand(value, lookup)
    if isinstance(value, dict):
        return {k: expand_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_all(v) for v in value]
    return value

info = expand_all(plistlib.load(open(src, "rb")))
info.update(plistlib.load(open(icon, "rb")))

sdk_version = json.load(open(os.path.join(sdk, "SDKSettings.json")))["Version"]
sdk_build = plistlib.load(
    open(os.path.join(sdk, "System/Library/CoreServices/SystemVersion.plist"), "rb"))["ProductBuildVersion"]
info.update({
    "CFBundleSupportedPlatforms": ["iPhoneOS"],
    "DTCompiler": "com.apple.compilers.llvm.clang.1_0",
    "DTPlatformName": "iphoneos",
    "DTPlatformVersion": sdk_version,
    "DTPlatformBuild": sdk_build,
    "DTSDKName": "iphoneos" + sdk_version,
    "DTSDKBuild": sdk_build,
    "MinimumOSVersion": min_ios,
    "UIDeviceFamily": [int(f) for f in families.split(",")],
    "UIRequiredDeviceCapabilities": ["arm64"],
})
# DTXcode / DTXcodeBuild name the Xcode the SDK was built from; install-toolchain.sh
# keeps that Xcode's version.plist beside the SDK cache (the file asc.py reads).
import glob
candidates = sorted(glob.glob(os.path.expanduser("~/.cache/xtool/darwin-*.xtoolsdk.version.plist")))
if candidates:
    v = plistlib.load(open(candidates[-1], "rb"))
    parts = (v["CFBundleShortVersionString"].split(".") + ["0", "0"])[:3]
    info["DTXcode"] = "%02d%s%s" % (int(parts[0]), parts[1], parts[2])
    info["DTXcodeBuild"] = v["ProductBuildVersion"]

plistlib.dump(info, open(out, "wb"), fmt=plistlib.FMT_BINARY)
