########################################
# Pinout image builder — GUI
# Louis Barbier
# MIT License
########################################

import base64
import io
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
import xml.etree.ElementTree as ET
from PIL import Image, ImageTk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins'))

from function import detect_pin
from main import build_pinout, generate_template_csv, load_pins_csv
import save
from svg import extract_points_from_path


# ── FunctionEntry: one label + type dropdown row ──────────────────────────────

class FunctionEntry(tk.Frame):
    """One row: a label entry + a function-type dropdown, with a remove button."""

    def __init__(self, parent, func_names, func_colors, label='', function='', **kwargs):
        super().__init__(parent, **kwargs)
        self._func_names  = func_names
        self._func_colors = func_colors

        self.label_var    = tk.StringVar(value=label)
        self.function_var = tk.StringVar(value=function)

        tk.Entry(self, textvariable=self.label_var, width=14).pack(side='left', padx=2)

        combo = ttk.Combobox(self, textvariable=self.function_var,
                             values=func_names, width=14, state='readonly')
        combo.pack(side='left', padx=2)
        combo.bind('<<ComboboxSelected>>', self._on_func_change)

        self._color_swatch = tk.Label(self, width=2, bg=self._current_color())
        self._color_swatch.pack(side='left', padx=2)

        tk.Button(self, text='✕', width=2, command=self.destroy).pack(side='left')

    def _current_color(self):
        name = self.function_var.get()
        try:
            idx = self._func_names.index(name)
            return self._func_colors[idx]
        except ValueError:
            return '#cccccc'

    def _on_func_change(self, _event=None):
        self._color_swatch.config(bg=self._current_color())

    def get(self):
        """Return (label, function_name, color) or None if empty."""
        label = self.label_var.get().strip()
        func  = self.function_var.get().strip()
        if not label and not func:
            return None
        color = self._current_color()
        return label or func, func, color


# ── PinRow: one detected pin with expandable function entries ─────────────────

class PinRow(tk.Frame):
    """Expandable row for one detected pin."""

    def __init__(self, parent, pin_number, func_names, func_colors, side='left', on_focus_cb=None, **kwargs):
        super().__init__(parent, relief='ridge', bd=1, **kwargs)
        self.pin_number   = pin_number
        self._func_names  = func_names
        self._func_colors = func_colors
        self._on_focus_cb = on_focus_cb

        header = tk.Frame(self)
        header.pack(fill='x', padx=4, pady=2)

        tk.Label(header, text=f'Pin {pin_number}', width=6, anchor='w',
                 font=('Consolas', 9, 'bold')).pack(side='left')

        # Side selector
        self.side_var = tk.StringVar(value=side)
        side_combo = ttk.Combobox(header, textvariable=self.side_var,
                                  values=['left', 'right', 'top', 'bottom'],
                                  width=7, state='readonly')
        side_combo.pack(side='left', padx=4)

        tk.Button(header, text='+ Function', command=self._add_entry,
                  padx=4).pack(side='left', padx=4)

        self._container = tk.Frame(self)
        self._container.pack(fill='x', padx=4, pady=(0, 4))

        self.bind('<Button-1>', self._on_click)
        header.bind('<Button-1>', self._on_click)

    def _on_click(self, _event=None):
        if self._on_focus_cb:
            self._on_focus_cb(self.pin_number)

    def _add_entry(self, label='', function=''):
        fe = FunctionEntry(self._container, self._func_names, self._func_colors,
                           label=label, function=function)
        fe.pack(anchor='w', pady=1)
        fe.label_var.trace_add('write', lambda *_: self._on_click())

    def populate(self, functions):
        """Load existing functions list [{'name':…,'color':…}]."""
        for func in functions:
            color = func.get('color', '')
            try:
                idx      = self._func_colors.index(color)
                func_key = self._func_names[idx]
            except ValueError:
                func_key = ''
            self._add_entry(label=func.get('name', ''), function=func_key)

    def get_functions(self):
        """Return list of {'name', 'function', 'color'} dicts."""
        result = []
        for fe in list(self._container.winfo_children()):
            if not isinstance(fe, FunctionEntry):
                continue
            data = fe.get()
            if data:
                label, func_key, color = data
                result.append({'name': label, 'function': func_key, 'color': color})
        return result


# ── Main GUI window ───────────────────────────────────────────────────────────

class PinoutGUI(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('Pinout Maker')
        self.resizable(True, True)

        self._config         = {}
        self._func_names     = []
        self._func_colors    = []
        self._pin_rows       = {}   # {pin_number: PinRow}
        self._detected_pins  = []   # list of Pin objects
        self._pin_count      = 0
        self._active_pin_num = None

        self._build_ui()
        self._load_config(self._cfg_var.get())

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Files panel ──────────────────────────────────────────────────────
        files_frame = tk.LabelFrame(self, text='Files', padx=6, pady=6)
        files_frame.pack(fill='x', padx=8, pady=6)

        self._svg_var = tk.StringVar(value=os.path.join('examples', 'br_micro_sensor-F_Mask.svg'))
        self._img_var = tk.StringVar(value=os.path.join('examples', 'br_micro_sensor_top_view.png'))
        self._out_var = tk.StringVar(value=os.path.join('examples', 'output_pinout.svg'))
        self._cfg_var = tk.StringVar(value=os.path.join('plugins', 'config.json'))

        rows = [
            ('Gerber mask SVG:', self._svg_var, self._browse_svg),
            ('Board image:',     self._img_var, self._browse_img),
            ('Output SVG:',      self._out_var, self._browse_out),
            ('Config JSON:',     self._cfg_var, self._browse_cfg),
        ]
        for r, (lbl, var, cmd) in enumerate(rows):
            tk.Label(files_frame, text=lbl, anchor='e', width=16).grid(
                row=r, column=0, sticky='e', pady=2)
            tk.Entry(files_frame, textvariable=var, width=44).grid(
                row=r, column=1, padx=4, pady=2, sticky='ew')
            tk.Button(files_frame, text='…', command=cmd, width=3).grid(
                row=r, column=2, pady=2)
        files_frame.columnconfigure(1, weight=1)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill='x', padx=8, pady=4)

        tk.Button(btn_frame, text='Detect pins',
                  command=self._detect_pins, width=14).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Import config…',
                  command=self._import_config, width=14).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Export config…',
                  command=self._save_config, width=14).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Export template…',
                  command=self._export_template, width=16).pack(side='left', padx=4)
        tk.Button(btn_frame, text='Generate pinout',
                  command=self._generate, width=15,
                  bg='#4CAF50', fg='white',
                  activebackground='#388E3C').pack(side='right', padx=4)

        # ── Horizontal PanedWindow: Pins | Preview ────────────────────────────
        paned = tk.PanedWindow(self, orient='horizontal',
                               sashwidth=6, sashrelief='raised', bg='#cccccc')
        paned.pack(fill='both', expand=True, padx=8, pady=4)

        # ── Left: Pins panel ──────────────────────────────────────────────────
        pins_outer = tk.LabelFrame(paned, text='Pins', padx=4, pady=4)
        paned.add(pins_outer, minsize=260, stretch='always')

        pins_canvas = tk.Canvas(pins_outer)
        pins_scroll = ttk.Scrollbar(pins_outer, orient='vertical', command=pins_canvas.yview)
        pins_canvas.configure(yscrollcommand=pins_scroll.set)
        pins_scroll.pack(side='right', fill='y')
        pins_canvas.pack(side='left', fill='both', expand=True)

        self._pins_frame = tk.Frame(pins_canvas)
        self._pins_window = pins_canvas.create_window((0, 0), window=self._pins_frame, anchor='nw')

        self._pins_frame.bind('<Configure>',
            lambda e: pins_canvas.configure(scrollregion=pins_canvas.bbox('all')))
        pins_canvas.bind('<Configure>',
            lambda e: pins_canvas.itemconfig(self._pins_window, width=e.width))
        pins_canvas.bind('<Enter>',
            lambda e: pins_canvas.bind_all('<MouseWheel>',
                lambda ev: pins_canvas.yview_scroll(-1 * (ev.delta // 120), 'units')))
        pins_canvas.bind('<Leave>',
            lambda e: pins_canvas.unbind_all('<MouseWheel>'))

        self._pins_canvas = pins_canvas

        # ── Right: Preview panel ──────────────────────────────────────────────
        preview_outer = tk.LabelFrame(paned, text='Preview', padx=4, pady=4)
        paned.add(preview_outer, minsize=200, stretch='always')

        preview_toolbar = tk.Frame(preview_outer)
        preview_toolbar.pack(fill='x', pady=(0, 4))
        tk.Button(preview_toolbar, text='Open in browser',
                  command=self._open_in_browser, width=14).pack(side='left', padx=4)

        self._preview_canvas = tk.Canvas(preview_outer, bg='#2b2b2b')
        self._preview_canvas.pack(fill='both', expand=True)
        self._preview_canvas.bind('<Configure>', self._on_preview_resize)
        self._preview_photo = None
        self._preview_transform = None

        # ── Status bar ────────────────────────────────────────────────────────
        self._status = tk.StringVar(value='Ready.')
        tk.Label(self, textvariable=self._status, anchor='w',
                 relief='sunken').pack(fill='x', padx=8, pady=(0, 4))

        self.geometry('1150x680')
        self.after(100, lambda: paned.sash_place(0, 420, 0))

    # ── File dialogs ──────────────────────────────────────────────────────────

    def _browse_svg(self):
        path = filedialog.askopenfilename(filetypes=[('SVG files', '*.svg'), ('All', '*.*')])
        if path:
            self._svg_var.set(path)

    def _browse_img(self):
        path = filedialog.askopenfilename(
            filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp'), ('All', '*.*')])
        if path:
            self._img_var.set(path)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(defaultextension='.svg',
            filetypes=[('SVG files', '*.svg'), ('All', '*.*')])
        if path:
            self._out_var.set(path)

    def _browse_cfg(self):
        path = filedialog.askopenfilename(filetypes=[('JSON files', '*.json'), ('All', '*.*')])
        if path:
            self._cfg_var.set(path)
            self._load_config(path)

    # ── Config loading ────────────────────────────────────────────────────────

    def _load_config(self, path):
        if not os.path.isfile(path):
            return
        try:
            self._config      = save.from_json(path)
            self._func_names  = [f['name']  for f in self._config.get('function', [])]
            self._func_colors = [f['color'] for f in self._config.get('function', [])]
        except Exception as exc:
            messagebox.showerror('Config error', str(exc))

    # ── Pin detection & Interactive Highlighting ──────────────────────────────

    def _detect_pins(self):
        svg_path = self._svg_var.get()
        if not os.path.isfile(svg_path):
            messagebox.showerror('Error', f'SVG file not found:\n{svg_path}')
            return
        try:
            tree = ET.parse(svg_path)
            root = tree.getroot()
            svg_width  = float(root.attrib.get('width',  '100mm').replace('mm', ''))
            svg_height = float(root.attrib.get('height', '100mm').replace('mm', ''))
            pins = detect_pin(root.iter(), (svg_width, svg_height), sort_pins=True)
            self._detected_pins = pins
        except Exception as exc:
            messagebox.showerror('Parse error', str(exc))
            return

        existing = {n: row.get_functions() for n, row in self._pin_rows.items()}
        self._clear_pin_rows()

        for pin in pins:
            row = PinRow(self._pins_frame, pin.number,
                         self._func_names, self._func_colors,
                         side=pin.side, on_focus_cb=self._highlight_pin)
            row.pack(fill='x', padx=2, pady=2)
            if pin.number in existing and existing[pin.number]:
                row.populate(existing[pin.number])
            self._pin_rows[pin.number] = row

        self._pin_count = len(pins)
        self._status.set(f'Detected and spatially sorted {len(pins)} pins.')

    def _highlight_pin(self, pin_number):
        self._active_pin_num = pin_number
        for num, row in self._pin_rows.items():
            if num == pin_number:
                row.config(relief='solid', bd=2, bg='#eef6ff')
            else:
                row.config(relief='ridge', bd=1, bg=self.cget('bg'))
        self._draw_pin_highlight()

    def _draw_pin_highlight(self):
        c = self._preview_canvas
        c.delete('highlight_tag')
        if not self._active_pin_num or not self._preview_transform:
            return

        matching = [p for p in self._detected_pins if p.number == self._active_pin_num]
        if not matching:
            return
        pin = matching[0]

        scale, offset_x, offset_y, vb_x, vb_y = self._preview_transform
        px = (pin.cx - vb_x) * scale + offset_x
        py = (pin.cy - vb_y) * scale + offset_y
        hr = max(6.0, (pin.r or 0.85) * scale + 4)

        c.create_oval(px - hr, py - hr, px + hr, py + hr,
                      outline='#00ffff', width=3, tags='highlight_tag')

    def _clear_pin_rows(self):
        for w in self._pins_frame.winfo_children():
            w.destroy()
        self._pin_rows.clear()

    # ── Config import / export ────────────────────────────────────────────────

    def _import_config(self):
        path = filedialog.askopenfilename(filetypes=[('CSV files', '*.csv'), ('All', '*.*')])
        if not path or not os.path.isfile(path):
            return
        if not self._pin_rows:
            self._detect_pins()
        if not self._pin_rows:
            return
        try:
            pins_data = load_pins_csv(path, self._config)
        except Exception as exc:
            messagebox.showerror('CSV error', str(exc))
            return
        for pin_number, data in pins_data.items():
            if pin_number not in self._pin_rows:
                continue
            row = self._pin_rows[pin_number]
            for w in list(row._container.winfo_children()):
                w.destroy()
            funcs = data.get('functions', []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            row.populate(funcs)
            if isinstance(data, dict) and data.get('side'):
                row.side_var.set(data['side'])
        self._status.set(f'Config imported: {os.path.basename(path)}')

    def _save_config(self):
        if not self._pin_rows:
            messagebox.showinfo('Info', 'Detect pins first.')
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv', initialfile='pins_config.csv',
            filetypes=[('CSV files', '*.csv'), ('All', '*.*')])
        if not path:
            return
        import csv as _csv
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = _csv.writer(f)
                writer.writerow(['number', 'label', 'function', 'side'])
                for pin_number in sorted(self._pin_rows):
                    row = self._pin_rows[pin_number]
                    funcs = row.get_functions()
                    side = row.side_var.get()
                    if funcs:
                        for func in funcs:
                            writer.writerow([pin_number,
                                             func.get('name', ''),
                                             func.get('function', ''),
                                             side])
                    else:
                        writer.writerow([pin_number, '', '', side])
        except Exception as exc:
            messagebox.showerror('Export error', str(exc))
            return
        self._status.set(f'Config saved: {os.path.basename(path)}')

    def _export_template(self):
        if not self._pin_rows:
            self._detect_pins()
        if not self._pin_rows:
            return
        path = filedialog.asksaveasfilename(
            defaultextension='.csv', initialfile='pins_template.csv',
            filetypes=[('CSV files', '*.csv'), ('All', '*.*')])
        if not path:
            return

        class _FakePin:
            def __init__(self, n, s):
                self.number = n
                self.side = s

        try:
            fake_pins = [_FakePin(n, self._pin_rows[n].side_var.get()) for n in sorted(self._pin_rows)]
            generate_template_csv(fake_pins, output_path=path, config=self._config)
        except Exception as exc:
            messagebox.showerror('Export error', str(exc))
            return
        self._status.set(f'Template exported: {os.path.basename(path)}')

    # ── Pinout generation ─────────────────────────────────────────────────────

    def _generate(self):
        svg_path = self._svg_var.get()
        img_path = self._img_var.get()
        out_path = self._out_var.get()

        for label, path in [('Gerber SVG', svg_path), ('Board image', img_path)]:
            if not os.path.isfile(path):
                messagebox.showerror('Error', f'{label} not found:\n{path}')
                return
        if not self._pin_rows:
            messagebox.showinfo('Info', 'Detect pins first.')
            return

        pins_data = {
            n: {
                'functions': row.get_functions(),
                'side': row.side_var.get()
            }
            for n, row in self._pin_rows.items()
        }

        self._status.set('Generating pinout…')
        self.update_idletasks()

        def run():
            try:
                build_pinout(svg_path, img_path, out_path, pins_data, sort_pins=True)
                self.after(0, lambda: [
                    self._status.set(f'Done — {out_path}'),
                    self._refresh_preview(),
                ])
            except Exception as exc:
                self.after(0, lambda: self._status.set(f'Error: {exc}'))
                self.after(0, lambda: messagebox.showerror('Error', str(exc)))

        threading.Thread(target=run, daemon=True).start()

    # ── Preview ───────────────────────────────────────────────────────────────

    def _on_preview_resize(self, _event=None):
        if hasattr(self, '_resize_job'):
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(150, self._refresh_preview)

    def _refresh_preview(self):
        c = self._preview_canvas
        c.delete('all')
        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 10 or ch < 10:
            return

        out_path = self._out_var.get()
        if not os.path.isfile(out_path):
            c.create_text(cw // 2, ch // 2,
                          text='No output file yet.\nGenerate the pinout first.',
                          justify='center', fill='#888888',
                          font=('Segoe UI', 10))
            return

        try:
            self._render_svg_on_canvas(out_path, c, cw, ch)
            self._draw_pin_highlight()
        except Exception as exc:
            c.create_text(cw // 2, ch // 2,
                          text=f'Preview error:\n{exc}',
                          justify='center', fill='#ff6666',
                          font=('Segoe UI', 9))

    def _render_svg_on_canvas(self, svg_path, c, cw, ch):
        """Parse output SVG and draw elements on tkinter Canvas."""
        tree = ET.parse(svg_path)
        root = tree.getroot()

        vb_str = root.get('viewBox', '')
        if vb_str:
            vb_x, vb_y, vb_w, vb_h = (float(v) for v in vb_str.split())
        else:
            vb_x, vb_y = 0.0, 0.0
            vb_w = float(root.get('width',  '100').replace('mm', ''))
            vb_h = float(root.get('height', '100').replace('mm', ''))

        scale    = min(cw / vb_w, ch / vb_h)
        offset_x = (cw - vb_w * scale) / 2
        offset_y = (ch - vb_h * scale) / 2

        self._preview_transform = (scale, offset_x, offset_y, vb_x, vb_y)

        def tx(x, y):
            return (x - vb_x) * scale + offset_x, (y - vb_y) * scale + offset_y

        def flat(points):
            out = []
            for px, py in points:
                cx2, cy2 = tx(px, py)
                out += [cx2, cy2]
            return out

        def svg_color(val):
            return val if (val and val != 'none') else ''

        c.create_rectangle(0, 0, cw, ch, fill='#2b2b2b', outline='')
        self._preview_photos = []

        for el in root.iter():
            tag = el.tag.split('}')[-1]

            if tag == 'image':
                href = (el.get('href') or el.get('{http://www.w3.org/1999/xlink}href', ''))
                if not href.startswith('data:'):
                    continue
                try:
                    _, payload = href.split(',', 1)
                    img = Image.open(io.BytesIO(base64.b64decode(payload.rstrip(';'))))
                    x  = float(el.get('x', 0))
                    y  = float(el.get('y', 0))
                    w  = float(el.get('width',  vb_w))
                    h  = float(el.get('height', vb_h))
                    x1, y1 = tx(x,     y)
                    x2, y2 = tx(x + w, y + h)
                    pw, ph = max(1, int(x2 - x1)), max(1, int(y2 - y1))
                    img = img.resize((pw, ph), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._preview_photos.append(photo)
                    c.create_image(x1, y1, image=photo, anchor='nw')
                except Exception:
                    pass

            elif tag == 'circle':
                cx  = float(el.get('cx', 0))
                cy  = float(el.get('cy', 0))
                r   = float(el.get('r',  1))
                sw  = float(el.get('stroke-width', 0)) * scale
                x1, y1 = tx(cx - r, cy - r)
                x2, y2 = tx(cx + r, cy + r)
                kw = dict(fill=svg_color(el.get('fill')),
                          outline=svg_color(el.get('stroke')),
                          width=max(1, sw))
                c.create_oval(x1, y1, x2, y2, **kw)

            elif tag == 'path':
                d = el.get('d', '')
                if not d:
                    continue
                try:
                    pts = extract_points_from_path(d)
                except Exception:
                    continue
                if len(pts) < 2:
                    continue
                coords = flat(pts)
                fill   = svg_color(el.get('fill'))
                stroke = svg_color(el.get('stroke'))
                sw     = float(el.get('stroke-width', 0)) * scale
                if 'Z' in d or 'z' in d:
                    c.create_polygon(coords, fill=fill, outline=stroke, width=max(1, sw), smooth=False)
                else:
                    c.create_line(coords, fill=stroke or fill, width=max(1, sw))

            elif tag == 'text':
                text = el.text
                if not text:
                    continue
                x = float(el.get('x', 0))
                y = float(el.get('y', 0))
                fill = svg_color(el.get('fill')) or 'black'

                style = el.get('style', '')
                m = re.search(r'font-size:([\d.]+)', style)
                fs = int(max(7, float(m.group(1)) * scale)) if m else 9

                ta  = el.get('text-anchor', 'start')
                dbl = el.get('dominant-baseline', '')
                if ta == 'middle' and dbl == 'central':
                    anchor = 'center'
                elif ta == 'middle':
                    anchor = 'n'
                elif ta == 'end':
                    anchor = 'e'
                else:
                    anchor = 'w'

                px, py = tx(x, y)
                c.create_text(px, py, text=text, fill=fill,
                              font=('Consolas', fs, 'bold'), anchor=anchor)

    def _open_in_browser(self):
        out_path = self._out_var.get()
        if not os.path.isfile(out_path):
            messagebox.showinfo('Info', 'No output file yet. Generate the pinout first.')
            return
        from pathlib import Path
        webbrowser.open(Path(os.path.abspath(out_path)).as_uri())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = PinoutGUI()
    app.mainloop()
