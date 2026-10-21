#!/usr/bin/env python3
"""One-time, root-run migration after review; subsequent deployments use Actions."""
import argparse
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package import package
from deploy.deploy import FILES, switch


def run(*args):
    subprocess.run(args, check=True)


def install():
    if os.geteuid() != 0:
        raise SystemExit("Run as root after reviewing and merging the PR.")
    os.umask(0o022)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise SystemExit("Use a clean checkout of the reviewed commit.")
    state = Path("/var/lib/weronikarafal")
    state.mkdir(exist_ok=True)
    with (state / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        migrate(state, revision)


def migrate(state, revision):
    data = Path("/var/lib/weronikarafal-data")
    config = Path("/etc/weronikarafal")
    config.mkdir(mode=0o700, exist_ok=True)
    backups = Path("/var/backups/weronikarafal")
    backups.mkdir(mode=0o700, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="app-migration-", dir=backups))
    files = {
        ROOT / "deploy/deploy.py": Path("/usr/local/sbin/weronikarafal-deploy"),
        ROOT / "deploy/ssh-command.sh": Path("/usr/local/bin/weronikarafal-cd-ssh"),
        ROOT / "deploy/weronikarafal-web.service": Path("/etc/systemd/system/weronikarafal-web.service"),
        ROOT / "deploy/nginx-site.conf": Path("/etc/nginx/sites-available/weronikarafal.com.conf"),
        ROOT / "deploy/nginx-loopback.conf": Path("/etc/nginx/conf.d/weronikarafal-health.conf"),
        ROOT / "deploy/nginx-cloudflare-realip.conf": Path("/etc/nginx/snippets/weronikarafal-realip.conf"),
    }
    changed = list(files.values())+[config / "deploy.json"]
    saved = {}
    for i, target in enumerate(changed):
        saved[target] = backup / str(i) if target.exists() else None
        if saved[target]:
            shutil.copy2(target, saved[target])
    (backup / "paths.json").write_text(json.dumps({str(k): str(v) if v else None for k, v in saved.items()}, indent=2))
    previous = (state / "current").resolve(strict=True) if (state / "current").is_symlink() else None
    was_active = subprocess.run(["systemctl", "is-active", "--quiet", "weronikarafal-web.service"]).returncode == 0
    if data.joinpath("guests.sqlite3").exists():
        source = sqlite3.connect(data / "guests.sqlite3")
        destination = sqlite3.connect(backup / "guests.sqlite3")
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
        (backup / "guests.sqlite3").chmod(0o600)
    try:
        account = pwd.getpwnam("weronikarafal-web")
    except KeyError:
        run("useradd", "--system", "--no-create-home", "--home-dir", str(data), "--shell", "/usr/sbin/nologin", "weronikarafal-web")
        account = pwd.getpwnam("weronikarafal-web")
    data.mkdir(mode=0o700, exist_ok=True)
    os.chown(data, account.pw_uid, account.pw_gid)
    data.chmod(0o700)
    env = config / "web.env"
    if not env.exists():
        # Use exclusive creation; the persistent secret must never change on redeploy.
        fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write("WEDDING_SECRET_KEY="+secrets.token_urlsafe(48)+"\nWEDDING_DATA_DIR="+str(data)+"\nWEDDING_TRUST_PROXY=1\n")
    requirements_hash = hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()
    runtime = Path("/opt/weronikarafal")
    venv = runtime / "venvs" / requirements_hash[:16]
    if not (venv / ".ready").exists():
        if venv.exists():
            shutil.rmtree(venv)
        run("python3", "-m", "venv", str(venv))
        run(str(venv / "bin/pip"), "install", "-r", str(ROOT / "requirements.txt"))
        run(str(venv / "bin/pip"), "check")
        (venv / ".ready").touch()
    old_venv = (runtime / "venv").resolve() if (runtime / "venv").is_symlink() else None
    payload = io.BytesIO()
    package(ROOT, payload, revision)
    release = state / "releases" / ("bootstrap-app-"+revision)
    if not release.exists():
        staging = Path(tempfile.mkdtemp(prefix="migration-", dir=state / "releases"))
        try:
            with zipfile.ZipFile(payload) as archive:
                if set(archive.namelist()) != FILES:
                    raise ValueError("Unexpected release files")
                for entry in archive.infolist():
                    target = staging / entry.filename
                    target.parent.mkdir(exist_ok=True, parents=True)
                    target.write_bytes(archive.read(entry))
                    target.chmod(0o644)
            staging.chmod(0o755)
            for directory in staging.rglob("*"):
                if directory.is_dir():
                    directory.chmod(0o755)
            staging.rename(release)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    try:
        switch(runtime / "venv", venv)
        # Keep the public site on its existing version until backend health passes.
        for source, target in files.items():
            if source.name != "nginx-site.conf":
                shutil.copy2(source, target)
                target.chmod(0o755 if target.parent in {Path('/usr/local/sbin'), Path('/usr/local/bin')} else 0o644)
        deploy_config = json.loads((ROOT / "deploy/deploy.example.json").read_text())
        deploy_config["requirements_sha256"] = requirements_hash
        (config / "deploy.json").write_text(json.dumps(deploy_config, indent=2)+"\n")
        (config / "deploy.json").chmod(0o600)
        nginx_path = Path("/etc/nginx/sites-available/weronikarafal.com.conf")
        if previous:
            # During the first migration keep the old static page served from its
            # absolute release path while current switches to the new application.
            old_site = nginx_path.read_text()
            pinned_site = old_site.replace("root /var/lib/weronikarafal/current/public;", "root "+str(previous / "public")+";")
            if pinned_site != old_site:
                nginx_path.write_text(pinned_site)
                run("nginx", "-t")
                run("systemctl", "reload", "nginx")
        switch(state / "current", release)
        run("systemctl", "daemon-reload")
        run("systemctl", "restart", "weronikarafal-web.service")
        for _ in range(15):
            try:
                with urlopen("http://127.0.0.1:18083/healthz", timeout=3) as response:
                    health = json.load(response)
                if health.get("status") == "ok" and health.get("revision") == revision:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Application failed health checks")
        shutil.copy2(ROOT / "deploy/nginx-site.conf", Path("/etc/nginx/sites-available/weronikarafal.com.conf"))
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
        run("systemctl", "enable", "weronikarafal-web.service")
        print("Application installed at revision", revision)
        print("Rollback/configuration backup:", backup)
    except BaseException:
        subprocess.run(["systemctl", "stop", "weronikarafal-web.service"])
        if previous:
            switch(state / "current", previous)
        if old_venv:
            switch(runtime / "venv", old_venv)
        for target, source in saved.items():
            if source:
                shutil.copy2(source, target)
            else:
                target.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"])
        if was_active:
            subprocess.run(["systemctl", "start", "weronikarafal-web.service"])
        subprocess.run(["nginx", "-t"], check=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Migrate the production server using this reviewed checkout.")
    args = parser.parse_args()
    if not args.apply:
        parser.error("Pass --apply only after reviewing and merging the PR; see deploy/README.md.")
    install()
