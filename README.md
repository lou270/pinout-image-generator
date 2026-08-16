# Pinout Image Generator

Generate annotated, publication-ready pinout diagrams (SVG & PNG) for PCBs. Works either:

- **Inside KiCad** as an *Action Plugin* (install via KiCad's Plugin and Content Manager, click the toolbar icon).
- **Standalone** via CLI or Tkinter GUI, starting from a Gerber mask SVG (`F.Mask`) + a top-view board image.

---

## Features

- **4-Sided Pinout Rendering**: Full support for `left`, `right`, `top`, and `bottom` pin annotations with clean leader lines.
- **Dynamic Box Sizing**: Function label boxes dynamically scale to fit text length without clipping or overflow.
- **Multi-Function Support**: Attach multiple functions to any pin (e.g. `TX / GPIO5 / PWM`).
- **Spatial Pin Sorting**: Auto-detects and numbers pins along the board edges in a natural, orderly sequence.
- **Transparent KiCad Board Rendering**: Automatic discovery of `kicad-cli` with transparent background rendering for pixel-perfect board overlay and scaling.
- **Dual Export (SVG + PNG)**: Produces vector SVGs and high-resolution PNGs (using `svglib+reportlab`, `cairosvg`, `inkscape`, or `librsvg`).

---

## Install in KiCad (PCM)

### One-click via third-party repository

1. Open KiCad → *Plugin and Content Manager* → *Manage repositories…* → *+*.
2. Add `https://github.com/lou270/pinout-image-generator/releases/latest/download/metadata.json`.
3. Select the repository, find **Pinout Image Generator** under *Plugins*, click *Install*.
4. Restart the PCB editor — the Pinout Image Generator toolbar icon appears.

### Manual install (KiCad 7, 8, 9+)

1. Download `com.lou270.pinout-image-generator.zip` from the [Releases](https://github.com/lou270/pinout-image-generator/releases) page.
2. KiCad → *Plugin and Content Manager* → *Install from file* → select the zip.

### Using in KiCad

1. Open your board in the PCB editor (`pcbnew`).
2. Click the **Pinout Image Generator** toolbar icon (or *Tools → External Plugins → Pinout Image Generator*).
3. A dialog shows pads detected on connector footprints (`J*`, `CN*`, `P*`, `HDR*`, `CONN*`, etc.).
   - Labels and functions are pre-filled using net names and regex rules from `plugins/netclass_map.json`.
   - Multiple functions per pin can be added using comma separation (e.g. `Label: "TX, GPIO5" | Function: "UART, GPIO/PWM"`) or across separate rows.
4. Set the output SVG path and click **Generate**.

---

## Standalone CLI

```bash
# 1. Produce a template CSV from a gerber F.Mask SVG
python main.py --input-svg examples/br_micro_sensor-F_Mask.svg --generate-template

# 2. Fill in pins_template.csv (number, label, function, side)

# 3. Render the pinout (SVG + PNG)
python main.py \
    --input-svg   examples/br_micro_sensor-F_Mask.svg \
    --board-image examples/br_micro_sensor_top_view.png \
    --pins        examples/pins_template.csv \
    --output      examples/output_pinout.svg
```

CLI options:
- `--no-sort-pins`: Disable spatial pin sorting.
- `--no-png`: Skip PNG export.
- `--png-dpi N`: Set PNG export DPI (default: 300).

---

## Standalone Tkinter GUI

Launch the desktop GUI:

```bash
python gui.py
```

- **Interactive Pad Highlighting**: Clicking or editing a pin row highlights the corresponding pad on the preview canvas.
- **4-Sided Selector**: Quickly configure the orientation (`left`, `right`, `top`, `bottom`) for each pin.
- **Dynamic Preview**: Real-time vector preview directly on the canvas.

---

## Automated Tests

Run the full automated test suite:

```bash
python -m unittest discover -s tests -v
```

---

## Repository Layout

```
pinout-image-generator/
├── metadata.json              # KiCad PCM manifest
├── resources/icon.png         # Toolbar icon (64×64)
├── plugins/                   # Core shared modules and KiCad plugin
│   ├── __init__.py            # Registers ActionPlugin in KiCad
│   ├── pinout_plugin.py       # KiCad ActionPlugin implementation
│   ├── board_parser.py        # KiCad board pad & net extraction
│   ├── board_render.py        # kicad-cli / plot top-view renderer
│   ├── dialog.py              # wxPython editing dialog
│   ├── function.py / Pin.py   # Core pinout rendering engine
│   ├── svg.py / save.py       # SVG manipulation and JSON helpers
│   ├── config.json            # Function types and colors
│   └── netclass_map.json      # Net-name regex mapping rules
├── main.py                    # Standalone CLI
├── gui.py                     # Standalone Tkinter GUI
├── tests/                     # Automated unit and integration tests
├── examples/                  # Sample boards, SVG masks, and CSVs
└── scripts/
    └── build_pcm_package.py   # Builds PCM distribution zip
```

---

## License

MIT — see individual source files.
