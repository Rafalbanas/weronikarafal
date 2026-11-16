"""Optional browser UX checks with synthetic accounts and no production server.

Requires Flask, OpenSSL and Playwright in the local test environment. A temporary
HTTPS server binds only to loopback, exercising real secure browser cookies,
CSRF-protected RSVP submission and logout. External requests are blocked.
"""
import argparse
from contextlib import ExitStack
from pathlib import Path
import re
import subprocess
import struct
import sys
import tempfile
from threading import Thread
from urllib.parse import urlsplit
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from playwright.sync_api import expect, sync_playwright
from wedding.store import connect, invitation
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server, WSGIRequestHandler


class QuietHandler(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


def synthetic_png():
    """A valid one-pixel RGB image; no private or third-party media involved."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xbc\xa9\x70"))
            + chunk(b"IEND", b""))


def check_placeholder_contrast(page, selector):
    """Cover native placeholder colours that axe can mark as incomplete."""
    style = page.locator(selector).evaluate("""e => {
        const placeholder = getComputedStyle(e, '::placeholder');
        return {color: placeholder.color, opacity: placeholder.opacity,
                background: getComputedStyle(e).backgroundColor};
    }""")
    foreground = [float(v) for v in re.findall(r"[\d.]+", style["color"])]
    background = [float(v) for v in re.findall(r"[\d.]+", style["background"])]
    alpha = (foreground[3] if len(foreground) == 4 else 1) * float(style["opacity"])
    effective = [f * alpha + b * (1 - alpha) for f, b in zip(foreground[:3], background[:3])]

    def luminance(values):
        channels = [v / 255 for v in values]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))

    dark, light = sorted((luminance(effective), luminance(background[:3])))
    ratio = (light + .05) / (dark + .05)
    assert ratio >= 4.5, (selector, style, "placeholder contrast", ratio)


def sign_out(page, base):
    """Wait for the actual POST, not just click dispatch (notably in WebKit)."""
    with page.expect_response(
        lambda response: response.url == base + "/logout" and response.request.method == "POST"
    ) as completed:
        page.locator('form[action="/logout"] button').click()
    assert completed.value.status == 303, ("logout status", completed.value.status)
    expect(page).to_have_url(base + "/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/opencode/wedding-guest-ux"))
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup, sync_playwright() as playwright:
        app = create_app({
            "TESTING": True, "SECRET_KEY": "synthetic-browser-" + "x" * 40,
            "DATABASE": directory + "/db", "DETAILS": directory + "/details.json",
            "UPLOADS_DIR": directory + "/uploads",
            "TRUSTED_HOSTS": ["localhost"], "TRUST_PROXY": False,
        })
        with connect(app.config["DATABASE"]) as db:
            guest_id, code = invitation(db, "Testowe zaproszenie", companion=True)
            db.execute("INSERT INTO administrators VALUES (?, ?)",
                       ("test-organiser", generate_password_hash("synthetic-password-only")))
        certificate, key = directory + "/localhost.crt", directory + "/localhost.key"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", key, "-out", certificate, "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost",
        ], check=True, capture_output=True, timeout=60)
        server = make_server("127.0.0.1", 0, app, ssl_context=(certificate, key),
                             request_handler=QuietHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cleanup.callback(server.server_close)
        cleanup.callback(thread.join, timeout=10)
        cleanup.callback(server.shutdown)
        base = f"https://localhost:{server.server_port}"
        browser = getattr(playwright, args.browser).launch(
            args=["--no-sandbox"] if args.browser == "chromium" else [])
        context = browser.new_context(ignore_https_errors=True,
                                      viewport={"width": 390, "height": 900})
        errors = []

        def respond(route):
            # No requests to production, remote fonts, analytics or map services.
            if route.request.url.startswith(base + "/"):
                route.continue_()
            else:
                route.abort()

        context.route("**/*", respond)
        page = context.new_page()
        page.set_default_navigation_timeout(120000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/?lang=pl")
        page.locator(".hero-actions .button").first.click()
        expect(page).to_have_url(base + "/login")
        check_placeholder_contrast(page, "#code")
        page.locator("#code").fill(code)
        toggle = page.locator('[data-password-toggle="code"]')
        expect(toggle).to_be_visible()
        toggle.click()
        expect(page.locator("#code")).to_have_attribute("type", "text")
        toggle.click()
        expect(page.locator("#code")).to_have_attribute("type", "password")
        page.locator('.form-stack button[type="submit"]').click()
        expect(page).to_have_url(base + "/guest")
        page.locator("#notes").fill("Syntetyczna odpowiedź testowa")
        page.locator("#rsvpForm button[type=submit]").click()
        expect(page.locator(".notice-success")).to_be_visible()
        expect(page.locator("#notes")).to_have_value("Syntetyczna odpowiedź testowa")
        with connect(app.config["DATABASE"]) as db:
            saved = db.execute("SELECT notes FROM rsvps WHERE guest_id=?", (guest_id,)).fetchone()
            assert saved["notes"] == "Syntetyczna odpowiedź testowa"

        # Real HTTPS/XHR upload, image decoding, keyboard lightbox and deletion.
        image = synthetic_png()
        page.goto(base + "/media")
        page.locator("#media-files").set_input_files(
            {"name": "browser-test.png", "mimeType": "image/png", "buffer": image})
        expect(page.locator(".media-pending-item")).to_have_count(1)
        page.locator("[data-media-submit]").click()
        expect(page.locator(".media-item")).to_have_count(1)
        thumbnail = page.locator(".media-item img")
        thumbnail.scroll_into_view_if_needed()
        expect(thumbnail).to_have_js_property("naturalWidth", 1)
        page.locator(".media-zoom").click()
        expect(page.locator("[data-media-lightbox]")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("[data-media-lightbox]")).to_be_hidden()
        expect(page.locator(".media-zoom")).to_be_focused()
        page.locator("[data-media-delete] button").click()
        expect(page.locator("[data-media-confirm]")).to_be_visible()
        page.locator('[data-media-confirm] button[value="cancel"]').click()
        expect(page.locator(".media-item")).to_have_count(1)
        page.locator("[data-media-delete] button").click()
        page.locator('[data-media-confirm] button[value="confirm"]').click()
        expect(page.locator(".media-item")).to_have_count(0)

        combinations = 0
        for role, paths in (
            ("guest", ("/", "/guest", "/media", "/schedule", "/tables")),
            ("admin", ("/admin", "/admin/login", "/admin/recover")),
        ):
            if role == "admin":
                sign_out(page, base)
                page.goto(base + "/guest")
                expect(page).to_have_url(base + "/login")
                page.goto(base + "/admin/login")
                page.locator("#username").fill("test-organiser")
                page.locator("#password").fill("synthetic-password-only")
                page.locator('.form-stack button[type="submit"]').click()
                expect(page).to_have_url(base + "/admin")
                page.goto(base + "/")
                expect(page.locator(".hero-actions .button").first).to_have_attribute("href", "/admin")
            for width in (320, 768, 1440):
                page.set_viewport_size({"width": width, "height": 900})
                for lang in ("pl", "en"):
                    for theme in ("dark", "light"):
                        page.evaluate("localStorage.setItem('wedding-theme', '" + theme + "')")
                        for path in paths:
                            response = page.goto(base + path + "?lang=" + lang)
                            assert response.status == 200, (role, path, response.status)
                            expected_path = "/admin" if role == "admin" and path == "/admin/login" else path
                            assert urlsplit(page.url).path == expected_path, (role, path, page.url)
                            expect(page.locator("html")).to_have_attribute("data-theme", theme)
                            expect(page.locator("html")).to_have_attribute("lang", lang)
                            assert not page.evaluate(
                                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                            ), (role, width, lang, theme, path, "horizontal overflow")
                            expect(page.locator("main h1")).to_be_visible()
                            if path == "/guest":
                                check_placeholder_contrast(page, "#notes")
                            if width == 320 and lang == "pl" and theme == "dark":
                                page.screenshot(path=str(args.output / (path.strip("/") or "home")) + ".png",
                                                full_page=True, animations="disabled")
                            combinations += 1
        page.goto(base + "/admin")
        sign_out(page, base)
        page.goto(base + "/guest")
        expect(page).to_have_url(base + "/login")
        page.goto(base + "/admin")
        expect(page).to_have_url(base + "/admin/login")
        assert not errors, errors
        context.close()

        # The same login and RSVP journey must remain usable without JavaScript.
        context = browser.new_context(ignore_https_errors=True, java_script_enabled=False,
                                      viewport={"width": 320, "height": 900})
        context.route("**/*", respond)
        page = context.new_page()
        page.set_default_navigation_timeout(120000)
        page.goto(base + "/login?lang=en")
        expect(page.locator('[data-password-toggle="code"]')).to_be_hidden()
        page.locator("#code").fill(code)
        page.locator('.form-stack button[type="submit"]').click()
        page.locator("#notes").fill("No JavaScript")
        page.locator("#rsvpForm button[type=submit]").click()
        expect(page.locator(".notice-success")).to_be_visible()
        expect(page.locator("#notes")).to_have_value("No JavaScript")
        page.goto(base + "/media?lang=en")
        page.keyboard.press("Tab")
        page.locator("#media-files").focus()
        assert page.locator("[data-dropzone]").evaluate(
            "e => getComputedStyle(e).outlineStyle != 'none' && parseFloat(getComputedStyle(e).outlineWidth) >= 2"
        ), "No-JavaScript file input needs a visible focus indicator on its label"
        page.locator("#media-files").set_input_files(
            {"name": "no-js.png", "mimeType": "image/png", "buffer": image})
        page.locator("[data-media-submit]").click()
        expect(page.locator(".media-item")).to_have_count(1)
        with page.expect_download() as download:
            page.locator(".media-meta a").click()
        target = Path(directory) / "download.png"
        download.value.save_as(target)
        assert target.read_bytes() == image
        context.close()
        browser.close()
    print(f"{args.browser}: {combinations} private/public layouts OK; login, code visibility, RSVP, "
          "upload/lightbox/delete, logout and no-JS file focus/upload/download OK.")


if __name__ == "__main__":
    main()
