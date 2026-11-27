#!/usr/bin/env python3
"""Build settings of a Flutter app's Runner target in one build configuration.

  xcode_settings.py <ios dir> <configuration> NAME...
  xcode_settings.py <ios dir> --flavor FLAVOR
  xcode_settings.py <ios dir> --storyboards

The first form prints the value of each NAME on its own line, with its $(VAR)s
expanded. The configuration is matched ignoring case, as Flutter does; a
configuration the Runner target lacks is an error that lists the ones it has.
The second prints the Release configuration and the scheme `flutter build ios
--flavor FLAVOR` builds, one per line, or stops with the schemes and
configurations the project has when there is no single match. The third prints
the storyboards the Runner target's Copy Bundle Resources phase lists, relative
to the ios dir (a localized one under its X.lproj), one per line.

As in Xcode, the target's settings win over the target's xcconfig, then the
project's settings, then the project's xcconfig, and $(inherited) is the value
one level down. project.pbxproj is read with tools/xcodeproj2xtool.py's parser.
xcconfig files are read with read_xcconfig below: `//` starts a comment, `$()`
is empty, a later assignment wins, a missing `#include?` file is skipped, an
include cycle is cut by file, and conditional settings (`A[sdk=iphoneos*]`)
are skipped. gen-info-plist.py reads the same settings for Info.plist values.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import xcodeproj2xtool  # noqa: E402


def read_xcconfig(path, settings, seen=()):
    path = os.path.realpath(path)  # `./A.xcconfig`, `A.xcconfig` and a symlink to it are one file
    if path in seen or not os.path.isfile(path):
        return settings
    for line in open(path, errors="replace"):
        line = line.split("//", 1)[0].strip()
        inc = re.match(r'#include\??\s+"([^"]+)"', line)
        if inc:
            read_xcconfig(os.path.join(os.path.dirname(path), inc.group(1)), settings, seen + (path,))
            continue
        m = re.match(r"(\w+)\s*=\s*(.*)", line)
        if m:
            settings[m.group(1)] = m.group(2).replace("$(inherited)", "").replace("$()", "").strip()
    return settings


def expand(text, lookup, resolving=()):
    """$(NAME)s in text, each replaced by lookup(NAME), recursively."""
    def setting(m):
        name = m.group(1)
        if name in resolving:  # A = $(A), or A = $(B) and B = $(A): Xcode refuses these
            print(f"warning: $({name}) refers to itself; substituting empty", file=sys.stderr)
            return ""
        return expand(lookup(name), lookup, resolving + (name,))
    return re.sub(r"\$\((\w+)\)", setting, text)


def configurations(gen, owner):
    cfg_list = gen.objs.get(owner.get("buildConfigurationList"), {})
    return [gen.objs[c].get("name") for c in cfg_list.get("buildConfigurations", [])]


def schemes(ios_dir):
    """The schemes `xcodebuild -list` shows: shared and user ones, or Runner when there are none."""
    proj = os.path.join(ios_dir, "Runner.xcodeproj")
    files = glob.glob(os.path.join(proj, "xcshareddata", "xcschemes", "*.xcscheme"))
    files += glob.glob(os.path.join(proj, "xcuserdata", "*.xcuserdatad", "xcschemes", "*.xcscheme"))
    return sorted({os.path.basename(f)[:-len(".xcscheme")] for f in files}) or ["Runner"]


def flavor_configuration(ios_dir, flavor):
    """(configuration, scheme) as flutter_tools' XcodeProjectInfo.schemeFor and
    buildConfigurationFor pick them for a release build (xcodeproj.dart, Flutter 3.47.6):
    the scheme is the flavor in sentence case, else the one scheme equal to it
    ignoring case; the configuration is Release-<scheme> ignoring case, else the one
    whose name contains both "release" and the scheme. Where Flutter falls back to
    plain Release with a warning, this stops: the flavor's settings would be lost."""
    names = schemes(ios_dir)
    expected = flavor[:1].upper() + flavor[1:]
    found = [expected] if expected in names else [n for n in names if n.lower() == expected.lower()]
    if len(found) != 1:
        raise SystemExit(f"error: no scheme for FLAVOR={flavor} (Flutter looks for {expected!r}, ignoring case); "
                         f"the Xcode project defines schemes: {', '.join(names)}")
    scheme = found[0]
    gen = xcodeproj2xtool.Generator(os.path.join(ios_dir, "Runner.xcodeproj"), "Runner")
    configs = configurations(gen, gen.project)
    found = [c for c in configs if c.lower() == f"release-{scheme}".lower()] or \
        [c for c in configs if "release" in c.lower() and scheme.lower() in c.lower()]
    if len(found) != 1:
        raise SystemExit(f"error: {'no' if not found else 'more than one'} Release build configuration for scheme "
                         f"{scheme} (Flutter looks for Release-{scheme}, then one name with both 'release' and "
                         f"{scheme!r} in it, ignoring case): {', '.join(found or configs)}; "
                         f"the Xcode project defines schemes: {', '.join(names)}")
    return found[0], scheme


def storyboards(ios_dir):
    gen = xcodeproj2xtool.Generator(os.path.join(ios_dir, "Runner.xcodeproj"), "Runner")
    _oid, target = gen.pick_target()
    return [path for _ref, path in gen.phase_files(target, "PBXResourcesBuildPhase")
            if path.lower().endswith(".storyboard")]


def resources(ios_dir):
    """Every file the Runner target's Copy Bundle Resources phase lists, storyboards
    and asset catalogs included (the caller decides what to compile vs copy)."""
    gen = xcodeproj2xtool.Generator(os.path.join(ios_dir, "Runner.xcodeproj"), "Runner")
    _oid, target = gen.pick_target()
    return [path for _ref, path in gen.phase_files(target, "PBXResourcesBuildPhase")]


def find_target(gen, target_name):
    """A native target by name. Unlike Generator.pick_target, which only looks
    at application targets, this also finds extension and test targets, whose
    settings gen-extensions.py reads."""
    for oid, o in gen.app_targets():
        if o.get("name") == target_name:
            return oid, o
    for oid, o in gen.objs.items():
        if o.get("isa") == "PBXNativeTarget" and o.get("name") == target_name:
            return oid, o
    names = sorted({o.get("name", "?") for o in gen.objs.values()
                    if o.get("isa") == "PBXNativeTarget"})
    raise SystemExit(f"error: no target named {target_name!r} (have: {', '.join(names) or 'none'})")


class Settings:
    def __init__(self, ios_dir, configuration, target_name="Runner"):
        gen = xcodeproj2xtool.Generator(os.path.join(ios_dir, "Runner.xcodeproj"))
        _oid, target = find_target(gen, target_name)
        names = configurations(gen, target)
        found = [n for n in names if n.lower() == configuration.lower()]
        if not found:
            raise SystemExit(f"error: the {target_name} target has no {configuration!r} build configuration "
                             f"(it has: {', '.join(names) or 'none'})")
        self.configuration = found[0]
        self.builtin = {"CONFIGURATION": self.configuration, "TARGET_NAME": target_name,
                        "PROJECT_DIR": os.path.abspath(ios_dir), "SRCROOT": os.path.abspath(ios_dir)}
        self.layers = []  # lowest precedence first
        for owner in (gen.project, target):
            for layer in gen.config_layers(owner.get("buildConfigurationList"), self.configuration):
                if isinstance(layer, str):
                    layer = read_xcconfig(os.path.join(gen.proj_dir, layer), {})
                self.layers.append(layer)

    def raw(self, name, below=None):
        """The setting as the highest level that sets it writes it, $(inherited)
        filled in; None when no level sets it."""
        for i in reversed(range(len(self.layers) if below is None else below)):
            if name in self.layers[i]:
                value = self.layers[i][name]
                if isinstance(value, list):  # LD_RUNPATH_SEARCH_PATHS = ( ... )
                    value = " ".join(value)
                if "$(inherited)" in value:
                    value = value.replace("$(inherited)", self.raw(name, i) or "").strip()
                return value
        return self.builtin.get(name)

    def value(self, name):
        def lookup(ref):
            found = self.raw(ref)
            if found is None:
                print(f"warning: no value for $({ref}) in {name}; substituting empty", file=sys.stderr)
            return found or ""
        return expand(self.raw(name) or "", lookup, (name,))


if __name__ == "__main__":
    if len(sys.argv) < 3 or len(sys.argv) < 4 and sys.argv[2] != "--storyboards":
        sys.exit("usage: xcode_settings.py <ios dir> <configuration> NAME... | <ios dir> --flavor FLAVOR"
                 " | <ios dir> --storyboards")
    if sys.argv[2] == "--storyboards":
        print("\n".join(storyboards(sys.argv[1])))
        sys.exit()
    if sys.argv[2] == "--resources":
        print("\n".join(resources(sys.argv[1])))
        sys.exit()
    if sys.argv[2] == "--flavor":
        print("\n".join(flavor_configuration(sys.argv[1], sys.argv[3])))
        sys.exit()
    settings = Settings(sys.argv[1], sys.argv[2])
    for setting_name in sys.argv[3:]:
        print(settings.value(setting_name))
