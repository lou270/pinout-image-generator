import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

from board_parser import (
    DEFAULT_CONNECTOR_PATTERN,
    _detect_side,
    _pad_radius_mm,
    _to_mm,
    load_netclass_map,
    match_function,
    parse_board,
    parse_footprint,
)


class MockVector:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class MockPad:
    def __init__(self, x_nm, y_nm, size_x_nm=1700000, size_y_nm=1700000, name="1", net_name="VCC", net_class="Power"):
        self.pos = MockVector(x_nm, y_nm)
        self.size = MockVector(size_x_nm, size_y_nm)
        self._name = name
        self._net_name = net_name
        self._net_class = net_class

    def GetPosition(self):
        return self.pos

    def GetSize(self):
        return self.size

    def GetName(self):
        return self._name

    def GetNet(self):
        return bool(self._net_name)

    def GetNetname(self):
        return self._net_name

    def GetNetClassName(self):
        return self._net_class


class MockFootprint:
    def __init__(self, ref, pads):
        self._ref = ref
        self._pads = pads

    def GetReference(self):
        return self._ref

    def Pads(self):
        return self._pads


class MockBoundingBox:
    def __init__(self, x_nm, y_nm, w_nm, h_nm):
        self._x = x_nm
        self._y = y_nm
        self._w = w_nm
        self._h = h_nm

    def GetX(self): return self._x
    def GetY(self): return self._y
    def GetWidth(self): return self._w
    def GetHeight(self): return self._h


class MockBoard:
    def __init__(self, footprints, bbox_nm=(0, 0, 50000000, 30000000)):
        self._footprints = footprints
        self._bbox = MockBoundingBox(*bbox_nm)

    def GetFootprints(self):
        return self._footprints

    def GetBoardEdgesBoundingBox(self):
        return self._bbox


class TestBoardParser(unittest.TestCase):

    def test_to_mm(self):
        self.assertAlmostEqual(_to_mm(1000000), 1.0)
        self.assertAlmostEqual(_to_mm(2540000), 2.54)

    def test_load_netclass_map(self):
        rules = load_netclass_map()
        self.assertIsInstance(rules, list)
        self.assertGreater(len(rules), 0)

    def test_match_function(self):
        rules = [
            {"pattern": "^Power$", "function": "Power"},
            {"pattern": "^VCC.*", "function": "Power"},
            {"pattern": "^GND$", "function": "Ground"},
            {"pattern": "^(TX|RX)D?\\b.*", "function": "UART"},
            {"pattern": "^(SDA|SCL)\\b.*", "function": "I2C"},
        ]
        self.assertEqual(match_function("VCC", "", rules), "Power")
        self.assertEqual(match_function("+3V3", "Power", rules), "Power")
        self.assertEqual(match_function("GND", "", rules), "Ground")
        self.assertEqual(match_function("TXD", "", rules), "UART")
        self.assertEqual(match_function("SDA", "", rules), "I2C")
        self.assertEqual(match_function("UNKNOWN_SIG", "", rules), "")

    def test_detect_side(self):
        bbox_mm = (0, 0, 100, 100)
        self.assertEqual(_detect_side(5, 50, bbox_mm), 'left')
        self.assertEqual(_detect_side(95, 50, bbox_mm), 'right')
        self.assertEqual(_detect_side(50, 5, bbox_mm), 'top')
        self.assertEqual(_detect_side(50, 95, bbox_mm), 'bottom')

    def test_parse_footprint_and_board(self):
        pads = [
            MockPad(2000000, 5000000, name="1", net_name="VCC", net_class="Power"),
            MockPad(2000000, 15000000, name="2", net_name="GND", net_class="Ground"),
            MockPad(48000000, 5000000, name="3", net_name="TX", net_class="Signal"),
        ]
        fp1 = MockFootprint("J1", pads)
        fp2 = MockFootprint("HDR_EXP1", [
            MockPad(25000000, 2000000, name="1", net_name="SDA", net_class="I2C")
        ])
        board = MockBoard([fp1, fp2])

        # Test parsing single footprint
        pins, meta = parse_footprint(fp1, board)
        self.assertEqual(len(pins), 3)
        self.assertEqual(meta[1]['net_name'], "VCC")
        self.assertEqual(meta[1]['suggested_function'], "Power")
        self.assertEqual(meta[2]['suggested_function'], "Ground")

        # Test parsing board with candidate connector regex
        all_pins, all_meta, size_mm = parse_board(board, pattern=DEFAULT_CONNECTOR_PATTERN)
        self.assertEqual(len(all_pins), 4)
        self.assertAlmostEqual(size_mm[0], 50.0)
        self.assertAlmostEqual(size_mm[1], 30.0)

    def test_dnp_footprints(self):
        pads = [MockPad(2000000, 5000000, name="1", net_name="VCC", net_class="Power")]
        fp_active = MockFootprint("J1", pads)
        fp_dnp = MockFootprint("J2", pads)
        fp_dnp.IsDNP = lambda: True

        board = MockBoard([fp_active, fp_dnp])
        pins, meta, _ = parse_board(board, pattern=DEFAULT_CONNECTOR_PATTERN, include_dnp=False)
        self.assertEqual(len(pins), 1)
        self.assertEqual(meta[1]['footprint'], "J1")

        pins_with_dnp, _, _ = parse_board(board, pattern=DEFAULT_CONNECTOR_PATTERN, include_dnp=True)
        self.assertEqual(len(pins_with_dnp), 2)


if __name__ == '__main__':
    unittest.main()

