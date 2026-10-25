"""Private persistent data. No guest list or invitation codes belong in Git."""
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import re
import fcntl
from werkzeug.security import generate_password_hash, check_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS guests (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, code_hash TEXT NOT NULL UNIQUE,
    allows_companion INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, guest_id TEXT NOT NULL REFERENCES guests(id),
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rsvps (
    guest_id TEXT PRIMARY KEY REFERENCES guests(id),
    attendance TEXT NOT NULL CHECK(attendance IN ('yes', 'no')),
    companion_name TEXT NOT NULL, diet TEXT NOT NULL, lodging TEXT NOT NULL,
    notes TEXT NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS throttle (
    bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, resets_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS administrators (
    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES administrators(username),
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_recovery (
    username TEXT PRIMARY KEY REFERENCES administrators(username), code_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    owner_kind TEXT NOT NULL CHECK(owner_kind IN ('guest', 'admin')),
    original_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL CHECK(size >= 0),
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS uploads_owner ON uploads(owner_id, created_at);
"""

DEFAULT_DETAILS = {
    "ceremony": {"name": 'Bazylika św. Ludwika Króla i Wniebowzięcia Najświętszej Maryi Panny',
                 "address": 'ul. Panewnicka 76, 40-760 Katowice (Panewniki)'},
    "venue": {"name": "", "address": ""},
    "contacts": [],
    "schedule": [],
}


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # SQLite's journal-mode transition can return BUSY without waiting. Protect
    # the whole initialization, including WAL setup, across worker processes.
    with path.with_name(path.name + ".init.lock").open("a") as lock:
        Path(lock.name).chmod(0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        db = connect(path)
        try:
            with db:
                db.execute("PRAGMA journal_mode = WAL")
                db.executescript(SCHEMA)
                db.execute("BEGIN IMMEDIATE")
                if "code_id" not in {row[1] for row in db.execute("PRAGMA table_info(guests)")}:
                    db.execute("ALTER TABLE guests ADD COLUMN code_id TEXT")
                columns = {row[1] for row in db.execute("PRAGMA table_info(guests)")}
                if "partner_name" not in columns:
                    db.execute("ALTER TABLE guests ADD COLUMN partner_name TEXT NOT NULL DEFAULT ''")
                if "children" not in columns:
                    db.execute("ALTER TABLE guests ADD COLUMN children TEXT NOT NULL DEFAULT '[]'")
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS guests_code_id ON guests(code_id)")
        finally:
            db.close()
        path.chmod(0o600)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_code(code):
    return "".join(code.split()).replace("-", "").lower()


def validate_household(name, partner_name="", children=None):
    children = [] if children is None else children
    if not isinstance(children, list) or len(children) > 20:
        raise ValueError("Invalid children")
    values = [name.strip(), partner_name.strip()] + [child.strip() for child in children]
    if not values[0] or any(len(value) > 120 or any(ord(c) < 32 for c in value) for value in values):
        raise ValueError("Invalid household names")
    return values[0], values[1], values[2:]


def invitation(db, name, companion=False, guest_id=None, code=None, partner_name="", children=None):
    name, partner_name, children = validate_household(name, partner_name, children)
    code = normalize_code(code) if code else secrets.token_hex(24)
    if not re.fullmatch(r"[a-f0-9]{48}", code):
        raise ValueError("Kod musi zawierać 48 znaków 0–9 / a–f; myślniki są opcjonalne.")
    guest_id = guest_id or secrets.token_hex(16)
    with db:
        db.execute("""INSERT INTO guests(id, name, code_hash, allows_companion, active, code_id, partner_name, children)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET
            code_hash=excluded.code_hash, code_id=excluded.code_id, active=1""",
            (guest_id, name, generate_password_hash(code), int(companion), code[:16], partner_name,
             json.dumps(children, ensure_ascii=False)))
        db.execute("DELETE FROM sessions WHERE guest_id=?", (guest_id,))
    return guest_id, "-".join(code[i:i+4] for i in range(0, len(code), 4))


def authenticate_invitation(db, code):
    code = normalize_code(code)
    if re.fullmatch(r"[a-f0-9]{48}", code):
        person = db.execute("SELECT * FROM guests WHERE code_id=? AND active=1", (code[:16],)).fetchone()
        if person and check_password_hash(person["code_hash"], code):
            return person
    elif re.fullmatch(r"[a-f0-9]{32}", code):
        # Only the pre-existing 128-bit codes use the legacy digest. A successful
        # login upgrades to a salted hash; the first eight characters become its ID.
        person = db.execute("SELECT * FROM guests WHERE code_id=? AND active=1", (code[:8],)).fetchone()
        if person and check_password_hash(person["code_hash"], code):
            return person
        person = db.execute("SELECT * FROM guests WHERE code_id IS NULL AND code_hash=? AND active=1", (digest(code),)).fetchone()
        if person:
            with db:
                db.execute("UPDATE guests SET code_hash=?, code_id=? WHERE id=?",
                           (generate_password_hash(code), code[:8], person["id"]))
            return person
    return None


def revoke(db, guest_id):
    with db:
        db.execute("UPDATE guests SET active=0 WHERE id=?", (guest_id,))
        db.execute("DELETE FROM sessions WHERE guest_id=?", (guest_id,))


def recovery_code():
    code = secrets.token_hex(16)
    return "-".join(code[i:i+4] for i in range(0, len(code), 4))


def issue_admin_recovery(db, username):
    if not db.execute("SELECT 1 FROM administrators WHERE username=?", (username,)).fetchone():
        raise ValueError("Unknown administrator")
    code = recovery_code()
    with db:
        db.execute("INSERT INTO admin_recovery VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET code_hash=excluded.code_hash",
                   (username, generate_password_hash(normalize_code(code))))
    return code


def record_media(db, owner_id, owner_kind, upload_id, original_name, content_type, size, created_at=None):
    """Register one saved binary. The upload id is also its random on-disk name."""
    created_at = int(time.time()) if created_at is None else created_at
    with db:
        db.execute("""INSERT INTO uploads(id, owner_id, owner_kind, original_name, content_type, size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (upload_id, owner_id, owner_kind, original_name, content_type, size, created_at))
    return created_at


def media_record(db, upload_id):
    if not isinstance(upload_id, str):
        return None
    return db.execute("SELECT * FROM uploads WHERE id=?", (upload_id,)).fetchone()


def media_list(db, owner_id, owner_kind, administrator=False):
    """Admins see every upload; everyone else only the files they own."""
    if administrator:
        return db.execute("""SELECT uploads.*, guests.name AS owner_name FROM uploads
            LEFT JOIN guests ON uploads.owner_kind='guest' AND guests.id=uploads.owner_id
            ORDER BY uploads.created_at DESC, uploads.id""").fetchall()
    return db.execute("""SELECT * FROM uploads WHERE owner_id=? AND owner_kind=?
        ORDER BY created_at DESC, id""", (owner_id, owner_kind)).fetchall()


def media_count(db, owner_id, owner_kind):
    return db.execute("SELECT count(*) FROM uploads WHERE owner_id=? AND owner_kind=?",
                      (owner_id, owner_kind)).fetchone()[0]


def remove_media(db, upload_id):
    with db:
        return db.execute("DELETE FROM uploads WHERE id=?", (upload_id,)).rowcount


def allow_request(db, buckets, now=None):
    """Atomic limits shared by all WSGI workers; never store raw IP addresses."""
    now = int(time.time()) if now is None else now
    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM throttle WHERE resets_at<=?", (now,))
        for key, limit, window in buckets:
            row = db.execute("SELECT attempts FROM throttle WHERE bucket=?", (key,)).fetchone()
            if row and row["attempts"] >= limit:
                return False
        for key, limit, window in buckets:
            db.execute("""INSERT INTO throttle VALUES (?, 1, ?)
                ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1""", (key, now+window))
    return True


def details(path):
    if not Path(path).exists():
        return json.loads(json.dumps(DEFAULT_DETAILS))
    return validate_details(json.loads(Path(path).read_text()))


def validate_details(data):
    import re
    if not isinstance(data, dict) or set(data) != set(DEFAULT_DETAILS):
        raise ValueError("Expected ceremony, venue, contacts and schedule.")
    for key in ("ceremony", "venue"):
        if not isinstance(data[key], dict) or set(data[key]) != {"name", "address"}:
            raise ValueError("Invalid location.")
        if any(not isinstance(value, str) or len(value) > 250 for value in data[key].values()):
            raise ValueError("Invalid location text.")
    if not isinstance(data["contacts"], list) or len(data["contacts"]) > 6:
        raise ValueError("Invalid contacts.")
    for contact in data["contacts"]:
        if not isinstance(contact, dict) or set(contact) != {"role", "name", "phone"}:
            raise ValueError("Invalid contact.")
        if any(not isinstance(value, str) or len(value) > 120 for value in contact.values()):
            raise ValueError("Invalid contact text.")
        if not re.fullmatch(r"\+?[0-9 ()-]{6,24}", contact["phone"]):
            raise ValueError("Invalid contact phone number.")
    if not isinstance(data["schedule"], list) or len(data["schedule"]) > 20:
        raise ValueError("Invalid schedule.")
    for item in data["schedule"]:
        if not isinstance(item, dict) or set(item) != {"time", "title", "description"}:
            raise ValueError("Invalid schedule item.")
        if any(not isinstance(value, str) or len(value) > 500 for value in item.values()):
            raise ValueError("Invalid schedule text.")
    return data
