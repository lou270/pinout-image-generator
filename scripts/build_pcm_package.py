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
IDENTIFIER  = 'com.lou270.pinout-image-generator'

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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default=str(DEFAULT_OUT))
    parser.add_argument('--download-url-base',
                        help='Override the download_url host (used in CI on a tag)')
    parser.add_argument('--tag',
                        help='Git tag name (e.g. v1.0.0) to synchronize version and URL')
    args = parser.parse_args(argv)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load the tracked metadata.json and compute derived fields.
    metadata = json.loads((ROOT / 'metadata.json').read_text(encoding='utf-8'))
    identifier = metadata.get('identifier', 'com.github.lou270.pinout-image-generator')
    zip_path = out_dir / f'{identifier}.zip'
    install_size = compute_install_size()

    version_entry = metadata['versions'][0]
    if args.tag:
        tag_name = args.tag
        version_entry['version'] = tag_name.lstrip('v')
    else:
        tag_name = f"v{version_entry['version']}"

    # Inside the zip package, metadata must have version/status/kicad_version
    # but MUST NOT have download_* or install_size fields.
    pkg_metadata = {
        k: v for k, v in metadata.items() if k != 'versions'
    }
    pkg_version = {
        'version': version_entry['version'],
        'status': version_entry.get('status', 'stable'),
        'kicad_version': version_entry.get('kicad_version', '10.0'),
    }
    if 'runtime' in version_entry:
        pkg_version['runtime'] = version_entry['runtime']
    if 'kicad_version_max' in version_entry:
        pkg_version['kicad_version_max'] = version_entry['kicad_version_max']
    if 'platforms' in version_entry:
        pkg_version['platforms'] = version_entry['platforms']
    pkg_metadata['versions'] = [pkg_version]

    # Write zip with clean packaged metadata.
    write_zip(zip_path, pkg_metadata)

    # Repository sidecar metadata (contains download_* and install_size).
    repo_metadata = {
        k: v for k, v in metadata.items() if k != 'versions'
    }
    repo_version = dict(pkg_version)
    repo_version['install_size'] = install_size
    repo_version['download_size'] = zip_path.stat().st_size
    repo_version['download_sha256'] = sha256_of(zip_path)
    if args.download_url_base:
        repo_version['download_url'] = (
            f'{args.download_url_base.rstrip("/")}/{tag_name}/{identifier}.zip'
        )
    elif 'download_url' in version_entry:
        repo_version['download_url'] = version_entry['download_url']
    else:
        repo_version['download_url'] = (
            f'https://github.com/lou270/pinout-image-generator/releases/download/{tag_name}/{identifier}.zip'
        )
    repo_metadata['versions'] = [repo_version]

    # Write sidecar metadata.json
    sidecar = out_dir / 'metadata.json'
    sidecar.write_text(json.dumps(repo_metadata, indent=2) + '\n', encoding='utf-8')

    print(f'Built: {zip_path}')
    print(f'  version:         {repo_version["version"]}')
    print(f'  install_size:    {install_size}')
    print(f'  download_size:   {repo_version["download_size"]}')
    print(f'  download_sha256: {repo_version["download_sha256"]}')
    print(f'Sidecar metadata: {sidecar}')


if __name__ == '__main__':
    sys.exit(main())
