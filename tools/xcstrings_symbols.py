"""`xcstringstool generate-symbols --language swift`: one LocalizedStringResource symbol per manually
managed key, in the shape Xcode 27's xcstringstool writes."""
import re
import sys

SPEC = re.compile(r"%(\d+\$)?([-+ #0]*\d*(?:\.\d+)?)(hh|h|ll|l|q|z|t|j|L)?([@dDiuUxXoOfeEgGcCsSpaA])")


def swift_type(length, conversion):
    """Swift parameter type for one format specifier, as Xcode 27 picks it (%d Int32, %lld Int,
    %u UInt32, %f Float, %@ String were checked against it; the other rows follow C's sizes)."""
    if conversion in "dDi":
        return {"hh": "Int8", "h": "Int16", None: "Int32"}.get(length, "Int")
    if conversion in "uUxXoO":
        return {"hh": "UInt8", "h": "UInt16", None: "UInt32"}.get(length, "UInt")
    if conversion in "feEgGaA":
        return "Float" if length is None else "Double"
    return {"c": "CChar", "C": "UInt16", "s": "UnsafePointer<CChar>", "S": "UnsafePointer<UInt16>",
            "p": "UnsafeRawPointer"}.get(conversion, "String")

HEADER = """// 
// GeneratedStringSymbols_{stem}.swift
// Auto-Generated symbols for localized strings defined in “{name}”.
// 

import Foundation

#if SWIFT_PACKAGE
private nonisolated let resourceBundle = Foundation.Bundle.module
@available(macOS 13, iOS 16, tvOS 16, watchOS 9, *)
private nonisolated let resourceBundleDescription = LocalizedStringResource.BundleDescription.atURL(resourceBundle.bundleURL)
#else

private class ResourceBundleClass {{}}
@available(macOS 13, iOS 16, tvOS 16, watchOS 9, *)
private nonisolated let resourceBundleDescription = LocalizedStringResource.BundleDescription.forClass(ResourceBundleClass.self)
#endif
"""


def camel(words):
    out = []
    for i, w in enumerate(words):
        if w.isupper():
            w = w.capitalize()
        out.append(w[0].lower() + w[1:] if i == 0 else w[0].upper() + w[1:])
    return "".join(out)


# Swift reserved words. Apple's generator escapes a symbol that matches one with backticks
# (key "CONTINUE" -> static var `continue`), so the generated file compiles.
SWIFT_KEYWORDS = frozenset("""
    associatedtype borrowing class consuming deinit enum extension fileprivate func import init
    inout internal let nonisolated open operator private precedencegroup protocol public rethrows
    static struct subscript typealias var break case catch continue default defer do else
    fallthrough for guard if in repeat return throw switch where while Any as await false is nil
    self Self super throws true try
""".split())


def identifier(key):
    text = SPEC.sub(" ", key).replace("'", "").replace("’", "")
    name = camel(re.findall(r"[^\W_]+", text, re.UNICODE)) or "string"
    if name[0].isdigit():
        return "_" + name
    return f"`{name}`" if name in SWIFT_KEYWORDS else name


def swift_literal(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def arguments(key, locs, source):
    """[(label or None, variable, swift type, specifier)] in argument-number order. A substitution
    claims its argNum position, labels it with the camelCased name and types it by its own
    formatSpecifier; remaining positions come from the key's and the source value's specifiers."""
    order = [source] + sorted(lang for lang in locs if lang != source)
    src_unit = (locs.get(source) or {}).get("stringUnit") or {}
    value = src_unit.get("value") if isinstance(src_unit.get("value"), str) else None
    submap = next((locs[lang]["substitutions"] for lang in order
                   if isinstance(locs.get(lang), dict) and "substitutions" in locs.get(lang, {})), {})
    claimed = {}
    for pos, (name, sub) in enumerate(submap.items(), start=1):
        n = sub.get("argNum", pos)
        words = re.findall(r"[^\W_]+", name, re.UNICODE)
        label = camel(words) if words else None
        fmt = sub.get("formatSpecifier", "d")
        m = re.fullmatch(r"(hh|h|ll|l|q|z|t|j|L)?([@dDiuUxXoOfeEgGcCsSpaA])", fmt)
        length, conv = (m.groups() if m else (None, "d"))
        claimed[n] = (label, label or f"arg{n}", swift_type(length, conv), "%" + fmt)
    args = {}
    for n, m in enumerate(SPEC.finditer(key.replace("%%", "")), start=1):
        spec = "%" + m.group(2) + (m.group(3) or "") + m.group(4)
        args[n] = (None, f"arg{n}", swift_type(m.group(3), m.group(4)), spec)
    if value is not None:
        for n, m in enumerate(SPEC.finditer(value.replace("%%", "")), start=1):
            if n not in args:
                spec = "%" + m.group(2) + (m.group(3) or "") + m.group(4)
                args[n] = (None, f"arg{n}", swift_type(m.group(3), m.group(4)), spec)
    args.update(claimed)
    return [args[n] for n in sorted(args)]


def symbol(key, entry, stem, source):
    doc = []
    if entry.get("comment"):
        first, *rest = entry["comment"].split("\n")
        doc += [f"     {first}", *rest, "     "]
    doc.append(f"     Localized string for key “{key}” in table “{stem}.xcstrings”.")
    head = ["    /**", *doc, "     */"]
    name, lit = identifier(key), swift_literal(key)
    locs = entry.get("localizations") or {}
    args = arguments(key, locs, source)
    if not args:
        return "\n".join([
            *head,
            f"    static var {name}: LocalizedStringResource {{",
            f'        LocalizedStringResource("{lit}", table: "{stem}", bundle: resourceBundleDescription)',
            "    }",
        ])
    params = ", ".join(f"{var}: {typ}" if label else f"_ {var}: {typ}" for label, var, typ, _ in args)
    default = "".join(f"\\({var})" if typ == "String" else f'\\({var}, specifier: "{spec}")'
                      for _, var, typ, spec in args)
    return "\n".join([
        *head,
        f"    static func {name}({params}) -> LocalizedStringResource {{",
        f'        LocalizedStringResource("{lit}", defaultValue: "{default}", table: "{stem}", '
        "bundle: resourceBundleDescription)",
        "    }",
    ])


def swift_symbols(catalog, name, stem):
    source = catalog["sourceLanguage"]
    strings = catalog.get("strings", {})
    manual = [(k, strings[k]) for k in sorted(strings) if strings[k].get("extractionState") == "manual"]
    if not manual:
        return ""
    # Keys that differ only in case or punctuation ("Cancel", "CANCEL") make the same symbol, and two
    # declarations of one name do not compile. Leave out every key of such a group; the strings stay
    # in the compiled table, only their symbols are not generated.
    names = {}
    for k, _ in manual:
        names.setdefault(identifier(k), []).append(k)
    clashes = {n: ks for n, ks in names.items() if len(ks) > 1}
    for n, ks in sorted(clashes.items()):
        print(f"warning: {stem}.xcstrings: no symbol '{n}' for keys {ks} (same name)", file=sys.stderr)
    manual = [(k, e) for k, e in manual if identifier(k) not in clashes]
    if not manual:
        return ""
    body = "\n\n".join(symbol(k, e, stem, source) for k, e in manual)
    if stem == "Localizable":
        # The default table's symbols sit flat in the extension; every other table is namespaced.
        return (HEADER.format(stem=stem, name=name)
                + "\n@available(macOS 13, iOS 16, tvOS 16, watchOS 9, *)\n"
                + f"nonisolated extension LocalizedStringResource {{\n{body}\n}}")
    words = re.findall(r"[^\W_]+", stem, re.UNICODE)
    enum_name = "".join(w[:1].upper() + w[1:] for w in words) or "Strings"
    indented = "\n".join("    " + ln if ln else ln for ln in body.split("\n"))
    return (HEADER.format(stem=stem, name=name)
            + "\n@available(macOS 13, iOS 16, tvOS 16, watchOS 9, *)\n"
            + "nonisolated extension LocalizedStringResource {\n"
            + f"    /// Namespace for strings in file “{name}”.\n"
            + f"    enum {enum_name} {{\n{indented}\n    }}\n}}")
