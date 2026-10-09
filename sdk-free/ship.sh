#!/usr/bin/env bash
# Ship a no-xcode app (built by sdk-free/flutter-build.sh) to App Store Connect:
# stamp the build keys, add the app privacy manifest, sign with an Apple Distribution
# identity and an App Store profile, validate offline, optionally upload.
#   sdk-free/ship.sh [--upload] <flutter app dir>
# The App Store record must exist once for the bundle id (web UI; the API cannot create
# apps). Same account variables as ship.sh:
#   ASC_KEY_ID=XXXXXXXXXX  ASC_ISSUER_ID=<uuid>  ASC_KEY_PATH=/path/AuthKey_XXXXXXXXXX.p8
# BUILD_NUMBER overrides CFBundleVersion (default: UTC yyyymmddHHMM, always increasing).
# XCODE_VERSION/XCODE_BUILD stamp DTXcode when the SDK has no recorded version.
set -euo pipefail

HERE=$(dirname "$(readlink -f "$0")")
REPO=$(dirname "$HERE")
PY="$HOME/pymobile3-venv/bin/python"
ASC="$REPO/tools/asc.py"
PATH="$HOME/.local/bin:$PATH"
export PATH

upload=0
if [ "${1:-}" = "--upload" ]; then upload=1; shift; fi
APP=$(readlink -f "${1:?usage: sdk-free/ship.sh [--upload] <flutter app dir>}")
OUT=$APP/build/ios-sdkfree/release
BUNDLE=$OUT/Runner.app
[ -d "$BUNDLE" ] || { echo "no $BUNDLE: run sdk-free/flutter-build.sh first" >&2; exit 1; }
[ -n "${ASC_KEY_ID:-}" ] || echo "warning: no ASC_KEY_ID: signing with the TEST identity (Apple rejects it)" >&2

# The app target ships its own privacy manifest in an Xcode build; the no-xcode runner
# has none (the Flutter engine's manifest rides in Flutter.framework).
[ -f "$BUNDLE/PrivacyInfo.xcprivacy" ] || cp "$HERE/runner/PrivacyInfo.xcprivacy" "$BUNDLE/"

echo "== 1. App Store Info.plist keys and Mach-O sdk =="
export XCODE_VERSION=${XCODE_VERSION:-27.0} XCODE_BUILD=${XCODE_BUILD:-27A266a}
"$PY" "$ASC" stamp "$BUNDLE" "${BUILD_NUMBER:-$(date -u +%Y%m%d%H%M)}"

echo "== 2. Distribution identity and signature =="
sign_dir=$OUT/ship-signing
if [ -n "${ASC_KEY_ID:-}" ]; then
  "$PY" "$ASC" identity "$BUNDLE" "$sign_dir"
else
  "$PY" "$ASC" test-identity "$BUNDLE" "$sign_dir"
fi
team=$("$PY" -c 'import plistlib,sys; print(plistlib.load(open(sys.argv[1],"rb"))["com.apple.developer.team-identifier"])' \
  "$sign_dir/entitlements.plist")
[[ "$team" =~ ^[A-Z0-9]{10}$ ]] || { echo "team id '$team' is not a bare 10-character team id" >&2; exit 1; }
# Inside-out: frameworks first, then the app, so the app seals already-signed nested code.
sign_args=(--pem-file "$sign_dir/key.pem" --certificate-der-file "$sign_dir/cert.der" --team-name "$team")
shopt -s nullglob
for framework in "$BUNDLE"/Frameworks/*.framework; do
  rcodesign sign "${sign_args[@]}" "$framework"
done
shopt -u nullglob
rcodesign sign "${sign_args[@]}" --entitlements-xml-file "$sign_dir/entitlements.plist" "$BUNDLE"

echo "== 3. Package =="
ipa=$OUT/Runner-store.ipa
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/Payload"
cp -a "$BUNDLE" "$stage/Payload/"
rm -f "$ipa"
(cd "$stage" && zip -qry "$ipa" Payload)
echo "wrote $ipa"

echo "== 4. Offline App Store validation =="
"$PY" "$ASC" validate "$ipa"

if [ "$upload" = 1 ]; then
  [ -n "${ASC_KEY_ID:-}" ] || { echo "--upload needs ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH" >&2; exit 1; }
  echo "== 5. Upload =="
  "$PY" "$ASC" upload "$ipa"
fi
