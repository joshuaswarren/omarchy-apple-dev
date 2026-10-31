#!/usr/bin/env bash
# Ship a Flutter app built by flutter/build.sh to App Store Connect: stamp the
# build keys, wrap SwiftPM dylibs as frameworks, sign with an Apple
# Distribution identity and an App Store profile, validate offline, and
# optionally upload.
#
#   flutter/ship.sh [--upload] <flutter app dir>
#
# Reads <app>/build/ios-linux/Payload/Runner.app (run flutter/build.sh first)
# and writes <app>/build/ios-linux/Runner-store.ipa. The built bundle is not
# changed: signing happens on a copy.
#
# Without ASC_KEY_ID the app is signed with the local TEST identity, which
# checks the pipeline; Apple rejects it. --upload needs the account variables
# ship.sh uses and the app record created once in App Store Connect:
#   ASC_KEY_ID=XXXXXXXXXX  ASC_ISSUER_ID=<uuid>  ASC_KEY_PATH=/path/AuthKey_XXXXXXXXXX.p8
# BUILD_NUMBER overrides CFBundleVersion (default: the one build.sh wrote, from
# pubspec.yaml or its own BUILD_NUMBER). ASC_ENTITLEMENTS_PATH requests
# capabilities as for ship.sh; when it is unset, the CODE_SIGN_ENTITLEMENTS file
# of the configuration build.sh built does. XCODE_VERSION/XCODE_BUILD stamp
# DTXcode when the SDK has no recorded version (install-toolchain.sh records it
# from the .xip).
#
# ASC_PROFILE signs with an identity and profile made elsewhere instead (for a
# build machine that must not hold the API key or create certificates):
#   ASC_SIGNING_KEY=key.pem  ASC_SIGNING_CERT=cert.der  ASC_PROFILE=app.mobileprovision
# Each is a file path: ASC_SIGNING_KEY is the path of the PEM private key file,
# not the key text.
# No App Store Connect call is made then, unless --upload is given.
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
repo=$(dirname "$here")
PY="$HOME/pymobile3-venv/bin/python"
ASC="$repo/tools/asc.py"
PATH="$HOME/.local/bin:$PATH"
export PATH

upload=0
if [ "${1:-}" = "--upload" ]; then upload=1; shift; fi
[ $# -eq 1 ] || { echo "usage: flutter/ship.sh [--upload] <flutter app dir>" >&2; exit 2; }
app=$(readlink -f "$1")
out=$app/build/ios-linux
built=$out/Payload/Runner.app
[ -d "$built" ] || { echo "no $built: run flutter/build.sh first" >&2; exit 1; }
# The entitlements the app requests, as Xcode signs with them: the
# CODE_SIGN_ENTITLEMENTS of the configuration build.sh recorded (a flavor's own).
if [ -z "${ASC_ENTITLEMENTS_PATH:-}" ] && [ -f "$out/configuration" ]; then
  configuration=$(cat "$out/configuration")
  entitlements=$(python3 "$here/tools/xcode_settings.py" "$app/ios" "$configuration" CODE_SIGN_ENTITLEMENTS)
  if [ -n "$entitlements" ]; then
    ASC_ENTITLEMENTS_PATH=$(cd "$app/ios" && realpath -m "$entitlements")
    [ -f "$ASC_ENTITLEMENTS_PATH" ] ||
      { echo "no $ASC_ENTITLEMENTS_PATH (the $configuration configuration's CODE_SIGN_ENTITLEMENTS)" >&2; exit 1; }
    export ASC_ENTITLEMENTS_PATH
    echo "entitlements: $ASC_ENTITLEMENTS_PATH ($configuration)"
  fi
fi
if [ "$upload" = 1 ]; then
  : "${ASC_KEY_ID:?--upload needs ASC_KEY_ID}" "${ASC_ISSUER_ID:?--upload needs ASC_ISSUER_ID}"
  : "${ASC_KEY_PATH:?--upload needs ASC_KEY_PATH (the .p8 file)}"
  export ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_PATH
fi
[ -n "${ASC_KEY_ID:-}${ASC_PROFILE:-}" ] ||
  echo "warning: no ASC_KEY_ID or ASC_PROFILE: signing with the TEST identity (Apple rejects it)" >&2

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/Payload"
cp -a "$built" "$stage/Payload/"
# SwiftPM build outputs are read-only; every step below writes into the bundle.
chmod -R u+w "$stage/Payload"
bundle=$stage/Payload/Runner.app

echo "== 1. App Store Info.plist keys and Mach-O sdk =="
build_number=${BUILD_NUMBER:-$("$PY" -c 'import plistlib,sys; print(plistlib.load(open(sys.argv[1],"rb"))["CFBundleVersion"])' \
  "$bundle/Info.plist")}
"$PY" "$ASC" stamp "$bundle" "$build_number"

echo "== 2. SwiftPM dylibs as frameworks =="
"$PY" "$ASC" frameworks "$bundle"

echo "== 3. Distribution identity and signature =="
# The signature's capability entitlements (Sign in with Apple, aps-environment,
# Associated Domains) come only from ASC_ENTITLEMENTS_PATH, never from the
# provisioning profile; the auto-detection above is the only fallback. Reaching
# the identity step without the variable means an entitlement-less signature
# that installs and validates fine and fails only in the field (a dead Sign in
# with Apple button, no APNs token, dead Associated Domains).
if [ -z "${ASC_ENTITLEMENTS_PATH:-}" ]; then
  echo "warning: ASC_ENTITLEMENTS_PATH is not set (no CODE_SIGN_ENTITLEMENTS was detected for the built configuration): signing WITHOUT the Sign in with Apple, push (aps-environment) and Associated Domains entitlements — asc.py takes capability entitlements only from that file, never from the provisioning profile" >&2
fi
sign_dir=$out/ship-signing
if [ -n "${ASC_PROFILE:-}" ]; then
  "$PY" "$ASC" given-identity "$bundle" "$sign_dir"
elif [ -n "${ASC_KEY_ID:-}" ]; then
  "$PY" "$ASC" identity "$bundle" "$sign_dir"
else
  "$PY" "$ASC" test-identity "$bundle" "$sign_dir"
fi
team=$("$PY" -c 'import plistlib,sys; print(plistlib.load(open(sys.argv[1],"rb"))["com.apple.developer.team-identifier"])' \
  "$sign_dir/entitlements.plist")
# rcodesign --team-name wants the bare 10-character team id (ship.sh step 6).
[[ "$team" =~ ^[A-Z0-9]{10}$ ]] || { echo "team id '$team' is not a bare 10-character team id" >&2; exit 1; }
"$PY" "$repo/tools/fill-team-prefix.py" --team "$team" "$bundle"
# Inside-out: frameworks first, then each extension with its own entitlements
# (asc.py identity writes one per PlugIns/*.appex bundle id), then the app, so
# the app seals already-signed nested code.
sign_args=(--pem-file "$sign_dir/key.pem" --certificate-der-file "$sign_dir/cert.der" --team-name "$team")
shopt -s nullglob
for framework in "$bundle"/Frameworks/*.framework; do
  rcodesign sign "${sign_args[@]}" "$framework"
done
for appex in "$bundle"/PlugIns/*.appex; do
  ent=$sign_dir/$(basename "$appex" .appex)-entitlements.plist
  [ -f "$ent" ] || { echo "no $ent: identity wrote none for $(basename "$appex")" >&2; exit 1; }
  rcodesign sign "${sign_args[@]}" --entitlements-xml-file "$ent" "$appex"
done
shopt -u nullglob
rcodesign sign "${sign_args[@]}" --entitlements-xml-file "$sign_dir/entitlements.plist" "$bundle"

echo "== 4. Package =="
ipa=$out/Runner-store.ipa
rm -f "$ipa"
(cd "$stage" && zip -qry "$ipa" Payload)
echo "wrote $ipa"

echo "== 5. Offline App Store validation =="
"$PY" "$ASC" validate "$ipa"

if [ "$upload" = 1 ]; then
  echo "== 6. Upload to App Store Connect =="
  "$PY" "$ASC" upload "$ipa"
fi
