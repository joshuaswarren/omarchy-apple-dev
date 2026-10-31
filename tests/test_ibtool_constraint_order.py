"""Ordering and refusal paths of tools/ibtool _constraint_order.

The corpus compiles reach most of the sort key, but not the macOS
grandchild-group walk, the guide-item group for a guide that is itself the
sort item, or the two attribute refusals. These tests pin the exact order the
function returns (direct calls, macOS included: tools/ibmac.py passes
mac=True) and the exact XibError text of the two refusals (compiled through
the CLI, as a user would hit them).
"""
import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "tools"
IBTOOL = TOOLS / "ibtool"
FLAGS = ["--target-device", "iphone", "--target-device", "ipad",
         "--minimum-deployment-target", "17.0"]

BASE = (HERE / "ibtool" / "src" / "probes" / "attr-top.xib").read_text()

_loader = importlib.machinery.SourceFileLoader("ibtool_module", str(IBTOOL))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
ibtool = importlib.util.module_from_spec(_spec)
_loader.exec_module(ibtool)

# One owner view V and a safe-area guide G, plus direct subviews. The iOS
# tree has A at the origin and P/Q with equal frame distance from it (so the
# frame-x tie-break shows), the macOS tree has a grandchild K of A (a
# grandchild has no group on iOS and must refuse).
HEAD = """<view id="V" userLabel="root">
  <viewLayoutGuide key="safeArea" id="G"/>
  <subviews>{}</subviews>
  <constraints>{}</constraints>
</view>"""
SUBS_IOS = """
    <label id="A"><rect key="frame" x="0.0" y="0.0" width="10" height="10"/></label>
    <label id="P"><rect key="frame" x="0.0" y="30.0" width="10" height="10"/></label>
    <label id="Q"><rect key="frame" x="30.0" y="0.0" width="10" height="10"/></label>"""
SUBS_MAC = """
    <label id="A"><rect key="frame" x="0.0" y="0.0" width="10" height="10"/>
      <subviews><button id="K"><rect key="frame" x="0.0" y="0.0" width="5" height="5"/></button></subviews>
    </label>
    <label id="B"><rect key="frame" x="0.0" y="20.0" width="10" height="10"/></label>"""
SUBS_MAC_DEEP = """
    <label id="A"><rect key="frame" x="0.0" y="0.0" width="10" height="10"/>
      <subviews><button id="D1"><rect key="frame" x="0.0" y="0.0" width="5" height="5"/>
          <subviews><button id="D2"><rect key="frame" x="0.0" y="0.0" width="5" height="5"/>
              <subviews><button id="D3"><rect key="frame" x="0.0" y="0.0" width="5" height="5"/>
                  <subviews><button id="D4"><rect key="frame" x="0.0" y="0.0" width="5" height="5"/>
                    <subviews><button id="D5"><rect key="frame" x="0.0" y="0.0" width="5" height="5"/></button></subviews>
                  </button></subviews>
              </button></subviews>
          </button></subviews>
      </button></subviews>
    </label>
    <label id="B"><rect key="frame" x="0.0" y="20.0" width="10" height="10"/></label>"""


def order_of(subviews, constraints, mac=False):
    el = ET.fromstring(HEAD.format(subviews, constraints))
    cons = el.find("constraints").findall("constraint")
    return [c.get("id") for c in ibtool._constraint_order(el, cons, "t", mac=mac)]


def ref(message):
    return f'error: ibtool: {message}'


class ConstraintOrder(unittest.TestCase):
    def test_ios_groups(self):
        """Guide-item, guide-to-owner, guide-to-subview, subview, owner-width
        and owner-side constraints sort in that group order on iOS. The
        guide-to-subview and subview constraints tie on group, distance and
        attribute and separate on the other side's subview index; the P and Q
        constraints tie on distance and separate on the frame x."""
        cons = """
    <constraint firstItem="G" firstAttribute="top" secondItem="P" secondAttribute="top" id="cGI"/>
    <constraint firstItem="G" firstAttribute="top" secondItem="V" secondAttribute="top" id="cGA"/>
    <constraint firstItem="A" firstAttribute="top" secondItem="P" secondAttribute="top" id="cAP"/>
    <constraint firstItem="G" firstAttribute="top" secondItem="A" secondAttribute="top" id="cGA2"/>
    <constraint firstAttribute="width" constant="9" id="cW"/>
    <constraint firstItem="P" firstAttribute="trailing" secondItem="V" secondAttribute="trailing" id="cPT"/>
    <constraint firstItem="P" firstAttribute="top" secondItem="V" secondAttribute="top" id="cPB"/>
    <constraint firstItem="P" firstAttribute="top" secondItem="Q" secondAttribute="top" id="cPQ"/>
    <constraint firstItem="Q" firstAttribute="top" secondItem="P" secondAttribute="top" id="cQP"/>"""
        self.assertEqual(order_of(SUBS_IOS, cons),
                         ["cGI", "cGA", "cGA2", "cAP", "cW", "cPT", "cPB",
                          "cPQ", "cQP"])

    def test_mac_groups(self):
        """On macOS the guide-item constraints, the direct-subview constraint
        and the grandchild constraint (inside its ancestor's group) sort in
        that order. The grandchild's fractional group index keeps it before
        bA, whose item is the next subview group."""
        cons = """
    <constraint firstItem="A" firstAttribute="top" secondItem="B" secondAttribute="top" id="cAB"/>
    <constraint firstItem="B" firstAttribute="top" secondItem="A" secondAttribute="top" id="bA"/>
    <constraint firstItem="K" firstAttribute="top" secondItem="B" secondAttribute="top" id="cKB"/>
    <constraint firstItem="G" firstAttribute="width" secondItem="A" secondAttribute="width" id="gW"/>
    <constraint firstItem="G" firstAttribute="top" secondItem="A" secondAttribute="top" id="gT"/>"""
        self.assertEqual(order_of(SUBS_MAC, cons, mac=True),
                         ["cAB", "gW", "gT", "cKB", "bA"])

    def test_mac_owner_relation_precedes_attribute(self):
        cons = """
    <constraint firstItem="A" firstAttribute="trailing" secondItem="V"
                secondAttribute="trailing" id="equalTrailing"/>
    <constraint firstItem="A" firstAttribute="leading" relation="greaterThanOrEqual"
                secondItem="V" secondAttribute="leading" id="greaterLeading"/>"""
        self.assertEqual(order_of(SUBS_MAC, cons, mac=True),
                         ["greaterLeading", "equalTrailing"])

    def test_mac_grandchild_depth_fraction(self):
        """A grandchild five levels under A stays in A's group at
        A + 5/10 = A + 0.5, before the next subview B. A depth / 5 fraction
        would put it at A + 1.0, tied with B's group, where cB wins the
        other-side tie-break and the order swaps."""
        cons = """
    <constraint firstItem="D5" firstAttribute="top" secondItem="B" secondAttribute="top" id="cD"/>
    <constraint firstItem="B" firstAttribute="top" secondItem="A" secondAttribute="top" id="cB"/>"""
        self.assertEqual(order_of(SUBS_MAC_DEEP, cons, mac=True),
                         ["cD", "cB"])

    def test_mac_unknown_item_refused(self):
        """A macOS constraint naming an item with no frame names the
        constraint id and the item."""
        cons = """
    <constraint firstItem="ZZ" firstAttribute="top" secondItem="B" secondAttribute="top" id="cZZ"/>"""
        with self.assertRaises(ibtool.XibError) as cm:
            order_of(SUBS_MAC, cons, mac=True)
        self.assertEqual(str(cm.exception),
                         "constraint cZZ: no frame for item 'ZZ'; "
                         "Apple's order unknown (t)")

    def compile_variant(self, old, new):
        self.assertEqual(BASE.count(old), 1, f"anchor not unique: {old}")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "VarMod")
            src.mkdir()
            (src / "Variant.xib").write_text(BASE.replace(old, new))
            out = Path(tmp, "out")
            p = subprocess.run([sys.executable, str(IBTOOL), *FLAGS,
                                "--compile", str(out / "o.nib"),
                                str(src / "Variant.xib")],
                               capture_output=True, text=True, timeout=280)
            return p.returncode, p.stderr

    def assert_refused(self, old, new, message):
        rc, err = self.compile_variant(old, new)
        self.assertNotEqual(rc, 0)
        self.assertIn(ref(message), err)

    def test_owner_side_unknown_attribute_refused(self):
        """A constraint to the owner view on an attribute outside the owner
        order refuses (attr-top cell, top to the owner changed to left)."""
        self.assert_refused(
            '<constraint firstItem="TRx-RV-za8" firstAttribute="top" secondItem="FzD-t2-JGy" secondAttribute="top" constant="14" id="cze-hi-8Uh"/>',
            '<constraint firstItem="TRx-RV-za8" firstAttribute="left" secondItem="FzD-t2-JGy" secondAttribute="top" constant="14" id="cze-hi-8Uh"/>',
            "constraint cze-hi-8Uh: left/top to the owner view; "
            "Apple's order unknown (Variant.xib object #2)")

    def test_unknown_attribute_pair_refused(self):
        """A subview-to-subview constraint on an attribute outside the iOS
        order refuses."""
        self.assert_refused(
            '<constraint firstItem="TRx-RV-za8" firstAttribute="top" secondItem="yiw-9t-gil" secondAttribute="trailing" constant="8" symbolic="YES" id="RUN-Ol-xSl"/>',
            '<constraint firstItem="TRx-RV-za8" firstAttribute="baseline" secondItem="yiw-9t-gil" secondAttribute="trailing" constant="8" symbolic="YES" id="RUN-Ol-xSl"/>',
            "constraint RUN-Ol-xSl: attribute baseline/trailing; "
            "Apple's order unknown (Variant.xib object #2)")


if __name__ == "__main__":
    unittest.main()
