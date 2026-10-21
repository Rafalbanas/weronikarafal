import unittest
import test_guests
from werkzeug.security import generate_password_hash
from wedding.store import connect


class LanguageTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login
    response = test_guests.GuestTests.response

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
