#!/usr/bin/env bash
# Build a macOS .app from the SwiftPM package in the current directory, sign it, and notarize it.
#
#   ship-mac.sh             build and sign: Developer ID if the identity below exists, else ad hoc
#   ship-mac.sh --notarize  also notarize and staple the ticket. Needs a Developer ID identity and
#                             ASC_KEY_PATH=/path/to/AuthKey_XXXXXXXXXX.p8 ASC_ISSUER_ID=<uuid> ASC_KEY_ID=XXXXXXXXXX
#                             (or ASC_API_KEY_FILE pointing at an rcodesign-encoded key JSON)
#
# The bundle reproduces an Xcode layout from SwiftPM products: executable, local
# dynamic libraries and frameworks in Contents/Frameworks, the app target's
# resource bundle contents also laid flat in Contents/Resources (Xcode puts app
# resources there; Bundle.module still resolves into the kept bundle), every
# target .xib that tools/ibtool compiles as a .nib (failures listed, not fatal),
# the app icon recompiled with tools/darwin-tools' actool (AppIcon.icns + car
# renditions + CFBundleIconFile/CFBundleIconName), and Info.plist from the
# package root when the generator wrote one there (build settings already
# expanded), else a minimal generated one. Each xtool.yml extension is built
# (stub executable + Foundation`_NSExtensionMain) into PlugIns/<name>.appex and
# signed inside-out before the app; profiles from build/provision/ embed as
# embedded.provisionprofile.
#
# PRODUCT: the executable product (default: the package's only executable).
# BUNDLE_ID (default: xtool.yml bundleID, else com.example.<PRODUCT>), VERSION
# (default 1.0), BUILD_NUMBER (default UTC yyyymmddHHMM), MACOS_MIN (default:
# the Info.plist's LSMinimumSystemVersion, else 14.0). ENTITLEMENTS names a
# plist to sign with (default: <PRODUCT>.entitlements under the target's
# sources, else any one entitlements file there); $(VAR) placeholders expand
# from the product name, bundle id and the Info.plist's custom keys.
# DEVELOPER_ID_DIR holds key.pem + cert.pem of a "Developer ID Application"
# certificate (default ~/.config/omarchy-apple-dev/developer-id). Apple lets
# only the Account Holder create that certificate, in the developer portal; the
# API key cannot (FINDINGS.md 57).
# Output: build/<PRODUCT>.app and build/<PRODUCT>.zip.
set -euo pipefail

notarize=0
case "${1:-}" in
  --notarize) notarize=1 ;;
  "") ;;
  *) echo "usage: ship-mac.sh [--notarize]" >&2; exit 2 ;;
esac

repo=$(dirname "$(readlink -f "$0")")
PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$HOME/.local/bin:$PATH"
ulimit -n 65536 2>/dev/null || true
# SwiftPM keeps Swift SDKs under $XDG_CONFIG_HOME/swiftpm when that is set, else ~/.swiftpm.
sdk="${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/swiftpm}"
sdk="${sdk:-$HOME/.swiftpm}/swift-sdks/darwin.artifactbundle"
idir="${DEVELOPER_ID_DIR:-$HOME/.config/omarchy-apple-dev/developer-id}"
product="${PRODUCT:-$(swift package describe --type json | python3 -c '
import json, sys
exe = [p["name"] for p in json.load(sys.stdin)["products"] if "executable" in p["type"]]
sys.exit("set PRODUCT: no single executable product") if len(exe) != 1 else print(exe[0])')}"

# Bundle id: xtool.yml (the generator writes it) unless overridden.
bundle_id=${BUNDLE_ID:-$(sed -n 's/^bundleID:[[:space:]]*//p' xtool.yml 2>/dev/null | head -1)}
bundle_id=${bundle_id:-com.example.$product}
app_target_path=$(swift package describe --type json | python3 -c '
import json, sys
pkg = json.load(sys.stdin)
t = next(t for t in pkg["targets"] if t["name"] == sys.argv[1])
print(t.get("path", "Sources/" + sys.argv[1]))' "$product")

build_flags=(-c release --build-system swiftbuild
  --toolset "$sdk/toolset-swb.json" --product "$product" -Xlinker -rpath
  -Xlinker @executable_path/../Frameworks)

# Deployment target: the generator-expanded Info.plist knows the app's own minimum.
min=${MACOS_MIN:-$(python3 -c '
import os, plistlib, sys
try:
    print(plistlib.load(open("Info.plist", "rb"))["LSMinimumSystemVersion"])
except Exception:
    print("14.0")')}
project_version=$(python3 -c '
import plistlib
try:
    print(plistlib.load(open("Info.plist", "rb"))["CFBundleShortVersionString"])
except Exception:
    print("")' 2>/dev/null)

echo "== 1. Release build (arm64-apple-macosx$min) =="
# SwiftBuild finds the macOS platform only through the SDK bundle's platform folders and toolset.
XCODE_EXTRA_PLATFORM_FOLDERS="$sdk/Developer/Platforms" PATH="$sdk/toolset/bin:$PATH" \
  swift build "${build_flags[@]}" --triple "arm64-apple-macosx$min"
bin=$(XCODE_EXTRA_PLATFORM_FOLDERS="$sdk/Developer/Platforms" PATH="$sdk/toolset/bin:$PATH" \
  swift build "${build_flags[@]}" --triple "arm64-apple-macosx$min" --show-bin-path | tail -1)

echo "== 2. App bundle =="
app="build/$product.app"
mkdir -p build
[ ! -e "$app" ] || rm -r "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" "$app/Contents/Frameworks"
printf 'APPL????' > "$app/Contents/PkgInfo"
cp "$bin/$product" "$app/Contents/MacOS/$product"
# Local dynamic products and vendored frameworks: Xcode puts them in Frameworks,
# and the executable's @executable_path/../Frameworks rpath (set at link time
# above) resolves their @rpath install names there.
cp "$bin"/*.dylib "$app/Contents/Frameworks/" 2>/dev/null || true
for f in "$bin"/*.framework; do [ -d "$f" ] && cp -R "$f" "$app/Contents/Frameworks/"; done
for b in "$bin"/*.bundle; do [ -d "$b" ] && cp -R "$b" "$app/Contents/Resources/"; done
# The app target's own resources serve both lookups: Bundle.module reads the
# bundle copy, Bundle.main (Xcode-built code paths, AppKit nib localization)
# reads the flat copy.
res="$bin/${product}_${product}.bundle/Contents/Resources"
[ ! -d "$res" ] || cp -R "$res/." "$app/Contents/Resources/"

echo "== 3. Nibs =="
nib_failed=""
for xib in $(find -L "$app_target_path" -name '*.xib' | sort); do
  rel=${xib#"$app_target_path"/}
  lproj=$(echo "$(dirname "$rel")" | grep -o '[A-Za-z_-]*\.lproj$' || true)
  out="$app/Contents/Resources/${lproj:+$lproj/}$(basename "$rel" .xib).nib"
  mkdir -p "$(dirname "$out")"
  if "$repo/tools/ibtool" --module "$product" --compile "$out" "$xib" >/dev/null 2>&1; then
    echo "compiled $rel"
  else
    rm -f "$out"
    echo "warning: ibtool cannot compile $rel; leaving it out"
    nib_failed="$nib_failed $rel"
  fi
done
[ -z "$nib_failed" ] || echo "nibs not compiled:${nib_failed// /$'\n'  }"

echo "== 4. App icon =="
# `swift build` passes no --app-icon, so the app target's catalogs compile
# again here, the way Xcode's asset step runs actool: Apple's macosx actool
# emits AppIcon.icns + icon renditions in Assets.car + CFBundleIconFile and
# CFBundleIconName in the partial plist (FINDINGS.md 61, actool 27.0 oracle).
actool=${ACTOOL:-$repo/tools/darwin-tools/.build/release/actool}
if [ ! -x "$actool" ] && [ -z "${ACTOOL:-}" ]; then
  (cd "$repo/tools/darwin-tools" && swift build -c release --product actool >&2)
fi
icon_dir=$(mktemp -d)
catalogs=$(find -L "$app_target_path" -name '*.xcassets' | sort)
if [ -z "$catalogs" ]; then
  echo "no asset catalogs under $app_target_path"
elif "$actool" $catalogs --compile "$icon_dir" --platform macosx \
    --target-device mac --minimum-deployment-target "$min" \
    --app-icon "${APPICON:-AppIcon}" \
    --output-partial-info-plist "$icon_dir/partial.plist" >/dev/null 2>&1; then
  [ ! -f "$icon_dir/Assets.car" ] || cp "$icon_dir/Assets.car" "$app/Contents/Resources/Assets.car"
  for icns in "$icon_dir"/*.icns; do
    [ -f "$icns" ] && cp "$icns" "$app/Contents/Resources/"
  done
  mkdir -p build
  cp "$icon_dir/partial.plist" build/icon-partial.plist
  echo "app icon: $(cd "$icon_dir" && ls | tr '\n' ' ')"
else
  echo "warning: actool could not compile the ${APPICON:-AppIcon} icon set; bundle keeps the build's Assets.car"
fi

echo "== 5. Info.plist =="
python3 - "$app/Contents/Info.plist" "$product" "$bundle_id" "${VERSION:-${project_version:-1.0}}" \
  "${BUILD_NUMBER:-$(date -u +%Y%m%d%H%M)}" "$min" <<'PY'
import os, plistlib, sys
path, name, ident, version, build, minos = sys.argv[1:]
try:  # the generator writes the project's Info.plist, placeholders expanded
    plist = plistlib.load(open("Info.plist", "rb"))
    plist.pop("OrganizationIdentifier", None)
except Exception:
    plist = {"NSPrincipalClass": "NSApplication"}
plist.update({
    "CFBundleExecutable": name, "CFBundleIdentifier": ident, "CFBundleName": name,
    "CFBundlePackageType": "APPL", "CFBundleShortVersionString": version,
    "CFBundleVersion": build, "CFBundleSupportedPlatforms": ["MacOSX"],
    "LSMinimumSystemVersion": minos,
})
try:  # Xcode merges actool's partial plist into the app Info.plist
    for key, value in plistlib.load(open("build/icon-partial.plist", "rb")).items():
        plist.setdefault(key, value)
except Exception:
    pass
plistlib.dump(plist, open(path, "wb"))
PY

echo "== 6. Extensions =="
# Each xtool.yml extension becomes a PlugIns/<name>.appex: a stub executable
# linked against the extension product with Foundation`_NSExtensionMain as the
# entry point (xtool's iOS recipe; macOS Foundation exports the same symbol),
# the generator's Info.plist with $(PRODUCT_MODULE_NAME) expanded, the
# target's resource bundle plus a flat copy, per-extension entitlements and
# provisioning profile, signed inside-out with Developer ID.
mkdir -p build
python3 - xtool.yml > build/extensions.tsv <<'PY'
import re, sys
cur, rows = None, []
for line in open(sys.argv[1], encoding="utf-8"):
    m = re.match(r"\s*-\s*product:\s*(.+?)\s*$", line)
    if m:
        cur = [m.group(1), "", ""]
        rows.append(cur)
        continue
    m = re.match(r"\s*(bundleID|infoPath):\s*(.+?)\s*$", line)
    if m and cur is not None:
        cur[1 if m.group(1) == "bundleID" else 2] = m.group(2)
for row in rows:
    print("\t".join(row))
PY

pkg_json=$(swift package describe --type json)
while IFS=$'\t' read -r ext ext_bundle ext_info; do
  [ -n "$ext" ] || continue
  echo "-- extension $ext ($ext_bundle)"
  ext_path=$(printf '%s' "$pkg_json" | EXTN="$ext" python3 -c '
import json, os, sys
pkg = json.load(sys.stdin)
t = next(t for t in pkg["targets"] if t["name"] == os.environ["EXTN"])
print(t.get("path", "Sources/" + os.environ["EXTN"]))')
  ext_dir="build/ext/$ext"
  mkdir -p "$ext_dir/Sources/$ext-Extension"
  : > "$ext_dir/Sources/$ext-Extension/stub.c"
  EXTN="$ext" MINV="$min" python3 - "$ext_dir/Package.swift" <<'PY'
import json, os, sys
ext, minos = os.environ["EXTN"], os.environ["MINV"]
open(sys.argv[1], "w").write(f'''// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: {json.dumps(ext + "-Builder")},
    platforms: [.macOS({json.dumps(minos)})],
    dependencies: [.package(name: "Adapter", path: "../../..")],
    targets: [
        .executableTarget(
            name: {json.dumps(ext + "-Extension")},
            dependencies: [.product(name: {json.dumps(ext)}, package: "Adapter")],
            linkerSettings: [
                .linkedFramework("Foundation"),
                .unsafeFlags([
                    "-Xlinker", "-e", "-Xlinker", "_NSExtensionMain",
                    "-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks",
                    "-Xlinker", "-rpath", "-Xlinker", "@executable_path/../../Frameworks",
                ]),
            ]
        )
    ]
)
''')
PY
  ext_build() {
    (cd "$ext_dir" && XCODE_EXTRA_PLATFORM_FOLDERS="$sdk/Developer/Platforms" \
      PATH="$sdk/toolset/bin:$PATH" swift build -c release --build-system swiftbuild \
      --toolset "$sdk/toolset-swb.json" --triple "arm64-apple-macosx$min" "$@")
  }
  ext_build 2>&1 | tail -1
  ext_bin=$(ext_build --show-bin-path | tail -1)
  appex="$app/Contents/PlugIns/$ext.appex"
  mkdir -p "$appex/Contents/MacOS" "$appex/Contents/Resources"
  cp "$ext_bin/$ext-Extension" "$appex/Contents/MacOS/$ext"
  for b in "$ext_bin"/*.bundle; do
    [ -d "$b" ] || continue
    cp -R "$b" "$appex/Contents/Resources/"
    cp -R "$b/Contents/Resources/." "$appex/Contents/Resources/" 2>/dev/null || true
  done
  python3 - "$appex/Contents/Info.plist" "$ext" "$ext_bundle" "$ext_info" \
    "${VERSION:-${project_version:-1.0}}" "${BUILD_NUMBER:-$(date -u +%Y%m%d%H%M)}" "$min" <<'PY'
import plistlib, re, sys
path, name, ident, info_path, version, build, minos = sys.argv[1:]
try:
    plist = plistlib.load(open(info_path, "rb"))
except Exception:
    plist = {"NSExtension": {}}
module = re.sub(r"[^A-Za-z0-9_]", "_", name)
vals = {"PRODUCT_MODULE_NAME": module, "PRODUCT_NAME": name, "EXECUTABLE_NAME": name,
        "PRODUCT_BUNDLE_IDENTIFIER": ident}
def expand(v):
    if isinstance(v, str):
        for key, val in vals.items():
            v = v.replace("$(%s)" % key, val)
        return re.sub(r"\$\((\w+)\)", "", v)
    if isinstance(v, list):
        return [expand(x) for x in v]
    if isinstance(v, dict):
        return {k: expand(x) for k, x in v.items()}
    return v
plist = expand(plist)
plist.update({
    "CFBundleExecutable": name, "CFBundleIdentifier": ident,
    "CFBundlePackageType": "XPC!", "CFBundleShortVersionString": version,
    "CFBundleVersion": build, "CFBundleSupportedPlatforms": ["MacOSX"],
    "LSMinimumSystemVersion": minos,
})
plistlib.dump(plist, open(path, "wb"))
PY
  ent_args=()
  ext_ent=$(find -L "$ext_path" -name '*.entitlements' ! -name '*-dev*' -print -quit)
  if [ -n "$ext_ent" ]; then
    team=$(openssl x509 -in "$idir/cert.pem" -noout -subject 2>/dev/null |
           sed -n 's/.*OU *= *\([A-Z0-9]*\).*/\1/p' | head -1)
    python3 - "$ext_ent" "build/$ext-entitlements.plist" "$ext" "$ext_info" "${team}." <<'PY'
import plistlib, re, sys
src, dst, name, info_path, team_prefix = sys.argv[1:]
try:
    custom = plistlib.load(open(info_path, "rb"))
except Exception:
    custom = {}
vals = {"PRODUCT_NAME": name, "EXECUTABLE_NAME": name,
        "PRODUCT_MODULE_NAME": re.sub(r"[^A-Za-z0-9_]", "_", name),
        "APP_GROUP_ID": custom.get("AppGroup", ""),
        "TeamIdentifierPrefix": team_prefix if team_prefix != "." else ""}
text = open(src, encoding="utf-8").read()
open(dst, "w", encoding="utf-8").write(
    re.sub(r"\$\((\w+)\)", lambda m: vals.get(m.group(1), ""), text))
PY
    ent_args=(--entitlements-xml-file "build/$ext-entitlements.plist")
    echo "signing $ext with entitlements from $ext_ent"
  fi
  [ ! -f "build/provision/$ext.provisionprofile" ] || \
    cp "build/provision/$ext.provisionprofile" "$appex/Contents/embedded.provisionprofile"
  if [ -f "$idir/key.pem" ] && [ -f "$idir/cert.pem" ]; then
    rcodesign sign --pem-file "$idir/key.pem" --pem-file "$idir/cert.pem" \
      --binary-identifier "$ext" "${ent_args[@]}" --for-notarization "$appex" 2>&1 | tail -1
  else
    rcodesign sign "${ent_args[@]}" "$appex" 2>&1 | tail -1
  fi
done < build/extensions.tsv

echo "== 7. Sign =="
# Developer ID restricted entitlements run only with the profile embedded
# before the bundle is sealed (tools/provision-mac.py writes build/provision/).
[ ! -f "build/provision/app.provisionprofile" ] || \
  cp "build/provision/app.provisionprofile" "$app/Contents/embedded.provisionprofile"
ent=${ENTITLEMENTS:-}
if [ -z "$ent" ]; then
  ent=$(find -L "$app_target_path" -name "$product.entitlements" -print -quit)
  [ -n "$ent" ] || ent=$(find -L "$app_target_path" -name '*.entitlements' ! -name '*-dev*' \
        ! -path '*ShareExtension*' ! -path '*SafariExtension*' -print -quit)
  # Restricted entitlements (com.apple.developer.*) are honored only with an
  # embedded provisioning profile; without one, macOS kills the process at
  # launch (AMFI). A profile made for another team cannot be distributed, so
  # the safe default is signing without entitlements.
  if [ -n "$ent" ] && [ ! -f "$app/Contents/embedded.provisionprofile" ] && \
     grep -q 'com\.apple\.developer\.' "$ent"; then
    echo "warning: $ent has restricted entitlements but the bundle has no embedded.provisionprofile; signing without entitlements (set ENTITLEMENTS to override)"
    ent=""; ent_skipped=1
  fi
fi
ent_args=()
if [ -n "$ent" ]; then
  # Placeholder expansion: product name, bundle id, the Info.plist's project
  # keys (AppGroup, OrganizationIdentifier), and the team prefix from the
  # Developer ID certificate's OU.
  team=$(openssl x509 -in "$idir/cert.pem" -noout -subject 2>/dev/null |
         sed -n 's/.*OU *= *\([A-Z0-9]*\).*/\1/p' | head -1)
  python3 - "$ent" "build/$product.entitlements" "$product" "$bundle_id" "${team}." <<'PY'
import plistlib, re, sys
src, dst, product, bundle_id, team_prefix = sys.argv[1:]
try:
    custom = plistlib.load(open("Info.plist", "rb"))
except Exception:
    custom = {}
vals = {"PRODUCT_NAME": product, "EXECUTABLE_NAME": product,
        "PRODUCT_BUNDLE_IDENTIFIER": bundle_id, "PRODUCT_MODULE_NAME": product,
        "ORGANIZATION_IDENTIFIER": custom.get("OrganizationIdentifier", ""),
        "APP_GROUP_ID": custom.get("AppGroup", ""),
        "TeamIdentifierPrefix": team_prefix if team_prefix != "." else ""}
text = open(src, encoding="utf-8").read()
open(dst, "w", encoding="utf-8").write(
    re.sub(r"\$\((\w+)\)", lambda m: vals.get(m.group(1), ""), text))
PY
  echo "signing with entitlements from $ent"
  ent_args=(--entitlements-xml-file "build/$product.entitlements")
else
  [ -n "${ent_skipped:-}" ] || echo "no entitlements file under $app_target_path; signing without"
fi
rm -f "$app/Contents/CodeSignature"/*
if [ -f "$idir/key.pem" ] && [ -f "$idir/cert.pem" ]; then
  # --for-notarization: hardened runtime and a secure timestamp. Apple's
  # notary wants the main executable's identifier to be CFBundleExecutable,
  # not the bundle id (submission 6e74a3fc vs 88786693).
  rcodesign sign --pem-file "$idir/key.pem" --pem-file "$idir/cert.pem" \
    --binary-identifier "$product" "${ent_args[@]}" --for-notarization "$app"
elif [ "$notarize" = 1 ]; then
  echo "--notarize needs a Developer ID identity in $idir (key.pem, cert.pem)" >&2; exit 1
else
  echo "no Developer ID identity in $idir: signing ad hoc (runs on your own Macs only)"
  rcodesign sign "${ent_args[@]}" "$app"
fi

if [ "$notarize" = 1 ]; then
  echo "== 8. Notarize =="
  key_json=${ASC_API_KEY_FILE:-}
  if [ -z "$key_json" ]; then
    : "${ASC_KEY_ID:?--notarize needs ASC_KEY_ID}" "${ASC_ISSUER_ID:?--notarize needs ASC_ISSUER_ID}"
    : "${ASC_KEY_PATH:?--notarize needs ASC_KEY_PATH (the .p8 file)}"
    key_json=$(mktemp)
    trap 'rm -f "$key_json"' EXIT
    rcodesign encode-app-store-connect-api-key -o "$key_json" "$ASC_ISSUER_ID" "$ASC_KEY_ID" "$ASC_KEY_PATH" >/dev/null 2>&1
  fi
  rcodesign notary-submit --api-key-file "$key_json" --max-wait-seconds 3600 --staple "$app"
fi

(cd build && rm -f "$product.zip" && zip -qry "$product.zip" "$product.app")
echo "wrote $app and build/$product.zip"
