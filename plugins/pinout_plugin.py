########################################
# Pinout image builder — KiCad ActionPlugin
# Louis Barbier
# MIT License
########################################
"""Registers a KiCad ActionPlugin that generates an annotated pinout SVG
from the currently-open board."""

import os
import traceback
import webbrowser

try:
    import pcbnew
    import wx
except ImportError:
    pcbnew = None
    wx = None

import board_parser
import board_render
import dialog
from function import render_pinout


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH  = os.path.join(os.path.dirname(PLUGIN_DIR), 'resources', 'icon.png')
if not os.path.isfile(ICON_PATH):
    ICON_PATH = os.path.join(PLUGIN_DIR, 'resources', 'icon.png')
CONFIG_PATH = os.path.join(PLUGIN_DIR, 'config.json')


class PinoutPlugin(pcbnew.ActionPlugin if pcbnew else object):

    def defaults(self):
        self.name        = 'Pinout Maker'
        self.category    = 'Documentation'
        self.description = 'Generate an annotated pinout SVG from the active board.'
        self.show_toolbar_button = True
        self.icon_file_name      = ICON_PATH if os.path.isfile(ICON_PATH) else ''

    def Run(self):
        try:
            self._run()
        except Exception as exc:
            if wx:
                wx.MessageBox(
                    f'{exc}\n\n{traceback.format_exc()}',
                    'Pinout Maker — error',
                    wx.OK | wx.ICON_ERROR,
                )
            else:
                raise

    def _run(self):
        if pcbnew is None or wx is None:
            raise RuntimeError("pcbnew and wx are required inside KiCad.")

        board = pcbnew.GetBoard()
        if board is None:
            wx.MessageBox('No board open.', 'Pinout Maker', wx.OK | wx.ICON_WARNING)
            return

        # Extract pads + nets.
        pins, meta, svg_size_mm = board_parser.parse_board(board)
        if not pins:
            pins = []
            meta = {}

        # Render top-view PNG (with transparent background)
        board_image = board_render.render_top_view(board)
        if board_image is None:
            with wx.FileDialog(None,
                               'Select a top-view PNG/JPG of the board',
                               wildcard='Images (*.png;*.jpg;*.jpeg;*.bmp)|*.png;*.jpg;*.jpeg;*.bmp',
                               style=wx.FD_OPEN) as dlg:
                if dlg.ShowModal() == wx.ID_OK:
                    board_image = dlg.GetPath()

        # Output path = alongside the board file by default.
        board_path = board.GetFileName() or ''
        default_out = os.path.splitext(board_path)[0] + '_pinout.svg' \
                      if board_path else os.path.join(os.path.expanduser('~'), 'pinout.svg')

        # Function names from config.json.
        color_map = dialog.function_color_map(CONFIG_PATH)
        function_names = list(color_map.keys())

        # Show the edit dialog.
        dlg = dialog.PinoutDialog(None, pins, meta, svg_size_mm,
                                  board_image, function_names, default_out)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        final_pins, size, out_path = dlg.collect(color_map)
        dlg.Destroy()

        if not final_pins:
            wx.MessageBox('No pins to render.', 'Pinout Maker',
                          wx.OK | wx.ICON_WARNING)
            return
        if not out_path:
            wx.MessageBox('No output path set.', 'Pinout Maker',
                          wx.OK | wx.ICON_WARNING)
            return

        render_pinout(final_pins, board_image, size, out_path)

        if wx.MessageBox(f'Generated:\n{out_path}\n\nOpen in browser?',
                         'Pinout Maker', wx.YES_NO | wx.ICON_INFORMATION) == wx.YES:
            from pathlib import Path
            webbrowser.open(Path(os.path.abspath(out_path)).as_uri())
