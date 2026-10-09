#!/usr/bin/env bash
# Build RNProbe (React Native 0.87.1) app target for iOS from Linux, no Xcode.
# Prebuilt RN core + dependencies + hermesvm dynamic frameworks are linked as-is;
# only the app target (main.m, AppDelegate.mm, RCTAppDependencyProvider.mm and
# RN codegen providers) is compiled here.
#   rn-build.sh   (run inside the arch chroot as builder; SDKFREE_HOME set below)
set -euo pipefail
export SDKFREE_HOME=/qwork/sdkfree-swift
REPO=/work
RN=/qwork/rn
APP=$RN/app
FW=$RN/artifacts
HDRS=$FW/core/ReactNativeHeaders.xcframework/ios-arm64/Headers
DEPSH=$FW/deps/packages/react-native/third-party/ReactNativeDependenciesHeaders.xcframework/ios-arm64/Headers
COREFW=$FW/core/React.xcframework/ios-arm64
DEPSFW=$FW/deps/packages/react-native/third-party/ReactNativeDependencies.xcframework/ios-arm64
HERMFW=$FW/hermes/destroot/Library/Frameworks/universal/hermesvm.xcframework/ios-arm64
CG=/home/builder/rnbuild/codegen2/build/generated/ios
SAC=/nonexistent-safe-area-context
OUT=/home/builder/rnbuild
SR=$SDKFREE_HOME/iPhoneOS.sdk

mkdir -p "$OUT/obj"
cc() { bash "$RN/rncc.sh" "$@"; }

echo "== compile app sources"
INC=(-I "$HDRS" -I "$DEPSH" -I "$CG" -F "$COREFW")
cc -x objective-c "${INC[@]}" -c "$APP/main.m" -o "$OUT/obj/main.o"
CCXX=(-x objective-c++ -std=gnu++20 "${INC[@]}")
cc "${CCXX[@]}" -c "$APP/AppDelegate.mm" -o "$OUT/obj/AppDelegate.o"
cc "${CCXX[@]}" -c "$APP/RCTAppDependencyProvider.mm" -o "$OUT/obj/RCTAppDependencyProvider.o"
echo "== safe-area-context"
if [ -d "$SAC" ]; then
for f in "$SAC"/*.m "$SAC"/*.mm "$SAC"/Fabric/*.mm; do
  [ -e "$f" ] || continue
  base=$(basename "$f"); base=${base%.*}
  std=(); case "$f" in *.mm) std=(-std=gnu++20);; esac
  cc "${std[@]}" -I "$HDRS" -I "$DEPSH" -I "$CG" -F "$COREFW" -I "$SAC" -I "$SAC/Fabric" -c "$f" -o "$OUT/obj/sac-$base.o" ||
    { echo "SAC FAILED: $f" >&2; exit 1; }
done
fi
for mm in "$CG"/ReactCodegen/*.mm; do
  [ -e "$mm" ] || continue
  base=$(basename "$mm" .mm)
  case "$base" in
    RCTModulesConformingToProtocolsProvider|RCTThirdPartyComponentsProvider|\
    RCTUnstableModulesRequiringMainQueueSetupProvider|RCTModuleProviders)
      cc "${CCXX[@]}" -c "$mm" -o "$OUT/obj/$base.o" ;;
  esac
done

echo "== link"
"$SDKFREE_HOME/toolset/ld64.lld" -arch arm64 -platform_version ios 17.0 26.0 -syslibroot "$SR" \
  -F"$COREFW" -F"$DEPSFW" -F"$HERMFW" \
  -framework React -framework ReactNativeDependencies -framework hermesvm \
  -framework UIKit -framework Foundation \
  -lSystem -lobjc -lc++ \
  -rpath @executable_path/Frameworks -ObjC -o "$OUT/RNProbe" "$OUT"/obj/*.o 2>&1 |
  grep -v "does not support linking for platform iOS" || true
[ -s "$OUT/RNProbe" ] || { echo "link failed" >&2; exit 1; }
echo "== app bundle"
BUNDLE=$OUT/RNProbe.app
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Frameworks"
cp "$OUT/RNProbe" "$BUNDLE/RNProbe"
cp "$APP/Info.plist" "$BUNDLE/Info.plist"
printf 'APPL????' > "$BUNDLE/PkgInfo"
[ -f "$OUT/main.hbc" ] && cp "$OUT/main.hbc" "$BUNDLE/main.jsbundle"
cp -a "$COREFW/React.framework" "$DEPSFW/ReactNativeDependencies.framework" "$HERMFW/hermesvm.framework" "$BUNDLE/Frameworks/"
echo "built $BUNDLE"
