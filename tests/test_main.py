import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import build_pinout, generate_template_csv, load_pins_csv
from Pin import Pin


class TestMainModule(unittest.TestCase):

    def setUp(self):
        self.config = {
            "function": [
                {"name": "Power", "color": "#E83131"},
                {"name": "Ground", "color": "#363A44"},
                {"name": "UART", "color": "#9D89CE"},
                {"name": "GPIO/PWM", "color": "#7AC943"},
                {"name": "I2C", "color": "#439ED6"},
            ]
        }

    def test_load_pins_csv_single_and_multi(self):
        tmp_csv = tempfile.NamedTemporaryFile(mode='w', newline='', suffix='.csv', delete=False, encoding='utf-8')
        try:
            writer = csv.writer(tmp_csv)
            writer.writerow(['number', 'label', 'function', 'side'])
            writer.writerow(['1', 'VCC', 'Power', 'left'])
            writer.writerow(['2', 'GND', 'Ground', 'left'])
            writer.writerow(['3', 'TX', 'UART', 'right'])
            writer.writerow(['3', 'GPIO5', 'GPIO/PWM', 'right'])
            tmp_csv.close()

            pins_data = load_pins_csv(tmp_csv.name, self.config)
            self.assertEqual(len(pins_data), 3)
            self.assertEqual(pins_data[1]['side'], 'left')
            self.assertEqual(len(pins_data[1]['functions']), 1)
            self.assertEqual(pins_data[1]['functions'][0]['name'], 'VCC')
            self.assertEqual(pins_data[1]['functions'][0]['color'], '#E83131')

            # Pin 3 has 2 functions
            self.assertEqual(len(pins_data[3]['functions']), 2)
            self.assertEqual(pins_data[3]['functions'][0]['name'], 'TX')
            self.assertEqual(pins_data[3]['functions'][1]['name'], 'GPIO5')
        finally:
            if os.path.isfile(tmp_csv.name):
                os.unlink(tmp_csv.name)

    def test_generate_template_csv(self):
        tmp_out = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        tmp_out.close()
        try:
            pins = [
                Pin(cx=5, cy=10, number=1, side='left'),
                Pin(cx=25, cy=10, number=2, side='right'),
            ]
            generate_template_csv(pins, output_path=tmp_out.name, config=self.config)
            self.assertTrue(os.path.isfile(tmp_out.name))
            with open(tmp_out.name, 'r', encoding='utf-8') as f:
                reader = list(csv.reader(f))
                self.assertEqual(reader[0], ['number', 'label', 'function', 'side'])
                self.assertEqual(reader[1][0], '1')
                self.assertEqual(reader[1][3], 'left')
                self.assertEqual(reader[2][0], '2')
                self.assertEqual(reader[2][3], 'right')
        finally:
            if os.path.isfile(tmp_out.name):
                os.unlink(tmp_out.name)

    def test_end_to_end_example_build(self):
        input_svg = os.path.join('examples', 'br_micro_sensor-F_Mask.svg')
        board_img = os.path.join('examples', 'br_micro_sensor_top_view.png')
        if not (os.path.isfile(input_svg) and os.path.isfile(board_img)):
            self.skipTest("Example files not present")

        tmp_out = tempfile.NamedTemporaryFile(suffix='.svg', delete=False)
        tmp_out.close()

        try:
            pins_data = {
                1: {'functions': [{'name': 'VCC', 'color': '#E83131'}], 'side': 'left'},
                2: {'functions': [{'name': 'GND', 'color': '#363A44'}], 'side': 'left'},
            }
            detected = build_pinout(input_svg, board_img, tmp_out.name, pins_data, export_png=False)
            self.assertGreater(len(detected), 0)
            self.assertTrue(os.path.isfile(tmp_out.name))
            self.assertGreater(os.path.getsize(tmp_out.name), 0)
        finally:
            if os.path.isfile(tmp_out.name):
                os.unlink(tmp_out.name)


if __name__ == '__main__':
    unittest.main()
