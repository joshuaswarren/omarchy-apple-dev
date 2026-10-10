#!/usr/bin/env python3
"""App Store steps for ship.sh: stamp, frameworks, identity, test-identity, validate, upload.

Runs with the pymobiledevice3 venv's python, which already has `cryptography`.
API key: ASC_KEY_ID, ASC_ISSUER_ID, and ASC_KEY_PATH (default
~/.appstoreconnect/AuthKey_<ASC_KEY_ID>.p8). The key needs the App Manager role
with access to Certificates, Identifiers & Profiles, or Admin.
"""
import base64
import datetime
import hashlib
import json
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

API = "https://api.appstoreconnect.apple.com"
IDENTITY_DIR = Path(os.environ.get("ASC_IDENTITY_DIR", Path.home() / ".config/omarchy-apple-dev/distribution"))
TEST_IDENTITY_DIR = Path.home() / ".config/omarchy-apple-dev/test-identity"
TEST_TEAM = "TEST000000"
# SwiftPM keeps Swift SDKs under $XDG_CONFIG_HOME/swiftpm when that is set, else ~/.swiftpm.
SWIFTPM_DIR = (Path(os.environ["XDG_CONFIG_HOME"], "swiftpm") if os.environ.get("XDG_CONFIG_HOME")
               else Path.home() / ".swiftpm")
SDK = Path(os.environ.get("DARWIN_SDK", SWIFTPM_DIR / "swift-sdks/darwin.artifactbundle"))
XCODE_VERSION_PLISTS = sorted(Path.home().glob(".cache/xtool/darwin-*.xtoolsdk.version.plist"))
APP_GROUPS = [g for g in os.environ.get("APP_GROUPS", "").split(",") if g]


def die(msg):
    sys.exit(f"asc.py: {msg}")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def token():
    key_id, issuer = os.environ.get("ASC_KEY_ID"), os.environ.get("ASC_ISSUER_ID")
    if not key_id or not issuer:
        die("set ASC_KEY_ID and ASC_ISSUER_ID (App Store Connect > Users and Access > Integrations)")
    path = Path(os.environ.get("ASC_KEY_PATH", Path.home() / f".appstoreconnect/AuthKey_{key_id}.p8"))
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    now = int(time.time())
    header = b64url(json.dumps({"alg": "ES256", "kid": key_id, "typ": "JWT"}).encode())
    claims = b64url(json.dumps({"iss": issuer, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}).encode())
    r, s = decode_dss_signature(key.sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"{header}.{claims}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def call(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        die(f"{method} {path}: HTTP {e.code}\n{e.read().decode(errors='replace')}")
    return json.loads(raw) if raw else {}


def rel(kind, ident):
    return {"data": {"type": kind, "id": ident}}


# -- stamp -------------------------------------------------------------------

def stamp(app_dir, build_number):
    """Add the build-environment keys App Store processing reads from Info.plist."""
    sdk = SDK / "Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
    settings = json.loads((sdk / "SDKSettings.json").read_text())
    version_plist = sdk / "System/Library/CoreServices/SystemVersion.plist"
    sdk_build = plistlib.loads(version_plist.read_bytes())["ProductBuildVersion"]
    if XCODE_VERSION_PLISTS:
        xcode = plistlib.loads(XCODE_VERSION_PLISTS[-1].read_bytes())
        xcode_version, xcode_build = xcode["CFBundleShortVersionString"], xcode["ProductBuildVersion"]
    else:
        xcode_version, xcode_build = os.environ.get("XCODE_VERSION"), os.environ.get("XCODE_BUILD")
        if not xcode_version or not xcode_build:
            die("no Xcode version recorded with the SDK; set XCODE_VERSION (27.0) and XCODE_BUILD (27A266a)")
    major, minor, patch = (xcode_version.split(".") + ["0", "0"])[:3]
    keys = {
        "CFBundleVersion": build_number,
        "DTCompiler": "com.apple.compilers.llvm.clang.1_0",
        "DTPlatformBuild": sdk_build,
        "DTPlatformName": "iphoneos",
        "DTPlatformVersion": settings["Version"],
        "DTSDKBuild": sdk_build,
        "DTSDKName": settings["CanonicalName"],
        "DTXcode": f"{int(major):02d}{minor}{patch}",
        "DTXcodeBuild": xcode_build,
    }
    # App extensions need the same keys, the app's versions (ITMS-90473) and arm64 in
    # UIRequiredDeviceCapabilities (ITMS-90502), as Xcode writes them.
    info = None
    for info_path in [Path(app_dir) / "Info.plist", *sorted(Path(app_dir).glob("PlugIns/*.appex/Info.plist"))]:
        with info_path.open("rb") as f:
            bundle_info = plistlib.load(f)
        bundle_info.update(keys)
        # Xcode adds these to every bundle it processes; xtool only writes them
        # for the app. BuildMachineOSBuild is the build host's macOS build
        # (Xcode reads it from the running OS); set BUILD_MACHINE_OS_BUILD to
        # the oracle value when reproducing an Xcode build.
        bundle_info.setdefault("CFBundleSupportedPlatforms", ["iPhoneOS"])
        if "BUILD_MACHINE_OS_BUILD" in os.environ:
            bundle_info.setdefault("BuildMachineOSBuild", os.environ["BUILD_MACHINE_OS_BUILD"])
        if info is None:
            info = bundle_info
        else:
            bundle_info["CFBundleShortVersionString"] = info["CFBundleShortVersionString"]
            caps = bundle_info.get("UIRequiredDeviceCapabilities", [])
            if isinstance(caps, list) and "arm64" not in caps:
                bundle_info["UIRequiredDeviceCapabilities"] = [*caps, "arm64"]
            # Extensions inherit the app's device family when the target does
            # not set TARGETED_DEVICE_FAMILY (the generator writes it there).
            bundle_info.setdefault("UIDeviceFamily", info.get("UIDeviceFamily", [1, 2]))
        with info_path.open("wb") as f:
            plistlib.dump(bundle_info, f, fmt=plistlib.FMT_BINARY)
    # The Linux link writes the deployment target into LC_BUILD_VERSION's sdk field; App Store
    # processing reads the SDK version from there (ITMS-90725). Record the SDK actually used.
    sdk_raw = sum(int(p) << s for p, s in zip((settings["Version"].split(".") + ["0", "0"])[:3], (16, 8, 0)))
    patched = 0
    for path in Path(app_dir).rglob("*"):
        if path.is_file() and not path.is_symlink() and set_macho_sdk(path, sdk_raw):
            patched += 1
    print(f"stamped {info['CFBundleIdentifier']} {info['CFBundleShortVersionString']} ({build_number}), "
          f"{settings['CanonicalName']} {sdk_build}, Xcode {xcode_version} {xcode_build}, "
          f"Mach-O sdk {settings['Version']} in {patched} file(s)")


def set_macho_sdk(path, sdk_raw):
    """Set the sdk version of every iOS LC_BUILD_VERSION in a thin 64-bit Mach-O. True if changed."""
    with path.open("rb") as f:
        if f.read(4) != b"\xcf\xfa\xed\xfe":
            return False
    data = bytearray(path.read_bytes())
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off, changed = 32, False
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        if cmd == 0x32 and struct.unpack_from("<I", data, off + 8)[0] == 2:
            struct.pack_into("<I", data, off + 16, sdk_raw)
            changed = True
        off += size
    if changed:
        path.write_bytes(data)
    return changed


# LC_LOAD_DYLIB, LC_ID_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB
DYLIB_COMMANDS = {0xC, 0xD, 0x80000018, 0x8000001F, 0x80000023}
FRAMEWORK_INFO_KEYS = (
    "CFBundleShortVersionString", "CFBundleVersion", "CFBundleSupportedPlatforms", "MinimumOSVersion",
    "UIDeviceFamily", "DTCompiler", "DTPlatformBuild", "DTPlatformName", "DTPlatformVersion", "DTSDKBuild",
    "DTSDKName", "DTXcode", "DTXcodeBuild",
)


def frameworks(app_dir):
    """Wrap each Frameworks/lib<Name>.dylib (a SwiftPM .dynamic product) as <Name>.framework, as
    Xcode does. App Store processing takes a loose dylib there for a Swift runtime library and
    rejects the build for a missing SwiftSupport folder (ITMS-90426). Run after stamp."""
    app = Path(app_dir)
    with (app / "Info.plist").open("rb") as f:
        info = plistlib.load(f)
    renames = {}
    for dylib in sorted(app.glob("Frameworks/lib*.dylib")):
        name = dylib.name[len("lib"):-len(".dylib")]
        framework = dylib.parent / f"{name}.framework"
        framework.mkdir()
        dylib.rename(framework / name)
        renames[f"@rpath/{dylib.name}".encode()] = f"@rpath/{name}.framework/{name}".encode()
        framework_info = {k: info[k] for k in FRAMEWORK_INFO_KEYS if k in info}
        framework_info.update({
            "CFBundleExecutable": name,
            "CFBundleIdentifier": f"{info['CFBundleIdentifier']}.{re.sub(r'[^A-Za-z0-9.-]', '-', name)}",
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": name,
            "CFBundlePackageType": "FMWK",
        })
        with (framework / "Info.plist").open("wb") as f:
            plistlib.dump(framework_info, f, fmt=plistlib.FMT_BINARY)
    for path in app.rglob("*"):
        if renames and path.is_file() and not path.is_symlink():
            rename_dylibs(path, renames)
    print(f"wrapped {len(renames)} dylib(s) as frameworks")


def rename_dylibs(path, renames):
    """Rewrite dylib install names in the load commands of a thin 64-bit Mach-O, in place. The
    longer names use the header padding before the first section."""
    with path.open("rb") as f:
        if f.read(4) != b"\xcf\xfa\xed\xfe":
            return
    data = bytearray(path.read_bytes())
    ncmds, sizeofcmds = struct.unpack_from("<2I", data, 16)
    off, commands, changed, first_section = 32, [], False, len(data)
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        raw = bytes(data[off:off + size])
        if cmd in DYLIB_COMMANDS:
            name = raw[struct.unpack_from("<I", raw, 8)[0]:].split(b"\0", 1)[0]
            if name in renames:
                new_name = renames[name] + b"\0" * (8 - (len(renames[name]) % 8))
                raw = struct.pack("<3I", cmd, 24 + len(new_name), 24) + raw[12:24] + new_name
                changed = True
        elif cmd == 0x19:  # LC_SEGMENT_64
            for i in range(struct.unpack_from("<I", raw, 64)[0]):
                sect_offset, = struct.unpack_from("<I", raw, 72 + i * 80 + 48)
                sect_type = struct.unpack_from("<I", raw, 72 + i * 80 + 64)[0] & 0xFF
                if sect_offset and sect_type not in (0x1, 0xC, 0x12):  # zerofill sections have no bytes
                    first_section = min(first_section, sect_offset)
        commands.append(raw)
        off += size
    if not changed:
        return
    new = b"".join(commands)
    if 32 + len(new) > first_section:
        die(f"{path}: no header room to rename its dylibs (link with -headerpad_max_install_names)")
    struct.pack_into("<I", data, 20, len(new))
    data[32:32 + max(len(new), sizeofcmds)] = new.ljust(sizeofcmds, b"\0")
    path.write_bytes(data)


# -- identity ----------------------------------------------------------------

def certificate():
    """Reuse the local Apple Distribution identity, or create one (key never leaves this machine)."""
    key_path, cert_path = IDENTITY_DIR / "key.pem", IDENTITY_DIR / "cert.der"
    if cert_path.exists():
        cert = x509.load_der_x509_certificate(cert_path.read_bytes())
        serial = format(cert.serial_number, "X")
        listed = call("GET", "/v1/certificates?filter[certificateType]=DISTRIBUTION&limit=200")["data"]
        found = [c for c in listed
                 if c["attributes"].get("serialNumber", "").upper().lstrip("0") == serial.lstrip("0")]
        if found and cert.not_valid_after_utc.timestamp() > time.time():
            return found[0]["id"], key_path, cert_path
        print(f"local certificate {serial} is expired or revoked; creating a new one")
    IDENTITY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "omarchy-apple-dev")]))
           .sign(key, hashes.SHA256()))
    created = call("POST", "/v1/certificates", {"data": {"type": "certificates", "attributes": {
        "certificateType": "DISTRIBUTION",
        "csrContent": csr.public_bytes(serialization.Encoding.PEM).decode(),
    }}})["data"]
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    cert_path.write_bytes(base64.b64decode(created["attributes"]["certificateContent"]))
    print(f"created Apple Distribution certificate {created['attributes'].get('serialNumber')}")
    return created["id"], key_path, cert_path


def bundle_id(identifier):
    found = call("GET", f"/v1/bundleIds?filter[identifier]={identifier}")["data"]
    exact = [b for b in found if b["attributes"]["identifier"] == identifier]
    if exact:
        return exact[0]["id"]
    print(f"registering bundle id {identifier}")
    return call("POST", "/v1/bundleIds", {"data": {"type": "bundleIds", "attributes": {
        "identifier": identifier, "name": identifier.replace(".", " "), "platform": "IOS",
    }}})["data"]["id"]


def profile(identifier, cert_id, force_create=False):
    name = f"omarchy-apple-dev {identifier} {cert_id[:8]}"
    found = call("GET", f"/v1/profiles?filter[name]={urllib.request.quote(name)}"
                        "&filter[profileType]=IOS_APP_STORE&filter[profileState]=ACTIVE")["data"]
    if found and not force_create:
        return base64.b64decode(found[0]["attributes"]["profileContent"])
    if found and force_create:
        print(f"recreating App Store profile '{name}' to pick up newly enabled capabilities")
        call("DELETE", f"/v1/profiles/{found[0]['id']}")
    print(f"creating App Store profile '{name}'")
    created = call("POST", "/v1/profiles", {"data": {
        "type": "profiles",
        "attributes": {"name": name, "profileType": "IOS_APP_STORE"},
        "relationships": {
            "bundleId": rel("bundleIds", bundle_id(identifier)),
            "certificates": {"data": [{"type": "certificates", "id": cert_id}]},
        },
    }})["data"]
    return base64.b64decode(created["attributes"]["profileContent"])


def ensure_app_groups(identifiers):
    """Best-effort enable APP_GROUPS capability on each bundle id via the API. Returns the subset
    of identifiers for which the call returned 201 (or the capability was already enabled), so the
    caller can re-create the matching profiles to pick up the new grant. Per Apple's public OpenAPI
    the bundleIdCapabilities endpoint exists but does not expose app-group identifiers in the
    capability body; if the API rejects the request we report it and fall back to dropping the
    entitlement."""
    if not APP_GROUPS:
        return set()
    attached = set()
    for ident in identifiers:
        bid = bundle_id(ident)
        try:
            existing = call("GET", f"/v1/bundleIds/{bid}/bundleIdCapabilities")["data"]
            if any(c.get("attributes", {}).get("capabilityType") == "APP_GROUPS" for c in existing):
                print(f"APP_GROUPS capability already enabled for {ident}")
                attached.add(ident)
                continue
            call("POST", "/v1/bundleIdCapabilities", {"data": {
                "type": "bundleIdCapabilities",
                "attributes": {"capabilityType": "APP_GROUPS"},
                "relationships": {"bundleId": rel("bundleIds", bid)},
            }})
            print(f"enabled APP_GROUPS capability for {ident}")
            attached.add(ident)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace") if e.fp else ""
            print(f"warning: cannot enable APP_GROUPS for {ident}: HTTP {e.code} {e.reason} {body[:160]}")
    return attached


def identity(app_dir, out_dir):
    """Apple identity via the API: register each bundle id, write embedded.mobileprovision into the
    app and every PlugIns/*.appex, and write per-bundle entitlements and the signing key/cert into
    out_dir."""
    cert_id, key_path, cert_path = certificate()
    idents = [ident for _, ident in bundles(app_dir)]
    attached = ensure_app_groups(idents)
    prov_for = lambda ident, c=attached, ci=cert_id: profile(
        ident, ci, force_create=(ident in c))
    install_all_bundles(app_dir, out_dir, prov_for, key_path, cert_path)


def test_identity(app_dir, out_dir):
    """A local stand-in with the same shape as an Apple Distribution identity and App Store profile,
    signed by a self-made certificate. It exercises signing and validation; Apple rejects it."""
    team = TEST_TEAM
    key_path, cert_path = TEST_IDENTITY_DIR / "key.pem", TEST_IDENTITY_DIR / "cert.der"
    now = datetime.datetime.now(datetime.timezone.utc)
    if not cert_path.exists():
        TEST_IDENTITY_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, f"Apple Distribution: omarchy-apple-dev TEST ({team})"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, team),
        ])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=365))
                .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CODE_SIGNING]), critical=True)
                .add_extension(x509.KeyUsage(
                    digital_signature=True, content_commitment=False, key_encipherment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                    encipher_only=False, decipher_only=False), critical=True)
                .sign(key, hashes.SHA256()))
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        key_path.chmod(0o600)
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    cert = x509.load_der_x509_certificate(cert_path.read_bytes())
    install_all_bundles(app_dir, out_dir,
                        lambda ident: make_test_profile(ident, key, cert, now), key_path, cert_path)
    print(f"TEST identity (self-signed, team {team}): Apple will reject this signature; use it to check the pipeline")


def make_test_profile(identifier, key, cert, now):
    team = TEST_TEAM
    entitlements = {
        "application-identifier": f"{team}.{identifier}", "com.apple.developer.team-identifier": team,
        "beta-reports-active": True, "get-task-allow": False, "keychain-access-groups": [f"{team}.*"],
    }
    if APP_GROUPS:
        entitlements["com.apple.security.application-groups"] = list(APP_GROUPS)
    payload = plistlib.dumps({
        "AppIDName": identifier, "ApplicationIdentifierPrefix": [team], "Platform": ["iOS"],
        "CreationDate": now.replace(tzinfo=None), "ExpirationDate": cert.not_valid_after_utc.replace(tzinfo=None),
        "DeveloperCertificates": [cert_path_bytes()],
        "Entitlements": entitlements,
        "Name": f"omarchy-apple-dev TEST profile {identifier} (not from Apple)",
        "TeamIdentifier": [team], "TeamName": "omarchy-apple-dev TEST", "TimeToLive": 365,
        "UUID": str(uuid.uuid4()).upper(), "Version": 1,
    })
    return (pkcs7.PKCS7SignatureBuilder().set_data(payload)
            .add_signer(cert, key, hashes.SHA256()).sign(serialization.Encoding.DER, []))


def cert_path_bytes():
    return (TEST_IDENTITY_DIR / "cert.der").read_bytes()


def bundles(app_dir):
    """The app and every PlugIns/*.appex, in deterministic order, each paired with its bundle id."""
    app = Path(app_dir)
    out = [(app, bundle_identifier(app))]
    for appex in sorted(app.glob("PlugIns/*.appex")):
        out.append((appex, bundle_identifier(appex)))
    return out


def install_all_bundles(app_dir, out_dir, prov_for, key_path, cert_path):
    """For every bundle (app + each PlugIns/*.appex): embed the profile, write a per-bundle
    entitlements plist (application-identifier, team-identifier, beta-reports-active if granted,
    get-task-allow false; com.apple.security.application-groups if the profile grants it; if a
    requested APP_GROUPS group is dropped, emit one warning naming it)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups_warned = False
    for path, ident in bundles(app_dir):
        prov = prov_for(ident)
        (path / "embedded.mobileprovision").write_bytes(prov)
        payload = profile_payload(prov)
        granted = payload["Entitlements"]
        entitlements = {k: granted[k] for k in (
            "application-identifier", "com.apple.developer.team-identifier", "beta-reports-active",
            "keychain-access-groups")
            if k in granted}
        entitlements["get-task-allow"] = False
        granted_groups = set(granted.get("com.apple.security.application-groups", []))
        if granted_groups:
            entitlements["com.apple.security.application-groups"] = sorted(granted_groups)
        elif APP_GROUPS and not groups_warned:
            print(f"warning: com.apple.security.application-groups dropped for {ident} "
                  f"(profile grants none; requested {', '.join(APP_GROUPS)})")
            groups_warned = True
        ent_name = "entitlements.plist" if path == Path(app_dir) else f"{path.stem}-entitlements.plist"
        (out / ent_name).write_bytes(plistlib.dumps(entitlements))
        print(f"identity for {entitlements['application-identifier']}: profile {payload['UUID']}, "
              f"expires {payload['ExpirationDate']:%Y-%m-%d}")
    for name, src in (("key.pem", key_path), ("cert.der", cert_path)):
        dest = out / name
        dest.unlink(missing_ok=True)
        dest.symlink_to(src)


def bundle_identifier(app_dir):
    with (Path(app_dir) / "Info.plist").open("rb") as f:
        return plistlib.load(f)["CFBundleIdentifier"]


def profile_payload(prov):
    # A profile is CMS-signed; its payload is a plain XML plist.
    return plistlib.loads(prov[prov.index(b"<?xml"):prov.index(b"</plist>") + len(b"</plist>")])


# -- validate ----------------------------------------------------------------

REQUIRED_INFO_KEYS = (
    "CFBundleIdentifier", "CFBundleExecutable", "CFBundleName", "CFBundleShortVersionString", "CFBundleVersion",
    "CFBundlePackageType", "CFBundleSupportedPlatforms", "CFBundleInfoDictionaryVersion", "MinimumOSVersion",
    "UIDeviceFamily", "UIRequiredDeviceCapabilities", "CFBundleIcons",
    "DTCompiler", "DTPlatformBuild", "DTPlatformName", "DTPlatformVersion", "DTSDKBuild", "DTSDKName",
    "DTXcode", "DTXcodeBuild",
)
IPAD_ORIENTATIONS = {
    "UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown",
    "UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight",
}


def macho(path):
    """(cputype, filetype, flags, minos, sdk, has code signature) of a thin 64-bit Mach-O;
    minos and sdk are version tuples or None."""
    data = Path(path).read_bytes()
    magic, cputype, _, filetype, ncmds, _, flags, _ = struct.unpack_from("<8I", data, 0)
    if magic != 0xFEEDFACF:
        return None
    off, minos, sdk, signed = 32, None, None, False
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        if cmd == 0x32:  # LC_BUILD_VERSION
            platform, raw_min, raw_sdk = struct.unpack_from("<3I", data, off + 8)
            if platform == 2:  # PLATFORM_IOS
                minos = (raw_min >> 16, (raw_min >> 8) & 0xFF, raw_min & 0xFF)
                sdk = (raw_sdk >> 16, (raw_sdk >> 8) & 0xFF, raw_sdk & 0xFF)
        elif cmd == 0x1D:  # LC_CODE_SIGNATURE
            signed = True
        off += size
    return cputype, filetype, flags, minos, sdk, signed


def loads_dylib(path, needle):
    """True if a thin 64-bit Mach-O has a load/weak/reexport/upward dylib command naming needle."""
    data = Path(path).read_bytes()
    if data[:4] != b"\xcf\xfa\xed\xfe":
        return False
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        if cmd in DYLIB_COMMANDS - {0xD}:
            name_off = struct.unpack_from("<I", data, off + 8)[0]
            if needle in data[off + name_off:off + size].split(b"\0", 1)[0]:
                return True
        off += size
    return False


# Protocol descriptors a binary imports when it declares an AppIntent, AppEntity, AppEnum or
# EntityQuery type (an App Shortcuts provider needs an AppIntent too).
APP_INTENTS_TYPE_SYMBOLS = (b"_$s10AppIntents0A6IntentMp", b"_$s10AppIntents0A6EntityMp",
                            b"_$s10AppIntents0A4EnumMp", b"_$s10AppIntents11EntityQueryMp")


def check_app_intents(check, bundle, exe):
    """Xcode writes Metadata.appintents for a bundle that links AppIntents and declares App Intents
    types (none when it only links the framework); without it the system registers none of the
    bundle's intents, App Shortcuts or widget configurations."""
    if not exe.is_file() or not loads_dylib(exe, b"/AppIntents.framework/"):
        return
    meta = bundle / "Metadata.appintents"
    data = exe.read_bytes()
    if any(s in data for s in APP_INTENTS_TYPE_SYMBOLS) or meta.exists():
        check((meta / "extract.actionsdata").is_file() and (meta / "version.json").is_file(),
              f"{bundle.name} declares App Intents types and has Metadata.appintents/extract.actionsdata + version.json")


def car_renditions(path):
    """(width, height, rendition name) for every CSI header in an Assets.car."""
    data, out, i = Path(path).read_bytes(), [], 0
    while (i := data.find(b"ISTC", i)) >= 0:
        width, height = struct.unpack_from("<2I", data, i + 12)
        out.append((width, height, data[i + 40:i + 168].split(b"\0")[0].decode(errors="replace")))
        i += 4
    return out


def png_info(path):
    """(width, height, has alpha) from a PNG IHDR."""
    data = Path(path).read_bytes()[:33]
    width, height, _, color_type = struct.unpack(">2I2B", data[16:26])
    return width, height, color_type in (4, 6)


def version_tuple(s):
    return tuple(int(p) for p in (s.split(".") + ["0", "0"])[:3])


def signature_blob(rcodesign, exe, magic):
    raw = subprocess.run([rcodesign, "extract", "signature-raw", str(exe)], capture_output=True, check=True).stdout
    i = raw.find(magic)
    if i < 0:
        return None
    length = struct.unpack_from(">I", raw, i + 4)[0]
    return raw[i + 8:i + length]


def placeholder_hits(node, where=""):
    """Paths of string values (at any depth) still carrying an unresolved
    $(BUILD_SETTING) placeholder - Xcode bakes every one of these in, so a
    surviving placeholder means the build pipeline dropped a key."""
    if isinstance(node, str):
        return [where] if "$(" in node else []
    if isinstance(node, list):
        return [hit for i, item in enumerate(node)
                for hit in placeholder_hits(item, f"{where}[{i}]")]
    if isinstance(node, dict):
        return [hit for key, item in node.items()
                for hit in placeholder_hits(item, f"{where}.{key}" if where else key)]
    return []


def _check_bundle_layout(check, names, apps):
    """Zip layout: everything under Payload/, no junk, exactly one .app."""
    check(all(n.startswith("Payload/") for n in names), "every entry is under Payload/")
    check(not any("__MACOSX" in n or n.endswith(".DS_Store") for n in names), "no __MACOSX or .DS_Store")
    if not check(len(apps) == 1, f"exactly one app bundle in Payload/: {apps}"):
        sys.exit(1)


def _check_bundle_contents(check, app, rcodesign):
    """Frameworks: extensions carry none, no loose dylibs, FMWK + signed."""
    nested = sorted(p.parent.name for p in app.glob("PlugIns/*.appex/Frameworks"))
    check(not nested, f"app extensions carry no Frameworks/ (ITMS-90206){': ' + ', '.join(nested) if nested else ''}")
    loose = sorted(p.name for p in app.glob("Frameworks/*.dylib"))
    check(not loose, f"no loose dylibs in Frameworks/ (ITMS-90426){': ' + ', '.join(loose) if loose else ''}")
    for framework in sorted(app.glob("Frameworks/*.framework")):
        with (framework / "Info.plist").open("rb") as f:
            finfo = plistlib.load(f)
        fexe = framework / finfo.get("CFBundleExecutable", "")
        fverify = subprocess.run([rcodesign, "verify", str(fexe)], capture_output=True, text=True, check=False)
        check(finfo.get("CFBundlePackageType") == "FMWK" and fexe.is_file() and fverify.returncode == 0,
              f"framework {framework.name}: FMWK Info.plist, signed executable")


def _check_info_plist(check, app, info):
    """The app Info.plist: required keys, placeholders, versions, UI keys.
    Returns True when iPad is a target family (sizes the icon checks)."""
    missing = [k for k in REQUIRED_INFO_KEYS if k not in info]
    check(not missing, f"Info.plist has the required keys{': missing ' + ', '.join(missing) if missing else ''}")
    unresolved = []
    for ipath in sorted(app.rglob("Info.plist")):
        with ipath.open("rb") as f:
            for where in placeholder_hits(plistlib.load(f)):
                unresolved.append(f"{ipath.relative_to(app)}:{where or '/'}")
    check(not unresolved,
          "Info.plists have no unresolved $(...) placeholders"
          f"{': ' + '; '.join(unresolved) if unresolved else ''}")
    number = re.compile(r"^\d+(\.\d+){0,2}$")
    short, build = info.get("CFBundleShortVersionString", ""), info.get("CFBundleVersion", "")
    check(bool(number.match(short)), f"CFBundleShortVersionString '{short}' is up to three integers")
    check(bool(number.match(build)), f"CFBundleVersion '{build}' is up to three integers")
    check(info.get("CFBundlePackageType") == "APPL", "CFBundlePackageType is APPL")
    check(info.get("CFBundleSupportedPlatforms") == ["iPhoneOS"], "CFBundleSupportedPlatforms is [iPhoneOS]")
    check(info.get("DTPlatformName") == "iphoneos" and str(info.get("DTSDKName", "")).startswith("iphoneos"),
          f"built against the device SDK: {info.get('DTSDKName')}")
    check(str(info.get("DTXcode", "")).isdigit(), f"DTXcode {info.get('DTXcode')} / {info.get('DTXcodeBuild')}")
    check("UILaunchScreen" in info or "UILaunchStoryboardName" in info, "launch screen declared")
    # App Store processing checks UIMainStoryboardFile (90029, Mastodon). NetNewsWire build ad8849b0 was
    # VALID with UILaunchStoryboardName and its scene manifest naming storyboards that were missing.
    for name in sorted({v for k, v in info.items() if k.split("~")[0] == "UIMainStoryboardFile"}):
        found = [p for p in app.glob(f"**/{name}*.storyboardc")
                 if p.name in (f"{name}.storyboardc", f"{name}~iphone.storyboardc", f"{name}~ipad.storyboardc")]
        check(bool(found), f"UIMainStoryboardFile '{name}' is compiled in the bundle (ITMS-90029)")
    families = info.get("UIDeviceFamily", [])
    check(bool(families) and set(families) <= {1, 2}, f"UIDeviceFamily {families} has only iPhone/iPad (ITMS-90100)")
    ipad = 2 in families
    if ipad and not info.get("UIRequiresFullScreen"):
        check(IPAD_ORIENTATIONS <= set(info.get("UISupportedInterfaceOrientations~ipad", [])),
              "iPad multitasking: all four iPad orientations declared")
    return ipad


def _check_executable(check, app, info, exe):
    """The app executable: thin arm64 PIE Mach-O built for the device SDK."""
    header = macho(exe) if exe.is_file() else None
    if check(header is not None, f"executable {exe.name} is a thin 64-bit Mach-O"):
        cputype, filetype, mh_flags, minos, sdk, signed = header
        check(cputype == 0x0100000C and filetype == 2, "arm64 MH_EXECUTE")
        check(bool(mh_flags & 0x200000), "position independent (MH_PIE)")
        plist_min = version_tuple(info.get("MinimumOSVersion", "0"))
        check(minos is not None and minos <= plist_min,
              f"LC_BUILD_VERSION iOS minos {minos} <= MinimumOSVersion {info.get('MinimumOSVersion')}")
        check(sdk is not None and sdk >= (26, 0, 0), f"LC_BUILD_VERSION sdk {sdk} is iOS 26 or later (ITMS-90725)")
        check(signed, "LC_CODE_SIGNATURE present")
    check_app_intents(check, app, exe)


def _check_assets(check, app, info, ipad):
    """Assets.car and the icon set: App Store 1024 (plus phone/iPad sizes when
    a multi-size set is present), primary icon name, declared icon files."""
    car = app / "Assets.car"
    sizes = {(w, h) for w, h, _ in car_renditions(car)} if car.exists() else set()
    check(car.exists(), f"Assets.car present ({len(sizes)} rendition sizes)")
    # actool 27.0 stores only the 1024 icon for a single-size AppIcon (the form App Store
    # processing accepted, FINDINGS.md 35); a multi-size set must then be complete.
    needed = {(1024, 1024): "App Store 1024"}
    if sizes & {(120, 120), (180, 180), (152, 152), (167, 167)}:
        needed[(120, 120)] = "iPhone 60@2x"
        if ipad:
            needed.update({(152, 152): "iPad 76@2x", (167, 167): "iPad Pro 83.5@2x"})
    for size, label in needed.items():
        check(size in sizes, f"Assets.car has the {label} icon ({size[0]}x{size[1]})")
    primary = info.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {})
    check(bool(primary.get("CFBundleIconName")), "CFBundleIcons names the primary icon (CFBundleIconName)")
    marketing = app / f"{primary.get('CFBundleIconName', 'AppIcon')}1024x1024.png"
    if marketing.exists():
        check(not png_info(marketing)[2], "App Store icon has no alpha channel")
    for stem in primary.get("CFBundleIconFiles", []):
        check(any(app.glob(f"{stem}*.png")), f"declared icon file {stem}*.png is in the bundle")


def _check_profile(check, app, info, exe, rcodesign):
    """embedded.mobileprovision: app id coverage, App Store kind, validity,
    then the executable's signature against it. Skips to the seals when the
    profile is missing."""
    prov_path = app / "embedded.mobileprovision"
    if not check(prov_path.exists(), "embedded.mobileprovision present"):
        return
    prov = profile_payload(prov_path.read_bytes())
    team = (prov.get("TeamIdentifier") or [""])[0]
    granted = prov.get("Entitlements", {})
    app_id = granted.get("application-identifier", "")
    check(app_id in (f"{team}.{info.get('CFBundleIdentifier')}", f"{team}.*"),
          f"profile app id {app_id} covers {info.get('CFBundleIdentifier')}")
    check("ProvisionedDevices" not in prov and not prov.get("ProvisionsAllDevices"),
          "App Store profile (no device list, not enterprise)")
    check(granted.get("get-task-allow") is False, "profile get-task-allow is false")
    expires = prov["ExpirationDate"].replace(tzinfo=datetime.timezone.utc)
    check(expires > datetime.datetime.now(datetime.timezone.utc), f"profile valid until {expires:%Y-%m-%d}")
    if prov.get("TeamName") == "omarchy-apple-dev TEST":
        print("note TEST identity: structure only; Apple rejects this signature")
    _check_signature_seals(check, app, exe, rcodesign, prov, team, app_id)


def _check_signature_seals(check, root, exe, rcodesign, prov, team, app_id):
    """The app executable's signature against its profile: rcodesign verify,
    CodeDirectory team, sealed Info.plist/CodeResources hashes, sealed file
    set, signed entitlements, signing certificate."""
    granted = prov.get("Entitlements", {})
    verify = subprocess.run([rcodesign, "verify", str(exe)], capture_output=True, text=True, check=False)
    check(verify.returncode == 0,
          f"rcodesign verify {exe.name}{'' if verify.returncode == 0 else ': ' + verify.stderr.strip()[-200:]}")
    cd = subprocess.run([rcodesign, "extract", "code-directory", str(exe)],
                        capture_output=True, text=True, check=True).stdout
    cd_team = re.search(r'team_name: Some\(\s*"([^"]*)"', cd)
    check(bool(cd_team) and cd_team.group(1) == team,
          f"CodeDirectory team id {cd_team.group(1) if cd_team else None} matches the profile")
    slots = dict(re.findall(r"(Info|Resources) \(\d\): ([0-9a-f]{64})", cd))
    seal = root / "_CodeSignature" / "CodeResources"
    check(slots.get("Info") == hashlib.sha256((root / "Info.plist").read_bytes()).hexdigest(),
          "Info.plist matches its sealed hash")
    check(seal.exists() and slots.get("Resources") == hashlib.sha256(seal.read_bytes()).hexdigest(),
          "_CodeSignature/CodeResources matches its sealed hash")
    files2 = plistlib.loads(seal.read_bytes()).get("files2", {}) if seal.exists() else {}
    changed = [p for p, v in files2.items() if not (isinstance(v, dict) and v.get("optional")) and (
        not (root / p).is_file()
        or (v["hash2"] if isinstance(v, dict) else v) != hashlib.sha256((root / p).read_bytes()).digest())]
    unsealed = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
                and str(p.relative_to(root)) not in files2
                and p not in (exe, root / "Info.plist", root / "PkgInfo")
                and p.relative_to(root).parts[0] != "_CodeSignature"]
    check(not changed and not unsealed, "every bundle file is sealed with a matching hash"
          f"{f'; changed {changed}' if changed else ''}{f'; unsealed {unsealed}' if unsealed else ''}")
    xml = signature_blob(rcodesign, exe, b"\xfa\xde\x71\x71")
    signed_ent = plistlib.loads(xml) if xml else {}
    check(signed_ent.get("application-identifier") == app_id
          and signed_ent.get("com.apple.developer.team-identifier") == team,
          f"signed entitlements match the profile: {signed_ent.get('application-identifier')}")
    check(signed_ent.get("get-task-allow") is False, "signed get-task-allow is false")
    extra = set(signed_ent) - set(granted)
    check(not extra,
          f"signed entitlements are a subset of the profile{': extra ' + str(extra) if extra else ''}")
    cms = subprocess.run([rcodesign, "extract", "cms-pem", str(exe)], capture_output=True, check=True).stdout
    signers = {c.public_bytes(serialization.Encoding.DER) for c in pkcs7.load_pem_pkcs7_certificates(cms)}
    check(bool(signers & set(prov.get("DeveloperCertificates", []))),
          "signing certificate is one of the profile's DeveloperCertificates")


def _check_appex(check, app, info, appex, rcodesign):
    """One embedded extension: build-environment and version match with the
    app, declared UI compiled, then its own profile and signature."""
    with (appex / "Info.plist").open("rb") as f:
        ainfo = plistlib.load(f)
    check(ainfo.get("DTPlatformName") == "iphoneos" and ainfo.get("DTXcode") == info.get("DTXcode"),
          f"appex {appex.name}: build-environment keys (ITMS-90507)")
    check(ainfo.get("CFBundleVersion") == info.get("CFBundleVersion")
          and ainfo.get("CFBundleShortVersionString") == info.get("CFBundleShortVersionString"),
          f"appex {appex.name}: versions match the app (ITMS-90473)")
    check("arm64" in ainfo.get("UIRequiredDeviceCapabilities", []),
          f"appex {appex.name}: UIRequiredDeviceCapabilities has arm64 (ITMS-90502)")
    extension = ainfo.get("NSExtension", {})
    if storyboard := extension.get("NSExtensionMainStoryboard"):
        check(any(appex.glob(f"**/{storyboard}.storyboardc")),
              f"appex {appex.name}: NSExtensionMainStoryboard '{storyboard}' is compiled in it (ITMS-90357)")
    if script := extension.get("NSExtensionAttributes", {}).get("NSExtensionJavaScriptPreprocessingFile"):
        check((appex / f"{script}.js").is_file(),
              f"appex {appex.name}: NSExtensionJavaScriptPreprocessingFile {script}.js at its root (ITMS-90362)")
    aexe = appex / ainfo.get("CFBundleExecutable", "")
    check_app_intents(check, appex, aexe)
    aprov = appex / "embedded.mobileprovision"
    if not check(aprov.exists(), f"appex {appex.name}: embedded.mobileprovision present"):
        return
    aprov_pl = profile_payload(aprov.read_bytes())
    ateam = (aprov_pl.get("TeamIdentifier") or [""])[0]
    agranted = aprov_pl["Entitlements"]
    aapp_id = agranted.get("application-identifier", "")
    check("ProvisionedDevices" not in aprov_pl and not aprov_pl.get("ProvisionsAllDevices"),
          f"appex {appex.name}: App Store profile")
    check(aapp_id in (f"{ateam}.{ainfo.get('CFBundleIdentifier')}", f"{ateam}.*"),
          f"appex {appex.name}: profile app id {aapp_id} covers {ainfo.get('CFBundleIdentifier')}")
    verify = subprocess.run([rcodesign, "verify", str(aexe)], capture_output=True, text=True, check=False)
    check(verify.returncode == 0,
          f"appex {appex.name}: rcodesign verify {aexe.name}"
          f"{'' if verify.returncode == 0 else ': ' + verify.stderr.strip()[-200:]}")
    acd = subprocess.run([rcodesign, "extract", "code-directory", str(aexe)],
                         capture_output=True, text=True, check=True).stdout
    acd_team = re.search(r'team_name: Some\(\s*"([^"]*)"', acd)
    check(bool(acd_team) and acd_team.group(1) == ateam,
          f"appex {appex.name}: CodeDirectory team id matches profile")
    aslots = dict(re.findall(r"(Info|Resources) \(\d\): ([0-9a-f]{64})", acd))
    aseal = appex / "_CodeSignature" / "CodeResources"
    check(aslots.get("Info") == hashlib.sha256((appex / "Info.plist").read_bytes()).hexdigest(),
          f"appex {appex.name}: Info.plist matches its sealed hash")
    check(aseal.exists() and aslots.get("Resources") == hashlib.sha256(aseal.read_bytes()).hexdigest(),
          f"appex {appex.name}: _CodeSignature/CodeResources matches its sealed hash")
    afiles2 = plistlib.loads(aseal.read_bytes()).get("files2", {}) if aseal.exists() else {}
    achanged = [p for p, v in afiles2.items() if not (isinstance(v, dict) and v.get("optional")) and (
        not (appex / p).is_file()
        or (v["hash2"] if isinstance(v, dict) else v) != hashlib.sha256((appex / p).read_bytes()).digest())]
    aunsealed = [str(p.relative_to(appex)) for p in appex.rglob("*") if p.is_file()
                 and str(p.relative_to(appex)) not in afiles2
                 and p not in (aexe, appex / "Info.plist", appex / "PkgInfo")
                 and p.relative_to(appex).parts[0] != "_CodeSignature"]
    check(not achanged and not aunsealed, f"appex {appex.name}: every file is sealed"
          f"{f'; changed {achanged}' if achanged else ''}"
          f"{f'; unsealed {aunsealed}' if aunsealed else ''}")
    axml = signature_blob(rcodesign, aexe, b"\xfa\xde\x71\x71")
    asent_ent = plistlib.loads(axml) if axml else {}
    check(asent_ent.get("application-identifier") == aapp_id
          and asent_ent.get("com.apple.developer.team-identifier") == ateam,
          f"appex {appex.name}: signed entitlements match its profile")
    check(asent_ent.get("get-task-allow") is False, f"appex {appex.name}: signed get-task-allow is false")
    aextra = set(asent_ent) - set(agranted)
    check(not aextra,
          f"appex {appex.name}: signed entitlements are a subset of its profile"
          f"{': extra ' + str(aextra) if aextra else ''}")
    acms = subprocess.run([rcodesign, "extract", "cms-pem", str(aexe)],
                          capture_output=True, check=True).stdout
    asigners = {c.public_bytes(serialization.Encoding.DER) for c in pkcs7.load_pem_pkcs7_certificates(acms)}
    check(bool(asigners & set(aprov_pl.get("DeveloperCertificates", []))),
          f"appex {appex.name}: signing certificate is one of the profile's DeveloperCertificates")


def _check_appexes(check, app, info, rcodesign):
    for appex in sorted(app.glob("PlugIns/*.appex")):
        _check_appex(check, app, info, appex, rcodesign)


def validate(ipa):
    """Check an .ipa offline against what App Store Connect rejects at upload. Exit 1 on any FAIL."""
    results = []

    def check(ok, msg):
        results.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {msg}")
        return ok

    rcodesign = (shutil.which("rcodesign", path=f"{os.environ.get('PATH', '')}:{Path.home() / '.local/bin'}")
                 or die("rcodesign not on PATH (install-toolchain.sh installs it)"))
    with zipfile.ZipFile(ipa) as z, tempfile.TemporaryDirectory() as tmp:
        names = z.namelist()
        apps = sorted({n.split("/")[1] for n in names if n.count("/") >= 2 and n.split("/")[1].endswith(".app")})
        _check_bundle_layout(check, names, apps)
        z.extractall(tmp)
        app = Path(tmp) / "Payload" / apps[0]
        _check_bundle_contents(check, app, rcodesign)
        with (app / "Info.plist").open("rb") as f:
            info = plistlib.load(f)
        ipad = _check_info_plist(check, app, info)
        exe = app / info.get("CFBundleExecutable", "")
        _check_executable(check, app, info, exe)
        _check_assets(check, app, info, ipad)
        _check_profile(check, app, info, exe, rcodesign)
        _check_appexes(check, app, info, rcodesign)

    failed = results.count(False)
    print(f"{len(results) - failed}/{len(results)} checks passed")
    if failed:
        sys.exit(1)

# -- upload ------------------------------------------------------------------

def upload(ipa):
    ipa = Path(ipa)
    with zipfile.ZipFile(ipa) as z:
        info_name = next(n for n in z.namelist() if n.count("/") == 2 and n.endswith(".app/Info.plist"))
        info = plistlib.loads(z.read(info_name))
    identifier = info["CFBundleIdentifier"]
    apps = call("GET", f"/v1/apps?filter[bundleId]={identifier}")["data"]
    if not apps:
        die(f"no App Store Connect app for {identifier}. Create it once in the web UI "
            "(Apps > + > New App); the API cannot create apps.")
    upload_id = call("POST", "/v1/buildUploads", {"data": {
        "type": "buildUploads",
        "attributes": {
            "cfBundleShortVersionString": info["CFBundleShortVersionString"],
            "cfBundleVersion": info["CFBundleVersion"],
            "platform": "IOS",
        },
        "relationships": {"app": rel("apps", apps[0]["id"])},
    }})["data"]["id"]
    data = ipa.read_bytes()
    file = call("POST", "/v1/buildUploadFiles", {"data": {
        "type": "buildUploadFiles",
        "attributes": {"assetType": "ASSET", "fileName": ipa.name, "fileSize": len(data), "uti": "com.apple.ipa"},
        "relationships": {"buildUpload": rel("buildUploads", upload_id)},
    }})["data"]
    for op in file["attributes"]["uploadOperations"]:
        part = data[op["offset"]:op["offset"] + op["length"]]
        headers = {h["name"]: h["value"] for h in op.get("requestHeaders") or []}
        req = urllib.request.Request(op["url"], data=part, method=op["method"], headers=headers)
        with urllib.request.urlopen(req, timeout=600) as resp:
            resp.read()
    print(f"uploaded {len(data)} bytes in {len(file['attributes']['uploadOperations'])} part(s)")
    call("PATCH", f"/v1/buildUploadFiles/{file['id']}", {"data": {
        "type": "buildUploadFiles", "id": file["id"],
        "attributes": {"uploaded": True, "sourceFileChecksums": {
            "file": {"hash": hashlib.md5(data).hexdigest(), "algorithm": "MD5"}}},
    }})
    state = {}
    for _ in range(120):
        state = call("GET", f"/v1/buildUploads/{upload_id}")["data"]["attributes"]["state"]
        if state.get("state") in ("COMPLETE", "FAILED"):
            break
        time.sleep(15)
    print(f"buildUpload {upload_id}: {state.get('state')}")
    for kind in ("errors", "warnings", "infos"):
        for item in state.get(kind) or []:
            print(f"  {kind[:-1]} {item.get('code')}: {item.get('description')}")
    if state.get("state") != "COMPLETE":
        sys.exit(1)


if __name__ == "__main__":
    commands = {"stamp": stamp, "frameworks": frameworks, "identity": identity, "test-identity": test_identity,
                "validate": validate, "upload": upload}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        die("usage: asc.py stamp APP BUILD | frameworks APP | identity APP OUTDIR | test-identity APP OUTDIR"
            " | validate IPA | upload IPA")
    commands[sys.argv[1]](*sys.argv[2:])
