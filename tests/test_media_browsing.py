"""Backend pagination/selection rules for the authenticated media library."""
import io
import re
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from werkzeug.security import generate_password_hash

import test_guests
from test_guests import BASE
from wedding.store import connect, media_page

from test_media import PNG, MP4


class MediaHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def ids(self):
        return [attrs['id'][6:] for tag, attrs in self.tags
                if tag == 'figure' and attrs.get('id', '').startswith('media-')]


class MediaBrowsingTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login
    post = test_guests.GuestTests.post

    ADMIN_PASSWORD = "media-browsing-admin-password-12345"

    def client_for(self, code):
        client = self.app.test_client()
        self.assertEqual(self.login(code, client).status_code, 303)
        return client

    def admin_client(self):
        with connect(self.app.config["DATABASE"]) as db:
            db.execute("""INSERT INTO administrators VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash""",
                ("para", generate_password_hash(self.ADMIN_PASSWORD)))
        client = self.app.test_client()
        response = self.post("/admin/login", {"csrf_token": self.token("/admin/login", client),
            "username": "para", "password": self.ADMIN_PASSWORD}, client)
        self.assertEqual(response.status_code, 303)
        return client

    def upload(self, client=None, name="photo.png", content=PNG, content_type="image/png",
                xhr=False, csrf=True):
        headers = {"X-Requested-With": "XMLHttpRequest"} if xhr else {}
        payload = {"files": (io.BytesIO(content), name, content_type)}
        if csrf:
            payload["csrf_token"] = self.token("/media", client)
        return self.post("/media", payload, client, content_type="multipart/form-data", headers=headers)

    def db(self):
        return connect(self.app.config["DATABASE"])

    def clear(self):
        with self.db() as db:
            db.execute("DELETE FROM uploads")

    def seed(self, count=49):
        """Deterministic gallery: interleaved image/video and guest/admin owners."""
        with self.db() as db:
            for i in range(count):
                content_type = "image/png" if i % 2 == 0 else "video/mp4"
                owner_id = self.alice if i % 3 == 0 else "para"
                owner_kind = "guest" if i % 3 == 0 else "admin"
                db.execute(
                    "INSERT INTO uploads (id, owner_id, owner_kind, original_name, content_type, size, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("a" + str(i).zfill(31), owner_id, owner_kind, f"photo{i}.png", content_type, 100, 1000 + i))

    def test_media_page_counts_and_pages_49_records(self):
        self.clear()
        self.seed(49)
        with self.db() as db:
            items, total, page, pages = media_page(db, "all", None, None, 1)
            self.assertEqual(total, 49)
            self.assertEqual(pages, 3)
            self.assertEqual(page, 1)
            self.assertEqual(len(items), 24)
        with self.db() as db:
            items2, total, page, pages = media_page(db, "all", None, None, 2)
            self.assertEqual(len(items2), 24)
            items3, total, page, pages = media_page(db, "all", None, None, 3)
            self.assertEqual(len(items3), 1)
        # No duplicates and no loss across pages.
        seen = [row["id"] for row in items] + [row["id"] for row in items2] + [row["id"] for row in items3]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(sorted(seen), sorted(row["id"] for row in
                           db.execute("SELECT id FROM uploads")))
        # Order is created_at DESC, id ASC.
        keys = [(row["created_at"], row["id"]) for row in items + items2 + items3]
        self.assertEqual(keys, sorted(keys, key=lambda k: (-k[0], k[1])))

    def test_clamp_page_past_last(self):
        self.clear()
        self.seed(49)
        with self.db() as db:
            items, total, page, pages = media_page(db, "all", None, None, 999)
            self.assertEqual(page, 3)
            self.assertEqual(len(items), 1)

    def test_kind_filters_image_and_video(self):
        self.clear()
        self.seed(49)
        with self.db() as db:
            images, total_i, *_ = media_page(db, "image", None, None, 1)
            videos, total_v, *_ = media_page(db, "video", None, None, 1)
            self.assertEqual(total_i, 25)
            self.assertEqual(total_v, 24)
            self.assertEqual({"image/png"}, {row["content_type"] for row in images})
            self.assertEqual({"video/mp4"}, {row["content_type"] for row in videos})
        # Paging through every kind reproduces the full id set, no dup/loss.
        all_ids = []
        for kind, total in (("image", total_i), ("video", total_v)):
            for page in range(1, (total + 23) // 24 + 1):
                with self.db() as db:
                    all_ids += [row["id"] for row in media_page(db, kind, None, None, page)[0]]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(set(all_ids), {"a" + str(i).zfill(31) for i in range(49)})

    def test_mine_uses_session_identity_never_client_ids(self):
        self.clear()
        self.seed(49)
        with self.db() as db:
            mine_alice, total, *_ = media_page(db, "all", self.alice, "guest", 1)
            self.assertEqual(total, 17)
            self.assertTrue(all(row["owner_id"] == self.alice and row["owner_kind"] == "guest"
                              for row in mine_alice))
        with self.db() as db:
            mine_admin, total, *_ = media_page(db, "all", "para", "admin", 1)
            self.assertEqual(total, 32)
            self.assertTrue(all(row["owner_id"] == "para" and row["owner_kind"] == "admin"
                              for row in mine_admin))

    def test_combined_kind_and_mine_filters(self):
        self.clear()
        self.seed(49)
        with self.db() as db:
            images_mine, total, *_ = media_page(db, "image", self.alice, "guest", 1)
            self.assertEqual(total, 9)
            self.assertTrue(all(row["content_type"] == "image/png" and row["owner_id"] == self.alice
                              for row in images_mine))

    def test_endpoint_validation_returns_400(self):
        alice = self.client_for(self.alice_code)
        with self.db() as db:
            db.execute("DELETE FROM uploads")
        for query in (
            "/media?kind=audio", "/media?owner=everyone",
            "/media?kind=all&kind=image", "/media?owner=mine&owner=mine", "/media?page=1&page=2",
            "/media?page=abc", "/media?page=0", "/media?page=-5", "/media?page=10000000000",
            "/media?kind=1 OR 1=1", "/media?page=1;DROP",
            "/media?page=²", "/media?page=١", "/media?page=", "/media?kind=", "/media?owner=",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.get(query, alice).status_code, 400)

    def test_endpoint_page_clamp_after_delete(self):
        alice = self.client_for(self.alice_code)
        self.seed(49)
        # Page far past the last page must not 500 and clamps to the final page.
        response = self.get("/media?page=999999999", alice)
        self.assertEqual(response.status_code, 200)
        self.assertIn("photo0.png", response.text)
        self.assertEqual(len(MediaHTML(response.text).ids()), 1)
        self.assertIn("Strona 3 z 3", response.text)

    def test_anonymous_get_media_redirects_to_login(self):
        anonymous = self.app.test_client()
        for query in ("/media", "/media?kind=image&owner=mine&page=2", "/media?page=bad"):
            response = anonymous.get(query, base_url=BASE)
            self.assertEqual(response.status_code, 303)
            self.assertIn("/login", response.location)

    def test_sql_injection_via_selectors_is_rejected(self):
        alice = self.client_for(self.alice_code)
        with self.db() as db:
            db.execute("DELETE FROM uploads")
        self.seed(49)
        for query in ("/media?kind='all' OR '1'='1'",
                     "/media?owner=mine' AND owner_kind='admin'--",
                     "/media?page=1/*"):
            with self.subTest(query=query):
                self.assertEqual(self.get(query, alice).status_code, 400)

    def test_filename_xss_is_not_rendered_as_script(self):
        alice = self.client_for(self.alice_code)
        with self.db() as db:
            db.execute("DELETE FROM uploads")
        name = '<script>alert(1)>.png'
        self.assertEqual(self.upload(alice, name=name, xhr=True).status_code, 200)
        page = self.get("/media", alice).text
        self.assertNotIn("<script>alert(1)", page)
        self.assertIn("&lt;script&gt;alert(1)&gt;.png", page)

    def test_zip_download_covers_whole_album_ignoring_filters(self):
        alice = self.client_for(self.alice_code)
        self.seed(49)
        uploads = Path(self.app.config['UPLOADS_DIR'])
        for i in range(49):
            (uploads / ('a' + str(i).zfill(31))).write_bytes(PNG if i % 2 == 0 else MP4)
        page = self.get('/media?kind=image&owner=mine&page=2', alice)
        parsed = MediaHTML(page.text)
        download = next(attrs['href'] for tag, attrs in parsed.tags
                        if tag == 'a' and attrs.get('href') == '/media/download')
        with self.get(download + '?kind=image&owner=mine&page=2', alice) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "application/zip")
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                self.assertEqual(len(archive.namelist()), 49)
                self.assertEqual(archive.read('a' + str(48).zfill(31) + '_photo48.png'), PNG)

    def test_tied_timestamps_have_stable_order_across_pages(self):
        self.seed(49)
        with self.db() as db:
            db.execute('UPDATE uploads SET created_at=1000')
            ids = [row['id'] for page in range(1, 4)
                   for row in media_page(db, 'all', page=page)[0]]
        self.assertEqual(ids, ['a' + str(i).zfill(31) for i in range(49)])

    def test_http_filters_use_guest_and_admin_session_identity(self):
        self.seed(49)
        alice = self.client_for(self.alice_code)
        admin = self.admin_client()
        # Identical owner IDs in different namespaces must not overlap.
        with self.db() as db:
            db.execute('UPDATE uploads SET owner_id=? WHERE owner_kind=?', (self.alice, 'admin'))
        for kind in ('all', 'image', 'video'):
            response = self.get(f'/media?kind={kind}&owner=mine&owner_id=para&owner_kind=admin', alice)
            with self.db() as db:
                expected = [row['id'] for row in media_page(db, kind, self.alice, 'guest')[0]]
            self.assertEqual(MediaHTML(response.text).ids(), expected)
        # The administrator named "para" does not own those guest-ID/admin-kind rows.
        self.assertEqual(MediaHTML(self.get('/media?owner=mine', admin).text).ids(), [])
        with self.db() as db:
            db.execute('UPDATE uploads SET owner_id=? WHERE owner_kind=?', ('para', 'admin'))
        for kind in ('all', 'image', 'video'):
            with self.db() as db:
                expected = [row['id'] for row in media_page(db, kind, 'para', 'admin')[0]]
            self.assertEqual(MediaHTML(self.get(f'/media?kind={kind}&owner=mine', admin).text).ids(), expected)

    def test_foreign_file_visible_but_guest_cannot_delete(self):
        self.seed(3)
        alice = self.client_for(self.alice_code)
        foreign_id = 'a' + str(1).zfill(31)
        self.assertIn(foreign_id, MediaHTML(self.get('/media', alice).text).ids())
        result = self.post(f'/media/{foreign_id}/delete',
                           {'csrf_token': self.token('/media', alice)}, alice)
        self.assertEqual(result.status_code, 403)
        with self.db() as db:
            self.assertIsNotNone(db.execute('SELECT id FROM uploads WHERE id=?', (foreign_id,)).fetchone())

    def test_ui_filters_and_pagination_in_both_languages(self):
        self.seed(49)
        # More than two pages matching both selectors.
        with self.db() as db:
            db.execute('UPDATE uploads SET content_type=?,owner_id=?,owner_kind=?',
                       ('image/png', self.alice, 'guest'))
        alice = self.client_for(self.alice_code)
        for lang, labels in (
            ('pl', ('Rodzaj pliku', 'Dodane przez', 'Filtruj', 'Strona 2 z 3', 'Strony biblioteki')),
            ('en', ('File type', 'Added by', 'Filter', 'Page 2 of 3', 'Library pages')),
        ):
            response = self.get(f'/media?kind=image&owner=mine&page=2&lang={lang}', alice)
            self.assertEqual(response.status_code, 200)
            for label in labels:
                self.assertIn(label, response.text)
            parsed = MediaHTML(response.text)
            self.assertEqual(len(parsed.ids()), 24)
            self.assertTrue(any(tag == 'form' and attrs.get('method') == 'get'
                                and attrs.get('action') == '/media' for tag, attrs in parsed.tags))
            selects = [attrs['value'] for tag, attrs in parsed.tags if tag == 'option' and 'selected' in attrs]
            self.assertEqual(selects, ['image', 'mine'])
            for rel, number in (('prev', '1'), ('next', '3')):
                href = next(attrs['href'] for tag, attrs in parsed.tags
                            if tag == 'a' and attrs.get('rel') == rel)
                url = urlsplit(href)
                self.assertEqual(url.path, '/media')
                self.assertEqual(parse_qs(url.query), {'kind': ['image'], 'owner': ['mine'],
                                                     'page': [number], 'lang': [lang]})
                self.assertEqual(self.get(href, alice).status_code, 200)
            # Filter submission has no hidden page: changing filters starts at page 1.
            self.assertFalse(any(tag == 'input' and attrs.get('name') == 'page' for tag, attrs in parsed.tags))

    def test_empty_states_and_reset_keep_zip_available(self):
        alice = self.client_for(self.alice_code)
        empty = self.get('/media', alice)
        self.assertIn('Jeszcze tu pusto', empty.text)
        self.seed(3)
        for lang, label in (('pl', 'Brak plików pasujących do filtrów'), ('en', 'No files match these filters')):
            response = self.get(f'/media?kind=video&owner=mine&lang={lang}', alice)
            self.assertIn(label, response.text)
            self.assertNotIn('Jeszcze tu pusto', response.text)
            parsed = MediaHTML(response.text)
            links = [attrs['href'] for tag, attrs in parsed.tags if tag == 'a']
            self.assertIn('/media/download', links)
            self.assertIn('/media?lang=' + lang, links)
            self.assertEqual(parsed.ids(), [])

    def test_http_gallery_query_is_bounded_in_sql(self):
        self.seed(49)
        alice = self.client_for(self.alice_code)
        queries = []

        def traced_connect(path):
            db = connect(path)
            db.set_trace_callback(queries.append)
            return db

        with patch('app.connect', side_effect=traced_connect):
            response = self.get('/media?page=2', alice)
        self.assertEqual(len(MediaHTML(response.text).ids()), 24)
        selects = [query for query in queries if re.search(r'SELECT.*FROM uploads', query, re.I | re.S)]
        self.assertEqual(len(selects), 2)
        self.assertTrue(any('count(*)' in query.lower() for query in selects))
        self.assertTrue(any('LIMIT 24 OFFSET 24' in query for query in selects))


if __name__ == "__main__":
    unittest.main()
