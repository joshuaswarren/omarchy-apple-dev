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
here does not replace it. Running it twice changes nothing more.

A refusal leaves the package as it was: the root manifest and the host copies
are put back as they were when a step refuses, and a dependency identity
declared by two calls is refused before the package is resolved at all.
Stdlib only.
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


def force_rmtree(directory):
    """rmtree that also removes read-only checkouts: SwiftPM leaves them 555 and
    copytree keeps the modes, and unlink needs write on the 555 directory itself,
    which os.walk does not hand back."""
    try:
        os.chmod(directory, os.stat(directory).st_mode | stat.S_IWUSR)
    except OSError:
        pass
    for parent, dirs, files in os.walk(directory):
        for entry in dirs + files:
            if not os.path.islink(os.path.join(parent, entry)):
                try:
                    os.chmod(os.path.join(parent, entry),
                             os.stat(os.path.join(parent, entry)).st_mode | stat.S_IWUSR)
                except OSError:
                    pass
    shutil.rmtree(directory, ignore_errors=True)


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
    each call on its own, on one line or several.

    An identity declared by two calls is refused: SwiftPM gives them the same
    dependency name, so the tool cannot tell which one to declare by path, and
    keeping one of them would drop the other without a word."""
    text = open(package_swift).read()
    calls = {}
    for start, end in package_calls(text):
        call = text[start:end]
        url = call_url(call)
        if url:
            calls.setdefault(identity(url), []).append(call)
    for name, group in calls.items():
        if len(group) > 1:
            sys.exit(f"host-manifests: the dependency identity {name} is declared {len(group)} times "
                     f"in Package.swift, left as is")
    return {name: group[0] for name, group in calls.items()}


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


def rewrite(package, checkouts, direct):
    """The rewrite phase: the direct dependencies whose manifest tests the
    build host are copied into .host-manifests with their host tests answered
    as on a Mac, and declared by path in the root manifest.

    The phase is a transaction: when a step refuses, the root manifest and the
    host copies are put back as they were, and the copies this run created are
    removed."""
    package_swift = os.path.join(package, "Package.swift")
    manifest = open(package_swift, "rb").read()  # the manifest before the phase
    copies = os.path.join(package, COPIES)
    had_copies = os.path.isdir(copies)
    backup = tempfile.mkdtemp(prefix=".host-manifests-backup-", dir=package)
    created = []  # the copies this run created
    replaced = []  # the copies of earlier runs this run replaced
    said = []  # the lines printed once the phase is committed
    try:
        for name in sorted(os.listdir(checkouts)) if os.path.isdir(checkouts) else []:
            source = os.path.join(checkouts, name)
            if not os.path.isdir(source) or not tests_host(source):
                continue
            call = direct.get(name.lower())
            if not call:
                said.append(f"{name}: its manifest tests the build host; left as is "
                            "(a dependency of a dependency)")
                continue
            copy = os.path.join(copies, name)
            os.makedirs(copies, exist_ok=True)
            if os.path.exists(copy):
                # The copy of an earlier run is copied aside, to be put back if
                # this run refuses. It is not moved: SwiftPM leaves checkouts
                # read-only, and renaming a 555 directory is refused (EPERM) on
                # some filesystems, ZFS among them.
                kept = os.path.join(backup, name)
                shutil.copytree(copy, kept, symlinks=True)
                replaced.append(copy)
            else:
                created.append(copy)
            force_rmtree(copy)
            shutil.copytree(source, copy, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            writable(copy)
            lines = answer_as_mac(copy)
            declare_by_path(package_swift, call, name)
            said.append(f"{name}: {lines} host test(s) answered as on a Mac, "
                        f"declared by path ({COPIES}/{name})")
    except BaseException:
        for copy in created:
            force_rmtree(copy)
        for copy in replaced:
            force_rmtree(copy)
            shutil.copytree(os.path.join(backup, os.path.basename(copy)), copy, symlinks=True)
        with open(package_swift, "wb") as f:
            f.write(manifest)
        if not had_copies:
            try:
                os.rmdir(copies)
            except OSError:
                pass
        raise
    finally:
        force_rmtree(backup)
    for line in said:
        print(line)
    return len(created) + len(replaced)


def run(package, resolve_fn=resolve):
    package = os.path.abspath(package)
    package_swift = os.path.join(package, "Package.swift")
    if not os.path.isfile(package_swift):
        sys.exit(f"host-manifests: no Package.swift in {package}")
    # The root manifest is read before the package is resolved: a dependency
    # identity declared twice is refused before anything is written.
    direct = direct_urls(package_swift)
    resolve_fn(package)
    checkouts = os.path.join(package, ".build", "checkouts")
    if rewrite(package, checkouts, direct):
        resolve_fn(package)
    else:
        print("no direct dependency tests the build host")


def _exits(f, *args):
    try:
        f(*args)
    except SystemExit:
        return True
    return False


def _refusal(f, *args):
    """The message of a refusal, or None when there was none."""
    try:
        f(*args)
    except SystemExit as e:
        return e.code
    return None


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
        # A refusal in the rewrite phase leaves the manifest and the copies as
        # they were: Alpha is rewritten, then Beta is found twice and refused.
        partial = os.path.join(root, "partial")
        for name in ("Alpha", "Beta"):
            checkout = os.path.join(partial, ".build", "checkouts", name)
            os.makedirs(checkout)
            with open(os.path.join(checkout, "Package.swift"), "w") as f:
                f.write("#if os(macOS)\nlet x = 1\n#endif\n")
        partial_pkg = os.path.join(partial, "Package.swift")
        with open(partial_pkg, "w") as f:
            f.write('let deps = [\n'
                    '  .package(url: "https://github.com/a/Alpha.git", from: "1.0.0"),\n'
                    '  .package(url: "https://github.com/b/Beta.git", from: "2.0.0"),\n'
                    '  // .package(url: "https://github.com/b/Beta.git", from: "2.0.0"),\n'
                    ']\n')
        # A copy of an earlier run, which the refusal must put back as it was
        old_copy = os.path.join(partial, COPIES, "Alpha")
        os.makedirs(old_copy)
        with open(os.path.join(old_copy, "Package.swift"), "w") as f:
            f.write("#if true" + MARK + "\n")
        # as SwiftPM leaves a checkout: read-only, and copytree keeps the modes
        os.chmod(os.path.join(old_copy, "Package.swift"), 0o444)
        os.chmod(old_copy, 0o555)
        partial_before = open(partial_pkg, "rb").read()
        old_copy_before = open(os.path.join(old_copy, "Package.swift"), "rb").read()
        resolved = []
        partial_refusal = _refusal(run, partial, lambda package: resolved.append(package))
        partial_after = open(partial_pkg, "rb").read()
        old_copy_after = open(os.path.join(old_copy, "Package.swift"), "rb").read()
        # A dependency identity declared twice is refused before the package
        # is resolved, so nothing is written at all.
        duplicate = os.path.join(root, "duplicate")
        os.makedirs(duplicate)
        duplicate_pkg = os.path.join(duplicate, "Package.swift")
        with open(duplicate_pkg, "w") as f:
            f.write('#if os(iOS)\n'
                    '.package(url: "https://example.test/first/Shared.git", from: "1.0.0")\n'
                    '#else\n'
                    '.package(url: "https://example.test/second/Shared.git", from: "2.0.0")\n'
                    '#endif\n')
        duplicate_before = open(duplicate_pkg, "rb").read()
        resolved = []
        duplicate_refusal = _refusal(run, duplicate, lambda package: resolved.append(package))
        duplicate_after = open(duplicate_pkg, "rb").read()
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
            ("a later refusal leaves the manifest as it was", partial_after == partial_before),
            ("a later refusal leaves the copies as they were",
             old_copy_after == old_copy_before
             and not os.path.exists(os.path.join(partial, COPIES, "Beta"))),
            ("the refusal names the dependency", "Beta" in str(partial_refusal)),
            ("a duplicate identity is refused", "shared" in str(duplicate_refusal)),
            ("the refusal counts the declarations", "2 times" in str(duplicate_refusal)),
            ("a duplicate identity is refused before anything is written",
             duplicate_after == duplicate_before and not resolved),
        ]
        failed = [n for n, ok in checks if not ok]
        if failed:
            sys.exit(f"self-test failed: {', '.join(failed)} (scratch dir kept: {root})")
        print(f"self-test passed ({len(checks)} checks)")
    except BaseException:
        print(f"scratch dir kept: {root}")
        raise
    # the restored old copy is read-only, as SwiftPM leaves checkouts, so the
    # plain rmtree of the fixture root cannot remove it
    force_rmtree(root)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        run(sys.argv[1])
    else:
        sys.exit(__doc__)
