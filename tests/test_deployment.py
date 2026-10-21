import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from deploy.deploy import deploy, healthy
from scripts.package import package

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class DeploymentTests(unittest.TestCase):
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
        self.assertEqual((public / "index.html").read_bytes(), (ROOT / "index.html").read_bytes())
        self.assertEqual({p.name for p in public.iterdir()}, {"index.html", "revision.txt"})
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
                archive.writestr("public/index.html", "replacement")
        with self.assertRaisesRegex(ValueError, "entries"):
            self.send("a" * 40, output.getvalue())

    def test_failed_first_release_leaves_no_current(self):
        with patch("deploy.deploy.healthy", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "health"):
                self.send("a" * 40, self.payload("a" * 40))
        self.assertFalse((Path(self.config["state_dir"]) / "current").exists())


if __name__ == "__main__":
    unittest.main()
