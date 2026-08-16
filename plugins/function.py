########################################
# Pinout image builder — Functions
# Louis Barbier
# MIT License
########################################

import base64
import io
import os
import random
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image

import svg
from Pin import Pin

SVG_NS = 'http://www.w3.org/2000/svg'
XLINK_NS = 'http://www.w3.org/1999/xlink'
SVG_TAG = lambda name: f'{{{SVG_NS}}}{name}'

# Register default namespace so serialisation emits plain <svg>/<path>/… rather
# than ns0:-prefixed tags.
ET.register_namespace('', SVG_NS)
ET.register_namespace('xlink', XLINK_NS)


def detect_side_pin(cx, cy, svg_size):
    """Detect which side of the board a pin is closest to: 'left', 'right', 'top', or 'bottom'."""
    w, h = svg_size
    if w <= 0 or h <= 0:
        return 'left'

    rx = cx / w
    ry = cy / h

    # If board is clearly landscape (w >= 1.5 * h), left/right are preferred unless close to top/bottom
    if w >= h * 1.5:
        if ry < 0.15:
            return 'top'
        elif ry > 0.85:
            return 'bottom'
        return 'left' if rx < 0.5 else 'right'

    # If board is clearly portrait (h >= 1.5 * w), top/bottom are preferred unless close to left/right
    if h >= w * 1.5:
        if rx < 0.15:
            return 'left'
        elif rx > 0.85:
            return 'right'
        return 'top' if ry < 0.5 else 'bottom'

    # Roughly square: pick the closest edge
    distances = {
        'left':   rx,
        'right':  1.0 - rx,
        'top':    ry,
        'bottom': 1.0 - ry,
    }
    return min(distances, key=distances.get)


def detect_pin(elements, svg_size, sort_pins=True):
    """Detect pins from SVG elements (<circle> and small <path> pads).
    
    If sort_pins is True, pins are sorted spatially (left pins top->down,
    top pins left->right, right pins top->down, bottom pins left->right).
    """
    raw_pins = []
    for element in elements:
        detected = False
        cx, cy, r = 0.0, 0.0, 0.85
        tag = element.tag.split('}')[-1]

        if tag == 'circle':
            try:
                cx = float(element.attrib['cx'])
                cy = float(element.attrib['cy'])
                r = float(element.attrib['r'])
                detected = True
            except (KeyError, ValueError):
                pass
        elif tag == 'path':
            d = element.attrib.get('d', '')
            if d:
                min_x, max_x, min_y, max_y = svg.get_min_max_pos(element)
                width, height = svg.get_size(min_x, max_x, min_y, max_y)
                cx = min_x + width / 2
                cy = min_y + height / 2
                r = max(width / 2, height / 2)
                # Typical SMD/THT pad threshold
                if 0.1 < r < 3.0:
                    detected = True

        if detected:
            side = detect_side_pin(cx, cy, svg_size)
            raw_pins.append(Pin(cx=cx, cy=cy, r=r, side=side))

    if not sort_pins:
        for idx, pin in enumerate(raw_pins, start=1):
            pin.number = idx
        return raw_pins

    # Spatial sorting: group by side then sort along the respective edge
    left_pins   = sorted([p for p in raw_pins if p.side == 'left'],   key=lambda p: (p.cy, p.cx))
    top_pins    = sorted([p for p in raw_pins if p.side == 'top'],    key=lambda p: (p.cx, p.cy))
    right_pins  = sorted([p for p in raw_pins if p.side == 'right'],  key=lambda p: (p.cy, -p.cx))
    bottom_pins = sorted([p for p in raw_pins if p.side == 'bottom'], key=lambda p: (p.cx, -p.cy))

    sorted_pins = left_pins + top_pins + right_pins + bottom_pins
    for idx, pin in enumerate(sorted_pins, start=1):
        pin.number = idx

    return sorted_pins


def add_pin_graphics(svg_root, pin):
    """Render a single pin's leader line, number badge, and function boxes into svg_root.
    
    Supports 'left', 'right', 'top', and 'bottom' side orientations with dynamic box sizing.
    """
    line_length = 3.0
    stroke_width = 0.05
    r = pin.r if (pin.r and pin.r > 0) else 0.85
    pin_font_size = max(0.7, min(1.3, r * 1.1))
    func_font_size = max(0.75, min(1.2, r * 1.05))
    box_h = max(1.5, min(2.4, r * 2.0))

    group = ET.Element(SVG_TAG('g'), {'id': f"g_pin_{pin.number}"})
    group.tail = "\n"

    side = pin.side.lower() if pin.side else 'left'

    # ── 1. Left / Right Orientations ──────────────────────────────────────────
    if side in ('left', 'right'):
        v = -1 if side == 'left' else 1

        # Leader line from pad to pin circle
        group.append(ET.Element(SVG_TAG('path'), {
            'd': f'M {pin.cx},{pin.cy} l {v * line_length},0',
            'fill': '#dcdcdc',
            'stroke': '#dcdcdc',
            'stroke-width': str(stroke_width)
        }))

        # Pin circle badge
        circle_cx = pin.cx + v * line_length + v * r
        group.append(ET.Element(SVG_TAG('circle'), {
            'cx': str(circle_cx),
            'cy': str(pin.cy),
            'r': str(r),
            'fill': '#dcdcdc',
            'stroke': 'none',
            'stroke-width': str(stroke_width)
        }))

        # Pin number text
        pin_text = ET.Element(SVG_TAG('text'), {
            'x': str(circle_cx),
            'y': str(pin.cy),
            'text-anchor': 'middle',
            'style': f'font-family:Consolas, monospace;font-size:{pin_font_size};font-weight:bold;',
            'dominant-baseline': 'central',
            'fill': '#000000',
            'stroke': '#000000',
            'stroke-width': str(stroke_width / 2)
        })
        pin_text.text = str(pin.number)
        group.append(pin_text)

        # Function boxes chained horizontally
        el_functions = ET.Element(SVG_TAG('g'), {'id': f"g_pin_{pin.number}_functions"})
        curr_x = pin.cx + v * line_length + v * 2 * r

        for func in pin.functions:
            func_name = str(func.get('name', ''))
            func_color = str(func.get('color', '#888888'))
            box_l = max(10.0, len(func_name) * 0.75 + 3.5)
            slope = 0.1

            # Inter-box connector line
            el_functions.append(ET.Element(SVG_TAG('path'), {
                'd': f'M {curr_x},{pin.cy} l {v * line_length},0',
                'fill': '#dcdcdc',
                'stroke': '#dcdcdc',
                'stroke-width': str(stroke_width)
            }))
            curr_x += v * line_length

            # Rounded parallelogram
            if v == 1:  # right side
                init_x = curr_x + (box_l * slope) / 2
                init_y = pin.cy - box_h / 2
                poly_d = (
                    f"M {init_x},{init_y} "
                    f"l {box_l * (1 - slope)},0 "
                    f"l {-box_l * slope},{box_h} "
                    f"l {-box_l * (1 - slope)},0 "
                    f"l {box_l * slope},{-box_h} Z"
                )
                text_cx = init_x + (box_l * (1 - slope)) / 2 - (box_l * slope) / 2
            else:       # left side
                init_x = curr_x - (box_l * slope) / 2
                init_y = pin.cy - box_h / 2
                poly_d = (
                    f"M {init_x},{init_y} "
                    f"l {-box_l * (1 - slope)},0 "
                    f"l {box_l * slope},{box_h} "
                    f"l {box_l * (1 - slope)},0 "
                    f"l {-box_l * slope},{-box_h} Z"
                )
                text_cx = init_x - (box_l * (1 - slope)) / 2 + (box_l * slope) / 2

            rounded_d = svg.round_path_corners(poly_d, 0.3)
            el_functions.append(ET.Element(SVG_TAG('path'), {
                'd': rounded_d,
                'fill': func_color,
                'stroke': func_color,
                'stroke-width': str(stroke_width * 2)
            }))

            # Function text
            box_text = ET.Element(SVG_TAG('text'), {
                'x': str(text_cx),
                'y': str(pin.cy),
                'text-anchor': 'middle',
                'style': f'font-family:Consolas, monospace;font-size:{func_font_size};font-weight:bold;',
                'dominant-baseline': 'central',
                'fill': '#FFFFFF',
                'stroke': '#FFFFFF',
                'stroke-width': str(stroke_width / 2)
            })
            box_text.text = func_name
            el_functions.append(box_text)

            curr_x += v * (box_l * (1 - slope) + (box_l * slope) / 2)

        group.append(el_functions)

    # ── 2. Top / Bottom Orientations ──────────────────────────────────────────
    else:
        v = -1 if side == 'top' else 1

        # Leader line from pad to pin circle
        group.append(ET.Element(SVG_TAG('path'), {
            'd': f'M {pin.cx},{pin.cy} l 0,{v * line_length}',
            'fill': '#dcdcdc',
            'stroke': '#dcdcdc',
            'stroke-width': str(stroke_width)
        }))

        # Pin circle badge
        circle_cy = pin.cy + v * line_length + v * r
        group.append(ET.Element(SVG_TAG('circle'), {
            'cx': str(pin.cx),
            'cy': str(circle_cy),
            'r': str(r),
            'fill': '#dcdcdc',
            'stroke': 'none',
            'stroke-width': str(stroke_width)
        }))

        # Pin number text
        pin_text = ET.Element(SVG_TAG('text'), {
            'x': str(pin.cx),
            'y': str(circle_cy),
            'text-anchor': 'middle',
            'style': f'font-family:Consolas, monospace;font-size:{pin_font_size};font-weight:bold;',
            'dominant-baseline': 'central',
            'fill': '#000000',
            'stroke': '#000000',
            'stroke-width': str(stroke_width / 2)
        })
        pin_text.text = str(pin.number)
        group.append(pin_text)

        # Function boxes chained vertically
        el_functions = ET.Element(SVG_TAG('g'), {'id': f"g_pin_{pin.number}_functions"})
        curr_y = pin.cy + v * line_length + v * 2 * r

        for func in pin.functions:
            func_name = str(func.get('name', ''))
            func_color = str(func.get('color', '#888888'))
            box_l = max(10.0, len(func_name) * 0.75 + 3.5)

            # Inter-box connector line
            el_functions.append(ET.Element(SVG_TAG('path'), {
                'd': f'M {pin.cx},{curr_y} l 0,{v * line_length}',
                'fill': '#dcdcdc',
                'stroke': '#dcdcdc',
                'stroke-width': str(stroke_width)
            }))
            curr_y += v * line_length

            # Horizontal rounded box centered on pin.cx
            if v == -1:  # top side (expanding upwards)
                init_x = pin.cx - box_l / 2
                init_y = curr_y - box_h
                text_cy = curr_y - box_h / 2
            else:       # bottom side (expanding downwards)
                init_x = pin.cx - box_l / 2
                init_y = curr_y
                text_cy = curr_y + box_h / 2

            poly_d = (
                f"M {init_x},{init_y} "
                f"l {box_l},0 "
                f"l 0,{box_h} "
                f"l {-box_l},0 "
                f"l 0,{-box_h} Z"
            )
            rounded_d = svg.round_path_corners(poly_d, 0.3)
            el_functions.append(ET.Element(SVG_TAG('path'), {
                'd': rounded_d,
                'fill': func_color,
                'stroke': func_color,
                'stroke-width': str(stroke_width * 2)
            }))

            # Function text
            box_text = ET.Element(SVG_TAG('text'), {
                'x': str(pin.cx),
                'y': str(text_cy),
                'text-anchor': 'middle',
                'style': f'font-family:Consolas, monospace;font-size:{func_font_size};font-weight:bold;',
                'dominant-baseline': 'central',
                'fill': '#FFFFFF',
                'stroke': '#FFFFFF',
                'stroke-width': str(stroke_width / 2)
            })
            box_text.text = func_name
            el_functions.append(box_text)

            curr_y += v * box_h

        group.append(el_functions)

    svg_root.append(group)


def pixels_to_mm(pixels, dpi):
    """Convert pixels to millimeters."""
    return (pixels / dpi) * 25.4


def scale_image_to_svg(image_width_mm, image_height_mm, svg_width_mm, svg_height_mm):
    """Scale image dimensions proportionally to fit inside SVG bounds."""
    if image_width_mm <= 0 or image_height_mm <= 0:
        return svg_width_mm, svg_height_mm
    scale_x = svg_width_mm / image_width_mm
    scale_y = svg_height_mm / image_height_mm
    scale_factor = min(scale_x, scale_y)
    return image_width_mm * scale_factor, image_height_mm * scale_factor


def _autocrop_transparent(image):
    """Crop fully-transparent borders from an RGBA image."""
    if image.mode not in ('RGBA', 'LA'):
        return image
    alpha = image.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None or bbox == (0, 0, image.size[0], image.size[1]):
        return image
    return image.crop(bbox)


def read_image(image_path):
    """Read an image (PNG, JPG, BMP) and return base64 data, dimensions (w, h), dpi, and mime type."""
    with open(image_path, 'rb') as img_file:
        image = Image.open(img_file)
        image.load()

        original_format = image.format or 'PNG'
        dpi = image.info.get('dpi', (96, 96))[0]

        cropped = _autocrop_transparent(image)
        width, height = cropped.size

        format_to_mime = {
            'PNG': 'image/png',
            'JPEG': 'image/jpeg',
            'JPG': 'image/jpeg',
            'BMP': 'image/bmp'
        }
        if original_format not in format_to_mime:
            original_format = 'PNG'

        if cropped.mode in ('RGBA', 'LA'):
            out_format = 'PNG'
        else:
            out_format = original_format
        mime_type = format_to_mime.get(out_format, 'image/png')

        image_buffer = io.BytesIO()
        cropped.save(image_buffer, format=out_format)
        image_base64 = base64.b64encode(image_buffer.getvalue()).decode('utf-8')

    return image_base64, width, height, dpi, mime_type


def add_board_image(svg_root, image_path, svg_width, svg_height):
    """Embed board image into SVG root, scaled proportionally and centered within the board bounds."""
    image_base64, img_w, img_h, _dpi, mime_type = read_image(image_path)
    # Proportional scaling
    scale_x = svg_width / img_w if img_w > 0 else 1.0
    scale_y = svg_height / img_h if img_h > 0 else 1.0
    scale = min(scale_x, scale_y)
    final_w = img_w * scale
    final_h = img_h * scale
    x_pos = (svg_width - final_w) / 2.0
    y_pos = (svg_height - final_h) / 2.0

    image_el = svg.create_image_element(image_base64, final_w, final_h, mime_type, x_pos, y_pos)
    svg_root.append(image_el)


def prettify_svg(root, indent="  "):
    """Prettify XML ElementTree with indentation."""
    def indent_element(elem, level=0):
        i = "\n" + level * indent
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + indent
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                indent_element(child, level + 1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    indent_element(root)


def create_svg_root(width_mm, height_mm):
    """Create a blank SVG root sized in millimetres."""
    root = ET.Element(SVG_TAG('svg'))
    root.set('width', f'{width_mm}mm')
    root.set('height', f'{height_mm}mm')
    root.set('viewBox', f'0 0 {width_mm} {height_mm}')
    return root


def render_pinout(pins, board_image_path, svg_size_mm, output_path,
                  export_png=True, png_dpi=300):
    """Render an annotated pinout SVG from a list of Pin objects."""
    width, height = svg_size_mm
    root = create_svg_root(width, height)

    for pin in pins:
        if getattr(pin, 'displayed', True):
            add_pin_graphics(root, pin)

    if board_image_path and os.path.isfile(board_image_path):
        add_board_image(root, board_image_path, width, height)

    svg.update_bounding_box(root, margin=2)
    prettify_svg(root)
    ET.ElementTree(root).write(output_path, encoding='utf-8', xml_declaration=True)

    if export_png:
        png_path = os.path.splitext(output_path)[0] + '.png'
        ok = svg_to_png(output_path, png_path, dpi=png_dpi)
        if not ok:
            print('[pinout] PNG export skipped (no rasteriser found).')

    return output_path


def _rasterize(svg_path, png_path, dpi):
    """Try available rasterisers in order: cairosvg, svglib+reportlab, inkscape, rsvg-convert."""
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path, dpi=dpi)
        if os.path.isfile(png_path) and os.path.getsize(png_path) > 0:
            return True
    except Exception:
        pass

    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        drawing = svg2rlg(svg_path)
        if drawing is not None:
            renderPM.drawToFile(drawing, png_path, fmt='PNG', dpi=dpi)
            if os.path.isfile(png_path) and os.path.getsize(png_path) > 0:
                return True
    except Exception:
        pass

    candidates = [
        ('inkscape',     ['inkscape', f'--export-dpi={dpi}',
                          '--export-type=png', f'--export-filename={png_path}',
                          svg_path]),
        ('rsvg-convert', ['rsvg-convert', '-d', str(dpi), '-p', str(dpi),
                          '-o', png_path, svg_path]),
    ]
    for _name, cmd in candidates:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            if result.returncode == 0 and os.path.isfile(png_path) and os.path.getsize(png_path) > 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    return False


def _decode_data_uri(uri):
    """Decode a base64 data URI into a PIL Image."""
    try:
        if not uri.startswith('data:'):
            return None
        _header, _, payload = uri.partition(',')
        if ';base64' not in _header:
            return None
        data = base64.b64decode(payload)
        return Image.open(io.BytesIO(data))
    except Exception:
        return None


def svg_to_png(svg_path, png_path, dpi=300):
    """Rasterise an SVG to PNG, cleanly compositing embedded board images."""
    tree = ET.parse(svg_path)
    root = tree.getroot()

    viewbox = root.attrib.get('viewBox', '').split()
    if len(viewbox) == 4:
        vb_x, vb_y, vb_w, vb_h = [float(v) for v in viewbox]
    else:
        vb_x = vb_y = 0.0
        vb_w = float(root.attrib.get('width', '100mm').replace('mm', ''))
        vb_h = float(root.attrib.get('height', '100mm').replace('mm', ''))

    images = []
    image_tag = SVG_TAG('image')
    href_key = 'href'
    xlink_href_key = f'{{{XLINK_NS}}}href'
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == image_tag:
                href = child.attrib.get(href_key) or child.attrib.get(xlink_href_key, '')
                try:
                    x = float(child.attrib.get('x', 0))
                    y = float(child.attrib.get('y', 0))
                    w = float(child.attrib.get('width', 0))
                    h = float(child.attrib.get('height', 0))
                except (TypeError, ValueError):
                    parent.remove(child)
                    continue
                images.append((href, x, y, w, h))
                parent.remove(child)

    tmp_fd, tmp_svg = tempfile.mkstemp(suffix='.svg')
    os.close(tmp_fd)
    try:
        tree.write(tmp_svg, encoding='utf-8', xml_declaration=True)
        if not _rasterize(tmp_svg, png_path, dpi):
            return False
    finally:
        try:
            os.unlink(tmp_svg)
        except OSError:
            pass

    if not images:
        return True

    try:
        base = Image.open(png_path).convert('RGBA')
    except Exception:
        return True

    base_w, base_h = base.size
    px_per_unit_x = base_w / vb_w if vb_w else 0
    px_per_unit_y = base_h / vb_h if vb_h else 0

    for href, x, y, w, h in images:
        img = _decode_data_uri(href)
        if img is None:
            continue
        img = img.convert('RGBA')
        target_w = max(1, int(round(w * px_per_unit_x)))
        target_h = max(1, int(round(h * px_per_unit_y)))
        img = img.resize((target_w, target_h), Image.LANCZOS)
        pos_x = int(round((x - vb_x) * px_per_unit_x))
        pos_y = int(round((y - vb_y) * px_per_unit_y))

        layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
        layer.paste(img, (pos_x, pos_y))
        base = Image.alpha_composite(layer, base)

    base.convert('RGBA').save(png_path)
    return True
