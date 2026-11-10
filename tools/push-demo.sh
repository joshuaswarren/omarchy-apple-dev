#!/usr/bin/env bash
# Push a new Main Status build number to the Duo over the Tailscale tunnel: stamp,
# dev-sign, package, install, query the version, launch. One command per version.
#
#   tools/push-demo.sh /path/to/MainStatus.ipa [INSTALL_HOST]
#
# INSTALL_HOST defaults to 192.168.3.91 (the Linux box with pymobiledevice3 and the
# phone's remote pairing record). The signing identity lives in
# /tmp/ms-devsign (dev-key.pem, dev-cert.der, dev.mobileprovision,
# dev-entitlements.plist), created once by the asc.py dev flow for UDID
# 00008160-0019095E2EC0000A.
set -euo pipefail
IPA_IN=${1:?usage: push-demo.sh MAINSTATUS.ipa [INSTALL_HOST]}
HOST=${2:-192.168.3.91}
SSH_KEY=~/.ssh/id_rsa_2025
SIGN=/tmp/ms-devsign
PY=${PY:-python3}

[ -f "$IPA_IN" ] || { echo "no IPA: $IPA_IN" >&2; exit 2; }
for f in "$SIGN/dev-key.pem" "$SIGN/dev-cert.der" "$SIGN/dev.mobileprovision" "$SIGN/dev-entitlements.plist"; do
  [ -f "$f" ] || { echo "missing dev identity file: $f" >&2; exit 2; }
done

WORK=$(mktemp -d /tmp/push-demo.XXXX)
unzip -qo "$IPA_IN" -d "$WORK"
APP="$WORK/Payload/MainStatus.app"

BUILD=$(date -u +%Y%m%d%H%M)
"$PY" - "$APP" "$BUILD" <<'PYEOF'
import plistlib, sys, pathlib
app, build = sys.argv[1], sys.argv[2]
paths = [pathlib.Path(app) / "Info.plist", *sorted(pathlib.Path(app).glob("PlugIns/*.appex/Info.plist"))]
for p in paths:
    with p.open("rb") as f:
        d = plistlib.load(f)
    d["CFBundleVersion"] = build
    with p.open("wb") as f:
        plistlib.dump(d, f)
    print("stamped", p, "->", build)
PYEOF

team=$("$PY" -c 'import plistlib,sys; print(plistlib.load(open(sys.argv[1],"rb"))["com.apple.developer.team-identifier"])' "$SIGN/dev-entitlements.plist")
args=(--pem-file "$SIGN/dev-key.pem" --certificate-der-file "$SIGN/dev-cert.der" --team-name "$team")
shopt -s nullglob
for fw in "$APP"/Frameworks/*.framework; do
  rcodesign sign "${args[@]}" "$fw"
done
for appex in "$APP"/PlugIns/*.appex; do
  rcodesign sign "${args[@]}" --entitlements-xml-file "$SIGN/dev-entitlements.plist" "$appex"
done
WATCH="$APP/Watch/MainStatusWatch.app"
if [ -d "$WATCH" ]; then
  for appex in "$WATCH"/PlugIns/*.appex; do
    rcodesign sign "${args[@]}" --entitlements-xml-file "$SIGN/dev-entitlements.plist" "$appex"
  done
  rcodesign sign "${args[@]}" --entitlements-xml-file "$SIGN/dev-entitlements.plist" "$WATCH"
fi
shopt -u nullglob
cp -f "$SIGN/dev.mobileprovision" "$APP/embedded.mobileprovision"
rcodesign sign "${args[@]}" --entitlements-xml-file "$SIGN/dev-entitlements.plist" "$APP"

IPA="$WORK/MainStatus-$BUILD.ipa"
(cd "$WORK" && zip -qry "$IPA" Payload)
echo "built: $IPA (build $BUILD)"

scp -q -i "$SSH_KEY" -o BatchMode=yes "$IPA" "joshuawarren@$HOST:/tmp/MainStatus-push.ipa"
ssh -o BatchMode=yes -i "$SSH_KEY" "joshuawarren@$HOST" bash -s <<REMOTE
set -euo pipefail
sudo -n ~/pmd3-apple-dev/bin/python3 ~/tailnet-tunnel.py 100.76.24.15 --udid 00008160-0019095E2EC0000A --hold 300 > /tmp/duo-tunnel-push.log 2>&1 &
sleep 8
read -r _ ADDR PORT < <(head -1 /tmp/duo-tunnel-push.log)
echo "rsd: \$ADDR \$PORT"
sudo -n ~/pmd3-apple-dev/bin/pymobiledevice3 apps install --rsd "\$ADDR" "\$PORT" /tmp/MainStatus-push.ipa 2>&1 | tail -2
sudo -n ~/pmd3-apple-dev/bin/pymobiledevice3 apps list --rsd "\$ADDR" "\$PORT" 2>/dev/null | python3 -c '
import sys, json
a = json.load(sys.stdin)["com.joshuaswarren.omarchyappledev.demo"]
print("version:", a.get("CFBundleShortVersionString"), "build:", a.get("CFBundleVersion"))'
sudo -n ~/pmd3-apple-dev/bin/pymobiledevice3 developer dvt launch --rsd "\$ADDR" "\$PORT" com.joshuaswarren.omarchyappledev.demo 2>&1 | tail -1
REMOTE
