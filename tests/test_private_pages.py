import json
import unittest

import test_admin
from wedding.store import connect, revoke


class PrivatePagesTests(unittest.TestCase):
    setUp = test_admin.AdminTests.setUp
    get = test_admin.AdminTests.get
    post = test_admin.AdminTests.post
    token = test_admin.AdminTests.token
    login = test_admin.AdminTests.login
    admin_login = test_admin.AdminTests.admin_login

    def test_anonymous_access_is_redirected_and_not_indexable(self):
        for path in ('/schedule', '/tables', '/schedule?admin=1', '/tables?guest=1'):
            response = self.get(path)
            self.assertEqual(response.status_code, 303)
            self.assertIn('/login', response.location)
            self.assertIn('noindex', response.headers['X-Robots-Tag'])
        robots = self.get('/robots.txt').text
        self.assertIn('Disallow: /schedule', robots)
        self.assertIn('Disallow: /tables', robots)
        public = self.get('/').text
        self.assertNotIn('href="/schedule"', public)
        self.assertNotIn('href="/tables"', public)

    def test_guest_pages_have_translated_placeholders_and_navigation(self):
        self.login()
        for path, heading_pl, heading_en, placeholder_pl, placeholder_en in (
            ('/schedule', 'Harmonogram', 'Schedule', 'Rozpiska godzinowa pojawi się wkrótce', 'The schedule is coming soon'),
            ('/tables', 'Rozmieszczenie stołów', 'Seating plan', 'Plan stołów pojawi się wkrótce', 'The seating plan is coming soon'),
        ):
            for lang, heading, placeholder in (('pl', heading_pl, placeholder_pl), ('en', heading_en, placeholder_en)):
                with self.subTest(path=path, lang=lang):
                    response = self.get(path + '?lang=' + lang)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('<h1>' + heading + '</h1>', response.text)
                    self.assertIn(placeholder, response.text)
                    self.assertIn('noindex', response.headers['X-Robots-Tag'])
                    self.assertIn('no-store', response.headers['Cache-Control'])
                    for href in ('/guest', '/schedule', '/tables'):
                        self.assertIn('href="' + href + '"', response.text)
                    self.assertIn('href="' + path + '?lang=en"', response.text)
                    self.assertNotIn('id="rsvpForm"', response.text)
                    self.assertNotIn('Gość Beta', response.text)
        guest = self.get('/guest').text
        self.assertIn('href="/schedule"', guest)
        self.assertIn('href="/tables"', guest)

    def test_schedule_can_be_filled_later_without_public_leaks(self):
        details_path = self.root / 'details.json'
        details = json.loads(details_path.read_text())
        details['schedule'] = [
            {'time': '16:30', 'title': 'Prywatny punkt planu', 'description': 'Prywatny opis'},
            {'time': '18:00', 'title': '<script>alert(1)</script>', 'description': '<img src=x onerror=alert(1)>'},
        ]
        details_path.write_text(json.dumps(details))
        self.assertNotIn('Prywatny punkt planu', self.get('/').text)
        self.assertNotIn('Prywatny punkt planu', self.get('/schedule').text)
        self.login()
        page = self.get('/schedule').text
        for text in ('<time>16:30</time>', '<time>18:00</time>', 'Prywatny punkt planu', 'Prywatny opis'):
            self.assertIn(text, page)
        self.assertLess(page.index('16:30'), page.index('18:00'))
        self.assertNotIn('Rozpiska godzinowa pojawi się wkrótce', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert(1)', page)
        self.assertNotIn('<img src=x onerror=', page)
        self.assertNotIn('Prywatny punkt planu', self.get('/tables').text)

    def test_admin_can_read_both_pages(self):
        self.admin_login()
        for path in ('/schedule', '/tables'):
            response = self.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('href="/admin"', response.text)
            self.assertNotIn('id="rsvpForm"', response.text)

    def test_revoked_invitation_loses_access(self):
        self.login()
        self.assertEqual(self.get('/schedule').status_code, 200)
        with connect(self.app.config['DATABASE']) as db:
            revoke(db, self.alice)
        self.assertEqual(self.get('/schedule').status_code, 303)
        self.assertEqual(self.get('/tables').status_code, 303)
