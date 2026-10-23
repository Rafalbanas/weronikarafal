"""Public ceremony page and authenticated guest area."""
from datetime import timedelta
from functools import wraps
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlencode

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import SecurityError
from werkzeug.security import check_password_hash, generate_password_hash

from wedding.store import allow_request, connect, details, digest, initialize, normalize_code, invitation, revoke, authenticate_invitation
from wedding import translate
from wedding.store import issue_admin_recovery, recovery_code
from wedding.store import validate_household

ROOT = Path(__file__).resolve().parent
DIETS = {"standard": "Standardowa", "vegetarian": "Wegetariańska", "vegan": "Wegańska",
         "gluten_free": "Bezglutenowa", "other": "Inna / alergie"}


def create_app(config=None):
    assets = ROOT / "public/assets" if (ROOT / "public/assets").exists() else ROOT / "assets"
    app = Flask(__name__, template_folder=str(ROOT), static_folder=str(assets), static_url_path="/assets")
    asset_versions = {name: hashlib.sha256((assets / name).read_bytes()).hexdigest()[:16]
                      for name in ("site.css", "site.js", "favicon.svg")}

    @app.template_global()
    def asset_url(filename):
        return url_for("static", filename=filename, v=asset_versions[filename])

    data = Path(os.environ.get("WEDDING_DATA_DIR", "/var/lib/weronikarafal-data"))
    app.config.update(
        SECRET_KEY=os.environ.get("WEDDING_SECRET_KEY"),
        DATABASE=str(data / "guests.sqlite3"), DETAILS=str(data / "details.json"),
        SESSION_COOKIE_NAME="__Host-wedding", SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=16*1024, MAX_FORM_MEMORY_SIZE=16*1024, MAX_FORM_PARTS=64,
        TRUSTED_HOSTS=["weronikarafal.com", "www.weronikarafal.com", "127.0.0.1", "localhost"],
        LOGIN_LIMIT=12, TRUST_PROXY=os.environ.get("WEDDING_TRUST_PROXY") == "1",
        ADMIN_LOGIN_LIMIT=5,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set a persistent WEDDING_SECRET_KEY with at least 32 random characters.")
    if app.config["TRUST_PROXY"]:
        # Only enabled behind the loopback Nginx listener, which overwrites these headers.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    @app.url_value_preprocessor
    def choose_language(_endpoint, _values):
        selected = request.args.get("lang")
        saved = request.cookies.get("__Host-wedding-language")
        g.language = selected if selected in {"pl", "en"} else saved if saved in {"pl", "en"} else "pl"

    @app.context_processor
    def language_context():
        # Language links lead to GET pages and never replay a form submission.
        target = {"admin_add_guest": "admin", "admin_update_guest": "admin",
                  "admin_password": "admin", "admin_issue_recovery": "admin", "rsvp": "guest", "logout": "index"}.get(request.endpoint, request.endpoint)
        if target not in {"index", "guest", "login", "admin", "admin_login", "admin_recover"}:
            target = "index"
        return {"_": translate, "language": g.get("language", "pl"),
                "language_urls": {lang: url_for(target, lang=lang) for lang in ("pl", "en")}}

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
        g.admin = None
        admin_sid = session.get("admin_sid")
        if isinstance(admin_sid, str):
            g.admin = db().execute("""SELECT administrators.username FROM admin_sessions
                JOIN administrators USING(username) WHERE token_hash=? AND expires_at>?""",
                (digest(admin_sid), int(time.time()))).fetchone()
            if not g.admin:
                session.pop("admin_sid", None)
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
        response.headers["Content-Language"] = g.get("language", "pl")
        if request.method == "GET" and request.args.get("lang") in {"pl", "en"}:
            response.set_cookie("__Host-wedding-language", request.args["lang"],
                max_age=365*24*3600, secure=True, httponly=True, samesite="Lax", path="/")
        response.headers.update({
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache", "Vary": "Cookie",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; "
                "frame-src https://www.google.com; frame-ancestors 'none'; base-uri 'none'; object-src 'none'",
        })
        if request.endpoint not in {"index", "robots"} or response.status_code != 200:
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
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

    def require_admin(view):
        @wraps(view)
        def protected(*args, **kwargs):
            if not g.admin:
                return redirect(url_for("admin_login"), code=303)
            return view(*args, **kwargs)
        return protected

    # A real hash keeps failed password checks equally expensive for unknown users.
    dummy_password_hash = generate_password_hash(secrets.token_urlsafe(32))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if g.admin:
            return redirect(url_for("admin"), code=303)
        error = None
        if request.method == "POST":
            limited("admin-login", [("ip:{ip}", app.config["ADMIN_LOGIN_LIMIT"], 900), ("global", 100, 900)])
            username = request.form.get("username", "").strip()[:120]
            password = request.form.get("password", "")
            account = db().execute("SELECT * FROM administrators WHERE username=?", (username,)).fetchone()
            valid = check_password_hash(account["password_hash"] if account else dummy_password_hash, password[:256])
            if account and valid and len(password) <= 256:
                sid = secrets.token_urlsafe(32)
                now = int(time.time())
                with db():
                    if isinstance(session.get("sid"), str):
                        db().execute("DELETE FROM sessions WHERE token_hash=?", (digest(session["sid"]),))
                    db().execute("DELETE FROM admin_sessions WHERE expires_at<=?", (now,))
                    db().execute("INSERT INTO admin_sessions VALUES (?, ?, ?)", (digest(sid), username, now+8*3600))
                session.clear()
                session.permanent = True
                session["admin_sid"] = sid
                return redirect(url_for("admin"), code=303)
            error = "Niepoprawny login lub hasło."
        return render_template("templates/admin_login.html", error=error), 401 if error else 200

    @app.route("/admin/recover", methods=["GET", "POST"])
    def admin_recover():
        error = None
        if request.method == "POST":
            limited("admin-recover", [("ip:{ip}", 5, 900), ("global", 100, 900)])
            username = request.form.get("username", "").strip()[:120]
            code = normalize_code(request.form.get("recovery_code", ""))
            password = request.form.get("new_password", "")
            saved = db().execute("SELECT code_hash FROM admin_recovery WHERE username=?", (username,)).fetchone()
            valid = check_password_hash(saved["code_hash"] if saved else dummy_password_hash, code[:64])
            if saved and valid and len(code) == 32 and 16 <= len(password) <= 256 and password == request.form.get("confirm_password"):
                replacement = recovery_code()
                replacement_hash = generate_password_hash(normalize_code(replacement))
                password_hash = generate_password_hash(password)
                with db():
                    # Compare-and-swap consumes the code once, even for concurrent requests.
                    consumed = db().execute("UPDATE admin_recovery SET code_hash=? WHERE username=? AND code_hash=?",
                        (replacement_hash, username, saved["code_hash"])).rowcount
                    if consumed:
                        db().execute("UPDATE administrators SET password_hash=? WHERE username=?", (password_hash, username))
                        db().execute("DELETE FROM admin_sessions WHERE username=?", (username,))
                        ip = hmac.new(app.secret_key.encode(), request.remote_addr.encode(), hashlib.sha256).hexdigest()
                        db().execute("DELETE FROM throttle WHERE bucket=?", ("admin-login:ip:"+ip,))
                if consumed:
                    session.clear()
                    return render_template("templates/admin_login.html", issued_recovery=replacement, recovered=True)
            error = "Nie udało się zresetować hasła. Sprawdź login i kod odzyskiwania. Nowe hasło musi mieć 16–256 znaków i być wpisane identycznie w obu polach."
        return render_template("templates/admin_login.html", recovery_form=True, error=error), 401 if error else 200

    @app.post("/admin/recovery")
    @require_admin
    def admin_issue_recovery():
        limited("admin-recovery-issue", [("user:"+g.admin["username"], 5, 900)])
        account = db().execute("SELECT password_hash FROM administrators WHERE username=?", (g.admin["username"],)).fetchone()
        password = request.form.get("current_password", "")
        if len(password) > 256 or not check_password_hash(account["password_hash"], password):
            flash("Nie wygenerowano kodu odzyskiwania. Sprawdź obecne hasło.")
            return redirect(url_for("admin", _anchor="konto"), code=303)
        return render_template("templates/admin_login.html", issued_recovery=issue_admin_recovery(db(), g.admin["username"]), recovered=False)

    @app.get("/admin")
    @require_admin
    def admin():
        people = db().execute("""SELECT guests.*, rsvps.attendance,
            rsvps.companion_name, rsvps.diet, rsvps.lodging, rsvps.notes, rsvps.updated_at
            FROM guests
            LEFT JOIN rsvps ON guests.id=rsvps.guest_id ORDER BY guests.name COLLATE NOCASE""").fetchall()
        people = [dict(person, child_names=json.loads(person["children"])) for person in people]
        active = [person for person in people if person["active"]]
        totals = {"invitations": len(active), "yes": sum(p["attendance"] == "yes" for p in active),
                  "no": sum(p["attendance"] == "no" for p in active),
                  "pending": sum(p["attendance"] is None for p in active),
                  "lodging": sum(p["attendance"] == "yes" and p["lodging"] == "yes" for p in active)}
        totals["adults"] = sum(2 if p["partner_name"] or p["allows_companion"] else 1 for p in active)
        totals["children"] = sum(len(p["child_names"]) for p in active)
        return render_template("templates/admin.html", people=people, totals=totals,
                               diets={key: translate(label) for key, label in DIETS.items()})

    def household_form(existing=None):
        kind = request.form.get("kind", "plusone" if request.form.get("companion") == "yes" else
                                "couple" if existing and existing["partner_name"] else "single")
        if kind not in {"single", "couple", "plusone"}:
            raise ValueError("Invalid invitation kind")
        partner = request.form.get("partner_name", existing["partner_name"] if existing else "") if kind == "couple" else ""
        if kind == "couple" and not partner.strip():
            raise ValueError("Partner name required")
        previous_children = json.loads(existing["children"]) if existing else []
        count = int(request.form.get("children_count", str(len(previous_children))))
        if not 0 <= count <= 20:
            raise ValueError("Invalid child count")
        children = request.form.getlist("children") if "children_count" in request.form or "children" in request.form else previous_children
        if len(children) > count:
            raise ValueError("Child count mismatch")
        name, partner, children = validate_household(request.form.get("name", ""), partner,
                                                    children + [""] * (count - len(children)))
        return name, partner, kind == "plusone", children

    @app.post("/admin/guests")
    @require_admin
    def admin_add_guest():
        limited("admin-write", [("user:"+g.admin["username"], 60, 60)])
        try:
            name, partner, companion, children = household_form()
            guest_id, code = invitation(db(), name, companion, code=request.form.get("code", "").strip() or None,
                                       partner_name=partner, children=children)
        except (ValueError, sqlite3.IntegrityError):
            flash("Nie zapisano zaproszenia. Sprawdź dane osób i liczbę dzieci (0–20). Para wymaga danych obu osób; osoba towarzysząca nie wymaga danych. Własny kod musi mieć 48 znaków 0–9 / a–f i być unikalny.")
        else:
            return render_template("templates/admin_code.html", code=code, name=name + (" & " + partner if partner else ""))
        return redirect(url_for("admin"), code=303)

    @app.post("/admin/guests/<guest_id>")
    @require_admin
    def admin_update_guest(guest_id):
        person = db().execute("SELECT * FROM guests WHERE id=?", (guest_id,)).fetchone()
        if not person:
            abort(404)
        action = request.form.get("action")
        try:
            if action == "rotate":
                _, code = invitation(db(), person["name"], person["allows_companion"], guest_id)
                return render_template("templates/admin_code.html", code=code,
                                       name=person["name"] + (" & " + person["partner_name"] if person["partner_name"] else ""))
            elif action == "revoke":
                revoke(db(), guest_id)
                flash("Zaproszenie wyłączone. Odpowiedź została zachowana.")
            elif action == "edit":
                name, partner, companion, children = household_form(person)
                with db():
                    db().execute("UPDATE guests SET name=?, partner_name=?, allows_companion=?, children=? WHERE id=?",
                                 (name, partner, int(companion), json.dumps(children, ensure_ascii=False), guest_id))
                    if not companion:
                        db().execute("UPDATE rsvps SET companion_name='' WHERE guest_id=?", (guest_id,))
                flash("Dane zaproszenia zapisane.")
            else:
                abort(400)
        except ValueError:
            flash("Sprawdź dane osób (do 120 znaków) i liczbę dzieci (0–20). Dla pary wpisz dane obu osób.")
        return redirect(url_for("admin", _anchor="guest-"+guest_id), code=303)

    @app.post("/admin/password")
    @require_admin
    def admin_password():
        limited("admin-password", [("user:"+g.admin["username"], 5, 900)])
        account = db().execute("SELECT * FROM administrators WHERE username=?", (g.admin["username"],)).fetchone()
        current = request.form.get("current_password", "")
        password = request.form.get("new_password", "")
        if (len(current) > 256 or not check_password_hash(account["password_hash"], current)
                or not 16 <= len(password) <= 256 or password != request.form.get("confirm_password")):
            flash("Nie zmieniono hasła. Sprawdź obecne hasło i podaj dwa razy nowe hasło o długości 16–256 znaków.")
            return redirect(url_for("admin", _anchor="konto"), code=303)
        with db():
            db().execute("UPDATE administrators SET password_hash=? WHERE username=?",
                         (generate_password_hash(password), g.admin["username"]))
            db().execute("DELETE FROM admin_sessions WHERE username=?", (g.admin["username"],))
        session.clear()
        flash("Hasło zmienione. Zaloguj się ponownie; pozostałe sesje tego konta zostały wylogowane.")
        return redirect(url_for("admin_login"), code=303)

    @app.get("/")
    def index():
        ceremony = details(app.config["DETAILS"])["ceremony"]
        map_query = ", ".join(value for value in (ceremony["name"], ceremony["address"]) if value)
        return render_template("index.html", ceremony=ceremony,
            map_url="https://www.google.com/maps/search/?"+urlencode({"api": 1, "query": map_query}),
            map_embed_url="https://www.google.com/maps?"+urlencode({"q": map_query, "output": "embed", "z": 16}))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.guest:
            return redirect(url_for("guest"), code=303)
        error = None
        if request.method == "POST":
            limits = limited("login", [("ip:{ip}", app.config["LOGIN_LIMIT"], 900), ("global", 1200, 3600)])
            code = normalize_code(request.form.get("code", ""))
            person = authenticate_invitation(db(), code)
            if person:
                sid = secrets.token_urlsafe(32)
                now = int(time.time())
                with db():
                    # Successful guests sharing a Wi-Fi network do not consume
                    # each other's failed-login budget. The global cap remains.
                    db().execute("UPDATE throttle SET attempts=max(0, attempts-1) WHERE bucket=?", (limits[0][0],))
                    db().execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
                    if isinstance(session.get("admin_sid"), str):
                        db().execute("DELETE FROM admin_sessions WHERE token_hash=?", (digest(session["admin_sid"]),))
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
        guests = db().execute("""SELECT CASE WHEN guests.partner_name<>'' THEN guests.name || ' & ' || guests.partner_name
            ELSE guests.name END AS name, rsvps.attendance FROM guests
            LEFT JOIN rsvps ON guests.id=rsvps.guest_id WHERE guests.active=1
            ORDER BY guests.name COLLATE NOCASE""").fetchall()
        return render_template("templates/guest.html", rsvp=rsvp, guests=guests,
            invited_children=json.loads(g.guest["children"]),
            diets={key: translate(label) for key, label in DIETS.items()}, private=details(app.config["DETAILS"]))

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
        if isinstance(session.get("admin_sid"), str):
            with db():
                db().execute("DELETE FROM admin_sessions WHERE token_hash=?", (digest(session["admin_sid"]),))
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
        return ("User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /guest\n"
                "Disallow: /login\nDisallow: /rsvp\nDisallow: /logout\nDisallow: /healthz\n",
                200, {"Content-Type": "text/plain; charset=utf-8"})

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
                return translate("Niepoprawny adres witryny."), 400
            response = app.make_response((render_template("templates/error.html", title="Chwila przerwy" if status == 429 else "Nie udało się otworzyć strony",
                message="Za dużo prób. Odczekaj 15 minut i spróbuj ponownie." if status == 429 else "Wróć do strony głównej. Jeśli problem się powtórzy, skontaktuj się z organizatorami."), status))
            if status == 429:
                response.headers["Retry-After"] = "900"
            return response
        app.register_error_handler(status, error_handler)

    return app
