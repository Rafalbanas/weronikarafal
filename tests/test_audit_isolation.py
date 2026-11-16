"""Audit fixtures must never inherit a deployment's private uploads directory."""
import os
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import test_guests
from scripts.check_site import ROOT, check


class AuditIsolationTests(unittest.TestCase):
    def test_site_checker_does_not_clean_environment_uploads(self):
        with tempfile.TemporaryDirectory() as outside:
            stale = Path(outside) / "private.part"
            stale.write_bytes(b"unrelated private upload")
            old = time.time() - 7200
            os.utime(stale, (old, old))
            with patch.dict(os.environ, {"WEDDING_UPLOADS_DIR": outside}), redirect_stdout(io.StringIO()):
                check(ROOT)
            self.assertEqual(stale.read_bytes(), b"unrelated private upload")

    def test_guest_fixture_does_not_clean_environment_uploads(self):
        with tempfile.TemporaryDirectory() as outside:
            stale = Path(outside) / "private.part"
            stale.write_bytes(b"unrelated private upload")
            old = time.time() - 7200
            os.utime(stale, (old, old))
            fixture = test_guests.GuestTests()
            try:
                with patch.dict(os.environ, {"WEDDING_UPLOADS_DIR": outside}):
                    fixture.setUp()
                uploads = Path(fixture.app.config["UPLOADS_DIR"])
                self.assertEqual(uploads, fixture.root / "uploads")
                self.assertEqual(stale.read_bytes(), b"unrelated private upload")
            finally:
                fixture.doCleanups()
