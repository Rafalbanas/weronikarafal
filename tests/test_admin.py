import re
import time
import unittest
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from werkzeug.security import check_password_hash, generate_password_hash

import test_guests
from test_guests import BASE
from wedding.store import connect, digest, initialize, normalize_code


class AdminTests(unittest.TestCase):
    get = test_guests.GuestTests.get
    post = test_guests.GuestTests.post
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login
    response = test_guests.GuestTests.response

    def setUp(self):
        test_guests.GuestTests.setUp(self)
        self.password = "private-test-password-12345"
        with connect(self.app.config["DATABASE"]) as db:
            db.execute("INSERT INTO administrators VALUES (?, ?)", ("para", generate_password_hash(self.password)))

    def admin_login(self, client=None, password=None):
        return self.post("/admin/login", {"csrf_token": self.token("/admin/login", client),
            "username": "para", "password": password or self.password}, client)

    def action(self, action="rotate", guest_id=None, client=None, **data):
        return self.post("/admin/guests/"+(guest_id or self.alice),
            {"csrf_token": self.token("/admin", client), "action": action, **data}, client)

    def code(self, response):
        self.assertEqual(response.status_code, 200)
        return re.search(r'id="new-code"[^>]*value="([^"]+)"', response.text).group(1)

    def test_guest_and_anonymous_cannot_read_or_modify_admin_data(self):
        self.assertEqual(self.get("/admin").status_code, 303)
        self.login()
        response = self.get("/admin")
        self.assertEqual(response.status_code, 303)
        self.assertIn("/admin/login", response.location)
        response = self.post("/admin/guests/"+self.bob, {"csrf_token": self.token("/guest"), "action": "rotate"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.login(self.bob_code, self.app.test_client()).status_code, 303)
        with self.client.session_transaction(base_url=BASE) as session:
            session["admin"] = True
            session["username"] = "para"
        self.assertEqual(self.get("/admin").status_code, 303)

    def test_admin_sees_all_rsvp_details_but_no_existing_codes(self):
        self.login()
        self.response()
        self.assertEqual(self.admin_login().status_code, 303)
        page = self.get("/admin")
        self.assertEqual(page.status_code, 200)
        for text in ("Prywatna alergia", "Towarzysząca Alfa", "Wegańska", "Gość Beta"):
            self.assertIn(text, page.text)
        self.assertNotIn(self.alice_code, page.text)
        self.assertIn("no-store", page.headers["Cache-Control"])

    def test_create_code_is_shown_once_and_only_salted_hash_is_stored(self):
        self.admin_login()
        response = self.post("/admin/guests", {"csrf_token": self.token("/admin"), "name": "Nowi Goście", "companion": "yes"})
        code = self.code(response)
        with connect(self.app.config["DATABASE"]) as db:
            person = db.execute("SELECT * FROM guests WHERE name=?", ("Nowi Goście",)).fetchone()
            self.assertEqual(person["allows_companion"], 1)
            self.assertTrue(check_password_hash(person["code_hash"], normalize_code(code)))
            self.assertNotIn(normalize_code(code), person["code_hash"])
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='invitation_codes'").fetchone())
            dump = "\n".join(db.iterdump())
            self.assertNotIn(code, dump)
            self.assertNotIn(normalize_code(code), dump)
        self.assertNotIn(code, self.get("/admin").text)
        guest = self.app.test_client()
        self.assertEqual(self.login(code, guest).status_code, 303)
        self.assertEqual(self.get("/admin", guest).status_code, 303)

    def test_reset_invalidates_old_code_and_sessions_and_preserves_rsvp(self):
        self.login()
        self.response()
        admin = self.app.test_client()
        self.admin_login(admin)
        code = self.code(self.action(client=admin))
        self.assertEqual(self.get().status_code, 303)
        self.assertEqual(self.login(self.alice_code).status_code, 401)
        self.assertEqual(self.login(code).status_code, 303)
        self.assertIn("Prywatna alergia", self.get().text)
        self.assertNotIn(code, self.get("/admin", admin).text)

    def test_salts_are_random_and_legacy_code_upgrades_on_login(self):
        self.admin_login()
        with connect(self.app.config["DATABASE"]) as db:
            old = "a"*32
            db.execute("UPDATE guests SET code_id=NULL, code_hash=? WHERE id=?", (digest(old), self.alice))
        guest = self.app.test_client()
        self.assertEqual(self.login(old, guest).status_code, 303)
        with connect(self.app.config["DATABASE"]) as db:
            first = db.execute("SELECT code_hash FROM guests WHERE id=?", (self.alice,)).fetchone()[0]
            self.assertTrue(check_password_hash(first, old))
        self.assertEqual(self.login(old, self.app.test_client()).status_code, 303)
        self.assertNotEqual(generate_password_hash(old), generate_password_hash(old))

    def test_additive_migration_preserves_legacy_guest_and_handles_parallel_workers(self):
        path = self.root / "legacy.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE guests (id TEXT PRIMARY KEY, name TEXT NOT NULL, code_hash TEXT NOT NULL UNIQUE, allows_companion INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1)")
            db.execute("INSERT INTO guests VALUES (?, ?, ?, 0, 1)", ("legacy", "Istniejący gość", digest("a"*32)))
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(initialize, [path] * 8))
        with connect(path) as db:
            person = db.execute("SELECT * FROM guests").fetchone()
            self.assertEqual(person["name"], "Istniejący gość")
            self.assertIsNone(person["code_id"])

    def test_csrf_origin_validation_and_no_public_signup(self):
        self.admin_login()
        self.assertEqual(self.post("/admin/guests", {"name": "No CSRF"}).status_code, 400)
        self.assertEqual(self.post("/admin/guests/"+self.alice, {"action": "rotate"}).status_code, 400)
        self.assertEqual(self.post("/admin/password", {}).status_code, 400)
        self.assertEqual(self.post("/admin/guests", {"csrf_token": self.token("/admin"), "name": "Evil"}, headers={"Origin": "https://evil.example"}).status_code, 400)
        self.assertEqual(self.get("/admin/register").status_code, 404)

    def test_edit_revoke_and_reactivate(self):
        self.admin_login()
        self.assertEqual(self.action("edit", name="Nowe nazwisko", companion="yes").status_code, 303)
        self.action("revoke")
        self.assertEqual(self.login(self.alice_code, self.app.test_client()).status_code, 401)
        code = self.code(self.action())
        guest = self.app.test_client()
        self.login(code, guest)
        self.assertIn("Nowe nazwisko", self.get(client=guest).text)

    def test_failed_admin_logins_are_limited_across_cookies(self):
        for _ in range(5):
            self.assertEqual(self.admin_login(self.app.test_client(), "wrong").status_code, 401)
        self.assertEqual(self.admin_login().status_code, 429)

    def test_logout_expiry_and_password_change_invalidate_admin_sessions(self):
        self.admin_login()
        copied = self.app.test_client()
        copied.set_cookie("__Host-wedding", self.client.get_cookie("__Host-wedding").value)
        self.post("/logout", {"csrf_token": self.token("/admin")})
        self.assertEqual(self.get("/admin", copied).status_code, 303)
        self.admin_login()
        self.admin_login(copied)
        new = "changed-password-123456789"
        self.post("/admin/password", {"csrf_token": self.token("/admin"), "current_password": self.password,
            "new_password": new, "confirm_password": new})
        self.assertEqual(self.get("/admin", copied).status_code, 303)
        self.assertEqual(self.admin_login(password=self.password).status_code, 401)
        self.assertEqual(self.admin_login(password=new).status_code, 303)
        with connect(self.app.config["DATABASE"]) as db:
            db.execute("UPDATE admin_sessions SET expires_at=?", (int(time.time())-1,))
        self.assertEqual(self.get("/admin").status_code, 303)

    def test_duplicate_custom_code_and_invalid_input_do_not_break_panel(self):
        self.admin_login()
        for name, code in [("", ""), ("Bad code", "1234"), ("Duplicate", self.alice_code)]:
            response = self.post("/admin/guests", {"csrf_token": self.token("/admin"), "name": name, "code": code})
            self.assertEqual(response.status_code, 303)
            self.assertEqual(self.get("/admin").status_code, 200)
        response = self.action("edit", name='<script>alert(1)</script>')
        self.assertEqual(response.status_code, 303)
        self.assertNotIn('<script>alert(1)</script>', self.get("/admin").text)
