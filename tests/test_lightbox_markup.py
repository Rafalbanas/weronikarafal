"""The rendered dialog must match the navigation JavaScript's DOM contract."""
from html.parser import HTMLParser
import unittest

import test_guests
from wedding.store import connect


class LightboxMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def marked(self, marker):
        return [(tag, attrs) for tag, attrs in self.tags if marker in attrs]


class LightboxMarkupTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login

    def test_dialog_contract_and_translations(self):
        self.login()
        for lang, template, prev, next_label, close in (
            ('pl', 'Zdjęcie {current} z {total}', 'Poprzednie zdjęcie', 'Następne zdjęcie', 'Zamknij podgląd'),
            ('en', 'Photo {current} of {total}', 'Previous photo', 'Next photo', 'Close preview'),
        ):
            with self.subTest(lang=lang):
                response = self.get('/media?lang=' + lang)
                self.assertEqual(response.status_code, 200)
                parsed = LightboxMarkup(response.text)
                for marker in ('data-media-lightbox', 'data-media-lightbox-image', 'data-media-prev',
                               'data-media-next', 'data-media-navigation', 'data-media-counter', 'data-media-caption'):
                    self.assertEqual(len(parsed.marked(marker)), 1, marker)
                tag, attrs = parsed.marked('data-media-lightbox')[0]
                self.assertEqual(tag, 'dialog')
                self.assertEqual(attrs['data-counter-template'], template)
                self.assertIn('hidden', parsed.marked('data-media-navigation')[0][1])
                for marker in ('data-media-prev', 'data-media-next'):
                    tag, attrs = parsed.marked(marker)[0]
                    self.assertEqual((tag, attrs.get('type')), ('button', 'button'))
                counter = parsed.marked('data-media-counter')[0][1]
                self.assertEqual((counter['role'], counter['aria-live'], counter['aria-atomic']),
                                 ('status', 'polite', 'true'))
                self.assertTrue(any(tag == 'form' and attrs.get('method') == 'dialog'
                                    for tag, attrs in parsed.tags))
                self.assertTrue(any(tag == 'button' and attrs.get('aria-label') == close
                                    for tag, attrs in parsed.tags))
                self.assertIn(prev, response.text)
                self.assertIn(next_label, response.text)

    def test_filename_is_escaped_for_preview_data(self):
        name = '<img src=x onerror="alert(1)"> & ślub.png'
        with connect(self.app.config['DATABASE']) as db:
            db.execute('INSERT INTO uploads VALUES (?,?,?,?,?,?,?)',
                       ('f' * 32, self.alice, 'guest', name, 'image/png', 100, 1000))
        self.login()
        response = self.get('/media')
        parsed = LightboxMarkup(response.text)
        self.assertEqual(parsed.marked('data-media-open')[0][1]['data-media-alt'], name)
        self.assertNotIn('<img src=x onerror=', response.text)
        self.assertFalse(any('onerror' in attrs for _, attrs in parsed.tags))

    def test_anonymous_gallery_remains_protected(self):
        self.assertEqual(self.get('/media').status_code, 303)
