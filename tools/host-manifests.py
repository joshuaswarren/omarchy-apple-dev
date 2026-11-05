#!/usr/bin/env python3
"""Answer as on a Mac the manifests of direct dependencies that test the build host.

    host-manifests.py <package dir>      (an xtool package, e.g. omarchy-xtool)
    host-manifests.py --self-test

SwiftPM evaluates every Package.swift on the machine it runs on. A manifest
that tests that machine instead of the platform it builds for answers for
Linux here: RxSwift 6.9 and later leave the RxCocoa product out when
canImport(Darwin) is false, so an iOS app that uses RxCocoa stops on
"product 'RxCocoa' required by package ... not found", though RxCocoa builds
for iOS. On a Mac the same manifest answers for macOS, which is what the iOS
build expects.

The tool resolves the package (swift package resolve: it fetches the
dependencies, as xtool dev build does next), finds the direct dependencies
whose manifest has an #if / #elseif on canImport(Darwin), os(macOS) or
os(Linux), copies each into <package>/.host-manifests/<name> with those tests
answered as on a Mac (true, true, false), declares it by path in place of its
URL, and resolves again. A dependency of a dependency is reported and left as
is: xtool builds the app from a package of its own, where a path declared
here does not replace it. Running it twice changes nothing more. Stdlib only.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HOST_TESTS = {"canImport(Darwin)": "true", "os(macOS)": "true", "os(Linux)": "false"}
HOST_LINE = re.compile(r"^\s*#\s*(if|elseif)\b.*(" + "|".join(re.escape(t) for t in HOST_TESTS) + ")")
MANIFEST = re.compile(r"Package(@swift-[0-9.]+)?\.swift")
MARK = "  // host-manifests.py: answered as on a Mac"
COPIES = ".host-manifests"


def identity(url):
    """SwiftPM's identity of a dependency: the last path component, lowercased, without .git."""
    return re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1]).lower()


def manifests(directory):
    return [os.path.join(directory, f) for f in sorted(os.listdir(directory)) if MANIFEST.fullmatch(f)]


def tests_host(directory):
    for path in manifests(directory):
        with open(path, errors="replace") as f:
            if any(HOST_LINE.match(line) for line in f):
                return True
    return False


def answer_as_mac(directory):
    """Rewrite the host tests of every manifest in directory; returns the lines changed."""
    changed = 0
    for path in manifests(directory):
        with open(path, errors="replace") as f:
            lines = f.read().split("\n")
        for i, line in enumerate(lines):
            if HOST_LINE.match(line):
                for test, answer in HOST_TESTS.items():
                    line = line.replace(test, answer)
                lines[i] = line + MARK
                changed += 1
        with open(path, "w") as f:
            f.write("\n".join(lines))
    return changed


def direct_urls(package_swift):
    """identity -> the .package(url: ...) call of each direct URL dependency."""
    text = open(package_swift).read()
    return {identity(m.group(1)): m.group(0)
            for m in re.finditer(r'\.package\(url: "([^"]+)"[^\n]*\)', text)}


def declare_by_path(package_swift, call, name):
    text = open(package_swift).read()
    text = text.replace(call, f'.package(path: "{COPIES}/{name}")', 1)
    with open(package_swift, "w") as f:
        f.write(text)


def resolve(package):
    print("swift package resolve (fetches the dependencies)")
    subprocess.run(["swift", "package", "resolve"], cwd=package, check=True)


def run(package):
    package = os.path.abspath(package)
    package_swift = os.path.join(package, "Package.swift")
    if not os.path.isfile(package_swift):
        sys.exit(f"host-manifests: no Package.swift in {package}")
    resolve(package)
    checkouts = os.path.join(package, ".build", "checkouts")
    direct = direct_urls(package_swift)
    replaced = 0
    for name in sorted(os.listdir(checkouts)) if os.path.isdir(checkouts) else []:
        source = os.path.join(checkouts, name)
        if not os.path.isdir(source) or not tests_host(source):
            continue
        call = direct.get(name.lower())
        if not call:
            print(f"{name}: its manifest tests the build host; left as is (a dependency of a dependency)")
            continue
        copy = os.path.join(package, COPIES, name)
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(source, copy, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        lines = answer_as_mac(copy)
        declare_by_path(package_swift, call, name)
        print(f"{name}: {lines} host test(s) answered as on a Mac, declared by path ({COPIES}/{name})")
        replaced += 1
    if replaced:
        resolve(package)
    else:
        print("no direct dependency tests the build host")


def self_test():
    root = tempfile.mkdtemp(prefix="host-manifests-test-")
    try:
        lib = os.path.join(root, "checkouts", "RxSwift")
        os.makedirs(lib)
        with open(os.path.join(lib, "Package.swift"), "w") as f:
            f.write("let a = 1\n#if canImport(Darwin)\nlet b = 2\n#elseif os(Linux)\nlet c = 3\n#endif\n")
        with open(os.path.join(lib, "Package@swift-5.9.swift"), "w") as f:
            f.write("#if os(macOS)\n#endif\n")
        plain = os.path.join(root, "checkouts", "swift-log")
        os.makedirs(plain)
        with open(os.path.join(plain, "Package.swift"), "w") as f:
            f.write("#if swift(>=5.9)\n#endif\n")
        pkg = os.path.join(root, "Package.swift")
        with open(pkg, "w") as f:
            f.write('        .package(url: "https://github.com/ReactiveX/RxSwift.git", from: "6.9.0"),\n'
                    '        .package(url: "https://github.com/apple/swift-log", from: "1.0.0"),\n')
        found = tests_host(lib)
        changed = answer_as_mac(lib)
        main = open(os.path.join(lib, "Package.swift")).read()
        direct = direct_urls(pkg)
        declare_by_path(pkg, direct["rxswift"], "RxSwift")
        checks = [
            ("finds a host test", found),
            ("no host test left", not tests_host(lib)),
            ("ignores a swift() test", not tests_host(plain)),
            ("three lines answered", changed == 3),
            ("canImport(Darwin) -> true", "#if true" + MARK in main),
            ("os(Linux) -> false", "#elseif false" + MARK in main),
            ("os(macOS) -> true", "#if true" in open(os.path.join(lib, "Package@swift-5.9.swift")).read()),
            ("idempotent", answer_as_mac(lib) == 0),
            ("identity", set(direct) == {"rxswift", "swift-log"}),
            ("declared by path", f'.package(path: "{COPIES}/RxSwift")' in open(pkg).read()),
            ("other dependency kept", "swift-log" in open(pkg).read()),
        ]
        failed = [n for n, ok in checks if not ok]
        if failed:
            sys.exit(f"self-test failed: {', '.join(failed)} (scratch dir kept: {root})")
        print(f"self-test passed ({len(checks)} checks)")
    except BaseException:
        print(f"scratch dir kept: {root}")
        raise
    shutil.rmtree(root)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        run(sys.argv[1])
    else:
        sys.exit(__doc__)
