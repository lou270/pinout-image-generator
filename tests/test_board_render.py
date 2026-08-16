import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'plugins'))

from board_render import find_kicad_cli, render_top_view


class TestBoardRender(unittest.TestCase):

    def test_find_kicad_cli(self):
        # find_kicad_cli may return a string path if KiCad is installed, or None if not
        cli_path = find_kicad_cli()
        if cli_path is not None:
            self.assertTrue(os.path.isfile(cli_path))
            self.assertTrue('kicad-cli' in os.path.basename(cli_path).lower())

    def test_render_top_view_no_board(self):
        # When board is None and pcbnew is not active, render_top_view safely returns None
        result = render_top_view(None)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
