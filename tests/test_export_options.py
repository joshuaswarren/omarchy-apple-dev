"""tools/asc.py ASC_EXPORT_OPTIONS: an Xcode ExportOptions.plist read by `asc.py identity`.
The functions under test are taken from asc.py with ast and run offline: the App Store
Connect calls, the certificate and the profile install are stubs.

Rows (expected results written before the code):
  1  unset: no options, nothing printed
  2  method app-store-connect and app-store (the pre-15.3 name) are accepted
  3  no method: refused (xcodebuild's default is development)
  4  method ad-hoc / development / enterprise: refused, message points to sign-dev.sh
  5  teamID not 10 characters: refused
  6  provisioningProfiles not a string-to-string map: refused
  7  Xcode-only keys (uploadSymbols, signingStyle): reported as ignored
  8  signingCertificate: "Apple Distribution", "Apple Distribution: Name (TEAM)",
     "iOS Distribution" and the local SHA-1 are accepted; "Apple Development" and
     another SHA-1 are refused
  9  select_profile: by name, by UUID; neither -> refused
  10 check_named_profile: exact app id and a matching wildcard are accepted; another
     app id or a profile without the local certificate is refused
  11 identity: mapped bundle ids use the listed profiles (one listing for both),
     the unmapped one gets asc.py's own profile; teamID that differs from the
     profile's team is refused
  12 identity: an unsupported method stops before the certificate is touched
Mutants (each must fail its row; checked by hand when the test was written):
  M1  default the method to app-store-connect -> row 3
  M2  drop the certificate check in check_named_profile -> row 10
  M3  list profiles once per mapped bundle -> row 11 (one listing)
"""
import ast
import base64
import hashlib
import io
import os
import plistlib
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

NAMES = {"export_options", "check_signing_certificate", "select_profile", "check_named_profile",
         "check_profile_team", "identity", "test_identity"}


def namespace():
    source = (Path(__file__).resolve().parents[1] / "tools/asc.py").read_text()
    tree = ast.parse(source)
    keep = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in NAMES:
            keep.append(node)
        elif isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in {"APP_STORE_METHODS", "DISTRIBUTION_CERTIFICATES", "EXPORT_KEYS"}
                for t in node.targets):
            keep.append(node)
    tree.body = keep
    if {n.name for n in keep if isinstance(n, ast.FunctionDef)} != NAMES:
        raise AssertionError("asc.py must contain the functions under test")
    ns = dict(os=os, re=re, Path=Path, plistlib=plistlib, hashlib=hashlib, base64=base64)

    def die(message):
        raise SystemExit(message)
    ns["die"] = die
    exec(compile(tree, "asc-export-options.py", "exec"), ns)
    return ns


CERT = b"LOCAL-CERTIFICATE-DER"


def payload(app_id="TEAM123456.com.example.app", certs=(CERT,), team="TEAM123456"):
    return {"Entitlements": {"application-identifier": app_id}, "DeveloperCertificates": list(certs),
            "TeamIdentifier": [team]}


class ExportOptionsTests(unittest.TestCase):
    def setUp(self):
        self.ns = namespace()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.plist = Path(tmp.name) / "ExportOptions.plist"

    def options(self, opts):
        self.plist.write_bytes(plistlib.dumps(opts))
        out = io.StringIO()
        with patch.dict(os.environ, ASC_EXPORT_OPTIONS=str(self.plist)), redirect_stdout(out):
            result = self.ns["export_options"]()
        return result, out.getvalue()

    def refused(self, opts, fragment=""):
        with self.assertRaises(SystemExit) as e:
            self.options(opts)
        self.assertIn(fragment, str(e.exception.code))

    def test_row1_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "ASC_EXPORT_OPTIONS"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.ns["export_options"](), {})

    def test_row2_app_store_methods(self):
        for method in ("app-store-connect", "app-store"):
            result, _ = self.options({"method": method, "teamID": "TEAM123456"})
            self.assertEqual(result["team"], "TEAM123456")

    def test_row3_no_method(self):
        self.refused({"teamID": "TEAM123456"}, "development")

    def test_row4_other_methods(self):
        for method in ("ad-hoc", "development", "enterprise", "release-testing"):
            with self.subTest(method=method):
                self.refused({"method": method}, "sign-dev.sh")

    def test_row5_bad_team(self):
        self.refused({"method": "app-store-connect", "teamID": "Apple Distribution"}, "teamID")

    def test_row6_bad_profiles(self):
        for profiles in (["a"], {"com.example.app": 3}, {"com.example.app": ""}):
            with self.subTest(profiles=profiles):
                self.refused({"method": "app-store-connect", "provisioningProfiles": profiles}, "provisioningProfiles")

    def test_row7_ignored_keys(self):
        _, out = self.options({"method": "app-store-connect", "uploadSymbols": True, "signingStyle": "manual"})
        self.assertIn("ignored signingStyle, uploadSymbols", out)

    def test_row8_signing_certificate(self):
        check = self.ns["check_signing_certificate"]
        for ok in ("Apple Distribution", "Apple Distribution: Example Ltd (TEAM123456)", "iOS Distribution",
                   hashlib.sha1(CERT).hexdigest(), hashlib.sha1(CERT).hexdigest().upper(), None):
            check(ok, CERT)
        for bad in ("Apple Development", "Apple Distributionx", "0" * 40):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                check(bad, CERT)

    def test_row9_select_profile(self):
        listed = [{"attributes": {"name": "Store", "uuid": "UUID-1",
                                  "profileContent": base64.b64encode(b"P1").decode()}}]
        self.assertEqual(self.ns["select_profile"](listed, "Store", "com.example.app"), b"P1")
        self.assertEqual(self.ns["select_profile"](listed, "UUID-1", "com.example.app"), b"P1")
        with self.assertRaises(SystemExit):
            self.ns["select_profile"](listed, "Other", "com.example.app")

    def test_row10_check_named_profile(self):
        check = self.ns["check_named_profile"]
        check(payload(), "Store", "com.example.app", CERT)
        check(payload("TEAM123456.com.example.*"), "Store", "com.example.app", CERT)
        check(payload("TEAM123456.*"), "Store", "com.example.app", CERT)
        with self.assertRaises(SystemExit):
            check(payload("TEAM123456.com.other.app"), "Store", "com.example.app", CERT)
        with self.assertRaises(SystemExit) as e:
            check(payload(certs=[b"MAC-CERTIFICATE"]), "Store", "com.example.app", CERT)
        self.assertIn("local Apple Distribution certificate", str(e.exception.code))


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.ns = namespace()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.plist = root / "ExportOptions.plist"
        cert = root / "cert.der"
        cert.write_bytes(CERT)
        self.calls, self.own = [], []
        content = lambda ident: base64.b64encode(f"named:{ident}".encode()).decode()
        self.listed = [{"attributes": {"name": f"Store {i}", "uuid": f"U{i}", "profileContent": content(i)}}
                       for i in ("com.example.app", "com.example.app.widget")]
        self.payloads = {b"named:com.example.app": payload(),
                         b"named:com.example.app.widget": payload("TEAM123456.com.example.app.widget"),
                         b"own:com.example.app.share": payload("TEAM123456.com.example.app.share")}
        self.installed = {}

        def call(method, path, body=None):
            self.calls.append(path)
            return {"data": self.listed}

        def install(app_dir, out_dir, prov_for, key_path, cert_path):
            for ident in ("com.example.app", "com.example.app.widget", "com.example.app.share"):
                self.installed[ident] = prov_for(ident)

        self.certificate_called = False

        def certificate():
            self.certificate_called = True
            return "CERTID", root / "key.pem", cert

        self.ns.update(
            call=call, certificate=certificate, install_all_bundles=install,
            bundles=lambda app: [(app, i) for i in ("com.example.app", "com.example.app.widget", "com.example.app.share")],
            ensure_app_groups=lambda idents: set(),
            ensure_requested_capabilities=lambda ident: False,
            profile=lambda ident, cert_id, force_create=False: self.own.append(ident) or f"own:{ident}".encode(),
            profile_payload=lambda prov: self.payloads.get(prov, payload()))

    def run_identity(self, opts):
        self.plist.write_bytes(plistlib.dumps(opts))
        with patch.dict(os.environ, ASC_EXPORT_OPTIONS=str(self.plist)), redirect_stdout(io.StringIO()):
            self.ns["identity"]("Runner.app", "out")

    def test_row11_mapped_and_own_profiles(self):
        self.run_identity({"method": "app-store-connect", "teamID": "TEAM123456", "provisioningProfiles": {
            "com.example.app": "Store com.example.app", "com.example.app.widget": "Ucom.example.app.widget"}})
        self.assertEqual(self.installed["com.example.app"], b"named:com.example.app")
        self.assertEqual(self.installed["com.example.app.widget"], b"named:com.example.app.widget")
        self.assertEqual(self.own, ["com.example.app.share"])
        self.assertEqual(len(self.calls), 1)

    def test_row11_team_mismatch(self):
        with self.assertRaises(SystemExit) as e:
            self.run_identity({"method": "app-store-connect", "teamID": "OTHER12345"})
        self.assertIn("OTHER12345", str(e.exception.code))

    def test_row12_bad_method_before_certificate(self):
        with self.assertRaises(SystemExit):
            self.run_identity({"method": "ad-hoc"})
        self.assertFalse(self.certificate_called)


if __name__ == "__main__":
    unittest.main()
