########################################
# Pinout image builder — KiCad board parser
# Louis Barbier
# MIT License
########################################
"""Extract pad positions, net names and net classes from a KiCad BOARD.

Only usable inside KiCad (requires pcbnew) or tested with duck-typed board objects.
The parser produces Pin objects (Pin.py) and sidecar metadata dicts.
"""

import json
import os
import re

from Pin import Pin

try:
    import pcbnew
except ImportError:
    pcbnew = None


# Connector / pin header regex pattern (matches J1, CN1, P1, HDR1, CONN1, HEADER1)
# Note: 'U' and 'MOD' (ICs and modules) are excluded from the default connector pattern
# so IC pins (e.g. 32-pin / 48-pin MCUs) are not lumped into connector pinouts by default.
DEFAULT_CONNECTOR_PATTERN = r'^(J|CN|P|HDR|CONN|HEADER)\d*'


def _to_mm(value_nm):
    """Wrap pcbnew.ToMM which handles ints, floats, and VECTOR2I across KiCad versions."""
    if pcbnew is not None and hasattr(pcbnew, 'ToMM'):
        return pcbnew.ToMM(value_nm)
    return float(value_nm) / 1e6


def _is_dnp(fp):
    """Check if footprint has the 'Do not populate' (DNP) attribute set."""
    if hasattr(fp, 'IsDNP'):
        return bool(fp.IsDNP())
    if hasattr(fp, 'GetDNP'):
        return bool(fp.GetDNP())
    return False


def load_netclass_map(path=None):
    """Load the net-name → function regex rules."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'netclass_map.json')
    if not os.path.isfile(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('rules', [])


def match_function(net_name, net_class, rules):
    """Return the first matching function name, or ''."""
    for key in (net_name or '', net_class or ''):
        if not key:
            continue
        for rule in rules:
            try:
                if re.match(rule['pattern'], key, re.IGNORECASE):
                    return rule['function']
            except re.error:
                continue
    return ''


def list_footprints(board):
    """Return [(reference, footprint)] for every footprint on the board."""
    if pcbnew is None and not hasattr(board, 'GetFootprints'):
        raise RuntimeError('pcbnew is not available — this function must run inside KiCad or with a valid board object.')
    return [(fp.GetReference(), fp) for fp in board.GetFootprints()]


def get_board_footprint_info(board, pattern=DEFAULT_CONNECTOR_PATTERN):
    """Return list of dicts describing all footprints with pads on the board."""
    fps = list_footprints(board)
    info = []
    for ref, fp in fps:
        pad_count = len(list(fp.Pads()))
        if pad_count == 0:
            continue
        is_sel = getattr(fp, 'IsSelected', lambda: False)()
        is_conn = bool(re.match(pattern, ref, re.IGNORECASE))
        is_dnp_val = _is_dnp(fp)
        info.append({
            'ref': ref,
            'pad_count': pad_count,
            'selected': is_sel,
            'is_connector': is_conn,
            'dnp': is_dnp_val,
        })
    return info


def get_candidate_footprints(board, pattern=DEFAULT_CONNECTOR_PATTERN, include_dnp=False):
    """Return a list of footprint references that look like connectors/headers."""
    fps = list_footprints(board)
    candidates = []
    for ref, fp in fps:
        if not include_dnp and _is_dnp(fp):
            continue
        if re.match(pattern, ref, re.IGNORECASE):
            candidates.append(ref)

    if not candidates:
        # Fallback: all footprints that have pads (excluding DNP unless requested)
        candidates = [ref for ref, fp in fps if len(list(fp.Pads())) > 0 and (include_dnp or not _is_dnp(fp))]
    return candidates


def _pad_radius_mm(pad):
    """Approximate pad radius in mm (max of X/Y half-size)."""
    size = pad.GetSize()
    sx = _to_mm(size.x) if hasattr(size, 'x') else _to_mm(size[0])
    sy = _to_mm(size.y) if hasattr(size, 'y') else _to_mm(size[1])
    return max(sx, sy) / 2.0


def _board_bbox_mm(board):
    """Return (min_x, min_y, width, height) in mm of the board edge."""
    bbox = board.GetBoardEdgesBoundingBox()
    return (
        _to_mm(bbox.GetX()),
        _to_mm(bbox.GetY()),
        _to_mm(bbox.GetWidth()),
        _to_mm(bbox.GetHeight()),
    )


def _detect_side(cx, cy, bbox_mm):
    """Detect 'left', 'right', 'top', or 'bottom' based on board bounding box & coordinates."""
    min_x, min_y, w, h = bbox_mm
    if w <= 0 or h <= 0:
        return 'left'

    cxr = cx - min_x
    cyr = cy - min_y

    rx = cxr / w
    ry = cyr / h

    distances = {
        'left':   rx,
        'right':  1.0 - rx,
        'top':    ry,
        'bottom': 1.0 - ry,
    }
    return min(distances, key=distances.get)


def parse_footprint(footprint, board, rules=None):
    """Extract pins from a single footprint.

    Returns (pins, metadata) where metadata is a dict pin.number → {
        'net_name', 'net_class', 'suggested_function', 'pad_name', 'footprint', 'dnp'
    }.
    """
    if pcbnew is None and not hasattr(board, 'GetBoardEdgesBoundingBox'):
        raise RuntimeError('pcbnew is not available — this function must run inside KiCad or with a valid board object.')
    if rules is None:
        rules = load_netclass_map()

    bbox_mm = _board_bbox_mm(board)
    pins = []
    meta = {}
    fp_ref = footprint.GetReference()
    is_dnp_val = _is_dnp(footprint)
    pads = list(footprint.Pads())

    if pads:
        # Determine dominant side from footprint centroid so header pins stay grouped
        all_cx = [_to_mm(p.GetPosition().x if hasattr(p.GetPosition(), 'x') else p.GetPosition()[0]) for p in pads]
        all_cy = [_to_mm(p.GetPosition().y if hasattr(p.GetPosition(), 'y') else p.GetPosition()[1]) for p in pads]
        fp_cx = sum(all_cx) / len(all_cx)
        fp_cy = sum(all_cy) / len(all_cy)
        fp_default_side = _detect_side(fp_cx, fp_cy, bbox_mm)
    else:
        fp_default_side = 'left'

    for idx, pad in enumerate(pads, start=1):
        pos = pad.GetPosition()
        cx = _to_mm(pos.x) if hasattr(pos, 'x') else _to_mm(pos[0])
        cy = _to_mm(pos.y) if hasattr(pos, 'y') else _to_mm(pos[1])
        r = _pad_radius_mm(pad)
        side = fp_default_side
        pad_num = pad.GetName() or str(idx)

        pin = Pin(cx=cx, cy=cy, r=r, number=idx, side=side, pad_name=pad_num, footprint=fp_ref)
        net_name = pad.GetNetname() if pad.GetNet() else ''
        try:
            net_class = pad.GetNetClassName()
        except AttributeError:
            net_class = ''

        meta[idx] = {
            'net_name':           net_name,
            'net_class':          net_class,
            'suggested_function': match_function(net_name, net_class, rules),
            'pad_name':           pad_num,
            'footprint':          fp_ref,
            'dnp':                is_dnp_val,
        }
        pins.append(pin)

    return pins, meta


def parse_board(board, footprint_ref=None, rules=None, pattern=DEFAULT_CONNECTOR_PATTERN, include_dnp=False):
    """Extract pins from specified footprint(s) or all detected connector footprints.

    Args:
        board: pcbnew.BOARD instance or duck-typed board object.
        footprint_ref: str (e.g. 'J1'), list of str, or None (checks selected, then pattern).
        rules: pre-loaded netclass_map rules or None.
        pattern: regex pattern to match connector references when footprint_ref is None.
        include_dnp: if False, skips footprints marked with DNP (Do Not Populate).

    Returns:
        (pins: list[Pin], meta: dict, svg_size_mm: tuple[float, float])
    """
    if pcbnew is None and not hasattr(board, 'GetFootprints'):
        raise RuntimeError('pcbnew is not available — this function must run inside KiCad or with a valid board object.')

    rules = rules or load_netclass_map()
    bbox = _board_bbox_mm(board)
    svg_size_mm = (bbox[2], bbox[3])

    all_fps = list_footprints(board)

    if footprint_ref:
        if isinstance(footprint_ref, str):
            target_refs = {footprint_ref}
        else:
            target_refs = set(footprint_ref)
        fps = [fp for ref, fp in all_fps if ref in target_refs]
    else:
        # Check if any footprints are currently selected in KiCad editor
        selected_fps = [fp for _, fp in all_fps if getattr(fp, 'IsSelected', lambda: False)()]
        if selected_fps:
            fps = selected_fps
        else:
            fps = [fp for ref, fp in all_fps if re.match(pattern, ref, re.IGNORECASE) and (include_dnp or not _is_dnp(fp))]
            if not fps:
                # Fallback to all footprints with pads (excluding DNP unless requested)
                fps = [fp for ref, fp in all_fps if len(list(fp.Pads())) > 0 and (include_dnp or not _is_dnp(fp))]

    all_pins, all_meta = [], {}
    offset = 0
    for fp in fps:
        pins, meta = parse_footprint(fp, board, rules)
        for pin in pins:
            # Shift pads to origin of the board bounding box
            pin.cx -= bbox[0]
            pin.cy -= bbox[1]
            pin.number += offset
        all_pins.extend(pins)
        for k, v in meta.items():
            all_meta[k + offset] = v
        offset += len(pins)

    return all_pins, all_meta, svg_size_mm
