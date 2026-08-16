########################################
# Pinout image builder — Configuration persistence
# Louis Barbier
# MIT License
########################################
"""Save and restore pinout configurations to/from JSON."""

import json
import os


def to_json(filename, data):
    """Save data to a JSON file."""
    with open(filename, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, indent=2, ensure_ascii=False)


def from_json(filename):
    """Load data from a JSON file."""
    with open(filename, 'r', encoding='utf-8') as json_file:
        return json.load(json_file)


def get_default_config_path(base_path):
    """Derive standard *_pinout_config.json path from board or SVG path."""
    if not base_path:
        return None
    root, _ = os.path.splitext(base_path)
    return root + '_pinout_config.json'


def save_pinout_config(filepath, config_data):
    """Save complete pinout project configuration to JSON."""
    to_json(filepath, config_data)


def load_pinout_config(filepath):
    """Load pinout project configuration from JSON file. Returns dict or None."""
    if not filepath or not os.path.isfile(filepath):
        return None
    try:
        return from_json(filepath)
    except Exception:
        return None