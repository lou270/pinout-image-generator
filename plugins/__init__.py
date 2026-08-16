########################################
# Pinout image builder — KiCad plugin entry point
# Louis Barbier
# MIT License
########################################
"""KiCad loads this file automatically from the plugins directory.

We register the ActionPlugin only when pcbnew is importable (i.e. running
inside KiCad). Outside KiCad — for CLI or standalone GUI use — main.py
and gui.py insert plugins/ into sys.path and import the modules directly,
so this guard prevents import errors on those paths.
"""

import os
import sys

# Ensure sibling modules (Pin, svg, save, …) are importable by the plugin
# when KiCad's loader executes __init__.py with plugins/ as CWD.
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

try:
    import pcbnew  # noqa: F401
except ImportError:
    pcbnew = None

if pcbnew is not None:
    try:
        from pinout_plugin import PinoutPlugin
        PinoutPlugin().register()
    except Exception as _exc:
        # Never crash KiCad on startup — log and continue.
        import traceback
        sys.stderr.write(f'[pinout-image-generator] plugin registration failed: {_exc}\n')
        sys.stderr.write(traceback.format_exc())
