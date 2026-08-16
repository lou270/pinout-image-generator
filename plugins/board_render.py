########################################
# Pinout image builder — KiCad board renderer
# Louis Barbier
# MIT License
########################################
"""Render a top-view PNG of the active board.

Tries three strategies, in order:
  1. Subprocess call to `kicad-cli pcb render --side top --background transparent --quality basic` (KiCad 8+).
  2. Subprocess call to `kicad-cli pcb export svg` (KiCad 8+) + rasterisation.
  3. pcbnew.PLOT_CONTROLLER → SVG → rasterise with cairosvg.
  4. Return None so the caller can prompt the user for a PNG manually.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from PIL import Image

try:
    import pcbnew
except ImportError:
    pcbnew = None

try:
    import cairosvg
except Exception:
    cairosvg = None


def find_kicad_cli():
    """Locate the kicad-cli executable across PATH and standard install paths."""
    # 1. System PATH
    found = shutil.which('kicad-cli') or shutil.which('kicad-cli.exe')
    if found and os.path.isfile(found):
        return found

    # 2. Alongside the current python executable (KiCad's internal Python)
    py_dir = os.path.dirname(sys.executable)
    cand1 = os.path.join(py_dir, 'kicad-cli.exe' if sys.platform == 'win32' else 'kicad-cli')
    if os.path.isfile(cand1):
        return cand1

    # 3. Windows standard installations (e.g. C:\Program Files\KiCad\*\bin\kicad-cli.exe)
    if sys.platform == 'win32':
        search_patterns = [
            r'C:\Program Files\KiCad\*\bin\kicad-cli.exe',
            r'C:\Program Files (x86)\KiCad\*\bin\kicad-cli.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Programs\KiCad\*\bin\kicad-cli.exe'),
        ]
        for pattern in search_patterns:
            matches = glob.glob(pattern)
            if matches:
                matches.sort(reverse=True)
                return matches[0]

    # 4. macOS standard location
    elif sys.platform == 'darwin':
        macos_cand = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
        if os.path.isfile(macos_cand):
            return macos_cand

    # 5. Linux standard locations
    elif sys.platform.startswith('linux'):
        for loc in ['/usr/bin/kicad-cli', '/usr/local/bin/kicad-cli']:
            if os.path.isfile(loc):
                return loc

    return None


def _tempfile(suffix):
    fd, path = tempfile.mkstemp(prefix='pinout_board_', suffix=suffix)
    os.close(fd)
    return path


def _clean_rendered_png(png_path, alpha_threshold=25):
    """Crop transparent and faint shadow fringes from rendered PNG in-place."""
    try:
        img = Image.open(png_path)
        img.load()
        if img.mode in ('RGBA', 'LA'):
            alpha = img.split()[-1]
            mask = alpha.point(lambda p: 255 if p > alpha_threshold else 0)
            bbox = mask.getbbox()
            if bbox and bbox != (0, 0, img.size[0], img.size[1]):
                cropped = img.crop(bbox)
                cropped.save(png_path, 'PNG')
    except Exception:
        pass


def _kicad_cli_render(board_path, out_png):
    """Render board top-view with transparent background using kicad-cli 3D renderer."""
    exe = find_kicad_cli()
    if not exe:
        return None

    # Note: we use --quality basic to avoid 3D floor shadows that distort board bounds
    cmd = [
        exe, 'pcb', 'render',
        '--side', 'top',
        '--background', 'transparent',
        '--quality', 'basic',
        '--output', out_png,
        board_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and os.path.isfile(out_png) and os.path.getsize(out_png) > 0:
            _clean_rendered_png(out_png)
            return out_png
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return None


def _kicad_cli_export_svg(board_path, out_png):
    """Export 2D board layers using kicad-cli export svg and rasterize."""
    exe = find_kicad_cli()
    if not exe:
        return None

    svg_tmp = _tempfile('.svg')
    cmd = [
        exe, 'pcb', 'export', 'svg',
        '--page-size-mode', '2',
        '--fit-page-to-board',
        '--exclude-drawing-sheet',
        '--layers', 'Edge.Cuts,F.Mask,F.Cu,F.SilkS',
        '--mode-single',
        '-o', svg_tmp,
        board_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and os.path.isfile(svg_tmp) and os.path.getsize(svg_tmp) > 0:
            if _svg_to_png(svg_tmp, out_png):
                return out_png
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    finally:
        if os.path.isfile(svg_tmp):
            try:
                os.unlink(svg_tmp)
            except OSError:
                pass

    return None


def _plot_to_svg(board, out_svg):
    """Plot F.Cu + F.SilkS + F.Mask + Edge.Cuts to a single SVG using pcbnew."""
    if pcbnew is None:
        raise RuntimeError('pcbnew is not available')

    plot_ctrl = pcbnew.PLOT_CONTROLLER(board)
    opts = plot_ctrl.GetPlotOptions()
    out_dir = os.path.dirname(out_svg) or tempfile.gettempdir()
    opts.SetOutputDirectory(out_dir)
    opts.SetFormat(pcbnew.PLOT_FORMAT_SVG)
    opts.SetMirror(False)
    opts.SetPlotFrameRef(False)
    opts.SetUseAuxOrigin(False)
    opts.SetDrillMarksType(getattr(pcbnew, 'DRILL_MARKS_NO_DRILL_SHAPE', 0))

    layers = [
        ('Edge.Cuts', getattr(pcbnew, 'Edge_Cuts', 44)),
        ('F.Mask',    getattr(pcbnew, 'F_Mask', 38)),
        ('F.Cu',      getattr(pcbnew, 'F_Cu', 0)),
        ('F.SilkS',   getattr(pcbnew, 'F_SilkS', 37)),
    ]
    plot_ctrl.OpenPlotfile('TopView', pcbnew.PLOT_FORMAT_SVG, 'Pinout top view')
    for name, layer_id in layers:
        plot_ctrl.SetLayer(layer_id)
        plot_ctrl.PlotLayer()
    plot_ctrl.ClosePlot()

    basename = os.path.splitext(os.path.basename(board.GetFileName() or 'board'))[0]
    produced = os.path.join(out_dir, f'{basename}-TopView.svg')
    if os.path.isfile(produced):
        os.replace(produced, out_svg)
        return out_svg
    return None


def _svg_to_png(in_svg, out_png, target_width_px=2000):
    """Rasterise an SVG to PNG via cairosvg or svglib."""
    if cairosvg is not None:
        try:
            cairosvg.svg2png(url=in_svg, write_to=out_png, output_width=target_width_px)
            if os.path.isfile(out_png) and os.path.getsize(out_png) > 0:
                return out_png
        except Exception:
            pass

    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        drawing = svg2rlg(in_svg)
        if drawing is not None:
            renderPM.drawToFile(drawing, out_png, fmt='PNG', dpi=300)
            if os.path.isfile(out_png) and os.path.getsize(out_png) > 0:
                return out_png
    except Exception:
        pass

    return None


def render_top_view(board):
    """Produce a top-view PNG of the board. Returns path or None if all strategies failed."""
    out_png = _tempfile('.png')
    board_path = board.GetFileName() if (pcbnew and board) else None

    # Strategy 1: kicad-cli 3D render with transparent background & basic quality (no floor shadow)
    if board_path and os.path.isfile(board_path):
        result = _kicad_cli_render(board_path, out_png)
        if result:
            return result

        # Strategy 2: kicad-cli export svg
        result = _kicad_cli_export_svg(board_path, out_png)
        if result:
            return result

    # Strategy 3: plot SVG via pcbnew PLOT_CONTROLLER
    if pcbnew is not None and board:
        svg_tmp = _tempfile('.svg')
        try:
            produced_svg = _plot_to_svg(board, svg_tmp)
            if produced_svg and _svg_to_png(produced_svg, out_png):
                return out_png
        finally:
            if os.path.isfile(svg_tmp):
                try:
                    os.unlink(svg_tmp)
                except OSError:
                    pass

    # Strategy 4: give up — caller prompts user
    if os.path.isfile(out_png):
        try:
            os.unlink(out_png)
        except OSError:
            pass

    return None
