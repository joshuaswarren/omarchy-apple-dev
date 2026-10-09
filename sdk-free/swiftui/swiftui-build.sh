#!/usr/bin/env bash
# Build the no-xcode SwiftUI module and compile a SwiftUI app against it.
#   sdk-free/swiftui/swiftui-build.sh [-Onone] -o OUT App.swift [more.swift ...]
# Step 1 builds the hand-written SwiftUI module (SwiftUI.swift next to this
# script) into $SDKFREE_HOME/swift/swiftui (a plain -I module directory), when
# the source is newer than the built module. Step 2 compiles the app files
# against it. Step 3 checks that every SwiftUI symbol the app object needs is
# in the sysroot's link stubs, then links like sdk-free/swiftc.sh does, with
# the SwiftUI frameworks added.
# Needs: sdk-free/setup.sh, sdk-free/swift/build-stdlib.sh and overlays.sh,
# and SwiftUI/SwiftUICore/Combine stubs in the sysroot (cut from the
# connected iPhone's system-library cache; see sdk-free/swiftui/README.md).
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
SDKFREE_HOME=${SDKFREE_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/sdk-free}
SR=$SDKFREE_HOME/iPhoneOS.sdk
RES=$SDKFREE_HOME/swift/res
MIN=${NOSDK_SWIFT_MIN:-17.0}
SWIFTC=$(command -v swiftc) || { echo "swiftc is not on PATH: run ./install-toolchain.sh first" >&2; exit 1; }
TC=$(dirname "$(dirname "$(readlink -f "$SWIFTC")")")
NM=$TC/bin/llvm-nm
OPT=-O
OUT=a.out
FILES=()
while [ $# -gt 0 ]; do
  case "$1" in
    -o) OUT=$2; shift 2 ;;
    -Onone) OPT=-Onone; shift ;;
    -O) OPT=-O; shift ;;
    *) FILES+=("$1"); shift ;;
  esac
done
[ ${#FILES[@]} -gt 0 ] || { echo "usage: swiftui-build.sh [-Onone] -o OUT file.swift ..." >&2; exit 2; }
[ -d "$RES/iphoneos/Swift.swiftmodule" ] || { echo "no Swift modules in $RES: run sdk-free/swift/build-stdlib.sh" >&2; exit 1; }

MOD=$SDKFREE_HOME/swift/swiftui
mkdir -p "$MOD"
SDKM=$SDKFREE_HOME/swift/sdkm
COMMON=(-target "arm64-apple-ios$MIN" -sdk "$SR" -resource-dir "$RES" -swift-version 5
  -I "$SDKFREE_HOME/swift/ovl" -I "$SDKFREE_HOME/swift/darwin/usr/include"
  -Xcc -isystem -Xcc "$SDKFREE_HOME/swift/darwin/usr/include" -I "$SDKM/ovlshims" -F "$SDKM/Frameworks"
  -Xcc -F -Xcc "$SDKM/Frameworks" -Xcc -fapinotes-modules -Xcc -fapinotes
  -Xcc "-fmodule-map-file=$TC/lib/swift/shims/module.modulemap" -Xcc "-I$TC/lib/swift/shims"
  -Xcc -isystem -Xcc "$SR/usr/include")

echo "== module SwiftUI ($HERE/SwiftUI.swift)"
if [ ! -f "$MOD/SwiftUI.swiftmodule" ] || [ "$HERE/SwiftUI.swift" -nt "$MOD/SwiftUI.swiftmodule" ]; then
  "$SWIFTC" -module-name SwiftUI -parse-as-library -wmo "$OPT" -enable-library-evolution "${COMMON[@]}" \
    -emit-module -emit-module-path "$MOD/SwiftUI.swiftmodule" \
    -emit-module-interface-path "$MOD/SwiftUI.swiftinterface" -no-verify-emitted-module-interface "$HERE/SwiftUI.swift"
fi

obj=$(mktemp -d)
trap 'rm -rf "$obj"' EXIT
echo "== app ($(basename "${FILES[0]}"))"
"$SWIFTC" "$OPT" -wmo -parse-as-library -enable-bare-slash-regex "${COMMON[@]}" -I "$MOD" \
  -emit-object -o "$obj/main.o" "${FILES[@]}"

echo "== symbol check against the sysroot stubs"
missing=0
while read -r s; do
  [ -n "$s" ] || continue
  found=0
  for tbd in "$SR"/System/Library/Frameworks/SwiftUI.framework/* "$SR"/System/Library/Frameworks/SwiftUICore.framework/* \
             "$SR"/System/Library/Frameworks/Combine.framework/* "$SR"/usr/lib/*.tbd; do
    [ -e "$tbd" ] || continue
    grep -qF -- "$s" "$tbd" && { found=1; break; }
  done
  if [ "$found" = 0 ]; then echo "MISSING $s"; missing=$((missing + 1)); fi
done < <("$NM" -u "$obj/main.o" | grep -E '_\$s(7SwiftUI|12SwiftUICore)' | sed 's/^ *U //' | sort -u)
echo "SwiftUI symbols checked, missing $missing"
[ "$missing" -eq 0 ] || exit 1

echo "== link"
libs=(-lSystem -lobjc -lswiftCore -lswift_Concurrency -lswift_StringProcessing -lswift_RegexParser
  -framework SwiftUI -framework SwiftUICore -framework Combine)
[ "$OPT" = -Onone ] && libs+=(-lswiftSwiftOnoneSupport)
"$SDKFREE_HOME/toolset/ld64.lld" -arch arm64 -platform_version ios "$MIN" 26.0 -syslibroot "$SR" \
  -L"$SR/usr/lib" -L"$SR/usr/lib/swift" "${libs[@]}" -rpath /usr/lib/swift -o "$OUT" "$obj/main.o" 2>&1 |
  grep -v "does not support linking for platform iOS" || true
[ -s "$OUT" ] || { echo "link failed" >&2; exit 1; }
echo "built $OUT"
