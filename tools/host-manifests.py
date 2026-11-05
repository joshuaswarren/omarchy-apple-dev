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
import stat
import subprocess
import sys
import tempfile

HOST_TESTS = {"canImport(Darwin)": "true", "os(macOS)": "true", "os(Linux)": "false"}
# A host test as a whole word: not the tail of a longer name (myos(Linux))
HOST_TEST = re.compile(r"(?<![\w.])(" + "|".join(re.escape(t) for t in HOST_TESTS) + ")")
HOST_LINE = re.compile(r"^\s*#\s*(if|elseif)\b.*" + HOST_TEST.pattern)
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


def writable(directory):
    """SwiftPM checks its checkouts out read-only, and copytree keeps the modes:
    the copy is made writable by its owner, to answer its manifests."""
    for parent, dirs, files in os.walk(directory):
        for entry in [parent] + [os.path.join(parent, f) for f in files]:
            if not os.path.islink(entry):
                os.chmod(entry, os.stat(entry).st_mode | stat.S_IWUSR)


def answer_as_mac(directory):
    """Rewrite the host tests of every manifest in directory; returns the lines changed."""
    changed = 0
    for path in manifests(directory):
        with open(path, errors="replace") as f:
            lines = f.read().split("\n")
        for i, line in enumerate(lines):
            if HOST_LINE.match(line):
                lines[i] = HOST_TEST.sub(lambda m: HOST_TESTS[m.group(1)], line) + MARK
                changed += 1
        with open(path, "w") as f:
            f.write("\n".join(lines))
    return changed


def package_calls(text):
    """(start, end) of every .package( ... ) call of a manifest, the closing
    parenthesis found past nested calls, string literals and newlines."""
    calls = []
    for m in re.finditer(r"\.package\s*\(", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            c = text[i]
            if c == '"':
                i += 1
                while i < len(text) and text[i] != '"':
                    i += 2 if text[i] == "\\" else 1
            elif c == "/" and text.startswith("//", i):
                i = text.find("\n", i)
                i = len(text) if i < 0 else i
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        if depth:
            sys.exit("host-manifests: Package.swift has a .package( call without its closing parenthesis")
        calls.append((m.start(), i))
    return calls


def direct_urls(package_swift):
    """identity -> the .package(url: ...) call of each direct URL dependency,
    each call on its own, on one line or several."""
    text = open(package_swift).read()
    found = {}
    for start, end in package_calls(text):
        call = text[start:end]
        url = re.search(r'\burl\s*:\s*"([^"]+)"', call)
        if url:
            found[identity(url.group(1))] = call
    return found


def declare_by_path(package_swift, call, name):
    """The call (as direct_urls read it) replaced by a declaration by path;
    refuses rather than guess when it is not there exactly once."""
    text = open(package_swift).read()
    if text.count(call) != 1:
        sys.exit(f"host-manifests: the declaration of {name} is not once in Package.swift, left as is")
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
        writable(copy)
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
            f.write("#if swift(>=5.9)\n#endif\n#if myos(Linux)\n#endif\n")
        pkg = os.path.join(root, "Package.swift")
        with open(pkg, "w") as f:
            f.write('        .package(url: "https://github.com/ReactiveX/RxSwift.git", from: "6.9.0"),\n'
                    '        .package(url: "https://github.com/apple/swift-log", from: "1.0.0"),\n')
        # Two declarations on one line, and one over several lines
        one_line = os.path.join(root, "OneLine.swift")
        with open(one_line, "w") as f:
            f.write('let deps = [.package(url: "https://github.com/a/Alpha.git", from: "1.0.0"), '
                    '.package(url: "https://github.com/b/Beta.git", from: "2.0.0")]\n'
                    '    .package(\n        url: "https://github.com/c/Gamma.git",\n'
                    '        .upToNextMajor(from: "3.0.0") // (a comment)\n    ),\n'
                    '    .package(name: "Delta", path: "../Delta"),\n')
        on_line = direct_urls(one_line)
        declare_by_path(one_line, on_line["alpha"], "Alpha")
        declare_by_path(one_line, on_line["gamma"], "Gamma")
        one_line_text = open(one_line).read()
        # A read-only checkout, as SwiftPM leaves them, copied as run() does
        ro_copy = os.path.join(root, "copy", "RxSwift")
        shutil.copytree(lib, ro_copy)
        for f in os.listdir(ro_copy):
            os.chmod(os.path.join(ro_copy, f), 0o444)
        os.chmod(ro_copy, 0o555)
        ro_source = ro_copy
        ro_copy = os.path.join(root, "copy2", "RxSwift")
        shutil.copytree(ro_source, ro_copy)
        writable(ro_copy)
        ro_changed = answer_as_mac(ro_copy)
        os.chmod(ro_source, 0o755)
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
            ("whole-word host test only", not tests_host(plain)),
            ("copy of a read-only checkout answered", ro_changed == 3),
            ("each call on its own", set(on_line) == {"alpha", "beta", "gamma"}),
            ("two on one line: second kept", one_line_text.startswith(
                f'let deps = [.package(path: "{COPIES}/Alpha"), '
                '.package(url: "https://github.com/b/Beta.git", from: "2.0.0")]')),
            ("multiline call replaced", f'    .package(path: "{COPIES}/Gamma"),\n' in one_line_text
             and "Gamma.git" not in one_line_text),
            ("path dependency kept", '.package(name: "Delta", path: "../Delta")' in one_line_text),
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
