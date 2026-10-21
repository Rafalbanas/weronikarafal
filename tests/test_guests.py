import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
import unittest

from app import create_app
from wedding.store import connect, digest, invitation, normalize_code, revoke

BASE = "https://localhost"


class GuestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        details = {"ceremony": {"name": "Publiczny kościół", "address": "Publiczna ulica"},
            "venue": {"name": "Prywatna sala weselna", "address": "Prywatny adres"},
            "contacts": [{"role": "Świadkowa", "name": "Prywatny świadek", "phone": "+48 555 000 111"}], "schedule": []}
        (self.root / "details.json").write_text(json.dumps(details))
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-only-"+"x"*40,
            "DATABASE": str(self.root / "guests.sqlite3"), "DETAILS": str(self.root / "details.json"),
            "TRUSTED_HOSTS": ["localhost"], "TRUST_PROXY": False, "LOGIN_LIMIT": 5})
        self.client = self.app.test_client()
        with connect(self.app.config["DATABASE"]) as db:
            self.alice, self.alice_code = invitation(db, "Gość Alfa", companion=True)
            self.bob, self.bob_code = invitation(db, "Gość Beta")

    def get(self, path="/guest", client=None):
        return (client or self.client).get(path, base_url=BASE)

    def token(self, path="/login", client=None):
        response = self.get(path, client)
        return re.search(r'name="csrf_token" value="([^"]+)"', response.text).group(1)

    def post(self, path, data, client=None, **kwargs):
        headers = {"Referer": BASE+path, "Origin": BASE}
        headers.update(kwargs.pop("headers", {}))
        return (client or self.client).post(path, data=data, base_url=BASE, headers=headers, **kwargs)

    def login(self, code=None, client=None):
        return self.post("/login", {"csrf_token": self.token(client=client), "code": code or self.alice_code}, client)

    def response(self, **changes):
        payload = {"csrf_token": self.token("/guest"), "attendance": "yes", "diet": "vegan",
            "lodging": "yes", "notes": "Prywatna alergia", "companion_name": "Towarzysząca Alfa"}
        payload.update(changes)
        return self.post("/rsvp", payload)

    def test_public_page_does_not_contain_guest_or_contact_data(self):
        response = self.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Publiczny kościół", response.text)
        for private in ("Gość Alfa", "Gość Beta", "Prywatna sala", "+48 555", "Prywatny świadek", "Prywatny adres"):
            self.assertNotIn(private, response.text)
        self.assertNotIn("csrf_token", response.text)

    def test_private_routes_require_authentication(self):
        self.assertEqual(self.get().status_code, 303)
        self.assertEqual(self.post("/rsvp", {}).status_code, 400)
        token = self.token()
        response = self.post("/rsvp", {"csrf_token": token})
        self.assertEqual(response.status_code, 303)
        for path in ("/templates/guest.html", "/index.html", "/app.py", "/guests.sqlite3", "/details.json"):
            self.assertEqual(self.get(path).status_code, 404)

    def test_login_and_saved_response_are_bound_to_invitation(self):
        self.assertEqual(self.login().status_code, 303)
        self.assertEqual(self.response().status_code, 303)
        with connect(self.app.config["DATABASE"]) as db:
            rows = db.execute("SELECT * FROM rsvps").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["guest_id"], self.alice)
        self.assertIn("Prywatna alergia", self.get().text)

    def test_repeated_response_updates_one_row(self):
        self.login()
        self.response()
        self.assertEqual(self.response(attendance="no").status_code, 303)
        with connect(self.app.config["DATABASE"]) as db:
            rows = db.execute("SELECT * FROM rsvps").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["attendance"], rows[0]["companion_name"], rows[0]["lodging"]), ("no", "", "no"))

    def test_cannot_change_someone_elses_response(self):
        self.login()
        self.assertEqual(self.response(guest_id=self.bob).status_code, 400)
        with connect(self.app.config["DATABASE"]) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM rsvps").fetchone()[0], 0)

    def test_other_guests_see_status_without_sensitive_rsvp_details(self):
        self.login()
        self.response()
        second = self.app.test_client()
        self.login(self.bob_code, second)
        page = self.get(client=second).text
        self.assertIn("Gość Alfa", page)
        self.assertIn("Będzie z nami", page)
        self.assertIn("Prywatny świadek", page)
        self.assertNotIn("Prywatna alergia", page)
        self.assertNotIn("Towarzysząca Alfa", page)

    def test_logout_invalidates_copied_session_cookie(self):
        self.login()
        cookie = self.client.get_cookie("__Host-wedding").value
        copied = self.app.test_client()
        copied.set_cookie("__Host-wedding", cookie)
        self.assertEqual(self.get(client=copied).status_code, 200)
        self.assertEqual(self.post("/logout", {"csrf_token": self.token("/guest")}).status_code, 303)
        self.assertEqual(self.get(client=copied).status_code, 303)

    def test_revocation_and_rotation_invalidate_old_code_and_sessions(self):
        self.login()
        with connect(self.app.config["DATABASE"]) as db:
            revoke(db, self.alice)
        self.assertEqual(self.get().status_code, 303)
        self.assertEqual(self.login().status_code, 401)
        with connect(self.app.config["DATABASE"]) as db:
            _, new_code = invitation(db, "Gość Alfa", True, self.alice)
        self.assertEqual(self.login(new_code).status_code, 303)
        self.assertEqual(self.get().status_code, 200)

    def test_expired_session_is_rejected(self):
        self.login()
        with connect(self.app.config["DATABASE"]) as db:
            db.execute("UPDATE sessions SET expires_at=?", (int(time.time())-1,))
        self.assertEqual(self.get().status_code, 303)

    def test_invalid_code_does_not_disclose_guest_names(self):
        response = self.post("/login", {"csrf_token": self.token(), "code": "0"*32})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Gość Alfa", response.text)

    def test_rate_limits_survive_cookie_reset_and_ignore_spoofed_client_header(self):
        for _ in range(5):
            client = self.app.test_client()
            response = self.post("/login", {"csrf_token": self.token(client=client), "code": "invalid"}, client,
                headers={"X-Forwarded-For": str(time.time())})
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_successful_logins_on_shared_wifi_do_not_use_failed_login_budget(self):
        for _ in range(7):
            client = self.app.test_client()
            self.assertEqual(self.login(client=client).status_code, 303)

    def test_forged_csrf_and_cross_origin_requests_cannot_write(self):
        self.login()
        for payload in ({}, {"csrf_token": "forged"}):
            self.assertEqual(self.post("/rsvp", payload).status_code, 400)
        response = self.post("/rsvp", {"csrf_token": self.token("/guest")}, headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("/logout", {}).status_code, 400)

    def test_large_invalid_and_unauthorized_companion_values_are_rejected(self):
        self.login()
        self.assertEqual(self.response(notes="x"*2001).status_code, 400)
        self.assertEqual(self.response(diet="invalid").status_code, 400)
        self.assertEqual(self.response(notes="x"*20000).status_code, 413)
        second = self.app.test_client()
        self.login(self.bob_code, second)
        response = self.post("/rsvp", {"csrf_token": self.token("/guest", second), "attendance": "yes",
            "diet": "standard", "lodging": "no", "companion_name": "Nieuprawniony gość"}, second)
        self.assertEqual(response.status_code, 403)

    def test_untrusted_host_is_rejected(self):
        self.assertEqual(self.client.get("/", base_url="https://evil.example").status_code, 400)

    def test_codes_and_session_tokens_are_not_stored_in_plaintext(self):
        self.login()
        with self.client.session_transaction(base_url=BASE) as sess:
            sid = sess["sid"]
        with connect(self.app.config["DATABASE"]) as db:
            code_hash = db.execute("SELECT code_hash FROM guests WHERE id=?", (self.alice,)).fetchone()[0]
            session_hash = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertEqual(code_hash, digest(normalize_code(self.alice_code)))
        self.assertEqual(session_hash, digest(sid))
        self.assertNotEqual(session_hash, sid)

    def test_html_is_escaped_and_security_headers_apply(self):
        with connect(self.app.config["DATABASE"]) as db:
            db.execute("UPDATE guests SET name=? WHERE id=?", ('<script>alert(1)</script>', self.bob))
        response = self.login()
        cookie = response.headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, cookie)
        page = self.get()
        self.assertNotIn('<script>alert(1)</script>', page.text)
        self.assertIn('&lt;script&gt;', page.text)
        self.assertIn("no-store", page.headers["Cache-Control"])
        self.assertIn("script-src 'self'", page.headers["Content-Security-Policy"])
        self.assertEqual(page.headers["X-Frame-Options"], "DENY")


if __name__ == "__main__":
    unittest.main()
