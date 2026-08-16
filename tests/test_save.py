import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

import save


class TestSaveModule(unittest.TestCase):

    def test_get_default_config_path(self):
        pcb = r"C:\path\to\my_board.kicad_pcb"
        self.assertEqual(save.get_default_config_path(pcb), r"C:\path\to\my_board_pinout_config.json")
        svg = r"/home/user/board.svg"
        self.assertEqual(save.get_default_config_path(svg), r"/home/user/board_pinout_config.json")
        self.assertIsNone(save.get_default_config_path(""))

    def test_save_and_load_pinout_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_file = os.path.join(tmp_dir, "test_pinout_config.json")
            data = {
                "version": "1.0",
                "selected_footprint": "J1",
                "output_path": "out.svg",
                "pins": [
                    {
                        "number": 1,
                        "x": 10.0,
                        "y": 20.0,
                        "side": "right",
                        "label": "VCC",
                        "function": "Power",
                        "show": True,
                        "pad_name": "1",
                        "footprint": "J1"
                    }
                ]
            }
            save.save_pinout_config(cfg_file, data)
            self.assertTrue(os.path.isfile(cfg_file))

            loaded = save.load_pinout_config(cfg_file)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["selected_footprint"], "J1")
            self.assertEqual(len(loaded["pins"]), 1)
            self.assertEqual(loaded["pins"][0]["label"], "VCC")

    def test_load_nonexistent_config(self):
        self.assertIsNone(save.load_pinout_config("nonexistent_path_xyz.json"))


if __name__ == '__main__':
    unittest.main()
