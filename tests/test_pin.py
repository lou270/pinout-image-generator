import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

from Pin import Pin


class TestPin(unittest.TestCase):

    def test_pin_init_defaults(self):
        pin = Pin(cx=10, cy=20)
        self.assertEqual(pin.cx, 10.0)
        self.assertEqual(pin.cy, 20.0)
        self.assertEqual(pin.r, 0.85)
        self.assertEqual(pin.number, 1)
        self.assertEqual(pin.side, 'left')
        self.assertTrue(pin.displayed)
        self.assertEqual(len(pin.functions), 0)

    def test_pin_add_function(self):
        pin = Pin(cx=5, cy=5, number=2, side='right')
        pin.add_function("VCC", "#FF0000")
        pin.add_function("3V3", "#00FF00")
        self.assertEqual(len(pin.functions), 2)
        self.assertEqual(pin.functions[0]['name'], "VCC")
        self.assertEqual(pin.functions[0]['color'], "#FF0000")
        self.assertEqual(pin.functions[1]['name'], "3V3")
        self.assertEqual(pin.functions[1]['color'], "#00FF00")

    def test_pin_repr(self):
        pin = Pin(cx=12.34, cy=56.78, number=4, side='top')
        repr_str = repr(pin)
        self.assertIn("#4", repr_str)
        self.assertIn("12.34", repr_str)
        self.assertIn("top", repr_str)


if __name__ == '__main__':
    unittest.main()
