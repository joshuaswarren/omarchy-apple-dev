#!/usr/bin/env bash
# Build a Flutter app for a physical iOS device on Linux: no Mac, no Xcode.
#
#   flutter/build.sh [--install] <flutter app dir> [KEY=VALUE dart-define ...]
#
# Output: <app dir>/build/ios-linux/Runner.ipa (unsigned; `xtool install`
# signs it) and build/ios-linux/dSYMs. Release mode, arm64. Run
# flutter/setup.sh once first.
#
# Env overrides: FLUTTER, BUNDLE_ID, BUILD_NAME, BUILD_NUMBER, MIN_IOS
# (defaults come from the app's Xcode project and pubspec.yaml).
# FLAVOR and TARGET are `flutter build ios --flavor` and `-t`: FLAVOR picks the
# scheme and its Release configuration, TARGET the Dart entry point (default:
# the configuration's FLUTTER_TARGET, else lib/main.dart).
# STRIP_FRAMEWORKS="A B" leaves A.framework and B.framework out of the app.
# SPLIT_DEBUG_INFO=<dir> and DART_OBFUSCATION=true do what `flutter build
# --split-debug-info` and `--obfuscate` do.
set -euo pipefail

install=
if [ "${1:-}" = "--install" ]; then install=1; shift; fi
app=$(readlink -f "${1:?usage: build.sh [--install] <flutter app dir> [KEY=VALUE ...]}"); shift
here=$(dirname "$(readlink -f "$0")")
FLUTTER=${FLUTTER:-$(command -v flutter)} || { echo "flutter is not on PATH; set FLUTTER" >&2; exit 1; }
flutter_root=$(dirname "$(dirname "$(readlink -f "$FLUTTER")")")

sdkb=${DARWIN_SDK_BUNDLE:-${XDG_CONFIG_HOME:-$HOME/.config}/swiftpm/swift-sdks/darwin.artifactbundle}
[ -d "$sdkb" ] || sdkb=$HOME/.swiftpm/swift-sdks/darwin.artifactbundle
[ -d "$sdkb" ] || { echo "no darwin SDK bundle; run install-toolchain.sh first" >&2; exit 1; }
ios_sdk=$sdkb/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk
tools=$sdkb/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin
# ibtool runs from this checkout, not from the copy install-toolchain.sh put in
# the SDK bundle, so a `git pull` is enough to pick up a newer one.
ibtool=$here/../tools/ibtool
tc=$(dirname "$(readlink -f "$(command -v swift)")")
# The shims forward to LLVM's binutils, which neither the Swift toolchain nor
# the darwin SDK bundle ships.
missing=
for t in llvm-strip llvm-lipo llvm-otool llvm-install-name-tool llvm-ar; do
  command -v "$t" >/dev/null || missing+=" $t"
done
[ -z "$missing" ] || { echo "missing:$missing (package providing llvm-strip, llvm-lipo, llvm-otool, llvm-install-name-tool, llvm-ar; docs/DISTROS.md lists it per distribution)" >&2; exit 1; }
for t in python3 zip file rsync; do
  command -v "$t" >/dev/null || { echo "missing: $t (docs/DISTROS.md lists the package per distribution)" >&2; exit 1; }
done
file -b "$flutter_root/bin/cache/artifacts/engine/ios-release/gen_snapshot_arm64" 2>/dev/null | grep -q ELF ||
  { echo "Flutter's iOS gen_snapshot is not the Linux build; run $here/setup.sh" >&2; exit 1; }

configuration=Release
flavor_opts=()
if [ -n "${FLAVOR:-}" ]; then
  # The scheme and configuration `flutter build ios --flavor` picks, and the
  # defines xcode_backend.dart then passes. On a Mac, flutter assemble reads
  # appFlavor back from the configuration's scheme, so -dFlavor is the scheme's
  # spelling; here flavor-scoped assets follow it too, where a Mac uses FLAVOR
  # as typed. A scheme spelled differently from FLAVOR gets a warning.
  picked=$(python3 "$here/tools/xcode_settings.py" "$app/ios" --flavor "$FLAVOR")
  configuration=${picked%%$'\n'*} scheme=${picked#*$'\n'}
  flavor_opts=("-dFlavor=$scheme" "-dConfiguration=$configuration")
  [ "$scheme" = "$FLAVOR" ] ||
    echo "warning: FLAVOR=$FLAVOR builds scheme $scheme; appFlavor and flavor-scoped assets get '$scheme'" >&2
fi
setting() { # a build setting of the Runner target in $configuration, expanded as Xcode does
  python3 "$here/tools/xcode_settings.py" "$app/ios" "$configuration" "$1"
}
BUNDLE_ID=${BUNDLE_ID:-$(setting PRODUCT_BUNDLE_IDENTIFIER)}
MIN_IOS=${MIN_IOS:-$(setting IPHONEOS_DEPLOYMENT_TARGET)}
families=$(setting TARGETED_DEVICE_FAMILY); families=${families:-1,2}
info_plist=$(setting INFOPLIST_FILE)
[ "$(cd "$app/ios" && realpath -m "${info_plist:-Runner/Info.plist}")" = "$app/ios/Runner/Info.plist" ] ||
  { echo "the $configuration configuration's INFOPLIST_FILE is $info_plist; build.sh reads Runner/Info.plist only" >&2; exit 1; }
target=${TARGET:-$(setting FLUTTER_TARGET)}; target=${target:-lib/main.dart}
(cd "$app" && [ -f "$target" ]) ||
  { echo "no Dart entry point $target in $app (TARGET, else the $configuration configuration's FLUTTER_TARGET, else lib/main.dart)" >&2; exit 1; }
# The app icon set the configuration names (flutter_flavorizr names one per
# flavor). A set that lists every size, as Flutter's template does, compiles,
# but App Store processing has hung on one with no error.
appicon=$(setting ASSETCATALOG_COMPILER_APPICON_NAME)
icon_args=()
[ -n "$appicon" ] && icon_args=(--app-icon "$appicon") ||
  echo "warning: the $configuration configuration names no app icon set (ASSETCATALOG_COMPILER_APPICON_NAME); the app gets no icon" >&2
iconset=$app/ios/Runner/Assets.xcassets/$appicon.appiconset
[ -z "$appicon" ] || [ -f "$iconset/Contents.json" ] ||
  { echo "no app icon set $appicon in ios/Runner/Assets.xcassets (the $configuration configuration's ASSETCATALOG_COMPILER_APPICON_NAME)" >&2; exit 1; }
[ -z "$appicon" ] || python3 -c 'import json, sys
images = json.load(open(sys.argv[1])).get("images", [])
sys.exit(not images or not all(i.get("idiom") == "universal" and "scale" not in i and i.get("size") == "1024x1024" for i in images))' "$iconset/Contents.json" ||
  echo "warning: app icon set $appicon lists several sizes; App Store processing has hung on such a set with no error (FINDINGS.md item 68). One 1024x1024 universal image avoids it." >&2
version=$(sed -n 's/^version: *//p' "$app/pubspec.yaml" | head -n1)
BUILD_NAME=${BUILD_NAME:-${version%%+*}}
BUILD_NUMBER=${BUILD_NUMBER:-$([ "${version#*+}" != "$version" ] && echo "${version#*+}" || echo 1)}
# Dart symbols, as `flutter build --split-debug-info=<dir> --obfuscate` passes
# them to the Xcode build: gen_snapshot writes app.ios-arm64.symbols into the
# directory (for `flutter symbolize`), and obfuscation needs that directory.
# A relative directory is taken from where build.sh runs, as flutter's is.
dart_opts=()
split_dir=
if [ -n "${SPLIT_DEBUG_INFO:-}" ]; then
  split_dir=$(realpath -m "$SPLIT_DEBUG_INFO")
  dart_opts+=("-dSplitDebugInfo=$split_dir")
fi
case ${DART_OBFUSCATION:-false} in
  true)
    [ -n "$split_dir" ] ||
      { echo "DART_OBFUSCATION=true needs SPLIT_DEBUG_INFO, as --obfuscate needs --split-debug-info" >&2; exit 1; }
    dart_opts+=(-dDartObfuscation=true) ;;
  false) ;;
  *) echo "DART_OBFUSCATION must be true or false, not '$DART_OBFUSCATION'" >&2; exit 1 ;;
esac
sdk_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["Version"])' "$ios_sdk/SDKSettings.json")

out=$app/build/ios-linux
asm=$out/assemble; shell_pkg=$out/shell; stage=$out/stage; bundle=$out/Payload/Runner.app
# Everything but the Swift build directory is rebuilt from scratch.
for d in "$asm" "$stage" "$out/Payload"; do
  [ ! -d "$d" ] || find "$d" -mindepth 1 -delete
done
mkdir -p "$asm" "$shell_pkg" "$stage/sbc" "$bundle/Frameworks"
# flutter/ship.sh signs with this configuration's entitlements.
printf '%s\n' "$configuration" >"$out/configuration"

export PATH="$here/shims:$sdkb/toolset/bin:$tc:$PATH"
export XCRUN_SHIM_LOG=$out/shims.log
export XCODE_EXTRA_PLATFORM_FOLDERS=$sdkb/Developer/Platforms
unset SDKROOT
ulimit -n 65536 2>/dev/null || true

echo "== 1. Flutter: Dart AOT, assets, engine framework, native assets"
defines=""
for d in "$@"; do defines+="${defines:+,}$(printf '%s' "$d" | base64 -w0)"; done
(cd "$app" && "$FLUTTER" pub get >/dev/null && "$FLUTTER" assemble --no-version-check --output="$asm" \
  -dTargetPlatform=ios -dTargetFile="$target" -dBuildMode=release -dIosArchs=arm64 \
  -dSdkRoot="$ios_sdk" -dTrackWidgetCreation=false -dTreeShakeIcons=true -dCodesignIdentity=- \
  "${dart_opts[@]+"${dart_opts[@]}"}" "${flavor_opts[@]+"${flavor_opts[@]}"}" \
  ${defines:+--DartDefines="$defines"} release_ios_bundle_flutter_assets) >"$out/assemble.log" 2>&1 ||
  { tail -n 40 "$out/assemble.log" >&2; exit 1; }

echo "== 2. Native: Runner and plugins as one Swift package"
python3 "$here/tools/gen-shell-package.py" "$app" "$shell_pkg" "$MIN_IOS"
# Swift autolinking adds a STRONG LC_LOAD_DYLIB for every framework a
# package's sources import, regardless of the deployment target: a
# dependency that imports SwiftUI (Sentry 9.x does) drags in SwiftUICore,
# which only exists from iOS 18 — the strong load then makes dyld abort
# the app at launch on every older iOS ("Library not loaded"). Xcode
# weak-links such frameworks; the cross linker cannot be asked to (an
# explicit -weak_framework trips the framework's allowed-clients tbd
# rule), so the load command is rewritten after the link. Env-overridable
# for apps that import other newer-than-MIN_IOS system frameworks.
WEAK_FRAMEWORKS=${WEAK_FRAMEWORKS:-SwiftUICore}
# Native-asset frameworks (flutter_soloud, objective_c, sqlite3, ...) are
# dlopen'ed by the Dart runtime only on demand, but plugins whose SwiftPM
# package compiles with -undefined dynamic_lookup against the asset's exports
# need them in the initial link closure: give Runner an LC_LOAD_DYLIB for each
# (what Xcode's native-assets phase does on a Mac).
natargs=()
if [ -d "$asm/native_assets" ]; then
  natargs+=(-Xlinker -F -Xlinker "$asm/native_assets")
  for f in "$asm"/native_assets/*.framework; do
    [ -d "$f" ] || continue
    natargs+=(-Xlinker -framework -Xlinker "$(basename "${f%.framework}")")
  done
fi
(cd "$shell_pkg" && swift build --configuration release --build-system swiftbuild \
  --triple "arm64-apple-ios$MIN_IOS" --toolset "$sdkb/toolset-swb.json" --product Runner \
  -Xswiftc "-F$asm" -Xcc "-F$asm" -Xlinker "-F$asm" -Xlinker -framework -Xlinker Flutter \
  "${natargs[@]+"${natargs[@]}"}" \
  -Xlinker -rpath -Xlinker @executable_path/Frameworks \
  -Xlinker -platform_version -Xlinker ios -Xlinker "$MIN_IOS" -Xlinker "$sdk_version") \
  >"$out/shell-build.log" 2>&1 || { grep -E 'error' "$out/shell-build.log" | head -n 40 >&2; exit 1; }
products=$shell_pkg/.build/out/Products/Release-iphoneos

echo "== 2b. Extensions: the app extensions the Runner embeds (widgets and friends)"
ext_pkg=$out/extensions
python3 "$here/tools/gen-extensions.py" "$app" "$ext_pkg" "$configuration"
ext_plan=$(python3 -c 'import json,sys
plan = json.load(open(sys.argv[1]))
print(plan["platform"])
print(" ".join(e["name"] for e in plan["extensions"]))' "$ext_pkg/plan.json")
ext_min=${ext_plan%%$'\n'*}
exts=${ext_plan#*$'\n'}
if [ -n "$exts" ]; then
  (cd "$ext_pkg" && swift build --configuration release --build-system swiftbuild \
    --triple "arm64-apple-ios$ext_min" --toolset "$sdkb/toolset-swb.json" \
    -Xlinker -platform_version -Xlinker ios -Xlinker "$ext_min" -Xlinker "$sdk_version") \
    >"$out/extensions-build.log" 2>&1 || { grep -E 'error' "$out/extensions-build.log" | head -n 40 >&2; exit 1; }
  ext_products=$ext_pkg/.build/out/Products/Release-iphoneos
fi

echo "== 3. Wrapper: icons, storyboards, Info.plist"
"$tools/actool" "$app/ios/Runner/Assets.xcassets" --compile "$bundle" --platform iphoneos \
  "${icon_args[@]+"${icon_args[@]}"}" --minimum-deployment-target "$MIN_IOS" --target-device iphone --target-device ipad \
  --output-partial-info-plist "$stage/icon.plist" --output-format human-readable-text >"$out/actool.log" 2>&1 ||
  { cat "$out/actool.log" >&2; exit 1; }
# The storyboards the Runner target's Copy Bundle Resources phase lists, as
# Xcode builds them: each is compiled into its X.lproj (which makes its strings
# localizable) or, when it is not localized, into a plain directory, and the
# link keeps that directory's X.lproj, so the rest land at the bundle root.
storyboards=$(python3 "$here/tools/xcode_settings.py" "$app/ios" --storyboards)
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  lproj=$(basename "$(dirname "$rel")")
  case $lproj in *.lproj) ;; *) lproj=root ;; esac
  mkdir -p "$stage/sbc/$lproj"
  "$ibtool" --module Runner --minimum-deployment-target "$MIN_IOS" --target-device iphone \
    --target-device ipad --output-partial-info-plist "$stage/$(basename "$rel").plist" "$app/ios/$rel" \
    --compilation-directory "$stage/sbc/$lproj" 2>"$out/ibtool.log" || { cat "$out/ibtool.log" >&2; exit 1; }
done <<<"$storyboards"
compiled=("$stage"/sbc/*/*.storyboardc)
[ ! -e "${compiled[0]}" ] || "$ibtool" --module Runner --target-device iphone --target-device ipad \
  --link "$bundle" "${compiled[@]}" 2>"$out/ibtool.log" || { cat "$out/ibtool.log" >&2; exit 1; }
python3 "$here/tools/gen-info-plist.py" "$app/ios/Runner/Info.plist" "$stage/icon.plist" "$bundle/Info.plist" \
  "$BUNDLE_ID" "$BUILD_NAME" "$BUILD_NUMBER" "$MIN_IOS" "$ios_sdk" "$families" "$configuration"
# The launch screen Info.plist names must be one of them, or the app launches
# to a black screen.
launch=$(python3 -c 'import plistlib, sys
info = plistlib.load(open(sys.argv[1], "rb"))
print("\n".join(sorted({v for k, v in info.items() if k.split("~")[0] == "UILaunchStoryboardName" and v})))' "$bundle/Info.plist")
while IFS= read -r name; do
  [ -z "$name" ] || [ -d "$bundle/$name.storyboardc" ] || compgen -G "$bundle/*.lproj/$name.storyboardc" >/dev/null ||
    { echo "launch screen $name (Info.plist, $configuration configuration) is not a storyboard the Runner target's resources list" >&2; exit 1; }
done <<<"$launch"

echo "== 4. Assemble"
cp "$products/Runner" "$bundle/Runner"
strip -x "$bundle/Runner"
for b in "$products"/*.bundle; do [ ! -d "$b" ] || cp -R "$b" "$bundle/"; done
# Dynamic SwiftPM products: a plugin may vend a .dylib product (flutter_soloud
# is type: .dynamic) or a dynamic framework (ScreenPreventerKit); Runner's load
# commands reference them under @rpath, which resolves to Frameworks. SwiftBuild
# also stages unreferenced binaryTargets into products (Sentry.framework here,
# which rcodesign cannot re-sign), so embed only what is actually loaded. The
# scan repeats until no new product is embedded, so a chain of any depth
# (Runner -> F0 -> F1 -> ...) closes; App/Flutter/native-asset frameworks are
# copied first so their binaries are scanned too.
find "$products" -maxdepth 1 -name '*.dylib' -exec cp {} "$bundle/Frameworks/" \;
cp -R "$asm/App.framework" "$asm/Flutter.framework" "$bundle/Frameworks/"
for f in "$asm"/native_assets/*.framework; do [ ! -d "$f" ] || cp -R "$f" "$bundle/Frameworks/"; done
for _ in $(seq 1 64); do  # ponytail: fixed 64-iteration cap; products are finite so the loop exits on its own first
  before=$(find "$bundle/Frameworks" -maxdepth 1 | wc -l)
  {
    llvm-otool -l "$bundle/Runner" "$bundle"/Frameworks/*.dylib 2>/dev/null || true
    for fw in "$bundle"/Frameworks/*.framework; do
      bin=$(basename "${fw%.framework}")
      [ -f "$fw/$bin" ] && llvm-otool -l "$fw/$bin" 2>/dev/null || true
    done
  } | sed -n 's/.*name @rpath\/\([^ ]*\).*/\1/p' | sort -u |
    while read -r name; do
      case $name in
        *.framework/*) rel=${name%%.framework/*}.framework ;;
        *) rel=$name ;;
      esac
      if [ -e "$products/$rel" ] && [ ! -e "$bundle/Frameworks/$rel" ]; then
        echo "embedding $rel"
        cp -R "$products/$rel" "$bundle/Frameworks/"
      fi
    done
  after=$(find "$bundle/Frameworks" -maxdepth 1 | wc -l)
  [ "$after" -gt "$before" ] || break
done
# Each extension becomes PlugIns/<name>.appex: the executable build.sh built
# above, the Info.plist gen-extensions.py wrote, the target's catalogs as
# Assets.car, its string catalogs as X.lproj, and the rest of its resources,
# as Xcode assembles an extension.
if [ -n "$exts" ]; then
  mkdir -p "$bundle/PlugIns"
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    appex=$bundle/PlugIns/$name.appex
    mkdir -p "$appex"
    cp "$ext_products/$name" "$appex/$name"
    strip -x "$appex/$name"
    cp "$ext_pkg/$name-Info.plist" "$appex/Info.plist"
    field() { # a plan.json list of one extension, one entry per line
      python3 -c 'import json, sys
e = next(x for x in json.load(open(sys.argv[1]))["extensions"] if x["name"] == sys.argv[2])
if sys.argv[3] == "resources":
    print("\n".join(f"{src}\t{dst}" for src, dst in e["resources"]))
else:
    print("\n".join(e[sys.argv[3]]))' "$ext_pkg/plan.json" "$name" "$1"
    }
    assets=$(field assets)
    if [ -n "$assets" ]; then
      mapfile -t asset_dirs <<<"$assets"
      "$tools/actool" "${asset_dirs[@]}" --compile "$appex" --platform iphoneos \
        --minimum-deployment-target "$ext_min" --target-device iphone --target-device ipad \
        --output-partial-info-plist "$stage/$name-assets.plist" \
        --output-format human-readable-text >>"$out/actool.log" 2>&1 ||
        { tail -n 20 "$out/actool.log" >&2; exit 1; }
      python3 -c 'import plistlib, sys
p = sys.argv[1]
d = plistlib.load(open(p, "rb"))
d.update(plistlib.load(open(sys.argv[2], "rb")))
plistlib.dump(d, open(p, "wb"), fmt=plistlib.FMT_BINARY)' "$appex/Info.plist" "$stage/$name-assets.plist"
    fi
    while IFS= read -r catalog; do
      [ -n "$catalog" ] || continue
      python3 "$here/../tools/xcstringstool" compile "$catalog" --output-dir "$appex" \
        --serialization-format binary >>"$out/xcstringstool.log" 2>&1 ||
        { tail -n 10 "$out/xcstringstool.log" >&2; exit 1; }
    done <<<"$(field strings)"
    while IFS=$'\t' read -r src dst; do
      [ -n "$src" ] || continue
      mkdir -p "$appex/$(dirname "$dst")"
      cp -R "$src" "$appex/$dst"
    done <<<"$(field resources)"
    printf 'BNDL????' >"$appex/PkgInfo"
  done < <(python3 -c 'import json, sys
print("\n".join(e["name"] for e in json.load(open(sys.argv[1]))["extensions"]))' "$ext_pkg/plan.json")
fi
cp "$app/ios/Flutter/AppFrameworkInfo.plist" "$bundle/"
printf 'APPL????' >"$bundle/PkgInfo"
# STRIP_FRAMEWORKS names frameworks to leave out (without .framework, separated
# by spaces or commas), as a Mac build strips the archive and exports it again.
# The script refuses one that the rest of the app still loads.
if [ -n "${STRIP_FRAMEWORKS:-}" ]; then
  IFS=', ' read -r -a strip_list <<<"$STRIP_FRAMEWORKS"
  strip_names=(); for n in "${strip_list[@]}"; do [ -n "$n" ] && strip_names+=("$n"); done # a trailing or doubled separator
  if [ "${#strip_names[@]}" -gt 0 ]; then
    python3 "$here/tools/strip-frameworks.py" "$bundle" "${strip_names[@]}"
  fi
fi
# The weak-link rewrite happens last: strip and the @rpath scan above must
# see the vanilla load commands (distro llvm-strip rejects an unfamiliar
# LC_LOAD_WEAK_DYLIB), and nothing after this point parses the binaries
# except signing, which treats both commands identically.
if [ -n "${WEAK_FRAMEWORKS:-}" ]; then
  python3 "$here/tools/weaklink.py" "$bundle/Runner" $WEAK_FRAMEWORKS
  for appex in "$bundle"/PlugIns/*.appex; do
    [ -d "$appex" ] || continue
    python3 "$here/tools/weaklink.py" "$appex/$(basename "${appex%.appex}")" $WEAK_FRAMEWORKS
  done
fi
rm -f "$out/Runner.ipa"
(cd "$out" && zip -qry Runner.ipa Payload)

echo "== 5. Debug symbols"
# One dSYM per Mach-O image in the app, as an Xcode archive's dSYMs folder, for
# crash symbolication (Crashlytics, Sentry, App Store Connect). App.framework's
# comes from flutter assemble (dsymutil after gen_snapshot), Flutter.framework's
# from the engine artifacts, a native asset's from its build. Runner and the
# SwiftPM products get SwiftBuild's dSYM when it wrote one, else dsymutil on
# the unstripped product: its debug map points at the objects in .build. The
# bundle's copies keep the products' UUIDs (strip, stamp and signing do not
# change LC_UUID), so each dSYM matches its image.
dsyms=$out/dSYMs
# Copies of SwiftPM outputs can be read-only, which would stop the next rm.
[ ! -d "$dsyms" ] || chmod -R u+w "$dsyms"
rm -rf "$dsyms"; mkdir -p "$dsyms"
: >"$out/dsymutil.log"
engine_dsym=$flutter_root/bin/cache/artifacts/engine/ios-release/Flutter.xcframework/ios-arm64/dSYMs/Flutter.framework.dSYM
dsym_missing=()
add_dsym() { # <image name, e.g. Runner.app or Foo.framework> <unstripped binary or empty>
  local name=$1 binary=$2 src
  for src in "$asm/$name.dSYM" "$asm/native_assets/$name.dSYM" "$products/${name%.app}.dSYM"; do
    if [ -d "$src" ]; then cp -R "$src" "$dsyms/$name.dSYM"; return; fi
  done
  if [ "$name" = Flutter.framework ] && [ -d "$engine_dsym" ]; then cp -R "$engine_dsym" "$dsyms/"; return; fi
  # dsymutil succeeds on a binary without a debug map (a prebuilt one) but
  # leaves no DWARF file: that counts as missing.
  if [ -n "$binary" ] && [ -f "$binary" ] &&
     dsymutil "$binary" -o "$dsyms/$name.dSYM" >>"$out/dsymutil.log" 2>&1 &&
     [ -n "$(find "$dsyms/$name.dSYM/Contents/Resources/DWARF" -type f 2>/dev/null)" ]; then return; fi
  rm -rf "$dsyms/$name.dSYM"
  dsym_missing+=("$name")
}
add_dsym Runner.app "$products/Runner"
for f in "$bundle"/Frameworks/*; do
  name=$(basename "$f")
  case $name in
    *.framework) add_dsym "$name" "$products/$name/${name%.framework}" ;;
    *.dylib) add_dsym "$name" "$products/$name" ;;
  esac
done
for name in ${exts:-}; do
  add_dsym "$name.appex" "$ext_products/$name"
done
echo "dSYMs: $(find "$dsyms" -mindepth 1 -maxdepth 1 -name '*.dSYM' | wc -l) in $dsyms"
if [ "${#dsym_missing[@]}" -gt 0 ]; then
  echo "warning: no dSYM for ${dsym_missing[*]} (see $out/dsymutil.log)" >&2
fi
if [ -n "$split_dir" ]; then echo "Dart symbols in $split_dir"; fi
echo "Built $out/Runner.ipa ($BUNDLE_ID $BUILD_NAME+$BUILD_NUMBER, iOS $MIN_IOS+${FLAVOR:+, $configuration})"

if [ -n "$install" ]; then
  xt=${XTOOL:-$HOME/.local/bin/xtool}
  [ -x "$xt" ] || xt=$(command -v xtool || echo "$xt") # on PATH with a packaged toolchain
  "$xt" install --usb "$out/Runner.ipa"
fi
