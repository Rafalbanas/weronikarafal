from concurrent.futures import ThreadPoolExecutor
import unittest
import test_admin
from werkzeug.security import check_password_hash
from wedding.store import connect, issue_admin_recovery, normalize_code


class RecoveryTests(unittest.TestCase):
    setUp = test_admin.AdminTests.setUp
    get = test_admin.AdminTests.get
    post = test_admin.AdminTests.post
    token = test_admin.AdminTests.token
    login = test_admin.AdminTests.login
    admin_login = test_admin.AdminTests.admin_login
    code = test_admin.AdminTests.code

    def issue(self):
        with connect(self.app.config['DATABASE']) as db:
            return issue_admin_recovery(db, 'para')

    def reset(self, code, client=None, **changes):
        payload = {'csrf_token': self.token('/admin/recover', client), 'username': 'para',
                   'recovery_code': code, 'new_password': 'new-private-password-12345',
                   'confirm_password': 'new-private-password-12345'}
        payload.update(changes)
        return self.post('/admin/recover', payload, client)

    def test_reset_consumes_code_rotates_it_and_revokes_all_admin_sessions(self):
        key = self.issue()
        self.admin_login()
        copied = self.app.test_client()
        copied.set_cookie('__Host-wedding', self.client.get_cookie('__Host-wedding').value)
        replacement = self.code(self.reset(key))
        self.assertEqual(self.get('/admin', copied).status_code, 303)
        self.assertEqual(self.admin_login(password=self.password).status_code, 401)
        self.assertEqual(self.reset(key).status_code, 401)
        self.assertEqual(self.admin_login(password='new-private-password-12345').status_code, 303)
        self.assertNotIn(replacement, self.get('/admin').text)
        with connect(self.app.config['DATABASE']) as db:
            stored = db.execute('SELECT code_hash FROM admin_recovery WHERE username=?', ('para',)).fetchone()[0]
            self.assertTrue(check_password_hash(stored, normalize_code(replacement)))
            dump = '\n'.join(db.iterdump())
            for secret in (key, normalize_code(key), replacement, normalize_code(replacement), 'new-private-password-12345'):
                self.assertNotIn(secret, dump)
        self.assertEqual(self.reset(replacement).status_code, 200)

    def test_invalid_code_account_and_password_do_not_consume_valid_code(self):
        key = self.issue()
        for code, values in [('wrong', {}), (key, {'username': 'unknown'}),
                             (key, {'new_password': 'short', 'confirm_password': 'short'}),
                             (key, {'confirm_password': 'different-password-12345'})]:
            self.assertEqual(self.reset(code, **values).status_code, 401)
        self.assertEqual(self.reset('  '+key.upper()+'  ').status_code, 200)

    def test_reset_is_single_use_under_concurrent_requests(self):
        key = self.issue()
        clients = [self.app.test_client(), self.app.test_client()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda client: self.reset(key, client).status_code, clients))
        self.assertEqual(sorted(statuses), [200, 401])

    def test_recovery_requires_csrf_and_same_origin(self):
        key = self.issue()
        self.assertEqual(self.post('/admin/recover', {'recovery_code': key}).status_code, 400)
        self.assertEqual(self.post('/admin/recover', {'csrf_token': self.token('/admin/recover'), 'recovery_code': key}, headers={'Origin': 'https://evil.example'}).status_code, 400)
        self.assertEqual(self.reset(key).status_code, 200)

    def test_failed_resets_limited_across_cookie_resets(self):
        for _ in range(5):
            self.assertEqual(self.reset('wrong', self.app.test_client()).status_code, 401)
        self.assertEqual(self.reset('wrong', self.app.test_client()).status_code, 429)

    def test_issuing_code_requires_admin_and_current_password(self):
        self.login()
        response = self.post('/admin/recovery', {'csrf_token': self.token('/guest'), 'current_password': self.password})
        self.assertEqual(response.status_code, 303)
        self.admin_login()
        self.assertEqual(self.post('/admin/recovery', {}).status_code, 400)
        key = self.issue()
        response = self.post('/admin/recovery', {'csrf_token': self.token('/admin'), 'current_password': 'wrong'})
        self.assertEqual(response.status_code, 303)
        response = self.post('/admin/recovery', {'csrf_token': self.token('/admin'), 'current_password': self.password})
        replacement = self.code(response)
        self.assertNotEqual(key, replacement)
        self.assertEqual(self.reset(key).status_code, 401)
        self.assertEqual(self.reset(replacement).status_code, 200)

    def test_recovery_unblocks_login_after_successful_reset(self):
        key = self.issue()
        for _ in range(5):
            self.assertEqual(self.admin_login(self.app.test_client(), password='wrong').status_code, 401)
        self.assertEqual(self.admin_login().status_code, 429)
        self.reset(key)
        self.assertEqual(self.admin_login(password='new-private-password-12345').status_code, 303)

    def test_login_hints_and_recovery_are_translated(self):
        page = self.get('/admin/login?lang=en')
        for text in ('Show password', 'Passwords are case-sensitive', 'Forgot password'):
            self.assertIn(text, page.text)
        page = self.get('/admin/recover')
        self.assertIn('Reset password', page.text)
        self.assertIn('/admin/recover?lang=pl', page.text)
        self.assertNotIn('new-code', page.text)
        page = self.reset(self.issue())
        self.assertIn('Password reset', page.text)
        self.assertIn('Single-use recovery code', page.text)
