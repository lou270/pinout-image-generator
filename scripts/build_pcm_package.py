#!/usr/bin/env python3
"""Build the KiCad PCM distribution zip for pinout-maker.

Produces dist/com.lou270.pinout_maker.zip containing:
  - metadata.json  (with download_sha256 / download_size / install_size patched)
  - plugins/       (Python sources)
  - resources/     (icon)

Usage:
  python scripts/build_pcm_package.py [--output-dir dist] [--tag v1.0.0]
"""

import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT        = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'dist'
IDENTIFIER  = 'com.lou270.pinout_maker'

INCLUDED_DIRS  = ['plugins', 'resources']
INCLUDED_FILES = ['metadata.json']
EXCLUDE_NAMES  = {'__pycache__', '.git', '.pytest_cache'}
EXCLUDE_SUFFIX = ('.pyc', '.pyo')


def iter_files(base: Path):
    """Yield every file under `base` to include in the zip, relative to ROOT."""
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_NAMES]
        for f in files:
            if f in EXCLUDE_NAMES or f.endswith(EXCLUDE_SUFFIX):
                continue
            yield Path(root) / f


def compute_install_size():
    total = 0
    for dname in INCLUDED_DIRS:
        for fpath in iter_files(ROOT / dname):
            total += fpath.stat().st_size
    for fname in INCLUDED_FILES:
        total += (ROOT / fname).stat().st_size
    return total


def write_zip(zip_path: Path, metadata_override: dict):
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # Write patched metadata.json at the root of the zip.
        zf.writestr('metadata.json',
                    json.dumps(metadata_override, indent=2) + '\n')

        for dname in INCLUDED_DIRS:
            for fpath in iter_files(ROOT / dname):
                arcname = fpath.relative_to(ROOT).as_posix()
                zf.write(fpath, arcname)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default=str(DEFAULT_OUT))
    parser.add_argument('--download-url-base',
                        help='Override the download_url host (used in CI on a tag)')
    parser.add_argument('--tag',
                        help='Git tag name (e.g. v1.0.0) to synchronize version and URL')
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f'{IDENTIFIER}.zip'

    # Load the tracked metadata.json and compute derived fields.
    metadata = json.loads((ROOT / 'metadata.json').read_text(encoding='utf-8'))
    install_size = compute_install_size()

    version_entry = metadata['versions'][0]
    if args.tag:
        tag_name = args.tag
        version_entry['version'] = tag_name.lstrip('v')
    else:
        tag_name = f"v{version_entry['version']}"

    version_entry['install_size'] = install_size
    version_entry['download_size'] = 0
    version_entry['download_sha256'] = '0' * 64
    if args.download_url_base:
        version_entry['download_url'] = (
            f'{args.download_url_base.rstrip("/")}/{tag_name}/{IDENTIFIER}.zip'
        )

    # Pass 1: write zip with placeholder hash.
    write_zip(zip_path, metadata)

    # Pass 2: compute actual hash + size of the written zip, then rewrite.
    version_entry['download_size'] = zip_path.stat().st_size
    version_entry['download_sha256'] = sha256_of(zip_path)
    write_zip(zip_path, metadata)

    # Also write an updated metadata.json alongside for repository publishing.
    sidecar = out_dir / 'metadata.json'
    sidecar.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')

    print(f'Built: {zip_path}')
    print(f'  version:         {version_entry["version"]}')
    print(f'  install_size:    {install_size}')
    print(f'  download_size:   {version_entry["download_size"]}')
    print(f'  download_sha256: {version_entry["download_sha256"]}')
    print(f'Sidecar metadata: {sidecar}')


if __name__ == '__main__':
    sys.exit(main())
