import unittest
import test_guests
from test_media_browsing import MediaHTML
from urllib.parse import parse_qs, urlsplit
from werkzeug.security import generate_password_hash
from wedding.store import connect


class LanguageTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login
    response = test_guests.GuestTests.response

    def client_for(self, code, client=None):
        client = client or self.app.test_client()
        self.assertEqual(self.login(code, client).status_code, 303)
        return client

    def db(self):
        return connect(self.app.config["DATABASE"])

    def seed(self, count=49):
        """49 guest-owned records: kind=image&owner=mine matches 25 records, so
        page 2 is a real page (the filter yields two pages with a single record).
        """
        with self.db() as db:
            db.execute("DELETE FROM uploads")
            for i in range(count):
                db.execute(
                    "INSERT INTO uploads (id, owner_id, owner_kind, original_name, content_type, size, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("a" + str(i).zfill(31), self.alice, "guest", f"photo{i}.png",
                     "image/png" if i % 2 == 0 else "video/mp4", 100, 1000 + i))

    def switch_links(self, page_text):
        """Header switch anchors have a lang attribute; other links do not."""
        return [(attrs['lang'], attrs['href'])
                for tag, attrs in MediaHTML(page_text).tags
                if tag == 'a' and attrs.get('lang') in ('pl', 'en')]

    def switch_pages(self, page_text):
        by_lang = {}
        for lang, href in self.switch_links(page_text):
            values = dict((key, values[0])
                         for key, values in parse_qs(urlsplit(href).query).items())
            self.assertNotIn("secret", values)
            self.assertNotIn("csrf_token", values)
            self.assertEqual(values.get("lang"), lang)
            by_lang[lang] = values
        return by_lang

    def test_media_language_switch_keeps_valid_selectors_replaces_lang(self):
        self.seed(49)
        alice = self.client_for(self.alice_code)
        page = self.get("/media?kind=image&owner=mine&page=2&lang=pl&secret=private&csrf_token=x", alice)
        self.assertEqual(page.status_code, 200)
        by_lang = self.switch_pages(page.text)
        self.assertEqual(by_lang["pl"],
                        {"kind": "image", "owner": "mine", "page": "2", "lang": "pl"})
        self.assertEqual(by_lang["en"],
                        {"kind": "image", "owner": "mine", "page": "2", "lang": "en"})
        original_ids = MediaHTML(page.text).ids()
        self.assertEqual(len(original_ids), 1)
        en_href = dict(self.switch_links(page.text))["en"]
        page = self.get(en_href, alice)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers['Content-Language'], 'en')
        self.assertEqual(MediaHTML(page.text).ids(), original_ids)
        self.assertEqual(self.switch_links(page.text),
                        [("pl", "/media?kind=image&owner=mine&page=2&lang=pl"),
                         ("en", "/media?kind=image&owner=mine&page=2&lang=en")])
        # Page 2 of 2 (25 matching images) holds a single record in both languages.
        self.assertIn("photo0.png", page.text)
        self.assertEqual(len(MediaHTML(page.text).ids()), 1)
        pl_href = dict(self.switch_links(page.text))["pl"]
        page = self.get(pl_href, alice)
        self.assertEqual(page.headers['Content-Language'], 'pl')
        self.assertEqual(MediaHTML(page.text).ids(), original_ids)

    def test_media_language_switch_is_plain_url_without_selectors(self):
        self.seed(25)
        alice = self.client_for(self.alice_code)
        by_lang = self.switch_pages(self.get("/media?lang=pl", alice).text)
        self.assertEqual(by_lang, {"pl": {"lang": "pl"}, "en": {"lang": "en"}})

    def test_other_pages_do_not_carry_media_selectors(self):
        alice = self.client_for(self.alice_code)
        page = self.get("/guest?kind=image&owner=mine&page=2&secret=x", alice)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.switch_links(page.text),
                        [("pl", "/guest?lang=pl"), ("en", "/guest?lang=en")])

    def test_media_400_switch_links_are_plain_and_safe(self):
        alice = self.client_for(self.alice_code)
        for query in ("/media?kind=bad&lang=pl", "/media?kind=all&kind=image&owner=mine&lang=pl",
                     "/media?page=abc&lang=pl", "/media?kind=1&lang=pl",
                     "/media?owner=1&lang=pl", "/media?kind=image&owner=mine&page=²&lang=pl",
                     "/media?kind=image&owner=mine&page=2&page=3&lang=pl"):
            page = self.get(query, alice)
            self.assertEqual(page.status_code, 400)
            self.assertEqual(self.switch_links(page.text),
                           [("pl", "/media?lang=pl"), ("en", "/media?lang=en")])

    def test_default_polish_switch_and_cookie_persistence(self):
        self.assertIn('<html lang="pl">', self.get('/').text)
        page = self.get('/?lang=en')
        self.assertIn('<html lang="en">', page.text)
        self.assertIn('Wedding ceremony', page.text)
        self.assertIn('27 August 2027', page.text)
        self.assertEqual(page.headers['Content-Language'], 'en')
        cookie = self.client.get_cookie('__Host-wedding-language')
        self.assertEqual(cookie.value, 'en')
        for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/'):
            self.assertIn(flag, page.headers['Set-Cookie'])
        self.assertIn('Invitation code', self.get('/login').text)
        self.assertIn('Couple’s dashboard', self.get('/admin/login').text)
        self.assertIn('<html lang="pl">', self.get('/?lang=pl').text)

    def test_preferences_are_independent_and_invalid_language_is_ignored(self):
        self.get('/?lang=en')
        self.assertIn('<html lang="pl">', self.get('/', self.app.test_client()).text)
        page = self.get('/?lang=%3Cscript%3E')
        self.assertIn('<html lang="en">', page.text)
        self.assertNotIn('<script>', page.text)
        self.assertIn('<html lang="en">', self.get('/?lang=fr').text)

    def test_guest_rsvp_and_logout_keep_language_and_database_values(self):
        self.get('/?lang=en')
        self.login()
        page = self.get()
        for text in ('Your invitation', 'Vegetarian', 'Will you need accommodation?', 'Save RSVP'):
            self.assertIn(text, page.text)
        self.assertIn('Prywatna sala weselna', page.text)
        self.response()
        page = self.get()
        self.assertIn('Your RSVP has been saved', page.text)
        self.assertIn('Prywatna alergia', page.text)
        with connect(self.app.config['DATABASE']) as db:
            row = db.execute('SELECT * FROM rsvps WHERE guest_id=?', (self.alice,)).fetchone()
            self.assertEqual((row['attendance'], row['diet'], row['lodging']), ('yes', 'vegan', 'yes'))
        self.post('/logout', {'csrf_token': self.token('/guest')})
        self.assertIn('<html lang="en">', self.get('/').text)

    def test_english_errors_and_validation_messages(self):
        self.get('/?lang=en')
        response = self.post('/login', {'csrf_token': self.token(), 'code': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertIn('Check your invitation code', response.text)
        response = self.post('/login', {})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Refresh the page', response.text)
        page = self.get('/missing')
        self.assertEqual(page.status_code, 404)
        self.assertIn('Unable to open this page', page.text)

    def test_admin_and_one_time_code_use_selected_language(self):
        self.get('/admin/login?lang=en')
        with connect(self.app.config['DATABASE']) as db:
            db.execute('INSERT INTO administrators VALUES (?, ?)', ('para', generate_password_hash('test-admin-password')))
        self.post('/admin/login', {'csrf_token': self.token('/admin/login'), 'username': 'para', 'password': 'test-admin-password'})
        page = self.get('/admin')
        for text in ('Everything in one place', 'Add guests', 'Generate a new code', 'Change password'):
            self.assertIn(text, page.text)
        page = self.post('/admin/guests', {'csrf_token': self.token('/admin'), 'name': 'Goście testowi'})
        self.assertEqual(page.status_code, 200)
        self.assertIn('This code is shown only once', page.text)
        self.assertIn('Goście testowi', page.text)
        self.assertNotIn('language-switch', page.text)
        self.assertIn('Copy code', page.text)
        self.assertIn('Panel pary młodej', self.get('/admin/login?lang=pl', self.app.test_client()).text)
