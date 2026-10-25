#!/usr/bin/python3
"""Root-owned receiver; app source only executes in an unprivileged service."""
import ast
import fcntl
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import zipfile

MAX_BYTES = 16 * 1024 * 1024
FILES = {"public/revision.txt", "app.py", "manage.py", "requirements.txt", "index.html",
         "wedding/__init__.py", "wedding/store.py", "templates/base.html",
         "templates/login.html", "templates/guest.html", "templates/error.html",
         "templates/admin.html", "templates/admin_login.html", "templates/admin_code.html",
         "templates/media.html",
         "public/assets/site.css", "public/assets/site.js", "public/assets/favicon.svg"}


def switch(current, destination):
    temporary = current.with_name("current.next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(destination)
    temporary.replace(current)


def healthy(config, revision, index_digest):
    try:
        base = config["health_url"].rstrip("/")
        with urlopen(base + "/revision.txt", timeout=3) as response:
            if response.read(100).decode().strip() != revision:
                return False
        with urlopen(config["application_health_url"], timeout=3) as response:
            health = json.loads(response.read(4096))
            return (health.get("status") == "ok" and health.get("revision") == revision
                    and health.get("index_sha256") == index_digest)
    except (OSError, ValueError, AttributeError):
        return False


def deploy(config, revision, digest, stream):
    if not re.fullmatch(r"[a-f0-9]{40}", revision) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid revision or archive digest")
    state = Path(config["state_dir"])
    state.mkdir(parents=True, exist_ok=True)
    with (state / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("Archive size or digest mismatch")
        releases = state / "releases"
        releases.mkdir(exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="staging-", dir=releases))
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                entries = archive.infolist()
                if len(entries) != len(FILES) or {entry.filename for entry in entries} != FILES:
                    raise ValueError("Unexpected archive entries")
                if sum(entry.file_size for entry in entries) > MAX_BYTES:
                    raise ValueError("Expanded archive too large")
                for entry in entries:
                    target = staging / entry.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # Write regular files only, ignoring archive modes and symlink metadata.
                    target.write_bytes(archive.read(entry))
                    target.chmod(0o644)
            if (staging / "public/revision.txt").read_text().strip() != revision:
                raise ValueError("Archive revision mismatch")
            if not (staging / "index.html").read_text().strip():
                raise ValueError("Empty index.html")
            if (config.get("requirements_sha256") and
                    hashlib.sha256((staging / "requirements.txt").read_bytes()).hexdigest() != config["requirements_sha256"]):
                raise ValueError("Dependencies changed: install the reviewed runtime before deploying")
            for name in FILES:
                if name.endswith(".py"):
                    ast.parse((staging / name).read_text())
            staging.chmod(0o755)
            for directory in staging.rglob("*"):
                if directory.is_dir():
                    directory.chmod(0o755)
            release = releases / (revision + "-" + digest[:16])
            if release.exists():
                shutil.rmtree(staging)
            else:
                staging.rename(release)
            current = state / "current"
            previous = current.resolve(strict=True) if current.is_symlink() else None
            index_digest = hashlib.sha256((release / "index.html").read_bytes()).hexdigest()
            switch(current, release)
            try:
                restart(config)
                for _ in range(config.get("health_attempts", 10)):
                    if healthy(config, revision, index_digest):
                        break
                    time.sleep(config.get("health_interval", 2))
                else:
                    raise RuntimeError("Origin health check failed")
                if previous and previous != release:
                    (state / "previous").write_text(str(previous) + "\n")
            except BaseException:
                if previous:
                    switch(current, previous)
                    old_revision = (previous / "public/revision.txt").read_text().strip()
                    restart(config)
                    old_digest = hashlib.sha256((previous / "index.html").read_bytes()).hexdigest()
                    if not healthy(config, old_revision, old_digest):
                        print("ROLLBACK HEALTH CHECK FAILED", file=sys.stderr)
                else:
                    current.unlink(missing_ok=True)
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    print(f"Deployed {revision}")


def restart(config):
    if config.get("restart_service"):
        # Fixed command, never derived from the archive or SSH arguments.
        subprocess.run(["systemctl", "restart", "weronikarafal-web.service"], check=True, timeout=45)


def main():
    config = json.loads(Path("/etc/weronikarafal/deploy.json").read_text())
    if sys.argv[1:] == ["status"]:
        print((Path(config["state_dir"]) / "current/public/revision.txt").read_text().strip())
    elif len(sys.argv) == 3:
        deploy(config, sys.argv[1], sys.argv[2], sys.stdin.buffer)
    else:
        raise SystemExit("Expected status or REVISION ARCHIVE_SHA256")


if __name__ == "__main__":
    main()
