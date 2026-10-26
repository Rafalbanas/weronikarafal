"""Upload, ownership and privacy rules for the authenticated media library."""
import io
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
import sqlite3
import struct
import zipfile
from pathlib import Path

from werkzeug.security import generate_password_hash

import test_guests
from app import create_app
from test_guests import BASE
from wedding.store import connect, record_media_batch, MediaLimitExceeded

PNG = b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sIIBBBBB", 13, b"IHDR", 1, 1, 8, 2, 0, 0, 0) + b"\x00" * 100
PNG_OTHER = PNG + b"different photo"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 120
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 120
WEBM = bytes.fromhex("1a45dfa39f4286810142f7810142f2810442f381084282847765626d4287810242858102")


class MediaTests(unittest.TestCase):
    setUp = test_guests.GuestTests.setUp
    get = test_guests.GuestTests.get
    token = test_guests.GuestTests.token
    login = test_guests.GuestTests.login
    post = test_guests.GuestTests.post

    ADMIN_PASSWORD = "media-admin-password-12345"

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

    def delete(self, upload_id, client=None, csrf=True):
        payload = {"csrf_token": self.token("/media", client)} if csrf else {}
        return self.post(f"/media/{upload_id}/delete", payload, client)

    def rows(self):
        with connect(self.app.config["DATABASE"]) as db:
            return db.execute("SELECT * FROM uploads ORDER BY created_at, id").fetchall()

    def uploads(self):
        return Path(self.app.config["UPLOADS_DIR"])

    def single_row(self):
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        return rows[0]

    def new_app(self, **config):
        settings = {"TESTING": True, "SECRET_KEY": self.app.config["SECRET_KEY"],
                    "DATABASE": self.app.config["DATABASE"], "DETAILS": self.app.config["DETAILS"],
                    "UPLOADS_DIR": self.app.config["UPLOADS_DIR"], "TRUSTED_HOSTS": ["localhost"],
                    "TRUST_PROXY": False}
        settings.update(config)
        return create_app(settings)

    def test_media_requires_authentication(self):
        anonymous = self.app.test_client()
        for path in ("/media", "/media/" + "a" * 32):
            response = anonymous.get(path, base_url=BASE)
            self.assertEqual(response.status_code, 303)
            self.assertIn("/login", response.location)
        token = self.token("/login", anonymous)
        response = self.post("/media", {"csrf_token": token,
            "files": (io.BytesIO(PNG), "photo.png", "image/png")}, anonymous,
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 303)
        self.assertIn("/login", response.location)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])
        self.assertEqual(anonymous.post("/media", data={}, base_url=BASE).status_code, 400)

    def test_guest_uploads_and_views_own_media(self):
        alice = self.client_for(self.alice_code)
        response = self.upload(alice, xhr=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        row = self.single_row()
        self.assertEqual(row["owner_id"], self.alice)
        self.assertEqual(row["owner_kind"], "guest")
        self.assertRegex(row["id"], r"^[a-f0-9]{32}$")
        self.assertEqual(row["original_name"], "photo.png")
        self.assertEqual(row["content_type"], "image/png")
        self.assertEqual(row["size"], len(PNG))
        stored = self.uploads() / row["id"]
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.stat().st_mode & 0o777, 0o600)
        page = self.get("/media", alice)
        self.assertEqual(page.status_code, 200)
        self.assertIn("photo.png", page.text)
        self.assertIn("Usuń", page.text)
        served = self.get("/media/" + row["id"], alice)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.data, PNG)
        self.assertEqual(served.headers["Content-Type"], "image/png")
        self.assertIn("private", served.headers["Cache-Control"])
        served.close()

    def test_video_uploads_support_byte_ranges(self):
        alice = self.client_for(self.alice_code)
        self.assertEqual(self.upload(alice, name="clip.mp4", content=MP4,
                                     content_type="video/mp4", xhr=True).status_code, 200)
        row = self.single_row()
        self.assertEqual(row["content_type"], "video/mp4")
        page = self.get("/media", alice)
        self.assertIn("<video", page.text)
        full = self.get("/media/" + row["id"], alice)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full.headers["Accept-Ranges"], "bytes")
        partial = alice.get("/media/" + row["id"], base_url=BASE, headers={"Range": "bytes=4-11"})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.data, MP4[4:12])
        self.assertEqual(partial.headers["Content-Range"], f"bytes 4-11/{len(MP4)}")
        suffix = alice.get("/media/" + row["id"], base_url=BASE, headers={"Range": "bytes=-8"})
        self.assertEqual(suffix.status_code, 206)
        self.assertEqual(suffix.data, MP4[-8:])
        full.close()
        partial.close()
        suffix.close()
        self.assertEqual(self.upload(alice, name="clip.webm", content=WEBM,
                                     content_type="video/webm", xhr=True).status_code, 200)

    def test_owner_can_delete_own_media(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, xhr=True)
        row = self.single_row()
        stored = self.uploads() / row["id"]
        response = self.delete(row["id"], alice)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.rows(), [])
        self.assertFalse(stored.exists())

    def test_other_guest_can_view_and_download_but_cannot_delete_media(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, xhr=True)
        row = self.single_row()
        stored = self.uploads() / row["id"]
        bob = self.client_for(self.bob_code)
        with self.get("/media/" + row["id"], bob) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, PNG)
        with self.get("/media/" + row["id"] + "?download=1", bob) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, PNG)
        page = self.get("/media", bob).text
        self.assertIn("photo.png", page)
        self.assertNotIn('/media/' + row["id"] + '/delete', page)
        response = self.delete(row["id"], bob)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.rows()), 1)
        self.assertTrue(stored.exists())

    def test_admin_para_can_view_and_delete_every_media_file(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, xhr=True)
        row = self.single_row()
        admin = self.admin_client()
        page = self.get("/media", admin)
        self.assertEqual(page.status_code, 200)
        self.assertIn("photo.png", page.text)
        self.assertIn("Gość Alfa", page.text)
        with self.get("/media/" + row["id"], admin) as response:
            self.assertEqual(response.status_code, 200)
        response = self.delete(row["id"], admin)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.rows(), [])
        self.assertFalse((self.uploads() / row["id"]).exists())

    def test_admin_uploads_are_visible_to_guests_but_only_admins_can_delete(self):
        admin = self.admin_client()
        self.assertEqual(self.upload(admin, name="admin.png", xhr=True).status_code, 200)
        row = self.single_row()
        self.assertEqual(row["owner_kind"], "admin")
        self.assertEqual(row["owner_id"], "para")
        alice = self.client_for(self.alice_code)
        self.assertIn("admin.png", self.get("/media", alice).text)
        with self.get("/media/" + row["id"], alice) as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.delete(row["id"], alice).status_code, 403)

    def test_identical_original_names_do_not_overwrite_each_other(self):
        alice = self.client_for(self.alice_code)
        self.assertEqual(self.upload(alice, name="photo.png", content=PNG, xhr=True).status_code, 200)
        self.assertEqual(self.upload(alice, name="photo.png", content=PNG_OTHER, xhr=True).status_code, 200)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["original_name"] for row in rows], ["photo.png", "photo.png"])
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        contents = []
        for row in rows:
            served = self.get("/media/" + row["id"], alice)
            contents.append(served.data)
            served.close()
        self.assertEqual({contents[0], contents[1]}, {PNG, PNG_OTHER})

    def test_unsupported_formats_and_mime_mismatch_are_rejected(self):
        alice = self.client_for(self.alice_code)
        cases = [
            ("notes.txt", b"plain text", "text/plain"),
            ("page.html", b"<script>alert(1)</script>", "text/html"),
            ("photo.png", b"<html>not an image</html>", "image/png"),
            ("photo.png", PNG, "image/jpeg"),
            ("archive.zip", b"PK\x03\x04", "application/zip"),
        ]
        for name, content, content_type in cases:
            with self.subTest(name=name, content_type=content_type):
                self.assertEqual(self.upload(alice, name=name, content=content,
                                             content_type=content_type).status_code, 415)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])

    def test_path_traversal_names_and_ids_are_rejected(self):
        alice = self.client_for(self.alice_code)
        for name in ("../../evil.png", "..", "folder/photo.png", "/etc/passwd"):
            with self.subTest(name=name):
                self.assertEqual(self.upload(alice, name=name).status_code, 400)
        self.assertEqual(self.rows(), [])
        self.assertFalse((self.root / "evil.png").exists())
        self.assertFalse((self.root.parent / "evil.png").exists())
        self.assertFalse((self.root.parent / "passwd").exists())
        self.assertEqual(list(self.uploads().iterdir()), [])
        for path in ("/media/..%2f..%2fetc%2fpasswd", "/media/" + "a" * 32, "/media/../../app.py"):
            self.assertEqual(self.get(path, alice).status_code, 404)
        # Windows-style paths are normalised by the multipart parser; whatever it
        # keeps is only metadata and the binary is always written under a random id.
        self.upload(alice, name="..\\..\\evil.png", xhr=True)
        for row in self.rows():
            self.assertNotIn("/", row["original_name"])
            self.assertNotIn("\\", row["original_name"])
            self.assertTrue((self.uploads() / row["id"]).is_file())
        self.assertFalse((self.root / "evil.png").exists())

    def test_uploaded_media_survives_application_restart(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, xhr=True)
        row = self.single_row()
        restarted = self.new_app()
        client = restarted.test_client()
        self.assertEqual(self.login(self.alice_code, client).status_code, 303)
        page = client.get("/media", base_url=BASE)
        self.assertEqual(page.status_code, 200)
        self.assertIn("photo.png", page.text)
        served = client.get("/media/" + row["id"], base_url=BASE)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.data, PNG)
        served.close()

    def test_upload_limit_is_enforced_per_file(self):
        limited = self.new_app(MAX_UPLOAD_BYTES=512)
        client = limited.test_client()
        self.assertEqual(self.login(self.alice_code, client).status_code, 303)
        token = self.token("/media", client)
        response = self.post("/media", {"csrf_token": token,
            "files": (io.BytesIO(PNG + b"\x00" * 1024), "large.png", "image/png")}, client,
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])
        response = self.post("/media", {"csrf_token": self.token("/media", client),
            "files": (io.BytesIO(PNG), "small.png", "image/png")}, client,
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(len(self.rows()), 1)

    def test_csrf_and_cross_origin_requests_cannot_upload_or_delete(self):
        alice = self.client_for(self.alice_code)
        response = self.post("/media", {"files": (io.BytesIO(PNG), "photo.png", "image/png")},
                             alice, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])
        response = self.post("/media",
            {"csrf_token": self.token("/media", alice),
             "files": (io.BytesIO(PNG), "photo.png", "image/png")}, alice,
            content_type="multipart/form-data", headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows(), [])
        self.upload(alice, xhr=True)
        row = self.single_row()
        self.assertEqual(self.post(f"/media/{row['id']}/delete", {}, alice).status_code, 400)
        self.assertEqual(len(self.rows()), 1)

    def test_media_page_escapes_client_filenames(self):
        alice = self.client_for(self.alice_code)
        name = '<script>alert(1)>.png'
        self.assertEqual(self.upload(alice, name=name, xhr=True).status_code, 200)
        page = self.get("/media", alice).text
        self.assertNotIn("<script>alert(1)></script>", page)
        self.assertIn("&lt;script&gt;alert(1)&gt;.png", page)

    def test_upload_count_limit_is_enforced(self):
        limited = self.new_app(MAX_UPLOADS_PER_USER=1)
        client = limited.test_client()
        self.assertEqual(self.login(self.alice_code, client).status_code, 303)
        token = self.token("/media", client)
        self.assertEqual(self.post("/media", {"csrf_token": token,
            "files": (io.BytesIO(PNG), "one.png", "image/png")}, client,
            content_type="multipart/form-data").status_code, 303)
        token = self.token("/media", client)
        self.assertEqual(self.post("/media", {"csrf_token": token,
            "files": (io.BytesIO(PNG), "two.png", "image/png")}, client,
            content_type="multipart/form-data").status_code, 413)
        self.assertEqual(len(self.rows()), 1)

    def test_files_larger_than_the_global_form_limit_are_accepted(self):
        alice = self.client_for(self.alice_code)
        content = PNG + b"\x00" * (64 * 1024)
        self.assertEqual(self.upload(alice, name="large.png", content=content, xhr=True).status_code, 200)
        row = self.single_row()
        self.assertEqual(row["size"], len(content))
        served = self.get("/media/" + row["id"], alice)
        self.assertEqual(served.data, content)
        served.close()

    def test_media_page_csp_allows_self_hosted_video(self):
        alice = self.client_for(self.alice_code)
        page = self.get("/media", alice)
        self.assertIn("media-src 'self'", page.headers["Content-Security-Policy"])
        self.assertIn("default-src 'none'", page.headers["Content-Security-Policy"])

    def test_stale_partial_uploads_are_cleaned_on_startup(self):
        stale = self.uploads() / ("a" * 32 + ".part")
        fresh = self.uploads() / ("b" * 32 + ".part")
        stale.write_bytes(b"incomplete")
        fresh.write_bytes(b"incomplete")
        old = time.time() - 7200
        os.utime(stale, (old, old))
        self.new_app()
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_rejected_file_in_a_batch_rolls_back_earlier_files(self):
        alice = self.client_for(self.alice_code)
        payload = {"csrf_token": self.token("/media", alice), "files": [
            (io.BytesIO(PNG), "ok.png", "image/png"),
            (io.BytesIO(b"<html>not an image</html>"), "bad.png", "image/png"),
        ]}
        response = self.post("/media", payload, alice, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])

    def test_several_files_can_be_uploaded_at_once(self):
        alice = self.client_for(self.alice_code)
        payload = {"csrf_token": self.token("/media", alice), "files": [
            (io.BytesIO(PNG), "one.png", "image/png"),
            (io.BytesIO(JPEG), "two.jpg", "image/jpeg"),
        ]}
        response = self.post("/media", payload, alice, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 303)
        rows = self.rows()
        self.assertEqual({row["original_name"] for row in rows}, {"one.png", "two.jpg"})
        self.assertEqual({row["content_type"] for row in rows}, {"image/png", "image/jpeg"})
        self.assertEqual(len(list(self.uploads().iterdir())), 2)

    def test_files_per_request_limit_is_enforced(self):
        limited = self.new_app(MAX_UPLOAD_FILES=1)
        client = limited.test_client()
        self.assertEqual(self.login(self.alice_code, client).status_code, 303)
        payload = {"csrf_token": self.token("/media", client), "files": [
            (io.BytesIO(PNG), "one.png", "image/png"),
            (io.BytesIO(JPEG), "two.jpg", "image/jpeg"),
        ]}
        response = self.post("/media", payload, client, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])

    def test_unsatisfiable_byte_range_returns_416(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, name="clip.mp4", content=MP4, content_type="video/mp4", xhr=True)
        row = self.single_row()
        for value in ("bytes=99999-", "bytes=abc", "bytes=10-2", "bytes=" + "9"*5000 + "-"):
            with self.subTest(range=value):
                response = alice.get("/media/" + row["id"], base_url=BASE, headers={"Range": value})
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response.headers["Content-Range"], f"bytes */{len(MP4)}")
                response.close()

    def test_guest_can_download_complete_gallery_as_zip(self):
        alice = self.client_for(self.alice_code)
        bob = self.client_for(self.bob_code)
        self.upload(alice, name="same.png", content=PNG, xhr=True)
        self.upload(bob, name="same.png", content=PNG_OTHER, xhr=True)
        self.assertEqual(self.get("/media/download", self.app.test_client()).status_code, 303)
        with self.get("/media/download", bob) as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "application/zip")
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                self.assertEqual(len(archive.namelist()), 2)
                self.assertEqual({archive.read(name) for name in archive.namelist()}, {PNG, PNG_OTHER})
                self.assertTrue(all(name.endswith("_same.png") for name in archive.namelist()))

    def test_extended_photo_and_video_formats_are_recognised_by_content(self):
        alice = self.client_for(self.alice_code)
        cases = [
            ("iphone.heic", b"\0\0\0\x18ftypheic\0\0\0\0mif1heic", "image/heic"),
            ("photo.avif", b"\0\0\0\x18ftypavif\0\0\0\0mif1avif", "image/avif"),
            ("camera.nef", b"II\x2a\0\x08\0\0\0" + b"\0"*128, "image/tiff"),
            ("movie.avi", b"RIFF\0\0\0\0AVI " + b"\0"*128, "video/x-msvideo"),
            ("movie.mkv", WEBM.replace(b"\x9f", b"\xa3", 1).replace(b"\x84webm", b"\x88matroska"), "video/x-matroska"),
            ("photo.unusual-extension", PNG, "image/png"),
        ]
        for name, content, expected in cases:
            with self.subTest(name=name):
                response = self.upload(alice, name=name, content=content,
                                       content_type="application/octet-stream", xhr=True)
                self.assertEqual(response.status_code, 200)
                with connect(self.app.config["DATABASE"]) as db:
                    row = db.execute("SELECT * FROM uploads WHERE original_name=?", (name,)).fetchone()
                self.assertEqual(row["content_type"], expected)

    def test_active_images_are_downloaded_and_never_embedded(self):
        alice = self.client_for(self.alice_code)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertEqual(self.upload(alice, name="image.svg", content=svg,
                                     content_type="image/svg+xml", xhr=True).status_code, 200)
        row = self.single_row()
        with self.get("/media/" + row["id"], alice) as response:
            self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertEqual(response.data, svg)
        page = self.get("/media", alice).text
        self.assertNotIn('<img src="/media/' + row["id"], page)
        self.assertIn("Pobierz oryginał", page)

    def test_download_preserves_original_filename_and_bytes(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, name="zdjęcie.png", xhr=True)
        row = self.single_row()
        with self.get("/media/" + row["id"] + "?download=1", alice) as response:
            self.assertEqual(response.data, PNG)
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertIn("filename*=UTF-8", response.headers["Content-Disposition"])

    def test_parallel_batches_cannot_exceed_account_quota(self):
        barrier = Barrier(2)

        def save(upload_id):
            connection = connect(self.app.config["DATABASE"])
            try:
                barrier.wait(timeout=5)
                record_media_batch(connection, self.alice, "guest",
                                   [(upload_id, "photo.png", "image/png", len(PNG))], 1)
                return True
            except MediaLimitExceeded:
                return False
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save, ["a" * 32, "b" * 32]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(self.rows()), 1)

    def test_storage_failure_removes_all_files_in_batch(self):
        alice = self.client_for(self.alice_code)
        payload = {"csrf_token": self.token("/media", alice), "files": [
            (io.BytesIO(PNG), "one.png", "image/png"),
            (io.BytesIO(PNG), "two.png", "image/png"),
        ]}
        with patch("app.record_media_batch", side_effect=sqlite3.OperationalError("unavailable")):
            response = self.post("/media", payload, alice, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])

    def test_batch_cannot_exceed_total_size_limit(self):
        limited = self.new_app(MAX_UPLOAD_BYTES=len(PNG) + 10)
        client = limited.test_client()
        self.login(self.alice_code, client)
        payload = {"csrf_token": self.token("/media", client), "files": [
            (io.BytesIO(PNG), "one.png", "image/png"),
            (io.BytesIO(PNG), "two.png", "image/png"),
        ]}
        response = self.post("/media", payload, client, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.rows(), [])
        self.assertEqual(list(self.uploads().iterdir()), [])

    def test_stale_if_range_returns_full_file_and_head_has_no_body(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, name="clip.mp4", content=MP4, content_type="video/mp4", xhr=True)
        path = "/media/" + self.single_row()["id"]
        response = alice.get(path, base_url=BASE,
                             headers={"Range": "bytes=4-11", "If-Range": '"stale-etag"'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, MP4)
        response.close()
        response = alice.head(path, base_url=BASE, headers={"Range": "bytes=4-11"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b"")
        self.assertEqual(response.content_length, 8)
        response.close()

    def test_media_page_is_translated(self):
        alice = self.client_for(self.alice_code)
        self.upload(alice, xhr=True)
        page = self.get("/media?lang=en", alice)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Media library", page.text)
        self.assertIn("Upload selected files", page.text)
        self.assertIn("/media?lang=pl", page.text)


if __name__ == "__main__":
    unittest.main()
