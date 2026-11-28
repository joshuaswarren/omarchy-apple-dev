import importlib.util
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "keyorder.py"
_spec = importlib.util.spec_from_file_location("keyorder", TOOL)
ko = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ko)

OBJREF = 10


class V:
    def __init__(self, key_idx, type=0, payload=None):
        self.key_idx, self.type, self.payload = key_idx, type, payload


class Arch:
    def __init__(self, objects, keys, classes):
        self.objects, self.keys, self.classes = objects, keys, classes

    def object_class(self, i):
        return self.classes[i]

    def object_values(self, obj):
        return obj

    def key(self, idx):
        return self.keys[idx]


class FirstUseOrder(unittest.TestCase):
    def test_dfs_through_object_refs_then_table_order(self):
        arch = Arch(
            [[V(0), V(1, OBJREF, 1)], [V(2)], [V(3)]],
            ["a", "b", "c", "d"],
            {0: "A", 1: "B", 2: "C"})
        # obj2 is unreferenced: table order, after the DFS
        self.assertEqual(ko.first_use_order(arch), ["a", "b", "c", "d"])

    def test_reference_cycle_visits_once(self):
        arch = Arch(
            [[V(0, OBJREF, 1)], [V(1, OBJREF, 0)]],
            ["a", "b"],
            {0: "A", 1: "B"})
        self.assertEqual(ko.first_use_order(arch), ["a", "b"])

    def test_navitem_does_not_pull_in_navbar_early(self):
        # controller -> item -> bar, plus a third unreferenced object.
        # Without the exception the bar's key would land before "z".
        arch = Arch(
            [[V(0), V(1, OBJREF, 1)],
             [V(2, OBJREF, 3)],
             [V(3)],
             [V(4)]],
            ["vc", "item", "bar", "z", "barkey"],
            {0: "UIViewController", 1: "UINavigationItem",
             2: "X", 3: "UINavigationBar"})
        # "bar" is emitted at the item's ref site, but the bar's own keys
        # ("barkey") wait for table order, after "z". Without the
        # UINavigationItem exception they would come before "z".
        self.assertEqual(ko.first_use_order(arch),
                         ["vc", "item", "bar", "z", "barkey"])


if __name__ == "__main__":
    unittest.main()
