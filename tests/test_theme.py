from html.parser import HTMLParser
from pathlib import Path
import subprocess
import unittest

import test_guests


class ThemeMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.controls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-theme-toggle' in attrs:
            self.controls.append((tag, attrs))


class ThemeTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login

    def test_translated_theme_toggle_on_public_and_private_pages(self):
        self.login()
        for path in ('/', '/guest', '/media', '/schedule', '/tables'):
            for lang, label in (('pl', 'Ciemny motyw'), ('en', 'Dark theme')):
                page = self.get(path + '?lang=' + lang)
                self.assertEqual(page.status_code, 200)
                controls = ThemeMarkup(page.text).controls
                self.assertEqual(len(controls), 1)
                tag, attrs = controls[0]
                self.assertEqual((tag, attrs['type'], attrs['aria-pressed']), ('button', 'button', 'false'))
                self.assertIn('hidden', attrs)
                self.assertIn(label, page.text)

    def test_preference_javascript(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run(['node', str(root / 'tests/theme_preference.cjs')],
                       cwd=root, check=True, timeout=30)
