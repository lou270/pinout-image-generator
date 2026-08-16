########################################
# Pinout image builder — KiCad wx dialog
# Louis Barbier
# MIT License
########################################
"""wxPython dialog for reviewing/editing detected pins before rendering.

Grid columns: #, X (mm), Y (mm), Side, Label, Function, Show.
Features:
  - Automatic loading of existing *_pinout_config.json configurations.
  - Automatic saving of configuration upon clicking 'Generate'.
  - Manual 'Save Config…' and 'Load Config…' buttons.
  - Footprint / connector filtering dropdown.
  - Multi-function definitions (comma-separated or stacked rows).
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
                 function_names, default_output, board=None, config_path=None):
        if not wx:
            raise RuntimeError("wxPython is required to display PinoutDialog")

        super().__init__(parent, title='Pinout Image Generator', size=(900, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self._board          = board
        self._function_names = list(function_names)
        self._svg_size_mm    = svg_size_mm
        self._board_image    = board_image_path
        self._meta           = dict(meta) if meta else {}

        # Default configuration path
        if config_path:
            self._config_path = config_path
        elif self._board and hasattr(self._board, 'GetFileName') and self._board.GetFileName():
            self._config_path = save_mod.get_default_config_path(self._board.GetFileName())
        elif default_output:
            self._config_path = save_mod.get_default_config_path(default_output)
        else:
            self._config_path = None

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

        # ── Header instructions & status ──────────────────────────────────────
        header_sizer = wx.BoxSizer(wx.VERTICAL)
        help_text = wx.StaticText(
            panel,
            label='Tip: Multiple functions on a pin can be entered separated by commas '
                  '(e.g. Label: "TX, GPIO5" | Function: "UART, GPIO/PWM") or on separate rows.'
        )
        help_text.SetForegroundColour(wx.Colour(100, 100, 100))
        header_sizer.Add(help_text, 0, wx.BOTTOM, 2)

        self.status_lbl = wx.StaticText(panel, label='')
        self.status_lbl.SetForegroundColour(wx.Colour(0, 120, 200))
        header_sizer.Add(self.status_lbl, 0)
        sizer.Add(header_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

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

        # ── Row & Config buttons ──────────────────────────────────────────────
        row_btns = wx.BoxSizer(wx.HORIZONTAL)
        add_btn  = wx.Button(panel, label='Add pin')
        rm_btn   = wx.Button(panel, label='Remove selected')
        load_btn = wx.Button(panel, label='Load Config…')
        save_btn = wx.Button(panel, label='Save Config…')

        add_btn.Bind(wx.EVT_BUTTON, self._on_add)
        rm_btn .Bind(wx.EVT_BUTTON, self._on_remove)
        load_btn.Bind(wx.EVT_BUTTON, self._on_load_config_btn)
        save_btn.Bind(wx.EVT_BUTTON, self._on_save_config_btn)

        row_btns.Add(add_btn, 0, wx.RIGHT, 6)
        row_btns.Add(rm_btn,  0, wx.RIGHT, 12)
        row_btns.AddStretchSpacer()
        row_btns.Add(load_btn, 0, wx.RIGHT, 6)
        row_btns.Add(save_btn, 0)
        sizer.Add(row_btns, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

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

        # ── Automatic config load on startup ──────────────────────────────────
        if self._config_path and os.path.isfile(self._config_path):
            self.load_config_file(self._config_path, silent=True)

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
        self._meta = dict(meta)
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

    def _append_row(self, number=0, x=0.0, y=0.0, side='left', label='', function='', show=True):
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
        self.grid.SetCellValue(row, 6, '1' if show else '0')
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

    # ── Configuration persistence ─────────────────────────────────────────────

    def export_config_dict(self):
        """Export current dialog state into a JSON-serializable dictionary."""
        pins_data = []
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

            meta_info = self._meta.get(number, {})
            pins_data.append({
                'number':    number,
                'x':         round(x, 3),
                'y':         round(y, 3),
                'side':      side,
                'label':     label,
                'function':  func,
                'show':      show,
                'pad_name':  meta_info.get('pad_name', str(number)),
                'footprint': meta_info.get('footprint', ''),
            })

        sel_fp = None
        if hasattr(self, 'fp_choice') and self.fp_choice.GetSelection() >= 0:
            _, sel_fp = self._fp_items[self.fp_choice.GetSelection()]

        return {
            'version':            '1.0',
            'selected_footprint': sel_fp,
            'output_path':        self.out_ctrl.GetValue().strip(),
            'pins':               pins_data,
        }

    def apply_config_dict(self, cfg):
        """Apply a saved configuration dictionary to the dialog controls and grid."""
        if not isinstance(cfg, dict) or 'pins' not in cfg:
            return False

        # Restore selected footprint if available
        saved_fp = cfg.get('selected_footprint')
        if saved_fp and hasattr(self, 'fp_choice'):
            for idx, (_, ref) in enumerate(self._fp_items):
                if ref == saved_fp:
                    self.fp_choice.SetSelection(idx)
                    pins, meta, _ = board_parser.parse_board(self._board, footprint_ref=saved_fp)
                    self._meta = dict(meta)
                    self._populate_grid(pins, meta)
                    break

        # Restore output path
        if cfg.get('output_path'):
            self.out_ctrl.SetValue(cfg['output_path'])

        saved_pins = cfg.get('pins', [])
        if not saved_pins:
            return True

        # Build lookup table from current grid rows
        # Primary key: (footprint, pad_name), fallback: number or (x, y)
        current_rows = {}
        for row in range(self.grid.GetNumberRows()):
            try:
                num = int(self.grid.GetCellValue(row, 0).strip())
                gx = round(float(self.grid.GetCellValue(row, 1).strip() or 0), 2)
                gy = round(float(self.grid.GetCellValue(row, 2).strip() or 0), 2)
            except ValueError:
                continue
            meta_info = self._meta.get(num, {})
            fp = meta_info.get('footprint', '')
            pad = meta_info.get('pad_name', str(num))
            current_rows[(fp, pad)] = row
            current_rows[num] = row
            current_rows[(gx, gy)] = row

        # Apply saved configurations to matching rows or append new ones
        applied_rows = set()
        for p in saved_pins:
            num = p.get('number', 0)
            px = round(float(p.get('x', 0)), 2)
            py = round(float(p.get('y', 0)), 2)
            fp = p.get('footprint', '')
            pad = p.get('pad_name', str(num))

            target_row = current_rows.get((fp, pad))
            if target_row is None:
                target_row = current_rows.get(num)
            if target_row is None:
                target_row = current_rows.get((px, py))

            if target_row is not None and target_row not in applied_rows:
                self.grid.SetCellValue(target_row, 3, p.get('side', 'left'))
                self.grid.SetCellValue(target_row, 4, p.get('label', ''))
                self.grid.SetCellValue(target_row, 5, p.get('function', ''))
                self.grid.SetCellValue(target_row, 6, '1' if p.get('show', True) else '0')
                applied_rows.add(target_row)
            else:
                # Additional row (e.g. multi-function stacked row)
                self._append_row(
                    number=num,
                    x=p.get('x', 0.0),
                    y=p.get('y', 0.0),
                    side=p.get('side', 'left'),
                    label=p.get('label', ''),
                    function=p.get('function', ''),
                    show=p.get('show', True),
                )

        return True

    def save_config_file(self, path=None):
        """Save current configuration to JSON."""
        save_path = path or self._config_path
        if not save_path:
            return False
        cfg = self.export_config_dict()
        save_mod.save_pinout_config(save_path, cfg)
        self._config_path = save_path
        self.status_lbl.SetLabel(f"Config saved to: {os.path.basename(save_path)}")
        return True

    def load_config_file(self, path, silent=False):
        """Load configuration from JSON file."""
        cfg = save_mod.load_pinout_config(path)
        if cfg and self.apply_config_dict(cfg):
            self._config_path = path
            self.status_lbl.SetLabel(f"Auto-resumed config: {os.path.basename(path)}")
            if not silent:
                wx.MessageBox(f'Configuration loaded from:\n{path}',
                              'Pinout Image Generator', wx.OK | wx.ICON_INFORMATION)
            return True
        return False

    def _on_save_config_btn(self, _event):
        default_dir = os.path.dirname(self._config_path) if self._config_path else ''
        default_file = os.path.basename(self._config_path) if self._config_path else 'pinout_config.json'
        with wx.FileDialog(self, 'Save pinout configuration',
                           defaultDir=default_dir, defaultFile=default_file,
                           wildcard='JSON files (*.json)|*.json',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                if self.save_config_file(path):
                    wx.MessageBox(f'Configuration saved to:\n{path}',
                                  'Pinout Image Generator', wx.OK | wx.ICON_INFORMATION)

    def _on_load_config_btn(self, _event):
        default_dir = os.path.dirname(self._config_path) if self._config_path else ''
        with wx.FileDialog(self, 'Load pinout configuration',
                           defaultDir=default_dir,
                           wildcard='JSON files (*.json)|*.json',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.load_config_file(dlg.GetPath(), silent=False)

    # ── Result ────────────────────────────────────────────────────────────────

    def collect(self, function_color_map):
        """Read the grid, auto-save config, and return (pins, svg_size_mm, output_path)."""
        # Automatically save configuration alongside the board / output
        try:
            self.save_config_file()
        except Exception:
            pass

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
