"""Run navigation behavior tests against the actual shipped JavaScript."""
from pathlib import Path
import subprocess
import unittest


class LightboxJavaScriptTests(unittest.TestCase):
    def test_lightbox_navigation(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(['node', str(root / 'tests/lightbox_navigation.cjs')],
                       cwd=root, check=True, timeout=30)
