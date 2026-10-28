#!/usr/bin/env python3
"""tools/asc.py validate on a SIGNED app with one app extension, with the real rcodesign.

tests/asc/golden-validate.py runs validate on an unsigned app with a stub rcodesign, so it never reaches the
profile, seal and appex checks. This test runs the signing steps of ship.sh (test identity, rcodesign on the
extension and then the app) on a synthetic app, packages the .ipa and runs validate on it. The app is a
hand-made thin arm64 Mach-O (no Apple-derived data). Skips with exit 0 when rcodesign or the cryptography
module is missing, as the simview tests skip without a Swift compiler.

The Mach-O has no asset catalog, so validate reports the two Assets.car lines as FAIL on every row; the rows
ignore those two and check the rest.

Rows (expected results written before the code):
  1  clean:           every extension line is ok (profile, rcodesign verify, team id, both sealed hashes, every
                      file sealed, entitlements); the only FAILs are the two Assets.car lines
  2  appex Info.plist edited after signing -> FAIL "appex Share.appex: Info.plist matches its sealed hash"
  3  file added to the appex after signing -> FAIL "appex Share.appex: every file is sealed"
  4  appex executable changed after signing -> FAIL "appex Share.appex: rcodesign verify Share"
  5  appex profile replaced by the app's profile -> FAIL "appex Share.appex: profile app id ... covers ..."
  6  app Info.plist edited after signing -> FAIL "Info.plist matches its sealed hash" (the app's own line), the
     extension's lines stay ok
  7  app profile deleted -> FAIL "embedded.mobileprovision present" (the app's own line)
Mutants (each must fail the rows named; checked by hand when the test was written):
  M1  validate skips the extensions -> rows 1 to 6
  M2  the extension's sealed-hash comparison always passes -> row 2
  M3  the app's sealed-hash comparison always passes -> row 6
Signing here uses --timestamp-url none, so the test needs no network; ship.sh signs with Apple's server.
"""
import os
import plistlib
import shutil
import site
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent.parent / "tools"
USER_BASE = site.getuserbase()  # kept when HOME is replaced, so cryptography in the user site stays importable
APPEX = "Share.appex"


def skip(why):
    print(f"SKIP appex-seal: {why}")
    sys.exit(0)


if shutil.which("rcodesign") is None:
    skip("rcodesign is not on PATH")
try:
    import cryptography  # noqa: F401
except ImportError:
    skip("tools/asc.py needs the cryptography module")


def segment(name, vmaddr, vmsize, fileoff, filesize, prot, sections=b"", nsects=0):
    return struct.pack("<II16sQQQQiiII", 0x19, 72 + len(sections), name, vmaddr, vmsize, fileoff, filesize,
                       prot, prot, nsects, 0) + sections


def macho():
    """Thin arm64 MH_EXECUTE, MH_PIE: __TEXT with one __text section (a `ret`), __LINKEDIT, LC_BUILD_VERSION
    (iOS 17.0 / SDK 26.0), unsigned. rcodesign needs a section and a __LINKEDIT to attach a signature."""
    page, code_off = 0x4000, 0x1000
    sect = struct.pack("<16s16sQQIIIIIIII", b"__text", b"__TEXT", 0x100000000 + code_off, 4, code_off, 2, 0, 0,
                       0x80000400, 0, 0, 0)
    cmds = (segment(b"__TEXT", 0x100000000, page, 0, page, 5, sect, 1)
            + segment(b"__LINKEDIT", 0x100000000 + page, page, page, 16, 1)
            + struct.pack("<6I", 0x32, 24, 2, 0x00110000, 0x001A0000, 0))
    body = bytearray(struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2, 3, len(cmds), 0x200000, 0) + cmds)
    body += b"\0" * (page - len(body))
    body[code_off:code_off + 4] = bytes.fromhex("c0035fd6")
    return bytes(body) + b"\0" * 16


def info(bundle_id, exe, package_type, extra):
    plist = {
        "CFBundleIdentifier": bundle_id, "CFBundleExecutable": exe, "CFBundleName": exe,
        "CFBundleShortVersionString": "1.2", "CFBundleVersion": "3", "CFBundlePackageType": package_type,
        "CFBundleSupportedPlatforms": ["iPhoneOS"], "CFBundleInfoDictionaryVersion": "6.0",
        "MinimumOSVersion": "17.0", "UIDeviceFamily": [1], "UIRequiredDeviceCapabilities": ["arm64"],
        "DTCompiler": "com.apple.compilers.llvm.clang.1_0", "DTPlatformBuild": "27A266a",
        "DTPlatformName": "iphoneos", "DTPlatformVersion": "27.0", "DTSDKBuild": "27A266a",
        "DTSDKName": "iphoneos27.0", "DTXcode": "2700", "DTXcodeBuild": "27A266a",
    }
    plist.update(extra)
    return plistlib.dumps(plist)


def build_app(app):
    appex = app / "PlugIns" / APPEX
    appex.mkdir(parents=True)
    (app / "Info.plist").write_bytes(info("dev.omarchy.fixture", "Fixture", "APPL", {
        "CFBundleIcons": {"CFBundlePrimaryIcon": {"CFBundleIconName": "AppIcon"}}, "UILaunchScreen": {}}))
    (app / "Fixture").write_bytes(macho())
    (appex / "Info.plist").write_bytes(info("dev.omarchy.fixture.share", "Share", "XPC!", {
        "NSExtension": {"NSExtensionPointIdentifier": "com.apple.share-services"}}))
    (appex / "Share").write_bytes(macho())
    for exe in (app / "Fixture", appex / "Share"):
        exe.chmod(0o755)
    return appex


def run(cmd, env, cwd):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd, check=False)


def sign(app, tmp, env):
    """ship.sh steps 6 and 7 for a test identity: identity, then the extension, then the app."""
    out = tmp / "ship-signing"
    done = run([sys.executable, str(TOOLS / "asc.py"), "test-identity", str(app), str(out)], env, tmp)
    assert done.returncode == 0, f"test-identity failed: {done.stdout}{done.stderr}"
    team = plistlib.loads((out / "entitlements.plist").read_bytes())["com.apple.developer.team-identifier"]
    args = ["rcodesign", "sign", "--timestamp-url", "none", "--pem-file", str(out / "key.pem"),
            "--certificate-der-file", str(out / "cert.der"), "--team-name", team]
    for target, ents in ((app / "PlugIns" / APPEX, "Share-entitlements.plist"), (app, "entitlements.plist")):
        done = run([*args, "--entitlements-xml-file", str(out / ents), str(target)], env, tmp)
        assert done.returncode == 0, f"rcodesign sign {target.name} failed: {done.stdout}{done.stderr}"


def package(app, ipa):
    with zipfile.ZipFile(ipa, "w") as z:
        z.writestr("Payload/", "")
        for path in sorted(app.rglob("*")):
            if path.is_file():
                z.write(path, f"Payload/{app.name}/{path.relative_to(app)}")


def validate(app, tmp, env, name):
    ipa = tmp / f"{name}.ipa"
    package(app, ipa)
    done = run([sys.executable, str(TOOLS / "asc.py"), "validate", str(ipa)], env, tmp)
    return [line.strip() for line in (done.stdout + done.stderr).splitlines()]


def with_status(lines, status):
    return [line[len(status):].strip() for line in lines if line.startswith(status + " ")]


def has(lines, text):
    """A check line is its text, optionally followed by detail ('; unsealed [...]', ': rcodesign's message')."""
    return any(line == text or line.startswith((text + ";", text + ":")) for line in lines)


def main():
    failed = []

    def row(label, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + label + ("" if ok else f"  {detail}"))
        if not ok:
            failed.append(label)

    with tempfile.TemporaryDirectory(prefix="asc-appex-") as tmp_name:
        tmp = Path(tmp_name)
        home = tmp / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), PYTHONUSERBASE=USER_BASE)
        for var in ("ASC_KEY_ID", "ASC_EXPORT_OPTIONS", "ASC_ENTITLEMENTS_PATH", "ASC_PROFILE", "APP_GROUPS"):
            env.pop(var, None)
        base = tmp / "base" / "Fixture.app"
        build_app(base)
        sign(base, tmp, env)

        def tampered(name, change):
            app = tmp / name / "Fixture.app"
            shutil.copytree(base, app, symlinks=True)
            change(app, app / "PlugIns" / APPEX)
            lines = validate(app, tmp, env, name)
            return with_status(lines, "FAIL"), with_status(lines, "ok")

        # 1
        failures, passed = tampered("clean", lambda app, appex: None)
        expected = [f"appex {APPEX}: {text}" for text in (
            "embedded.mobileprovision present", "App Store profile", "rcodesign verify Share",
            "CodeDirectory team id matches profile", "Info.plist matches its sealed hash",
            "_CodeSignature/CodeResources matches its sealed hash", "every file is sealed",
            "signed entitlements match its profile", "signed get-task-allow is false",
            "signed entitlements are a subset of its profile",
            "signing certificate is one of the profile's DeveloperCertificates")]
        missing = [text for text in expected if not has(passed, text)]
        icon = [line for line in failures if line.startswith("Assets.car")]
        row("row 1 clean: every extension line is ok", not missing, f"missing: {missing}")
        row("row 1 clean: the only FAILs are the two Assets.car lines", sorted(failures) == sorted(icon) and len(icon) == 2,
            f"FAILs: {failures}")

        # 2
        def edit_appex_plist(app, appex):
            data = plistlib.loads((appex / "Info.plist").read_bytes())
            data["CFBundleDisplayName"] = "Changed after signing"
            (appex / "Info.plist").write_bytes(plistlib.dumps(data))
        failures, passed = tampered("appex-plist", edit_appex_plist)
        row("row 2 appex Info.plist edited -> its sealed hash FAILs",
            has(failures, f"appex {APPEX}: Info.plist matches its sealed hash"), f"FAILs: {failures}")

        # 3
        failures, passed = tampered("appex-extra", lambda app, appex: (appex / "extra.txt").write_text("not sealed"))
        row("row 3 file added to the appex -> 'every file is sealed' FAILs",
            has(failures, f"appex {APPEX}: every file is sealed"), f"FAILs: {failures}")

        # 4
        def edit_appex_code(app, appex):
            exe = bytearray((appex / "Share").read_bytes())
            exe[0x1000:0x1004] = bytes.fromhex("1f2003d5")  # ret -> nop
            (appex / "Share").write_bytes(bytes(exe))
        failures, passed = tampered("appex-code", edit_appex_code)
        row("row 4 appex executable changed -> rcodesign verify FAILs",
            has(failures, f"appex {APPEX}: rcodesign verify Share"), f"FAILs: {failures}")

        # 5
        failures, passed = tampered("appex-profile", lambda app, appex: shutil.copy(
            app / "embedded.mobileprovision", appex / "embedded.mobileprovision"))
        row("row 5 app's profile in the appex -> the profile app id line FAILs",
            any(line.startswith(f"appex {APPEX}: profile app id") for line in failures), f"FAILs: {failures}")

        # 6
        def edit_app_plist(app, appex):
            data = plistlib.loads((app / "Info.plist").read_bytes())
            data["CFBundleDisplayName"] = "Changed after signing"
            (app / "Info.plist").write_bytes(plistlib.dumps(data))
        failures, passed = tampered("app-plist", edit_app_plist)
        row("row 6 app Info.plist edited -> the app's sealed hash FAILs",
            has(failures, "Info.plist matches its sealed hash"), f"FAILs: {failures}")
        row("row 6 ... and the extension's seal stays ok",
            has(passed, f"appex {APPEX}: Info.plist matches its sealed hash"), f"ok lines: {passed[-8:]}")

        # 7
        failures, passed = tampered("app-profile", lambda app, appex: (app / "embedded.mobileprovision").unlink())
        row("row 7 app profile deleted -> 'embedded.mobileprovision present' FAILs",
            has(failures, "embedded.mobileprovision present"), f"FAILs: {failures}")

    if failed:
        print(f"{len(failed)} row(s) failed")
        sys.exit(1)
    print("asc appex-seal OK")


if __name__ == "__main__":
    main()
