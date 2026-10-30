"""Correcting invitation names must not rotate credentials or invalidate RSVP."""
import unittest

import test_admin
import test_households
from wedding.store import connect, normalize_code


class InvitationNameEditTests(unittest.TestCase):
    setUp = test_admin.AdminTests.setUp
    get = test_admin.AdminTests.get
    post = test_admin.AdminTests.post
    token = test_admin.AdminTests.token
    login = test_admin.AdminTests.login
    admin_login = test_admin.AdminTests.admin_login
    action = test_admin.AdminTests.action
    code = test_admin.AdminTests.code
    add = test_households.HouseholdTests.add

    def test_correcting_both_names_preserves_code_sessions_and_rsvp(self):
        self.admin_login()
        code = self.code(self.add(name='Ewa testowa', kind='couple', partner_name='Jan przykładowy',
                                  children_count='1', children=['Dziecko Testowe']))
        with connect(self.app.config['DATABASE']) as db:
            before = dict(db.execute('SELECT * FROM guests WHERE name=?', ('Ewa testowa',)).fetchone())
            guest_count = db.execute('SELECT count(*) FROM guests').fetchone()[0]
        guest_id = before['id']
        guest = self.app.test_client()
        self.assertEqual(self.login(code, guest).status_code, 303)
        self.assertEqual(self.post('/rsvp', {
            'csrf_token': self.token('/guest', guest), 'attendance': 'yes', 'diet': 'vegan',
            'lodging': 'yes', 'notes': 'Prywatne uwagi testowe',
        }, guest).status_code, 303)
        with connect(self.app.config['DATABASE']) as db:
            saved_rsvp = dict(db.execute('SELECT * FROM rsvps WHERE guest_id=?', (guest_id,)).fetchone())
            sessions = [tuple(row) for row in db.execute('SELECT * FROM sessions WHERE guest_id=?', (guest_id,))]
        self.assertEqual(len(sessions), 1)

        response = self.action('edit', guest_id=guest_id, name='Ewa Testowa', kind='couple',
                               partner_name='Jan Przykładowy', children_count='1', children=['Dziecko Testowe'])
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.endswith('#guest-' + guest_id))
        with connect(self.app.config['DATABASE']) as db:
            after = dict(db.execute('SELECT * FROM guests WHERE id=?', (guest_id,)).fetchone())
            self.assertEqual(after, {**before, 'name': 'Ewa Testowa', 'partner_name': 'Jan Przykładowy'})
            self.assertEqual(db.execute('SELECT count(*) FROM guests').fetchone()[0], guest_count)
            self.assertEqual(dict(db.execute('SELECT * FROM rsvps WHERE guest_id=?', (guest_id,)).fetchone()), saved_rsvp)
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM sessions WHERE guest_id=?', (guest_id,))], sessions)

        # A logged-in guest remains logged in, and both names are updated immediately.
        page = self.get('/guest', guest)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Ewa Testowa &amp; Jan Przykładowy', page.text)
        self.assertIn('Prywatne uwagi testowe', page.text)
        # Another invitation sees the corrected names, but not the private response.
        other = self.app.test_client()
        self.login(self.bob_code, other)
        others_page = self.get('/guest', other)
        self.assertIn('Ewa Testowa &amp; Jan Przykładowy', others_page.text)
        self.assertNotIn('Prywatne uwagi testowe', others_page.text)
        # Existing printed codes must also keep working in a fresh session.
        fresh = self.app.test_client()
        self.assertEqual(self.login(code, fresh).status_code, 303)
        self.assertEqual(self.get('/guest', fresh).status_code, 200)
        admin_page = self.get('/admin').text
        self.assertNotIn('id="new-code"', admin_page)
        self.assertNotIn(code, admin_page)
        self.assertNotIn(normalize_code(code), admin_page)
        self.assertNotIn('Ewa Testowa', self.get('/').text)

    def test_edit_form_explains_code_preservation_in_both_languages(self):
        self.admin_login()
        for lang, heading, help_text in (
            ('pl', 'Edytuj dane — kod bez zmian',
             'Możesz poprawić imiona i nazwiska bez zmiany kodu zaproszenia. Dotychczasowy kod nadal działa.'),
            ('en', 'Edit details — keep invitation code',
             'You can correct names without changing the invitation code. The existing code will still work.'),
        ):
            with self.subTest(lang=lang):
                page = self.get('/admin?lang=' + lang)
                self.assertEqual(page.status_code, 200)
                self.assertIn(heading, page.text)
                self.assertIn(help_text, page.text)
                self.assertIn('name="action" value="edit"', page.text)
                self.assertIn('name="action" value="rotate"', page.text)
