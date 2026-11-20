"""Tests for tools/xcarchive and ship.sh --xcarchive.

Rows (expected results written before the implementation):
  1  standard layout & Info.plist: copies .app under Products/Applications/ (preserving
     executable bits and symlinks), copies .dSYM under dSYMs/, and emits XML Info.plist
     with ArchiveVersion=2, Name, SchemeName, CreationDate, and ApplicationProperties
     (ApplicationPath, CFBundleIdentifier, CFBundleShortVersionString, CFBundleVersion,
     Architectures, IconPaths); omits SigningIdentity/Team when unsigned.
  2  signing metadata: extracts Team and certificate Common Name (UTF8String and
     PrintableString) from embedded.mobileprovision; --signing-identity and --team
     override; invalid --team is refused.
  3  dSYM handling: zero --dsym yields an empty dSYMs/ dir; directory containing
     multiple *.dSYM bundles plus an explicit framework .dSYM copies all bundles.
  4  Mach-O architectures: thin arm64e and fat arm64+x86_64 binaries report the right
     Architectures list in slice order.
  5  atomic replace: replacing an existing read-only .xcarchive succeeds; a failing run
     leaves an existing .xcarchive intact.
  6  validation refusals: invalid .app, missing Info.plist/keys/executable, invalid
     output suffix or nesting, invalid/empty/duplicate dSYMs, and bad --creation-date
     all exit non-zero and leave no partial output.
  7  --name, --scheme, and SOURCE_DATE_EPOCH override defaults deterministically.
  8  ship.sh --xcarchive wiring: syntax clean, invalid flag combinations exit 2 with
     usage, and the extracted --xcarchive package block builds both default and custom
     .xcarchive outputs.

Mutants (each must fail its row):
  M1  omit ApplicationPath or prefix it with Products/ -> row 1
  M2  ignore embedded.mobileprovision DeveloperCertificates CN -> row 2
  M3  fail to unlink read-only target before replacing -> row 5
  M4  skip duplicate .dSYM basename rejection -> row 6
  M5  accept --device --xcarchive in ship.sh -> row 8
"""
import datetime
import os
import plistlib
import shutil
import stat
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "xcarchive"
SHIP = ROOT / "ship.sh"


def _tlv(tag: int, body: bytes) -> bytes:
    n = len(body)
    if n < 0x80:
        len_bytes = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        len_bytes = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + len_bytes + body


def make_der_cert_with_cn(cn: str, tag: int = 0x0C) -> bytes:
    """Minimal syntactically valid X.509 DER certificate carrying Subject CN."""
    oid_sha256_rsa = _tlv(0x06, bytes.fromhex("2a864886f70d01010b"))
    alg_id = _tlv(0x30, oid_sha256_rsa + _tlv(0x05, b""))
    oid_cn = _tlv(0x06, b"\x55\x04\x03")
    atv = _tlv(0x30, oid_cn + _tlv(tag, cn.encode("utf-8")))
    rdn = _tlv(0x31, atv)
    name = _tlv(0x30, rdn)
    validity = _tlv(0x30, _tlv(0x17, b"260101000000Z") + _tlv(0x17, b"270101000000Z"))
    spki = _tlv(0x30, alg_id + _tlv(0x03, b"\x00\x01\x02"))
    tbs = _tlv(
        0x30,
        _tlv(0xA0, _tlv(0x02, b"\x02"))  # v3
        + _tlv(0x02, b"\x01")
        + alg_id
        + name
        + validity
        + name
        + spki,
    )
    return _tlv(0x30, tbs + alg_id + _tlv(0x03, b"\x00\xab\xcd"))


def make_mobileprovision(team: str, cert_der: bytes, app_id: str) -> bytes:
    payload = plistlib.dumps(
        {
            "TeamIdentifier": [team],
            "DeveloperCertificates": [cert_der],
            "Entitlements": {
                "com.apple.developer.team-identifier": team,
                "application-identifier": f"{team}.{app_id}",
            },
        },
        fmt=plistlib.FMT_XML,
    )
    return b"\x30\x82\x01\x00CMS-HEADER" + payload + b"CMS-TRAILER"


def make_thin_macho(cputype: int = 0x0100000C, cpusubtype: int = 0) -> bytes:
    return struct.pack("<8I", 0xFEEDFACF, cputype, cpusubtype, 2, 0, 0, 0, 0)


def make_fat_macho(slices: list[tuple[int, int]]) -> bytes:
    thin_blobs = [make_thin_macho(ct, st) for ct, st in slices]
    header_size = 8 + 20 * len(slices)
    offset = (header_size + 15) & ~15
    arches = bytearray()
    body = bytearray(b"\x00" * (offset - header_size))
    for (ct, st), blob in zip(slices, thin_blobs):
        arches.extend(struct.pack(">5I", ct, st, offset, len(blob), 4))
        body.extend(blob)
        offset += len(blob)
    return struct.pack(">2I", 0xCAFEBABE, len(slices)) + bytes(arches) + bytes(body)


def make_app(
    parent: Path,
    name: str = "Demo",
    bundle_id: str = "com.example.demo",
    version: str = "1.2.3",
    build: str = "42",
    macho: bytes | None = None,
    icons: list[str] | None = None,
    provision: bytes | None = None,
    with_symlink: bool = False,
    omit_plist_key: str | None = None,
    omit_executable: bool = False,
) -> Path:
    app = parent / f"{name}.app"
    app.mkdir(parents=True, exist_ok=True)
    info: dict[str, object] = {
        "CFBundleIdentifier": bundle_id,
        "CFBundleName": name,
        "CFBundleExecutable": name,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": build,
        "CFBundlePackageType": "APPL",
    }
    if icons is None:
        icons = ["AppIcon60x60@2x.png"]
    if icons:
        info["CFBundleIcons"] = {
            "CFBundlePrimaryIcon": {
                "CFBundleIconFiles": ["AppIcon60x60"],
                "CFBundleIconName": "AppIcon",
            }
        }
        for icon in icons:
            (app / icon).write_bytes(b"\x89PNG\r\n\x1a\n")
    if omit_plist_key is not None:
        info.pop(omit_plist_key, None)
    with (app / "Info.plist").open("wb") as f:
        plistlib.dump(info, f, fmt=plistlib.FMT_BINARY)
    if not omit_executable:
        exe = app / name
        exe.write_bytes(macho if macho is not None else make_thin_macho())
        exe.chmod(0o755)
    if provision is not None:
        (app / "embedded.mobileprovision").write_bytes(provision)
    if with_symlink:
        fw = app / "Frameworks" / "Foo.framework"
        (fw / "Versions" / "A").mkdir(parents=True, exist_ok=True)
        (fw / "Versions" / "A" / "Foo").write_bytes(make_thin_macho())
        os.symlink("Versions/A/Foo", fw / "Foo")
    return app


def make_dsym(
    parent: Path,
    bundle_name: str = "Demo.app.dSYM",
    binary_name: str = "Demo",
    with_info: bool = True,
    with_dwarf: bool = True,
) -> Path:
    dsym = parent / bundle_name
    dwarf_dir = dsym / "Contents" / "Resources" / "DWARF"
    dwarf_dir.mkdir(parents=True, exist_ok=True)
    if with_info:
        with (dsym / "Contents" / "Info.plist").open("wb") as f:
            plistlib.dump({"CFBundleIdentifier": f"com.apple.xcode.dsym.{binary_name}"}, f)
    if with_dwarf:
        (dwarf_dir / binary_name).write_bytes(b"DWARFDATA")
    return dsym


class XcarchiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def run_tool(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        run_env = os.environ.copy()
        run_env.pop("SOURCE_DATE_EPOCH", None)
        if env:
            run_env.update(env)
        return subprocess.run(
            ["python3", str(TOOL), *args],
            capture_output=True,
            text=True,
            env=run_env,
        )

    def test_row1_standard_layout_and_plist(self):
        app = make_app(self.tmp / "build", with_symlink=True)
        dsym = make_dsym(self.tmp / "sym")
        out = self.tmp / "out" / "Demo.xcarchive"

        res = self.run_tool(
            str(app),
            "-o", str(out),
            "--dsym", str(dsym),
            "--creation-date", "2026-11-20T17:00:00Z",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("wrote ", res.stdout)

        archived_app = out / "Products" / "Applications" / "Demo.app"
        self.assertTrue(archived_app.is_dir())
        self.assertTrue((archived_app / "Demo").stat().st_mode & stat.S_IXUSR)
        symlink_path = archived_app / "Frameworks" / "Foo.framework" / "Foo"
        self.assertTrue(symlink_path.is_symlink())
        self.assertEqual(os.readlink(symlink_path), "Versions/A/Foo")

        archived_dsym = out / "dSYMs" / "Demo.app.dSYM"
        self.assertTrue((archived_dsym / "Contents" / "Info.plist").is_file())
        self.assertTrue((archived_dsym / "Contents" / "Resources" / "DWARF" / "Demo").is_file())

        raw_plist = (out / "Info.plist").read_bytes()
        self.assertTrue(raw_plist.startswith(b"<?xml"))
        plist = plistlib.loads(raw_plist)
        self.assertIs(type(plist["ArchiveVersion"]), int)
        self.assertEqual(plist["ArchiveVersion"], 2)
        self.assertEqual(plist["Name"], "Demo")
        self.assertEqual(plist["SchemeName"], "Demo")
        self.assertEqual(plist["CreationDate"], datetime.datetime(2026, 11, 20, 17, 0, 0))

        props = plist["ApplicationProperties"]
        self.assertEqual(props["ApplicationPath"], "Applications/Demo.app")
        self.assertTrue((out / "Products" / props["ApplicationPath"]).is_dir())
        self.assertEqual(props["CFBundleIdentifier"], "com.example.demo")
        self.assertEqual(props["CFBundleShortVersionString"], "1.2.3")
        self.assertEqual(props["CFBundleVersion"], "42")
        self.assertEqual(props["Architectures"], ["arm64"])
        self.assertEqual(props["IconPaths"], ["Applications/Demo.app/AppIcon60x60@2x.png"])
        for icon_rel in props["IconPaths"]:
            self.assertTrue((out / "Products" / icon_rel).is_file())
        self.assertNotIn("SigningIdentity", props)
        self.assertNotIn("Team", props)

    def test_row2_signing_metadata_auto_and_override(self):
        cert_utf8 = make_der_cert_with_cn("Apple Distribution: Example Co (ABCDE12345)", tag=0x0C)
        prov_utf8 = make_mobileprovision("ABCDE12345", cert_utf8, "com.example.demo")
        app = make_app(self.tmp / "build", provision=prov_utf8)
        out = self.tmp / "Demo.xcarchive"

        res = self.run_tool(str(app), "-o", str(out))
        self.assertEqual(res.returncode, 0, res.stderr)
        props = plistlib.loads((out / "Info.plist").read_bytes())["ApplicationProperties"]
        self.assertEqual(props["Team"], "ABCDE12345")
        self.assertEqual(props["SigningIdentity"], "Apple Distribution: Example Co (ABCDE12345)")

        cert_print = make_der_cert_with_cn("Apple Distribution: Printable Co (XYZ9876543)", tag=0x13)
        prov_print = make_mobileprovision("XYZ9876543", cert_print, "com.example.demo")
        (app / "embedded.mobileprovision").write_bytes(prov_print)
        res = self.run_tool(str(app), "-o", str(out))
        self.assertEqual(res.returncode, 0, res.stderr)
        props = plistlib.loads((out / "Info.plist").read_bytes())["ApplicationProperties"]
        self.assertEqual(props["Team"], "XYZ9876543")
        self.assertEqual(props["SigningIdentity"], "Apple Distribution: Printable Co (XYZ9876543)")

        res = self.run_tool(
            str(app),
            "-o", str(out),
            "--signing-identity", "Apple Distribution: Custom (ZZZZZ11111)",
            "--team", "ZZZZZ11111",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        props = plistlib.loads((out / "Info.plist").read_bytes())["ApplicationProperties"]
        self.assertEqual(props["Team"], "ZZZZZ11111")
        self.assertEqual(props["SigningIdentity"], "Apple Distribution: Custom (ZZZZZ11111)")

        bad_team = self.run_tool(str(app), "-o", str(self.tmp / "BadTeam.xcarchive"), "--team", "short")
        self.assertNotEqual(bad_team.returncode, 0)

    def test_row3_dsyms_variants(self):
        app = make_app(self.tmp / "build")
        out_empty = self.tmp / "NoDsyms.xcarchive"
        res = self.run_tool(str(app), "-o", str(out_empty))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((out_empty / "dSYMs").is_dir())
        self.assertEqual(list((out_empty / "dSYMs").iterdir()), [])

        dsym_dir = self.tmp / "dsym_bundle_dir"
        make_dsym(dsym_dir, "Demo.app.dSYM", "Demo")
        make_dsym(dsym_dir, "DemoExt.appex.dSYM", "DemoExt")
        fw_dsym = make_dsym(self.tmp / "extra", "Foo.framework.dSYM", "Foo")
        out_multi = self.tmp / "MultiDsyms.xcarchive"
        res = self.run_tool(str(app), "-o", str(out_multi), "--dsym", str(dsym_dir), "--dsym", str(fw_dsym))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(
            sorted(p.name for p in (out_multi / "dSYMs").iterdir()),
            ["Demo.app.dSYM", "DemoExt.appex.dSYM", "Foo.framework.dSYM"],
        )

    def test_row4_macho_architectures(self):
        fat_app = make_app(
            self.tmp / "fat",
            macho=make_fat_macho([(0x0100000C, 0), (0x01000007, 3)]),
        )
        out_fat = self.tmp / "Fat.xcarchive"
        res = self.run_tool(str(fat_app), "-o", str(out_fat))
        self.assertEqual(res.returncode, 0, res.stderr)
        props = plistlib.loads((out_fat / "Info.plist").read_bytes())["ApplicationProperties"]
        self.assertEqual(props["Architectures"], ["arm64", "x86_64"])

        arm64e_app = make_app(
            self.tmp / "arm64e",
            macho=make_thin_macho(0x0100000C, 2),
        )
        out_arm64e = self.tmp / "Arm64e.xcarchive"
        res = self.run_tool(str(arm64e_app), "-o", str(out_arm64e))
        self.assertEqual(res.returncode, 0, res.stderr)
        props = plistlib.loads((out_arm64e / "Info.plist").read_bytes())["ApplicationProperties"]
        self.assertEqual(props["Architectures"], ["arm64e"])

    def test_row5_overwrite_readonly_and_atomic_failure(self):
        app = make_app(self.tmp / "build")
        out = self.tmp / "Replace.xcarchive"
        res = self.run_tool(str(app), "-o", str(out), "--creation-date", "2026-11-20T01:00:00Z")
        self.assertEqual(res.returncode, 0, res.stderr)
        sentinel = out / "Products" / "Applications" / "Demo.app" / "Demo"
        sentinel.chmod(0o444)
        (out / "Products" / "Applications" / "Demo.app").chmod(0o555)
        (out / "Products").chmod(0o555)
        out.chmod(0o555)
        self.addCleanup(lambda: subprocess.run(["chmod", "-R", "u+w", str(self.tmp)], check=False))

        res2 = self.run_tool(str(app), "-o", str(out), "--creation-date", "2026-11-20T02:00:00Z")
        self.assertEqual(res2.returncode, 0, res2.stderr)
        plist = plistlib.loads((out / "Info.plist").read_bytes())
        self.assertEqual(plist["CreationDate"], datetime.datetime(2026, 11, 20, 2, 0, 0))

        # Failing invocation targeting an existing archive must leave the prior archive untouched.
        fail_res = self.run_tool(str(app), "-o", str(out), "--dsym", str(self.tmp / "does-not-exist.dSYM"))
        self.assertNotEqual(fail_res.returncode, 0)
        plist_after = plistlib.loads((out / "Info.plist").read_bytes())
        self.assertEqual(plist_after["CreationDate"], datetime.datetime(2026, 11, 20, 2, 0, 0))

    def test_row6_validation_refusals(self):
        good_app = make_app(self.tmp / "good")
        bad_dsym_no_dwarf = make_dsym(self.tmp / "bd1", "NoDwarf.dSYM", with_dwarf=False)
        bad_dsym_no_plist = make_dsym(self.tmp / "bd2", "NoPlist.dSYM", with_info=False)
        empty_dir = self.tmp / "empty_dsyms"
        empty_dir.mkdir()
        dup_a = make_dsym(self.tmp / "da", "Dup.dSYM", "Dup")
        dup_b = make_dsym(self.tmp / "db", "Dup.dSYM", "Dup")

        cases = [
            ("missing_app", [str(self.tmp / "Missing.app"), "-o", str(self.tmp / "a.xcarchive")]),
            ("missing_info_plist", [
                str(self._make_no_plist_app()), "-o", str(self.tmp / "b.xcarchive")
            ]),
            ("missing_bundle_id", [
                str(make_app(self.tmp / "k1", omit_plist_key="CFBundleIdentifier")),
                "-o", str(self.tmp / "c.xcarchive"),
            ]),
            ("missing_executable", [
                str(make_app(self.tmp / "k2", omit_executable=True)),
                "-o", str(self.tmp / "d.xcarchive"),
            ]),
            ("bad_output_suffix", [str(good_app), "-o", str(self.tmp / "bad_out")]),
            ("nested_output", [str(good_app), "-o", str(good_app / "Out.xcarchive")]),
            ("missing_dsym", [str(good_app), "-o", str(self.tmp / "e.xcarchive"), "--dsym", str(self.tmp / "nope.dSYM")]),
            ("dsym_no_dwarf", [str(good_app), "-o", str(self.tmp / "f.xcarchive"), "--dsym", str(bad_dsym_no_dwarf)]),
            ("dsym_no_plist", [str(good_app), "-o", str(self.tmp / "g.xcarchive"), "--dsym", str(bad_dsym_no_plist)]),
            ("empty_dsym_dir", [str(good_app), "-o", str(self.tmp / "h.xcarchive"), "--dsym", str(empty_dir)]),
            ("duplicate_dsym", [
                str(good_app), "-o", str(self.tmp / "i.xcarchive"),
                "--dsym", str(dup_a), "--dsym", str(dup_b),
            ]),
            ("bad_creation_date", [str(good_app), "-o", str(self.tmp / "j.xcarchive"), "--creation-date", "not-a-date"]),
        ]
        for label, args in cases:
            with self.subTest(case=label):
                res = self.run_tool(*args)
                self.assertNotEqual(res.returncode, 0, f"{label} unexpectedly succeeded")
                self.assertTrue(res.stderr.strip(), f"{label} produced empty stderr")

    def _make_no_plist_app(self) -> Path:
        app = self.tmp / "no_plist" / "NoPlist.app"
        app.mkdir(parents=True)
        return app

    def test_row7_name_scheme_and_source_date_epoch(self):
        app = make_app(self.tmp / "build")
        out = self.tmp / "Named.xcarchive"
        res = self.run_tool(
            str(app),
            "-o", str(out),
            "--name", "CustomApp",
            "--scheme", "CustomScheme",
            env={"SOURCE_DATE_EPOCH": "1700000000"},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        plist = plistlib.loads((out / "Info.plist").read_bytes())
        self.assertEqual(plist["Name"], "CustomApp")
        self.assertEqual(plist["SchemeName"], "CustomScheme")
        self.assertEqual(plist["CreationDate"], datetime.datetime(2023, 11, 14, 22, 13, 20))

    def test_row8_ship_sh_xcarchive_wiring(self):
        syntax = subprocess.run(["bash", "-n", str(SHIP)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        for bad_args in (
            ["--device", "--xcarchive"],
            ["--simulator", "--xcarchive"],
            ["--device", "--upload"],
            ["--xcarchive="],
            ["--unknown-flag"],
        ):
            with self.subTest(args=bad_args):
                res = subprocess.run(["bash", str(SHIP), *bad_args], capture_output=True, text=True)
                self.assertEqual(res.returncode, 2, res.stderr)
                self.assertIn("usage:", res.stderr)

        ship_text = SHIP.read_text()
        begin_marker = "# -- xcarchive-begin --"
        end_marker = "# -- xcarchive-end --"
        self.assertIn(begin_marker, ship_text)
        self.assertIn(end_marker, ship_text)
        block = ship_text.split(begin_marker, 1)[1].split(end_marker, 1)[0]

        proj = self.tmp / "proj"
        app = make_app(proj / "xtool")
        make_dsym(proj / "xtool", "Demo.app.dSYM", "Demo")
        stage = self.tmp / "stage"
        stage.mkdir()

        script = (
            "set -euo pipefail\n"
            f'cd "{proj}"\n'
            f'here="{ROOT}"\n'
            'PY=python3\n'
            'app=xtool/Demo.app\n'
            'name=Demo\n'
            'team=ABCDE12345\n'
            f'stage="{stage}"\n'
            'xcarchive=1\n'
            'xcarchive_out=\n'
            + block
        )
        run1 = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(run1.returncode, 0, run1.stderr + run1.stdout)
        default_arc = proj / "xtool" / "Demo.xcarchive"
        self.assertTrue((default_arc / "Products" / "Applications" / "Demo.app").is_dir())
        self.assertTrue((default_arc / "dSYMs" / "Demo.app.dSYM" / "Contents" / "Resources" / "DWARF" / "Demo").is_file())
        plist = plistlib.loads((default_arc / "Info.plist").read_bytes())
        self.assertEqual(plist["ApplicationProperties"]["Team"], "ABCDE12345")

        custom_arc = self.tmp / "custom" / "MyOut.xcarchive"
        script_custom = script.replace("xcarchive_out=\n", f'xcarchive_out="{custom_arc}"\n')
        run2 = subprocess.run(["bash", "-c", script_custom], capture_output=True, text=True)
        self.assertEqual(run2.returncode, 0, run2.stderr + run2.stdout)
        self.assertTrue((custom_arc / "Info.plist").is_file())


if __name__ == "__main__":
    unittest.main()
