"""Refusal, event-connection and runtime-attribute paths of tools/ibtool
compile_xib.

The corpus in tests/ibtool/src compiles every xib through compile_xib, but it
only contains valid documents: the targetRuntime and <objects> refusals, the
per-object refusals, the event-connection block and the key-value pairs block
have no coverage there. Each test here builds one small xib (modeled on
TinyView.xib) and compiles it through the command line, as a user would, or
decodes the produced nib with tools/nibarchive.py.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
IBTOOL = TOOLS / "ibtool"
FLAGS = ["--target-device", "iphone", "--target-device", "ipad",
         "--minimum-deployment-target", "17.0"]
sys.path.insert(0, str(TOOLS))
import nibarchive  # noqa: E402

XIB = """<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.CocoaTouch.XIB" version="3.0" toolsVersion="18122" targetRuntime="{runtime}" propertyAccessControl="none" useAutolayout="YES" colorMatched="YES">
    <objects>{objects}
    </objects>
</document>"""

PLACEHOLDERS = """
        <placeholder placeholderIdentifier="IBFilesOwner" id="-1" userLabel="File's Owner"/>
        <placeholder placeholderIdentifier="IBFirstResponder" id="-2" customClass="UIResponder"/>"""

VIEW = """
        <view contentMode="scaleToFill" id="v1">
            <rect key="frame" x="0.0" y="0.0" width="390" height="844"/>
            <autoresizingMask key="autoresizingMask" widthSizable="YES" heightSizable="YES"/>
            <subviews>
                <button opaque="NO" contentMode="scaleToFill" contentHorizontalAlignment="center" contentVerticalAlignment="center" buttonType="system" lineBreakMode="middleTruncation" translatesAutoresizingMaskIntoConstraints="NO" id="b1">
                    <rect key="frame" x="8.0" y="8.0" width="100" height="31"/>
                    <connections>
                        <action selector="tapped:" destination="{dst}"{etype_attr} id="a1"/>
                    </connections>
                </button>
            </subviews>
            {extra}
        </view>"""


def compile_xib_xml(xml, name="t.xib"):
    """Compile one xib through the CLI; return (rc, stderr, nib bytes or None)."""
    with tempfile.TemporaryDirectory() as tmp:
        xib = os.path.join(tmp, name)
        with open(xib, "w") as fh:
            fh.write(xml)
        p = subprocess.run([sys.executable, str(IBTOOL), *FLAGS,
                            "--compile", "out.nib", name],
                           capture_output=True, text=True, timeout=300, cwd=tmp)
        data = None
        if p.returncode == 0:
            with open(os.path.join(tmp, "out.nib"), "rb") as fh:
                data = fh.read()
    return p.returncode, p.stderr, data


def event_connections(data):
    """The decoded event connections: (UILabel, UIEventMask or None, dst id)."""
    a = nibarchive.parse(data)
    out = []
    for i, obj in enumerate(a.objects):
        if a.object_class(i) != "UIRuntimeEventConnection":
            continue
        vals = {a.key(v.key_idx): v for v in a.object_values(obj)}
        label = a.render(vals["UILabel"]).split(" -> ")[0]
        mask = a.render(vals["UIEventMask"]) if "UIEventMask" in vals else None
        dst = vals["UIDestination"].payload
        dvals = {a.key(v.key_idx): v for v in a.object_values(a.objects[dst])}
        ident = a.render(dvals["UIProxiedObjectIdentifier"]).split(" -> ")[0]
        out.append((label, mask, ident))
    return out


class CompileXibRefusals(unittest.TestCase):
    """Each case is one xib that trips one refusal of compile_xib."""

    def check(self, xml, message):
        rc, err, _ = compile_xib_xml(xml)
        self.assertEqual(rc, 1, err)
        self.assertEqual(err.strip(), f"error: ibtool: {message}")

    def test_bad_target_runtime(self):
        self.check(XIB.format(runtime="AppleTV.CocoaTouch", objects=PLACEHOLDERS),
                   "t.xib: targetRuntime 'AppleTV.CocoaTouch' is not iOS.CocoaTouch")

    def test_no_objects_element(self):
        doc = """<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.CocoaTouch.XIB" version="3.0" toolsVersion="18122" targetRuntime="iOS.CocoaTouch" colorMatched="YES">
    <dependencies>
        <deployment identifier="iOS"/>
    </dependencies>
</document>"""
        self.check(doc, "t.xib: no <objects> element")

    def test_unsupported_placeholder(self):
        ph = PLACEHOLDERS + """
        <placeholder placeholderIdentifier="IBToolBar" id="-3" userLabel="Toolbar"/>"""
        self.check(XIB.format(runtime="iOS.CocoaTouch", objects=ph),
                   "unsupported placeholder 'IBToolBar' (t.xib object #2)")

    def test_multiple_top_level_objects(self):
        objects = PLACEHOLDERS \
            + VIEW.format(dst="-1", etype_attr=' eventType="touchUpInside"', extra="") \
            + VIEW.format(dst="-1", etype_attr=' eventType="touchUpInside"', extra="")
        self.check(XIB.format(runtime="iOS.CocoaTouch", objects=objects),
                   "t.xib: multiple top-level objects are not supported")

    def test_unsupported_element(self):
        objects = PLACEHOLDERS + """
        <button opaque="NO" contentMode="scaleToFill" contentHorizontalAlignment="center" contentVerticalAlignment="center" buttonType="system" lineBreakMode="middleTruncation" id="b1">
            <rect key="frame" x="0.0" y="0.0" width="100" height="31"/>
        </button>"""
        self.check(XIB.format(runtime="iOS.CocoaTouch", objects=objects),
                   "unsupported element <button> (t.xib object #2)")

    def test_no_top_level_object(self):
        self.check(XIB.format(runtime="iOS.CocoaTouch", objects=PLACEHOLDERS),
                   "t.xib: no top-level object")


class CompileXibEventConnections(unittest.TestCase):
    """The UIRuntimeEventConnection block: reachable only with an <action>
    on a subview button; the destination must be a Files Owner or First
    Responder placeholder."""

    def view(self, dst, etype_attr):
        return XIB.format(runtime="iOS.CocoaTouch",
                          objects=PLACEHOLDERS
                          + VIEW.format(dst=dst, etype_attr=etype_attr, extra=""))

    def test_event_to_files_owner_with_type(self):
        rc, err, data = compile_xib_xml(self.view("-1", ' eventType="touchUpInside"'))
        self.assertEqual(rc, 0, err)
        self.assertEqual(event_connections(data),
                         [("string 'tapped:'", "int 64", "string 'IBFilesOwner'")])

    def test_event_to_first_responder_without_type(self):
        rc, err, data = compile_xib_xml(self.view("-2", ""))
        self.assertEqual(rc, 0, err)
        self.assertEqual(event_connections(data),
                         [("string 'tapped:'", None, "string 'IBFirstResponder'")])

    def test_event_unknown_destination(self):
        rc, err, _ = compile_xib_xml(self.view("zzz", ' eventType="touchUpInside"'))
        self.assertEqual(rc, 1, err)
        self.assertEqual(err.strip(),
                         "error: ibtool: t.xib: unparsable connection destination 'zzz'")

    def test_event_unknown_event_type(self):
        rc, err, _ = compile_xib_xml(self.view("-1", ' eventType="bogusEvent"'))
        self.assertEqual(rc, 1, err)
        self.assertEqual(err.strip(),
                         "error: ibtool: t.xib: unsupported eventType 'bogusEvent'")


class CompileXibKeyValuePairs(unittest.TestCase):
    """userDefinedRuntimeAttributes on the top-level view fill the
    UINibKeyValuePairsKey list."""

    def test_runtime_attributes(self):
        extra = """<userDefinedRuntimeAttributes>
                <userDefinedRuntimeAttribute type="boolean" keyPath="isHidden" value="YES"/>
            </userDefinedRuntimeAttributes>"""
        xml = XIB.format(runtime="iOS.CocoaTouch",
                         objects=PLACEHOLDERS
                         + VIEW.format(dst="-1", etype_attr="", extra=extra))
        rc, err, data = compile_xib_xml(xml)
        self.assertEqual(rc, 0, err)
        a = nibarchive.parse(data)
        kv = [i for i, _ in enumerate(a.objects)
              if a.object_class(i) == "UINibKeyValuePair"]
        self.assertEqual(len(kv), 1)
        root = {a.key(v.key_idx): v for v in a.object_values(a.objects[0])}
        pairs_ref = root["UINibKeyValuePairsKey"]
        self.assertEqual(pairs_ref.type, nibarchive.OBJREF)
        self.assertEqual(a.object_class(pairs_ref.payload), "NSArray")
        pairs = a.object_values(a.objects[pairs_ref.payload])
        self.assertEqual(
            [(a.key(v.key_idx), v.type, v.payload) for v in pairs],
            [("NSInlinedValue", nibarchive.FALSE, False),
             ("UINibEncoderEmptyKey", nibarchive.OBJREF, kv[0])])
        obj = a.objects[kv[0]]
        vals = {a.key(v.key_idx): v for v in a.object_values(obj)}
        self.assertTrue(a.render(vals["UIKeyPath"]).startswith("string 'isHidden'"))
        self.assertEqual(a.object_class(vals["UIValue"].payload), "NSNumber")
        num = a.objects[vals["UIValue"].payload]
        nvals = {a.key(v.key_idx): v for v in a.object_values(num)}
        self.assertEqual(a.render(nvals["NS.intval"]), "int 1")
        self.assertEqual(a.object_class(vals["UIObject"].payload), "UIView")


if __name__ == "__main__":
    unittest.main()
