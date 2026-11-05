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


def skip_comment(text, i):
    """Index just past the Swift comment starting at i: // to the end of the
    line, /* to its */, block comments nested as Swift nests them."""
    if text.startswith("//", i):
        end = text.find("\n", i)
        return len(text) if end < 0 else end
    depth, i = 1, i + 2
    while depth:
        if i >= len(text):
            sys.exit("host-manifests: Package.swift has a /* comment without its */, left as is")
        if text.startswith("/*", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("*/", i):
            depth, i = depth - 1, i + 2
        else:
            i += 1
    return i


def skip_string(text, i):
    """Index just past the string literal starting at i ("..." or \"\"\"...\"\"\")."""
    quote = '\"\"\"' if text.startswith('\"\"\"', i) else '"'
    i += len(quote)
    while not text.startswith(quote, i):
        if i >= len(text):
            sys.exit("host-manifests: Package.swift has a string without its closing quote, left as is")
        i += 2 if text[i] == "\\" else 1
    return i + len(quote)


def package_calls(text):
    """(start, end) of every .package( ... ) call of a manifest, the closing
    parenthesis found past nested calls, string literals, comments (block
    comments nested) and newlines. Calls inside a comment are not calls. A raw
    string (#"...") is refused rather than guessed at."""
    calls, i = [], 0
    while i < len(text):
        if text.startswith(("//", "/*"), i):
            i = skip_comment(text, i)
        elif text[i] == '"':
            i = skip_string(text, i)
        elif text.startswith('#"', i):
            sys.exit("host-manifests: Package.swift has a raw string (#\"...\"), not supported, left as is")
        elif (m := re.compile(r"\.package\s*\(").match(text, i)):
            depth, i = 1, m.end()
            while depth:
                if i >= len(text):
                    sys.exit("host-manifests: Package.swift has a .package( call without its "
                             "closing parenthesis, left as is")
                if text.startswith(("//", "/*"), i):
                    i = skip_comment(text, i)
                elif text[i] == '"':
                    i = skip_string(text, i)
                elif text.startswith('#"', i):
                    sys.exit("host-manifests: Package.swift has a raw string (#\"...\"), not supported, left as is")
                else:
                    depth += {"(": 1, ")": -1}.get(text[i], 0)
                    i += 1
            calls.append((m.start(), i))
        else:
            i += 1
    return calls


def call_url(call):
    """The url: argument of a .package( ... ) call, read with the same scanner:
    a url: inside a comment, a string or a nested call is not the argument."""
    label = re.compile(r"(?<![\w.])url\s*:\s*")
    depth, i = 0, call.index("(")
    while i < len(call):
        if call.startswith(("//", "/*"), i):
            i = skip_comment(call, i)
        elif call[i] == '"':
            i = skip_string(call, i)
        elif call[i] in "()":
            depth += 1 if call[i] == "(" else -1
            i += 1
        elif depth == 1 and (m := label.match(call, i)):
            j = m.end()
            if not call.startswith('"', j) or call.startswith('"""', j):
                sys.exit("host-manifests: a .package(url:) argument that is not a plain string, left as is")
            end = skip_string(call, j)
            k = end
            while True:  # past whitespace and comments, the argument must end there
                while k < len(call) and call[k].isspace():
                    k += 1
                if call.startswith(("//", "/*"), k):
                    k = skip_comment(call, k)
                else:
                    break
            if k >= len(call) or call[k] not in ",)":
                sys.exit("host-manifests: a .package(url:) argument that is not a single string literal "
                         "(an expression?), left as is")
            url = call[j + 1:end - 1]
            if "\\" in url or "\\(" in url:
                sys.exit("host-manifests: a .package(url:) string with escapes or interpolation, left as is")
            return url
        else:
            i += 1
    return None


def direct_urls(package_swift):
    """identity -> the .package(url: ...) call of each direct URL dependency,
    each call on its own, on one line or several."""
    text = open(package_swift).read()
    found = {}
    for start, end in package_calls(text):
        call = text[start:end]
        url = call_url(call)
        if url:
            found[identity(url)] = call
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


def _exits(f, *args):
    try:
        f(*args)
    except SystemExit:
        return True
    return False


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
                    '    .package(name: "Delta", path: "../Delta"),\n'
                    '    .package(url: "https://github.com/e/Epsilon.git", /* pinned (see notes) /* nested ) */ */ '
                    'from: "1.0.0"),\n'
                    '    // .package(url: "https://github.com/f/Commented.git", from: "1.0.0"),\n'
                    '    /* .package(url: "https://github.com/g/Blocked.git", from: "1.0.0"), */\n')
        commented_url = os.path.join(root, "CommentedURL.swift")
        with open(commented_url, "w") as f:
            f.write('let deps = [\n  .package(url: "https://github.com/a/Alpha.git", from: "1.0.0"),\n'
                    '  .package(\n    // url: "https://github.com/a/Alpha.git",\n'
                    '    /* url: "https://github.com/x/Old.git", */\n'
                    '    url: "https://github.com/b/Beta.git", from: "2.0.0")\n]\n')
        by_url = direct_urls(commented_url)
        concat = os.path.join(root, "Concat.swift")
        with open(concat, "w") as f:
            f.write('  .package(url: "https://github.com/a/Alpha.git", from: "1.0.0"),\n'
                    '  .package(url: "https://github.com/a/Alpha" + "More.git", from: "1.0.0"),\n')
        concat_before = open(concat).read()
        concat_refused = _exits(direct_urls, concat) and open(concat).read() == concat_before
        spaced = os.path.join(root, "Spaced.swift")
        with open(spaced, "w") as f:
            f.write('  .package(url: "https://github.com/a/Alpha.git" /* main */ , from: "1.0.0"),\n'
                    '  .package(url: "https://github.com/b/Beta.git")\n')
        spaced_urls = direct_urls(spaced)
        declare_by_path(commented_url, by_url["alpha"], "Alpha")
        commented_url_text = open(commented_url).read()
        on_line = direct_urls(one_line)
        declare_by_path(one_line, on_line["alpha"], "Alpha")
        declare_by_path(one_line, on_line["gamma"], "Gamma")
        declare_by_path(one_line, on_line["epsilon"], "Epsilon")
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
            ("each call on its own, commented calls skipped",
             set(on_line) == {"alpha", "beta", "gamma", "epsilon"}),
            ("block comment with a parenthesis inside the call",
             f'    .package(path: "{COPIES}/Epsilon"),\n' in one_line_text and "Epsilon.git" not in one_line_text),
            ("url expression (concatenation) refused, manifest unchanged", concat_refused),
            ("url literal then comment or closing parenthesis accepted", set(spaced_urls) == {"alpha", "beta"}),
            ("url: read past a commented old url", set(by_url) == {"alpha", "beta"}
             and "Beta.git" in by_url["beta"] and "Beta.git" not in by_url["alpha"]),
            ("commented old url: Beta kept, Alpha replaced",
             '.package(path: ".host-manifests/Alpha")' in commented_url_text
             and 'url: "https://github.com/b/Beta.git", from: "2.0.0")' in commented_url_text
             and "github.com/a/Alpha.git\", from" not in commented_url_text),
            ("commented declarations left as they are",
             '// .package(url: "https://github.com/f/Commented.git"' in one_line_text
             and '/* .package(url: "https://github.com/g/Blocked.git"' in one_line_text),
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
