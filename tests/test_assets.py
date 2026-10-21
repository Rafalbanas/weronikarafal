import hashlib
from pathlib import Path
import re
import shutil
import unittest
from unittest.mock import patch
import test_guests
from app import create_app


class AssetCacheTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get

    def test_asset_urls_use_content_versions_and_serve_expected_source(self):
        page = self.get('/')
        root = Path(__file__).resolve().parents[1] / 'assets'
        for name in ('site.js', 'site.css', 'favicon.svg'):
            content = (root / name).read_bytes()
            version = hashlib.sha256(content).hexdigest()[:16]
            url = f'/assets/{name}?v={version}'
            self.assertIn(url, page.text)
            with self.get(url) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, content)
        self.assertNotRegex(page.text, r'(?:src|href)="/assets/[^"?]+"')

    def test_changed_javascript_gets_a_new_url_for_cached_clients(self):
        source = Path(__file__).resolve().parents[1]
        release = self.root / 'release'
        release.mkdir()
        shutil.copytree(source / 'assets', release / 'assets')
        (release / 'templates').symlink_to(source / 'templates', target_is_directory=True)
        (release / 'index.html').symlink_to(source / 'index.html')
        with patch('app.ROOT', release):
            first = create_app(self.app.config).test_client().get('/', base_url='https://localhost')
            with (release / 'assets/site.js').open('a') as script:
                script.write('\n// Changed release for cache regression.\n')
            client = create_app(self.app.config).test_client()
            second = client.get('/', base_url='https://localhost')
        old_url = re.search(r'src="([^"]*site.js[^"]*)"', first.text).group(1)
        new_url = re.search(r'src="([^"]*site.js[^"]*)"', second.text).group(1)
        self.assertNotEqual(old_url, new_url)
        with client.get(new_url, base_url='https://localhost') as response:
            self.assertIn(b'Changed release for cache regression', response.data)
