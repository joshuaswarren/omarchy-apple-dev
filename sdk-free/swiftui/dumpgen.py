#!/usr/bin/env python3
"""Report the device-side layout of a SwiftUI/SwiftUICore type.

Reads reflection dumps of the iPhone's SwiftUI/SwiftUICore from the iOS
dyld shared cache (made with `ipsw swift-dump <cache> <image> --demangle
--no-color`) and prints, for each requested type name: its stored fields
with Swift types, nested types, protocol conformances, and how many
demangled exported symbols mention the type (a proxy for frozen-like:
the device exports code for the exact type, so a matching frozen
declaration can pass it in registers). Sizes are not in the reflection
dump: confirm them with sdk-free/swiftui/layout-probe.swift against the
field count/types printed here.

Dumps are cached in a scratch directory and never committed; nothing
Apple-derived goes into the repo. Example:

  python3 sdk-free/swiftui/dumpgen.py Color Font Image \
      --cache dsc27/24A446__iPhone16,2/dyld_shared_cache_arm64e \
      --scratch /path/to/scratch --demangled demangled-syms.txt
"""
import argparse, os, re, subprocess, sys

IMAGES = ["SwiftUI", "SwiftUICore"]
DECL = re.compile(r"^(struct|enum|class|protocol|typealias) (.+?)( \{|$)")


def dump_path(scratch, image):
    return os.path.join(scratch, image + ".txt")


def get_dump(cache, scratch, image, refresh=False):
    path = dump_path(scratch, image)
    if refresh or not os.path.exists(path):
        os.makedirs(scratch, exist_ok=True)
        img = f"/System/Library/Frameworks/{image}.framework/{image}"
        print(f"== ipsw swift-dump {image} (cached at {path})", file=sys.stderr)
        r = subprocess.run(["ipsw", "swift-dump", cache, img,
                            "--demangle", "--no-color"],
                           stdout=subprocess.PIPE, stderr=sys.stderr,
                           text=True)
        if r.returncode != 0:
            sys.exit(f"ipsw failed for {image}")
        with open(path, "w") as f:
            f.write(r.stdout)
    with open(path) as f:
        return f.read().splitlines()


def blocks_for(lines, name):
    """Yield the declaration block of every type whose last name
    component matches `name`, plus its nested types."""
    hits, i = [], 0
    pat = re.compile(r"^(struct|enum|class|protocol) ([\w.$]*[.:])?"
                     + re.escape(name) + r"(\.[\w$]+)? \{")
    while i < len(lines):
        m = pat.match(lines[i])
        if not m:
            i += 1
            continue
        start = i
        full = m.group(0)[:-2].strip()
        while i < len(lines) and lines[i] != "}" and not lines[i].endswith("{}"):
            i += 1
        if i < len(lines) and lines[i].endswith("{}"):
            hits.append((full, [lines[i]]))
            i += 1
            continue
        hits.append((full, lines[start:i + 1]))
        i += 1
    return hits


def conformances(lines, name):
    out = []
    for ln in lines:
        if ln.startswith("extension ") and re.search(
                r"[.:]" + re.escape(name) + r"(?![\w$])", ln):
            out.append(ln)
    return out


def symbol_hits(demangled, name):
    if not demangled:
        return 0, []
    hits = [ln for ln in demangled
            if re.search(r"\." + re.escape(name) + r"(?![\w$])", ln)]
    return len(hits), hits[:25]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="+", help="type names, e.g. Color Font")
    ap.add_argument("--cache", required=True, help="dyld shared cache path")
    ap.add_argument("--scratch", required=True,
                    help="dump cache dir (keep out of the repo)")
    ap.add_argument("--demangled",
                    help="file of demangled exported symbols (one per line)")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    lines, dem = [], []
    for image in IMAGES:
        lines += get_dump(a.cache, a.scratch, image, a.refresh)
    if a.demangled:
        with open(a.demangled) as f:
            dem = f.read().splitlines()

    for name in a.names:
        blocks = blocks_for(lines, name)
        if not blocks:
            print(f"== {name}: NOT FOUND in {'/'.join(IMAGES)} dumps")
            continue
        print(f"== {name}: {len(blocks)} declaration(s)")
        for full, body in blocks:
            print(f"--- {full}")
            print("\n".join(body))
        cons = conformances(lines, name)
        if cons:
            print(f"--- conformances mentioning {name}: {len(cons)}")
            print("\n".join(cons[:15]))
        n, sample = symbol_hits(dem, name)
        verdict = ("frozen-like (device exports symbols)"
                   if n else "no exported methods (inline-only or resilient)")
        print(f"--- exported symbol mentions: {n} -> {verdict}")
        for s in sample:
            print("    " + s)


if __name__ == "__main__":
    main()
