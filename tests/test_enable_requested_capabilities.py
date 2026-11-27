"""tools/asc.py ensure_requested_capabilities: before the App Store profile is fetched, the app's
bundle id gets the capabilities its entitlements (ASC_ENTITLEMENTS_PATH) request, as Xcode's
automatic signing does, and a newly enabled one makes identity() re-create the profile.
The functions under test are taken from asc.py with ast and run offline: the App Store Connect
calls are a stub that records them.

Rows (expected results written before the code):
  1  nothing requested: no App Store Connect call, nothing to re-create
  2  Sign in with Apple requested, not enabled: one POST of APPLE_ID_AUTH with the primary
     consent setting for that bundle id; re-create
  3  Sign in with Apple requested, already enabled: no POST, nothing to re-create
  4  push and Associated Domains requested: PUSH_NOTIFICATIONS and ASSOCIATED_DOMAINS posted
  5  the API refuses the POST: stops (no signing without the grant)
  6  identity: a newly enabled capability re-creates the app's profile (force_create), an
     unchanged bundle id keeps its profile
Mutants (each must fail its row; checked by hand when the test was written):
  M1  drop the settings of APPLE_ID_AUTH -> row 2
  M2  post without checking the enabled ones -> row 3
  M3  ignore the return value in identity -> row 6
"""
import ast
import os
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

NAMES = {"ensure_requested_capabilities", "requested_capabilities", "requested_associated_domains",
         "associated_domains_allowed", "identity"}
SIWA = "com.apple.developer.applesignin"
APS = "aps-environment"
DOMAINS = "com.apple.developer.associated-domains"
CONSENT = [{"key": "APPLE_ID_AUTH_APP_CONSENT", "options": [{"key": "PRIMARY_APP_CONSENT"}]}]


class Api:
    def __init__(self, enabled=(), refuse=False):
        self.enabled, self.refuse, self.calls = set(enabled), refuse, []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path.startswith("/v1/bundleIds/BID/bundleIdCapabilities"):
            return {"data": [{"attributes": {"capabilityType": c}} for c in sorted(self.enabled)]}
        if method == "POST" and path == "/v1/bundleIdCapabilities":
            if self.refuse:
                raise SystemExit("asc.py: POST /v1/bundleIdCapabilities: HTTP 409")
            self.enabled.add(body["data"]["attributes"]["capabilityType"])
            return {"data": {}}
        raise AssertionError(f"unexpected call {method} {path}")

    def posts(self):
        return [b["data"]["attributes"] for m, p, b in self.calls if m == "POST"]


def namespace(api, profiles=None):
    source = (Path(__file__).resolve().parents[1] / "tools/asc.py").read_text()
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    if {n.name for n in tree.body} != NAMES:
        raise AssertionError("asc.py must contain the functions under test")

    def die(message):
        raise SystemExit(message)

    ns = dict(os=os, Path=Path, plistlib=plistlib, APS_KEY=APS, SIWA_KEY=SIWA, call=api, die=die,
              bundle_id=lambda ident: "BID", rel=lambda kind, ident: {"data": {"type": kind, "id": ident}})
    # identity() collaborators: certificate, bundles and the profile install are stubs.
    profiles = [] if profiles is None else profiles
    ns.update(
        export_options=lambda: {}, certificate=lambda: ("CERT", Path("key"), Path("cert")),
        check_signing_certificate=lambda *a: None, ensure_app_groups=lambda idents: set(),
        check_profile_team=lambda *a: None, profile_payload=lambda prov: {},
        profile=lambda ident, cert_id, force_create=False: profiles.append((ident, force_create)) or b"P",
        install_all_bundles=lambda app_dir, out_dir, prov_for, *a: [prov_for(i) for i in ns["_idents"]],
        bundles=lambda app_dir: [(None, i) for i in ns["_idents"]],
        _idents=["com.example.app", "com.example.app.widget"])
    exec(compile(tree, "asc.py", "exec"), ns)
    return ns


class EnableRequestedCapabilities(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_with(self, requested, api):
        env = {}
        if requested is not None:
            path = Path(self.tmp.name) / "Runner.entitlements"
            path.write_bytes(plistlib.dumps(requested))
            env["ASC_ENTITLEMENTS_PATH"] = str(path)
        with patch.dict(os.environ, env):
            if requested is None:
                os.environ.pop("ASC_ENTITLEMENTS_PATH", None)
            with patch("builtins.print"):
                return namespace(api)["ensure_requested_capabilities"]("com.example.app")

    def test_row1_nothing_requested(self):
        api = Api()
        self.assertFalse(self.run_with(None, api))
        self.assertFalse(self.run_with({}, api))
        self.assertEqual(api.calls, [])

    def test_row2_sign_in_with_apple_enabled(self):
        api = Api(enabled={"IN_APP_PURCHASE"})
        self.assertTrue(self.run_with({SIWA: ["Default"]}, api))
        self.assertEqual(api.posts(), [{"capabilityType": "APPLE_ID_AUTH", "settings": CONSENT}])
        body = [b for m, p, b in api.calls if m == "POST"][0]
        self.assertEqual(body["data"]["relationships"]["bundleId"], {"data": {"type": "bundleIds", "id": "BID"}})

    def test_row3_already_enabled(self):
        api = Api(enabled={"APPLE_ID_AUTH"})
        self.assertFalse(self.run_with({SIWA: ["Default"]}, api))
        self.assertEqual(api.posts(), [])

    def test_row4_push_and_domains(self):
        api = Api()
        self.assertTrue(self.run_with({APS: "production", DOMAINS: ["applinks:example.com"]}, api))
        self.assertEqual([a["capabilityType"] for a in api.posts()], ["PUSH_NOTIFICATIONS", "ASSOCIATED_DOMAINS"])

    def test_row5_refused(self):
        with self.assertRaises(SystemExit):
            self.run_with({SIWA: ["Default"]}, Api(refuse=True))

    def test_row6_identity_recreates_profile(self):
        path = Path(self.tmp.name) / "Runner.entitlements"
        path.write_bytes(plistlib.dumps({SIWA: ["Default"]}))
        for enabled, expected in ((set(), True), ({"APPLE_ID_AUTH"}, False)):
            profiles = []
            ns = namespace(Api(enabled=enabled), profiles)
            cert = Path(self.tmp.name) / "cert.der"
            cert.write_bytes(b"cert")
            ns["certificate"] = lambda: ("CERT", Path(self.tmp.name) / "key.pem", cert)
            with patch.dict(os.environ, {"ASC_ENTITLEMENTS_PATH": str(path)}), patch("builtins.print"):
                ns["identity"]("app", "out")
            self.assertEqual(profiles, [("com.example.app", expected), ("com.example.app.widget", False)])


if __name__ == "__main__":
    unittest.main()
