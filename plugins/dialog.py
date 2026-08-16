########################################
# Pinout image builder — KiCad wx dialog
# Louis Barbier
# MIT License
########################################
"""wxPython dialog for reviewing/editing detected pins before rendering.

Grid columns: #, X (mm), Y (mm), Side, Label, Function, Show.
Users can filter by footprint, add / remove rows, edit any cell,
define multiple functions per pin (via comma separation or stacked rows),
and choose the output path.
"""

import json
import os

try:
    import wx
    import wx.grid
except ImportError:
    wx = None

import board_parser
import save as save_mod
from Pin import Pin


COLS = ('#', 'X (mm)', 'Y (mm)', 'Side', 'Label', 'Function', 'Show')


class PinoutDialog(wx.Dialog if wx else object):

    def __init__(self, parent, pins, meta, svg_size_mm, board_image_path,
                 function_names, default_output, board=None):
        if not wx:
            raise RuntimeError("wxPython is required to display PinoutDialog")

        super().__init__(parent, title='Pinout Image Generator', size=(880, 580),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self._board          = board
        self._function_names = list(function_names)
        self._svg_size_mm    = svg_size_mm
        self._board_image    = board_image_path

        panel   = wx.Panel(self)
        sizer   = wx.BoxSizer(wx.VERTICAL)

        # ── Footprint / Connector selector ────────────────────────────────────
        if self._board is not None:
            fp_sizer = wx.BoxSizer(wx.HORIZONTAL)
            fp_sizer.Add(wx.StaticText(panel, label='Target Connector / Footprint:'),
                         0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

            self.fp_choice = wx.Choice(panel)
            self._fp_items = self._populate_footprint_choices()
            for label, _ in self._fp_items:
                self.fp_choice.Append(label)
            if self.fp_choice.GetCount() > 0:
                self.fp_choice.SetSelection(0)
            self.fp_choice.Bind(wx.EVT_CHOICE, self._on_footprint_changed)

            fp_sizer.Add(self.fp_choice, 1, wx.EXPAND | wx.RIGHT, 6)
            sizer.Add(fp_sizer, 0, wx.EXPAND | wx.ALL, 6)

        # ── Header instructions ───────────────────────────────────────────────
        help_text = wx.StaticText(
            panel,
            label='Tip: Multiple functions on a pin can be entered separated by commas '
                  '(e.g. Label: "TX, GPIO5" | Function: "UART, GPIO/PWM") or on separate rows.'
        )
        help_text.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(help_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # ── Grid ──────────────────────────────────────────────────────────────
        self.grid = wx.grid.Grid(panel)
        self.grid.CreateGrid(0, len(COLS))
        for i, name in enumerate(COLS):
            self.grid.SetColLabelValue(i, name)
        self.grid.SetColSize(0, 45)
        self.grid.SetColSize(1, 80)
        self.grid.SetColSize(2, 80)
        self.grid.SetColSize(3, 70)
        self.grid.SetColSize(4, 170)
        self.grid.SetColSize(5, 170)
        self.grid.SetColSize(6, 50)

        self._populate_grid(pins, meta)

        sizer.Add(self.grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # ── Row buttons ───────────────────────────────────────────────────────
        row_btns = wx.BoxSizer(wx.HORIZONTAL)
        add_btn  = wx.Button(panel, label='Add pin')
        rm_btn   = wx.Button(panel, label='Remove selected')
        add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        rm_btn .Bind(wx.EVT_BUTTON, self._on_remove)
        row_btns.Add(add_btn, 0, wx.RIGHT, 6)
        row_btns.Add(rm_btn,  0)
        sizer.Add(row_btns, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        # ── Output path ───────────────────────────────────────────────────────
        out_row = wx.BoxSizer(wx.HORIZONTAL)
        out_row.Add(wx.StaticText(panel, label='Output SVG:'),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.out_ctrl = wx.TextCtrl(panel, value=default_output)
        browse_btn = wx.Button(panel, label='…', size=(28, -1))
        browse_btn.Bind(wx.EVT_BUTTON, self._on_browse)
        out_row.Add(self.out_ctrl, 1, wx.EXPAND | wx.RIGHT, 4)
        out_row.Add(browse_btn, 0)
        sizer.Add(out_row, 0, wx.EXPAND | wx.ALL, 6)

        # ── OK / Cancel ───────────────────────────────────────────────────────
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn     = wx.Button(panel, wx.ID_OK, 'Generate')
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, 'Cancel')
        btn_row.AddStretchSpacer()
        btn_row.Add(cancel_btn, 0, wx.RIGHT, 6)
        btn_row.Add(ok_btn, 0)
        sizer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 6)

        panel.SetSizer(sizer)

    # ── Footprint selection helpers ───────────────────────────────────────────

    def _populate_footprint_choices(self):
        """Return list of (display_label, ref_or_none)."""
        items = []
        try:
            info_list = board_parser.get_board_footprint_info(self._board)
        except Exception:
            info_list = []

        if not info_list:
            return [('All detected connectors', None)]

        # Connectors first
        conn_fps = [f for f in info_list if f['is_connector']]
        other_fps = [f for f in info_list if not f['is_connector']]

        items.append(('All detected connectors (excluding DNP)', None))
        for f in conn_fps:
            dnp_str = ' [DNP]' if f.get('dnp') else ''
            items.append((f"{f['ref']} ({f['pad_count']} pads){dnp_str}", f['ref']))
        for f in other_fps:
            dnp_str = ' [DNP]' if f.get('dnp') else ''
            items.append((f"{f['ref']} ({f['pad_count']} pads){dnp_str}", f['ref']))

        return items

    def _on_footprint_changed(self, _event):
        sel = self.fp_choice.GetSelection()
        if sel < 0 or sel >= len(self._fp_items):
            return
        _, target_ref = self._fp_items[sel]
        pins, meta, _ = board_parser.parse_board(self._board, footprint_ref=target_ref)
        self._populate_grid(pins, meta)

    # ── Grid helpers ──────────────────────────────────────────────────────────

    def _populate_grid(self, pins, meta):
        if self.grid.GetNumberRows() > 0:
            self.grid.DeleteRows(0, self.grid.GetNumberRows())

        for pin in pins:
            info = meta.get(pin.number, {})
            self._append_row(
                number=pin.number,
                x=pin.cx,
                y=pin.cy,
                side=pin.side,
                label=info.get('net_name', ''),
                function=info.get('suggested_function', ''),
            )

    def _append_row(self, number=0, x=0.0, y=0.0, side='left', label='', function=''):
        row = self.grid.GetNumberRows()
        self.grid.AppendRows(1)
        self.grid.SetCellValue(row, 0, str(number))
        self.grid.SetCellValue(row, 1, f'{x:.3f}')
        self.grid.SetCellValue(row, 2, f'{y:.3f}')
        self.grid.SetCellValue(row, 3, side)
        self.grid.SetCellEditor(row, 3, wx.grid.GridCellChoiceEditor(
            ['left', 'right', 'top', 'bottom'], allowOthers=False))
        self.grid.SetCellValue(row, 4, label)
        self.grid.SetCellValue(row, 5, function)
        self.grid.SetCellEditor(row, 5, wx.grid.GridCellChoiceEditor(
            [''] + self._function_names, allowOthers=True))
        self.grid.SetCellValue(row, 6, '1')
        self.grid.SetCellEditor(row, 6, wx.grid.GridCellBoolEditor())
        self.grid.SetCellRenderer(row, 6, wx.grid.GridCellBoolRenderer())

    def _on_add(self, _event):
        next_n = self.grid.GetNumberRows() + 1
        self._append_row(number=next_n)

    def _on_remove(self, _event):
        rows = sorted({b.GetTopRow() for b in self.grid.GetSelectedBlocks()}, reverse=True)
        if not rows:
            rows = [self.grid.GetGridCursorRow()] if self.grid.GetNumberRows() else []
        for r in rows:
            if 0 <= r < self.grid.GetNumberRows():
                self.grid.DeleteRows(r, 1)

    def _on_browse(self, _event):
        with wx.FileDialog(self, 'Save pinout SVG',
                            wildcard='SVG files (*.svg)|*.svg',
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.out_ctrl.SetValue(dlg.GetPath())

    # ── Result ────────────────────────────────────────────────────────────────

    def collect(self, function_color_map):
        """Read the grid and return (pins, svg_size_mm, output_path).
        
        Supports multiple functions per pin either via comma-separated entries
        or multiple rows with identical pin number / coordinates.
        """
        pins_by_key = {}
        pins_order = []

        for row in range(self.grid.GetNumberRows()):
            try:
                number = int(self.grid.GetCellValue(row, 0).strip())
                x      = float(self.grid.GetCellValue(row, 1).strip() or 0)
                y      = float(self.grid.GetCellValue(row, 2).strip() or 0)
            except ValueError:
                continue
            side  = self.grid.GetCellValue(row, 3).strip() or 'left'
            label = self.grid.GetCellValue(row, 4).strip()
            func  = self.grid.GetCellValue(row, 5).strip()
            show  = self.grid.GetCellValue(row, 6).strip() in ('1', 'True', 'true', 'TRUE')
            if not show:
                continue

            key = (number, round(x, 3), round(y, 3))
            if key not in pins_by_key:
                pin = Pin(cx=x, cy=y, r=0.85, number=number, side=side, displayed=True)
                pins_by_key[key] = pin
                pins_order.append(pin)
            else:
                pin = pins_by_key[key]

            # Parse single or comma-separated functions
            if label or func:
                labels = [lbl.strip() for lbl in label.split(',') if lbl.strip()] if ',' in label else ([label] if label else [])
                funcs  = [f.strip() for f in func.split(',') if f.strip()] if ',' in func else ([func] if func else [])
                count = max(len(labels), len(funcs), 1)

                for idx in range(count):
                    sub_lbl = labels[idx] if idx < len(labels) else (labels[0] if labels else '')
                    sub_func = funcs[idx] if idx < len(funcs) else (funcs[0] if funcs else '')
                    if sub_lbl or sub_func:
                        color = function_color_map.get(sub_func, '#888888')
                        pin.add_function(sub_lbl or sub_func or f'pin_{number}', color)

        return pins_order, self._svg_size_mm, self.out_ctrl.GetValue().strip()


def function_color_map(config_path):
    """Build {function_name: hex_color} from config.json."""
    if not os.path.isfile(config_path):
        return {}
    cfg = save_mod.from_json(config_path)
    return {f['name']: f['color'] for f in cfg.get('function', [])}
