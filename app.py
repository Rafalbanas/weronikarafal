"""Public ceremony page and authenticated guest area."""
from datetime import timedelta
from functools import wraps
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import SecurityError

from wedding.store import allow_request, connect, details, digest, initialize, normalize_code

ROOT = Path(__file__).resolve().parent
DIETS = {"standard": "Standardowa", "vegetarian": "Wegetariańska", "vegan": "Wegańska",
         "gluten_free": "Bezglutenowa", "other": "Inna / alergie"}


def create_app(config=None):
    assets = ROOT / "public/assets" if (ROOT / "public/assets").exists() else ROOT / "assets"
    app = Flask(__name__, template_folder=str(ROOT), static_folder=str(assets), static_url_path="/assets")
    data = Path(os.environ.get("WEDDING_DATA_DIR", "/var/lib/weronikarafal-data"))
    app.config.update(
        SECRET_KEY=os.environ.get("WEDDING_SECRET_KEY"),
        DATABASE=str(data / "guests.sqlite3"), DETAILS=str(data / "details.json"),
        SESSION_COOKIE_NAME="__Host-wedding", SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=16*1024, MAX_FORM_MEMORY_SIZE=16*1024, MAX_FORM_PARTS=20,
        TRUSTED_HOSTS=["weronikarafal.com", "www.weronikarafal.com", "127.0.0.1", "localhost"],
        LOGIN_LIMIT=12, TRUST_PROXY=os.environ.get("WEDDING_TRUST_PROXY") == "1",
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set a persistent WEDDING_SECRET_KEY with at least 32 random characters.")
    if app.config["TRUST_PROXY"]:
        # Only enabled behind the loopback Nginx listener, which overwrites these headers.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    CSRFProtect(app)
    initialize(app.config["DATABASE"])

    def db():
        if "db" not in g:
            g.db = connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_):
        if connection := g.pop("db", None):
            connection.close()

    @app.before_request
    def load_guest():
        g.guest = None
        sid = session.get("sid")
        if isinstance(sid, str):
            g.guest = db().execute("""SELECT guests.* FROM sessions JOIN guests
                ON guests.id=sessions.guest_id WHERE sessions.token_hash=?
                AND sessions.expires_at>? AND guests.active=1""", (digest(sid), int(time.time()))).fetchone()
            if not g.guest:
                session.clear()
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                abort(400)

    @app.after_request
    def headers(response):
        response.headers.update({
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache", "Vary": "Cookie",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
        })
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    def require_guest(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if not g.guest:
                return redirect(url_for("login"), code=303)
            return view(*args, **kwargs)
        return protected

    def limited(kind, buckets):
        # HMAC prevents recovering stored IPs by guessing hashes of common addresses.
        ip = hmac.new(app.secret_key.encode(), request.remote_addr.encode(), hashlib.sha256).hexdigest()
        limits = [(kind+":"+name.replace("{ip}", ip), limit, window) for name, limit, window in buckets]
        if not allow_request(db(), limits):
            abort(429)
        return limits

    @app.get("/")
    def index():
        ceremony = details(app.config["DETAILS"])["ceremony"]
        return render_template("index.html", ceremony=ceremony,
            map_url="https://www.google.com/maps/search/?"+urlencode({"api": 1, "query": ceremony["address"]}))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.guest:
            return redirect(url_for("guest"), code=303)
        error = None
        if request.method == "POST":
            limits = limited("login", [("ip:{ip}", app.config["LOGIN_LIMIT"], 900), ("global", 1200, 3600)])
            code = normalize_code(request.form.get("code", ""))
            valid = re.fullmatch(r"[a-f0-9]{32}", code) is not None
            person = db().execute("SELECT * FROM guests WHERE code_hash=? AND active=1", (digest(code),)).fetchone()
            if valid and person:
                sid = secrets.token_urlsafe(32)
                now = int(time.time())
                with db():
                    # Successful guests sharing a Wi-Fi network do not consume
                    # each other's failed-login budget. The global cap remains.
                    db().execute("UPDATE throttle SET attempts=max(0, attempts-1) WHERE bucket=?", (limits[0][0],))
                    db().execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
                    db().execute("INSERT INTO sessions VALUES (?, ?, ?)", (digest(sid), person["id"], now+8*3600))
                session.clear()
                session.permanent = True
                session["sid"] = sid
                return redirect(url_for("guest"), code=303)
            error = "Nie udało się zalogować. Sprawdź kod z zaproszenia i spróbuj ponownie."
        return render_template("templates/login.html", error=error), 401 if error else 200

    @app.get("/guest")
    @require_guest
    def guest():
        rsvp = db().execute("SELECT * FROM rsvps WHERE guest_id=?", (g.guest["id"],)).fetchone()
        guests = db().execute("""SELECT guests.name, rsvps.attendance FROM guests
            LEFT JOIN rsvps ON guests.id=rsvps.guest_id WHERE guests.active=1
            ORDER BY guests.name COLLATE NOCASE""").fetchall()
        return render_template("templates/guest.html", rsvp=rsvp, guests=guests,
            diets=DIETS, private=details(app.config["DETAILS"]))

    @app.post("/rsvp")
    @require_guest
    def rsvp():
        limited("rsvp", [("guest:"+g.guest["id"], 10, 60), ("ip:{ip}", 60, 60)])
        expected = {"csrf_token", "attendance", "companion_name", "diet", "lodging", "notes"}
        if set(request.form) - expected or any(len(request.form.getlist(key)) != 1 for key in request.form):
            abort(400)
        attendance = request.form.get("attendance", "")
        companion = request.form.get("companion_name", "").strip()
        diet = request.form.get("diet", "")
        lodging = request.form.get("lodging", "")
        notes = request.form.get("notes", "").strip()
        if attendance not in {"yes", "no"} or diet not in DIETS or lodging not in {"yes", "no"}:
            abort(400)
        if len(companion) > 120 or len(notes) > 2000 or "\x00" in companion+notes:
            abort(400)
        if companion and not g.guest["allows_companion"]:
            abort(403)
        if attendance == "no":
            companion, diet, lodging = "", "standard", "no"
        with db():
            db().execute("""INSERT INTO rsvps VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guest_id) DO UPDATE SET attendance=excluded.attendance,
                companion_name=excluded.companion_name, diet=excluded.diet,
                lodging=excluded.lodging, notes=excluded.notes, updated_at=excluded.updated_at""",
                (g.guest["id"], attendance, companion, diet, lodging, notes, int(time.time())))
        flash("Dziękujemy! Twoja odpowiedź została zapisana. Możesz ją później zmienić.")
        return redirect(url_for("guest", _anchor="rsvp"), code=303)

    @app.post("/logout")
    def logout():
        if isinstance(session.get("sid"), str):
            with db():
                db().execute("DELETE FROM sessions WHERE token_hash=?", (digest(session["sid"]),))
        session.clear()
        return redirect(url_for("index"), code=303)

    @app.get("/healthz")
    def health():
        db().execute("SELECT 1 FROM guests LIMIT 1")
        revision_file = ROOT / "public/revision.txt"
        revision = revision_file.read_text().strip() if revision_file.exists() else "development"
        return {"status": "ok", "revision": revision,
                "index_sha256": hashlib.sha256((ROOT / "index.html").read_bytes()).hexdigest()}

    @app.get("/robots.txt")
    def robots():
        return "User-agent: *\nDisallow: /\n", 200, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        return render_template("templates/error.html", title="Odśwież stronę", message="Formularz wygasł lub pochodzi z innej strony. Odśwież stronę i spróbuj ponownie."), 400

    @app.errorhandler(sqlite3.OperationalError)
    def storage_error(_):
        app.logger.error("Guest storage unavailable")
        return render_template("templates/error.html", title="Spróbuj ponownie później", message="Nie udało się teraz zapisać danych. Twoja odpowiedź nie została potwierdzona."), 503

    for status in (400, 403, 404, 405, 413, 429, 500):
        def error_handler(error, status=status):
            if isinstance(error, SecurityError):
                return "Niepoprawny adres witryny.", 400
            response = app.make_response((render_template("templates/error.html", title="Chwila przerwy" if status == 429 else "Nie udało się otworzyć strony",
                message="Za dużo prób. Odczekaj 15 minut i spróbuj ponownie." if status == 429 else "Wróć do strony głównej. Jeśli problem się powtórzy, skontaktuj się z organizatorami."), status))
            if status == 429:
                response.headers["Retry-After"] = "900"
            return response
        app.register_error_handler(status, error_handler)

    return app
