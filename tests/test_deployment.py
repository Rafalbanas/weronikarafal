import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from deploy.deploy import deploy, healthy
from scripts.package import package, SOURCE_FILES, ASSET_FILES

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/healthz":
            release = Path(self.directory).parent
            body = json.dumps({"status": "ok", "revision": (release / "public/revision.txt").read_text().strip(),
                "index_sha256": hashlib.sha256((release / "index.html").read_bytes()).hexdigest()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()


class DeploymentTests(unittest.TestCase):
    def test_archive_is_independent_of_checkout_and_packaging_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in SOURCE_FILES + ASSET_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
            first, second = io.BytesIO(), io.BytesIO()
            package(root, first, "a" * 40)
            for name in SOURCE_FILES + ASSET_FILES:
                os.utime(root / name, (946684800, 946684800))
            with patch("zipfile.time.localtime", return_value=(2030, 1, 2, 3, 4, 6, 0, 0, 0)):
                package(root, second, "a" * 40)
            self.assertEqual(first.getvalue(), second.getvalue())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        state = self.root / "state"
        self.config = {"state_dir": str(state), "health_attempts": 1, "health_interval": 0}
        handler = lambda *args, **kwargs: QuietHandler(
            *args, directory=str(state / "current/public"), **kwargs)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.config["health_url"] = f"http://127.0.0.1:{self.server.server_port}"
        self.config["application_health_url"] = self.config["health_url"]+"/healthz"

    def payload(self, revision):
        output = io.BytesIO()
        package(ROOT, output, revision)
        return output.getvalue()

    def send(self, revision, payload):
        deploy(self.config, revision, hashlib.sha256(payload).hexdigest(), io.BytesIO(payload))

    def test_release_is_exact_static_source_and_redeploy_is_safe(self):
        revision = "a" * 40
        payload = self.payload(revision)
        self.send(revision, payload)
        self.send(revision, payload)
        public = Path(self.config["state_dir"]) / "current/public"
        self.assertEqual((public.parent / "index.html").read_bytes(), (ROOT / "index.html").read_bytes())
        self.assertEqual({p.name for p in public.iterdir()}, {"assets", "revision.txt"})
        self.assertFalse((public / "app.py").exists())
        self.assertFalse((public / "templates").exists())
        self.assertTrue(public.stat().st_mode & 0o005 == 0o005)

    def test_redeploy_preserves_original_rollback_target(self):
        self.send("a" * 40, self.payload("a" * 40))
        self.send("b" * 40, self.payload("b" * 40))
        previous = Path(self.config["state_dir"]) / "previous"
        saved = previous.read_text()
        self.send("b" * 40, self.payload("b" * 40))
        self.assertEqual(previous.read_text(), saved)
        self.assertIn("a" * 40, saved)

    def test_failed_health_restores_previous_release(self):
        self.send("a" * 40, self.payload("a" * 40))
        with patch("deploy.deploy.healthy", side_effect=lambda config, sha, digest:
                   False if sha == "b" * 40 else healthy(config, sha, digest)):
            with self.assertRaisesRegex(RuntimeError, "health"):
                self.send("b" * 40, self.payload("b" * 40))
        current = Path(self.config["state_dir"]) / "current/public/revision.txt"
        self.assertEqual(current.read_text().strip(), "a" * 40)

    def test_rejects_traversal_before_switch(self):
        output = io.BytesIO(self.payload("a" * 40))
        with zipfile.ZipFile(output, "a") as archive:
            archive.writestr("../../escape", "bad")
        with self.assertRaisesRegex(ValueError, "entries"):
            self.send("a" * 40, output.getvalue())
        self.assertFalse((self.root / "escape").exists())
        self.assertFalse((Path(self.config["state_dir"]) / "current").exists())

    def test_rejects_corrupt_digest_and_wrong_revision(self):
        payload = self.payload("a" * 40)
        with self.assertRaisesRegex(ValueError, "digest"):
            deploy(self.config, "a" * 40, "0" * 64, io.BytesIO(payload))
        with self.assertRaisesRegex(ValueError, "revision mismatch"):
            self.send("b" * 40, payload)

    def test_rejects_duplicate_entries_and_missing_index(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("public/revision.txt", "a" * 40 + "\n")
        with self.assertRaisesRegex(ValueError, "entries"):
            self.send("a" * 40, output.getvalue())
        output = io.BytesIO(self.payload("a" * 40))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(output, "a") as archive:
                archive.writestr("index.html", "replacement")
        with self.assertRaisesRegex(ValueError, "entries"):
            self.send("a" * 40, output.getvalue())

    def test_failed_first_release_leaves_no_current(self):
        with patch("deploy.deploy.healthy", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "health"):
                self.send("a" * 40, self.payload("a" * 40))
        self.assertFalse((Path(self.config["state_dir"]) / "current").exists())

    def test_rollbacks_restart_application_and_do_not_touch_guest_database(self):
        data = self.root / "private.sqlite3"
        data.write_bytes(b"existing guests and responses")
        with patch("deploy.deploy.restart") as restart:
            self.send("a" * 40, self.payload("a" * 40))
            with patch("deploy.deploy.healthy", side_effect=lambda config, sha, digest:
                       sha != "b" * 40 and healthy(config, sha, digest)):
                with self.assertRaisesRegex(RuntimeError, "health"):
                    self.send("b" * 40, self.payload("b" * 40))
            self.assertEqual(restart.call_count, 3)
        self.assertEqual(data.read_bytes(), b"existing guests and responses")

    def test_changed_runtime_dependencies_are_rejected_before_switch(self):
        self.config["requirements_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "Dependencies changed"):
            self.send("a"*40, self.payload("a"*40))
        self.assertFalse((Path(self.config["state_dir"]) / "current").exists())

    def test_packaged_release_serves_calendar_and_private_pages_from_extracted_copy(self):
        # The archive must include wedding/calendar.py, and the extracted release
        # must serve /ceremony.ics without importing anything from the source repo.
        payload = self.payload("a" * 40)
        extracted = Path(self.temp.name) / "release"
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIn("wedding/calendar.py", {entry.filename for entry in archive.infolist()})
            for entry in archive.infolist():
                target = extracted / entry.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))
        data_dir = Path(self.temp.name) / "data"
        data_dir.mkdir()
        probe = Path(self.temp.name) / "probe.py"
        probe.write_text(
            "import os\n"
            "import re\n"
            "import sys\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from app import create_app\n"
            "from wedding.store import connect, invitation\n"
            "app = create_app({'TESTING': True, 'TRUSTED_HOSTS': ['localhost'], 'TRUST_PROXY': False})\n"
            "client = app.test_client()\n"
            "base = 'https://localhost'\n"
            "response = client.get('/ceremony.ics', base_url=base)\n"
            "body = response.get_data().decode('utf-8')\n"
            "assert response.status_code == 200\n"
            "assert 'DTSTART:20270827T120000Z' in body\n"
            "for path in ('/schedule', '/tables'):\n"
            "    assert client.get(path, base_url=base).status_code == 303\n"
            "with connect(app.config['DATABASE']) as db:\n"
            "    _, code = invitation(db, 'Guest fixture')\n"
            "login = client.get('/login', base_url=base).text\n"
            "token = re.search(r'name=\"csrf_token\" value=\"([^\"]+)\"', login).group(1)\n"
            "assert client.post('/login', base_url=base, data={'csrf_token': token, 'code': code}, headers={'Referer': base + '/login', 'Origin': base}).status_code == 303\n"
            "for path in ('/schedule', '/tables'):\n"
            "    page = client.get(path, base_url=base)\n"
            "    assert page.status_code == 200\n"
            "    assert 'data-theme-toggle' in page.text\n"
            "    assert 'noindex' in page.headers['X-Robots-Tag']\n"
            "print('OK')\n")
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONDATADIR", None)
        env.update(WEDDING_SECRET_KEY="k" * 32, WEDDING_DATA_DIR=str(data_dir))
        result = subprocess.run([sys.executable, str(probe)], cwd=extracted, env=env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "OK\n")


if __name__ == "__main__":
    unittest.main()
