import json
import os
import sys
import tempfile
import unittest
import zipfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, 'scripts'))

import build_pcm_package


class TestPcmPackage(unittest.TestCase):

    def test_compute_install_size(self):
        size = build_pcm_package.compute_install_size()
        self.assertGreater(size, 1000)

    def test_build_pcm_package_run(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, f'{build_pcm_package.IDENTIFIER}.zip')

            metadata_path = os.path.join(ROOT_DIR, 'metadata.json')
            self.assertTrue(os.path.isfile(metadata_path))

            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            build_pcm_package.write_zip(zip_path, metadata)
            self.assertTrue(os.path.isfile(zip_path))

            # Inspect zip contents
            with zipfile.ZipFile(zip_path, 'r') as zf:
                namelist = zf.namelist()
                self.assertIn('metadata.json', namelist)
                self.assertTrue(any(name.startswith('plugins/') for name in namelist))
                self.assertTrue(any(name.startswith('resources/') for name in namelist))


if __name__ == '__main__':
    unittest.main()
