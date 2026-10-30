"""Preview navigation must stay within the photos on the rendered gallery page."""
from html.parser import HTMLParser
import unittest

import test_guests
from wedding.store import connect


class PreviewButtons(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.sources = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button' and 'data-media-open' in attrs:
            self.sources.append(attrs['data-media-src'])


class LightboxGalleryScopeTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login

    def test_navigation_only_uses_previewable_photos_on_current_page(self):
        with connect(self.app.config['DATABASE']) as db:
            for i in range(26):
                kind = 'video/mp4' if i == 1 else 'image/svg+xml' if i == 2 else 'image/jpeg'
                db.execute('INSERT INTO uploads VALUES (?,?,?,?,?,?,?)',
                           (f'{i:032x}', self.alice, 'guest', f'photo-{i}', kind, 10, 1000))
        self.login()
        first = PreviewButtons(self.get('/media').text).sources
        second = PreviewButtons(self.get('/media?page=2').text).sources
        self.assertEqual(first, [f'/media/{i:032x}' for i in range(24) if i not in (1, 2)])
        self.assertEqual(second, [f'/media/{i:032x}' for i in range(24, 26)])
        filtered = PreviewButtons(self.get('/media?kind=video').text).sources
        self.assertEqual(filtered, [])
