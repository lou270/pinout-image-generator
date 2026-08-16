import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

from dialog import function_color_map, PinoutDialog
from Pin import Pin


class MockGrid:
    def __init__(self, rows):
        self._rows = rows

    def GetNumberRows(self):
        return len(self._rows)

    def GetCellValue(self, row, col):
        return self._rows[row][col]


class MockTextCtrl:
    def __init__(self, value):
        self._value = value

    def GetValue(self):
        return self._value


class TestDialogModule(unittest.TestCase):

    def test_function_color_map(self):
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins', 'config.json')
        cmap = function_color_map(cfg_path)
        self.assertIsInstance(cmap, dict)
        self.assertIn("Power", cmap)
        self.assertIn("Ground", cmap)
        self.assertIn("UART", cmap)

    def test_dialog_collect_multi_functions(self):
        # Create a mock dialog instance to test collect() without wx UI display
        dlg = object.__new__(PinoutDialog)
        dlg._svg_size_mm = (100.0, 100.0)
        dlg.out_ctrl = MockTextCtrl("/path/to/output.svg")

        # Columns: #, X (mm), Y (mm), Side, Label, Function, Show
        dlg.grid = MockGrid([
            ['1', '10.0', '20.0', 'left', 'VCC', 'Power', '1'],
            ['2', '10.0', '30.0', 'left', 'TX, GPIO5', 'UART, GPIO/PWM', '1'],
            ['3', '90.0', '20.0', 'right', 'SDA', 'I2C', '1'],
            ['3', '90.0', '20.0', 'right', 'ADC1', 'ADC', '1'],  # Duplicate row for multi-function
            ['4', '90.0', '30.0', 'right', 'NC', '', '0'],        # Hidden row
        ])

        cmap = {
            'Power': '#E83131',
            'Ground': '#363A44',
            'UART': '#9D89CE',
            'GPIO/PWM': '#7AC943',
            'I2C': '#439ED6',
            'ADC': '#427F21',
        }

        pins, size_mm, out_path = PinoutDialog.collect(dlg, cmap)

        self.assertEqual(len(pins), 3)  # Pin 1, 2, 3 (Pin 4 was hidden)
        self.assertEqual(size_mm, (100.0, 100.0))
        self.assertEqual(out_path, "/path/to/output.svg")

        # Pin 1: single function
        self.assertEqual(pins[0].number, 1)
        self.assertEqual(len(pins[0].functions), 1)
        self.assertEqual(pins[0].functions[0]['name'], 'VCC')

        # Pin 2: comma-separated multi-functions
        self.assertEqual(pins[1].number, 2)
        self.assertEqual(len(pins[1].functions), 2)
        self.assertEqual(pins[1].functions[0]['name'], 'TX')
        self.assertEqual(pins[1].functions[0]['color'], '#9D89CE')
        self.assertEqual(pins[1].functions[1]['name'], 'GPIO5')
        self.assertEqual(pins[1].functions[1]['color'], '#7AC943')

        # Pin 3: stacked rows multi-functions
        self.assertEqual(pins[2].number, 3)
        self.assertEqual(len(pins[2].functions), 2)
        self.assertEqual(pins[2].functions[0]['name'], 'SDA')
        self.assertEqual(pins[2].functions[0]['color'], '#439ED6')
        self.assertEqual(pins[2].functions[1]['name'], 'ADC1')
        self.assertEqual(pins[2].functions[1]['color'], '#427F21')

    def test_dialog_export_and_apply_config(self):
        dlg = object.__new__(PinoutDialog)
        dlg.out_ctrl = MockTextCtrl("/path/to/output.svg")
        dlg._meta = {
            1: {'pad_name': '1', 'footprint': 'J1'},
            2: {'pad_name': '2', 'footprint': 'J1'},
        }
        dlg.grid = MockGrid([
            ['1', '10.0', '20.0', 'left', 'VCC', 'Power', '1'],
            ['2', '10.0', '30.0', 'left', 'GND', 'Ground', '1'],
        ])

        exported = PinoutDialog.export_config_dict(dlg)
        self.assertEqual(exported['output_path'], "/path/to/output.svg")
        self.assertEqual(len(exported['pins']), 2)
        self.assertEqual(exported['pins'][0]['label'], 'VCC')
        self.assertEqual(exported['pins'][0]['pad_name'], '1')
        self.assertEqual(exported['pins'][0]['footprint'], 'J1')


if __name__ == '__main__':
    unittest.main()

