from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackagingArtifactTests(unittest.TestCase):
    def test_built_sdist_and_wheel_exclude_junk_and_include_key_docs(self):
        repo_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            subprocess.run(
                [sys.executable, '-m', 'build', '--sdist', '--wheel', '--outdir', str(outdir)],
                cwd=repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            sdists = list(outdir.glob('*.tar.gz'))
            wheels = list(outdir.glob('*.whl'))
            self.assertEqual(len(sdists), 1)
            self.assertEqual(len(wheels), 1)

            with tarfile.open(sdists[0], 'r:gz') as tf:
                sdist_names = tf.getnames()
            with zipfile.ZipFile(wheels[0]) as zf:
                wheel_names = zf.namelist()

            for archive_names in (sdist_names, wheel_names):
                joined = '\n'.join(archive_names)
                self.assertNotIn('__pycache__', joined)
                self.assertNotIn('.pyc', joined)
                self.assertNotIn('.pyo', joined)

            sdist_joined = '\n'.join(sdist_names)
            self.assertIn('README.md', sdist_joined)
            self.assertIn('conf.example.toml', sdist_joined)
            self.assertIn('STARTER_RENAME_GUIDE.md', sdist_joined)
            self.assertIn('RELEASE_CHECKLIST.md', sdist_joined)

            wheel_joined = '\n'.join(wheel_names)
            self.assertIn('landing_gear/__init__.py', wheel_joined)
            self.assertIn('hello_service/__init__.py', wheel_joined)


if __name__ == '__main__':
    unittest.main()
