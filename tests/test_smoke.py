#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP smoke tests for the İlim Halkası API.

The suite is completely self-contained: it copies the application sources and
a *copy* of the database into a temporary directory, starts the copied server
on a free local port and talks to it over HTTP.  The live ``ilimhalkasi.db``
and the live server on port 8765 are never touched.

Run from the project root::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Only these files are copied; nothing in the project directory is modified.
SOURCE_FILES = (
    "server.py",
    "scholars_data.py",
    "index.html",
    "app.js",
    "i18n.js",
    "styles.css",
    "vendor/lucide-1.80.0.min.js",
    "favicon.svg",
    "logo.svg",
    "fonts/amiri-400-arabic.woff2",
    "fonts/amiri-400-latin-ext.woff2",
    "fonts/amiri-400-latin.woff2",
    "fonts/amiri-700-arabic.woff2",
    "fonts/amiri-700-latin-ext.woff2",
    "fonts/amiri-700-latin.woff2",
    "fonts/el-messiri-arabic.woff2",
    "fonts/el-messiri-latin-ext.woff2",
    "fonts/el-messiri-latin.woff2",
    "fonts/lora-latin-ext.woff2",
    "fonts/lora-latin.woff2",
    "fonts/plus-jakarta-sans-latin-ext.woff2",
    "fonts/plus-jakarta-sans-latin.woff2",
)
DB_FILENAME = "ilimhalkasi.db"

ADMIN_EMAIL = "admin@ilimhalkasi.local"
ADMIN_PASSWORD = "k9Mq-c5gipJRP41-"  # documented in README.md
REQUEST_TIMEOUT = 15  # 8.000+ kayıtlı katalogda yükleme anında 5s yetmiyordu
STARTUP_TIMEOUT = 20


def _free_port() -> int:
    """Ask the OS for an unused localhost port (avoids clashing with 8765)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _new_opener() -> tuple[urllib.request.OpenerDirector, http.cookiejar.CookieJar]:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def _request(
    opener: urllib.request.OpenerDirector,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[int, dict]:
    """Return (http_status, parsed_json). HTTP error bodies are parsed too."""
    data = None
    headers: dict[str, str] = {}
    jar = next(
        (
            handler.cookiejar
            for handler in getattr(opener, "handlers", [])
            if isinstance(handler, urllib.request.HTTPCookieProcessor)
        ),
        None,
    )
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if method != "GET" and jar is not None:
        token = getattr(jar, "ih_csrf_token", "")
        if token:
            headers["X-CSRF-Token"] = token
    request = urllib.request.Request(
        "http://127.0.0.1:{}{}".format(_CURRENT_PORT, path),
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        try:
            raw = exc.read()
        finally:
            exc.close()
    if not raw:
        return status, {}
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        body = {}
    if isinstance(body, dict) and body.get("csrfToken") and jar is not None:
        setattr(jar, "ih_csrf_token", body["csrfToken"])
    return status, body if isinstance(body, dict) else {}


# Set by the test class before any request is made.  Keeping the base URL in a
# module-level variable keeps the request helper small and avoids passing the
# port through every single call.
_CURRENT_PORT = 0


def _marker(prefix: str) -> str:
    return "smoke-{}-{}".format(prefix, uuid.uuid4().hex[:10])


def _launch_server(
    tmp_dir: Path, port: int, env_overrides: dict | None = None
) -> tuple[subprocess.Popen, object]:
    """Copy the server into tmp_dir, rewrite its port and start it locally."""
    server_path = tmp_dir / "server.py"
    text = server_path.read_text(encoding="utf-8")
    patched, count = re.subn(
        r"(?m)^PORT(?:\s*:\s*int)?\s*=\s*\d+\s*$",
        "PORT = {}".format(port),
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not rewrite PORT in the copied server.py")
    server_path.write_text(patched, encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["IH_ADMIN_PASSWORD"] = ADMIN_PASSWORD
    # Deterministic behaviour: no real SMTP, no rate-limit interference.
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_USE_TLS"):
        env.pop(name, None)
    env["ILIMHALKASI_RATE_LIMIT"] = "0"
    env["ILIMHALKASI_CSRF"] = "1"
    # The test server must never inherit the live DB directory or production mode.
    env.pop("ILIMHALKASI_DB_DIR", None)
    env.pop("ILIMHALKASI_PRODUCTION", None)
    env.update(env_overrides or {})
    log_handle = (tmp_dir / "server.log").open("wb")
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=str(tmp_dir),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return proc, log_handle


def _copy_sources(tmp_dir: Path) -> None:
    for filename in SOURCE_FILES:
        source = PROJECT_ROOT / filename
        if not source.is_file():
            raise RuntimeError("Missing source file required by smoke tests: " + filename)
        target = tmp_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    configured_dir = os.environ.get("ILIMHALKASI_DB_DIR", "").strip()
    if not configured_dir:
        local_env = PROJECT_ROOT / "local.env"
        if local_env.is_file():
            for line in local_env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ILIMHALKASI_DB_DIR="):
                    configured_dir = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    db_source = Path(configured_dir).expanduser() / DB_FILENAME if configured_dir else PROJECT_ROOT / DB_FILENAME
    if not db_source.is_file():
        raise RuntimeError("Database not found for smoke tests: " + str(db_source))
    shutil.copy2(db_source, tmp_dir / DB_FILENAME)


class SmokeAPITests(unittest.TestCase):
    """End-to-end checks against an isolated, temporary server instance."""

    @classmethod
    def setUpClass(cls) -> None:
        global _CURRENT_PORT

        cls._tmp = tempfile.TemporaryDirectory(prefix="ilimhalkasi-smoke-")
        cls.tmp_dir = Path(cls._tmp.name)
        try:
            _copy_sources(cls.tmp_dir)
            cls.port = _free_port()
            _CURRENT_PORT = cls.port
            cls.base_url = "http://127.0.0.1:{}".format(cls.port)
            # DB_PATH is `BASE / "ilimhalkasi.db"` and BASE is the copied file's
            # directory, so the server now necessarily uses the copied DB.
            cls.proc, cls.log_handle = _launch_server(cls.tmp_dir, cls.port)
            cls._wait_until_ready()

            cls.admin_opener, cls.admin_jar = _new_opener()
            status, body = _request(
                cls.admin_opener,
                "POST",
                "/api/login",
                {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            )
            if status != 200 or not body.get("user"):
                raise RuntimeError("Admin login failed during test setup: {} {}".format(status, body))

            cls.anon_opener, _ = _new_opener()
            cls._book_id = None
        except Exception:
            cls._stop_resources()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stop_resources()

    @classmethod
    def _stop_resources(cls) -> None:
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        handle = getattr(cls, "log_handle", None)
        if handle is not None and not handle.closed:
            handle.close()
        tmp = getattr(cls, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    @classmethod
    def _log_tail(cls) -> str:
        path = cls.tmp_dir / "server.log"
        try:
            return path.read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            return ""

    @classmethod
    def _wait_until_ready(cls) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        last_error = None
        while time.monotonic() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError(
                    "Test server exited during startup.\n" + cls._log_tail()
                )
            try:
                with urllib.request.urlopen(cls.base_url + "/api/me", timeout=1) as response:
                    response.read()
                return
            except urllib.error.HTTPError:
                # Any HTTP response means the server is listening.
                return
            except urllib.error.URLError as exc:
                last_error = exc
                time.sleep(0.1)
        raise RuntimeError(
            "Test server did not start within {}s: {}\n{}".format(
                STARTUP_TIMEOUT, last_error, cls._log_tail()
            )
        )

    # ---- small helpers -------------------------------------------------

    def get(self, path: str, opener=None) -> tuple[int, dict]:
        return _request(opener or self.admin_opener, "GET", path)

    def post(self, path: str, payload: dict | None = None, opener=None) -> tuple[int, dict]:
        return _request(opener or self.admin_opener, "POST", path, payload if payload is not None else {})

    def bootstrap(self, opener=None) -> dict:
        status, body = self.get("/api/bootstrap", opener=opener)
        self.assertEqual(status, 200, "bootstrap failed: {}".format(body))
        return body

    def book_id(self) -> int:
        if self.__class__._book_id is None:
            status, body = self.get("/api/books?limit=1")
            self.assertEqual(status, 200, "book catalogue failed: {}".format(body))
            books = body.get("books") or []
            self.assertTrue(books, "test catalogue contains no books")
            self.__class__._book_id = int(books[0]["id"])
        return self.__class__._book_id

    def register_user(self) -> tuple[urllib.request.OpenerDirector, dict]:
        suffix = uuid.uuid4().hex[:10]
        opener, _ = _new_opener()
        status, body = self.post(
            "/api/register",
            {
                "email": "smoke.{}@example.test".format(suffix),
                "username": "smk{}".format(suffix)[:20],
                "display_name": "Smoke {}".format(suffix[:5]),
                "password": "SmokeTest-{}".format(suffix),
            },
            opener=opener,
        )
        self.assertEqual(status, 200, "registration failed: {}".format(body))
        self.assertTrue(body.get("user"))
        return opener, body["user"]

    # ---- tests ---------------------------------------------------------

    def test_public_health_and_bootstrap_keys(self) -> None:
        """Public endpoints respond, and an authenticated bootstrap has the core keys."""
        status, _ = self.get("/", opener=self.anon_opener)
        self.assertEqual(status, 200, "static index should be publicly served")

        status, body = self.get("/api/me", opener=self.anon_opener)
        self.assertEqual(status, 200)
        self.assertIn("user", body)

        data = self.bootstrap()
        for key in ("user", "books", "posts", "shelf", "lists", "stats"):
            self.assertIn(key, data, "bootstrap is missing key: " + key)
        self.assertEqual(data["user"].get("email"), ADMIN_EMAIL)

    def test_admin_login_succeeds(self) -> None:
        opener, jar = _new_opener()
        status, body = self.post(
            "/api/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, opener=opener
        )
        self.assertEqual(status, 200, "admin login failed: {}".format(body))
        self.assertTrue(body.get("user"))
        self.assertTrue(body["user"].get("is_admin"))
        self.assertEqual(body["user"].get("email"), ADMIN_EMAIL)
        self.assertTrue(len(jar) > 0, "login should set a session cookie")

    def test_unauthenticated_bootstrap_has_no_user(self) -> None:
        status, body = self.get("/api/bootstrap", opener=self.anon_opener)
        self.assertEqual(status, 200, "guest bootstrap failed: {}".format(body))
        self.assertIsNone(body.get("user"))
        for key in ("books", "posts", "groups", "shelf", "lists", "stats"):
            self.assertIn(key, body, "guest bootstrap is missing public key: " + key)
        self.assertNotIn("admin", body)
        for key in ("tickets", "reports", "follows", "blocked"):
            self.assertEqual(body.get(key), [], "guest bootstrap leaked private " + key)
        self.assertEqual(
            body["stats"],
            {"followers": 0, "following": 0, "circles": 0, "ilimSeries": 0},
        )

    def test_guest_member_actions_are_still_server_gated(self) -> None:
        status, body = self.post("/api/posts", {"text": "guest post"}, opener=self.anon_opener)
        self.assertEqual(status, 401, "anonymous post should be rejected: {}".format(body))
        self.assertEqual(body.get("error"), "Giriş yapmalısın")

        status, _ = self.get("/api/notifications", opener=self.anon_opener)
        self.assertEqual(status, 401, "anonymous notifications should be rejected")

        for path in ("/api/books", "/api/books/filters", "/api/catalog-authors"):
            status, _ = self.get(path, opener=self.anon_opener)
            self.assertEqual(status, 200, "public catalog endpoint failed: " + path)

    def test_book_detail_endpoint_returns_real_metadata(self) -> None:
        books = self.bootstrap().get("books") or []
        sample = next((b for b in books if b.get("title")), None)
        self.assertIsNotNone(sample, "bootstrap contains no book")
        status, body = self.get("/api/books/{}".format(sample["id"]), opener=self.anon_opener)
        self.assertEqual(status, 200, "public book detail failed: {}".format(body))
        detail = body.get("book") or {}
        self.assertEqual(detail.get("title"), sample.get("title"))
        self.assertEqual(detail.get("author"), sample.get("author"))
        self.assertNotRegex(
            str(detail.get("cover", "")), r"^https?://", "covers must be served from our own origin"
        )

    def test_unknown_book_detail_returns_404(self) -> None:
        status, body = self.get("/api/books/99999999", opener=self.anon_opener)
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_cover_proxy_returns_an_image(self) -> None:
        request = urllib.request.Request(self.base_url + "/cover/3996717-M.jpg")
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            self.assertEqual(response.status, 200)
        self.assertTrue(content_type.startswith("image/"), content_type)
        self.assertTrue(body.startswith(b"\xff\xd8"), "expected JPEG bytes from cover proxy")

    def test_shelf_accepts_valid_book(self) -> None:
        book_id = self.book_id()
        status, body = self.post("/api/shelf", {"book_id": book_id, "status": "reading", "page": 1})
        self.assertEqual(status, 200, "valid shelf update failed: {}".format(body))
        self.assertTrue(body.get("ok"))

        shelf = self.bootstrap().get("shelf") or []
        self.assertTrue(any(int(entry.get("book_id", 0)) == book_id for entry in shelf))

    def test_shelf_rejects_invalid_page(self) -> None:
        status, body = self.post(
            "/api/shelf", {"book_id": self.book_id(), "status": "reading", "page": "abc"}
        )
        self.assertEqual(status, 400, "non-numeric page should be a 400: {}".format(body))
        self.assertIn("error", body)

    def test_lists_create_dedupe_and_add_book(self) -> None:
        name = _marker("list")
        book_id = self.book_id()

        status, body = self.post("/api/lists", {"name": name})
        self.assertEqual(status, 200, "list creation failed: {}".format(body))
        created = body.get("list") or {}
        self.assertEqual(created.get("name"), name)
        self.assertTrue(created.get("id"))

        status, duplicate = self.post("/api/lists", {"name": name})
        self.assertEqual(status, 200, "duplicate list request failed: {}".format(duplicate))
        self.assertEqual(
            (duplicate.get("list") or {}).get("id"),
            created.get("id"),
            "duplicate list name must return the existing list",
        )

        status, added = self.post("/api/lists/add", {"list_id": created["id"], "book_id": book_id})
        self.assertEqual(status, 200, "adding a book to a list failed: {}".format(added))
        self.assertTrue(added.get("ok"))
        self.assertEqual(added.get("list_id"), created["id"])

        lists = [item for item in (self.bootstrap().get("lists") or []) if item.get("name") == name]
        self.assertEqual(len(lists), 1, "duplicate name created a second list")
        self.assertTrue(
            any(int(book.get("id", 0)) == book_id for book in lists[0].get("books") or []),
            "added book is missing from the list in bootstrap",
        )

    def test_favorites_list_seeded_once(self) -> None:
        opener, user = self.register_user()
        names = [item.get("name") for item in self.bootstrap(opener=opener).get("lists") or []]
        self.assertIn("Kaydettiklerim", names, "new users should receive a favorites list")

        conn = sqlite3.connect(self.tmp_dir / DB_FILENAME)
        try:
            marker = conn.execute(
                "SELECT value FROM user_meta WHERE user_id=? AND key='favorites_seeded'",
                (int(user["id"]),),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(marker[0] if marker else None, "1", "favorites seed marker is missing")

        favorites = next(
            item for item in self.bootstrap(opener=opener).get("lists") or []
            if item.get("name") == "Kaydettiklerim"
        )
        status, body = self.post(
            "/api/lists/delete", {"list_id": favorites["id"]}, opener=opener
        )
        self.assertEqual(status, 200, "deleting favorites failed: {}".format(body))

        names = [item.get("name") for item in self.bootstrap(opener=opener).get("lists") or []]
        self.assertNotIn("Kaydettiklerim", names, "deleted favorites list must not come back")

    def test_list_rename_and_delete_are_owner_only(self) -> None:
        name = _marker("rename-list")
        renamed = _marker("renamed-list")
        status, body = self.post("/api/lists", {"name": name})
        self.assertEqual(status, 200, "list creation failed: {}".format(body))
        list_id = (body.get("list") or {}).get("id")
        self.assertTrue(list_id)

        status, updated = self.post(
            "/api/lists/update", {"list_id": list_id, "name": renamed}
        )
        self.assertEqual(status, 200, "list rename failed: {}".format(updated))
        self.assertTrue(updated.get("ok"))
        names = [item.get("name") for item in self.bootstrap().get("lists") or []]
        self.assertIn(renamed, names)
        self.assertNotIn(name, names)

        other_opener, _ = self.register_user()
        status, body = self.post(
            "/api/lists/update", {"list_id": list_id, "name": _marker("hijack")},
            opener=other_opener,
        )
        self.assertEqual(status, 404, "other users must not rename this list")
        status, body = self.post(
            "/api/lists/delete", {"list_id": list_id}, opener=other_opener
        )
        self.assertEqual(status, 404, "other users must not delete this list")

        status, body = self.post("/api/lists/delete", {"list_id": list_id})
        self.assertEqual(status, 200, "owner delete failed: {}".format(body))
        names = [item.get("name") for item in self.bootstrap().get("lists") or []]
        self.assertNotIn(renamed, names)

    def test_notification_preferences_and_theme_defaults_are_wired(self) -> None:
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        for key in (
            "notifyAnnouncements", "notifyCirclePosts", "notifyComments",
            "notifyMentions", "notifyMessages", "notifyFollowers", "notifySupport",
        ):
            self.assertIn(key, app_js, "missing notification preference: " + key)
            self.assertIn(key, index_html, "missing settings toggle: " + key)
        self.assertIn("theme: 'auto'", app_js, "system theme should be the default")
        self.assertIn("prefers-color-scheme: dark", app_js)
        self.assertIn('data-theme-choice="auto"', index_html)
        self.assertIn("phoneNotificationAllowed", app_js)
        self.assertIn("syncPhoneNotificationPrefs", app_js)
        self.assertNotIn(".filter((n) => notificationAllowed(n.kind))", app_js,
                         "preferences must not hide in-app notifications")

    def test_removed_copy_and_clean_labels(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        removed = (
            "İLK ADIMLAR",
            "paylaşım akışı",
            "Birlikte okuyacağınız, müzakere edeceğiniz ve öğrendiklerinizi kaydedeceğiniz alanlar.",
            "Platform genelindeki en yeni içerikleri, popüler kitapları ve listeleri gösteren ana sayfa.",
            "İncelemelerin ve alıntıların; hepsi bir yerde.",
            "Henüz defterinize bir alıntı düşmemişsiniz.",
            "Okuduklarından bir satır veya bir kitap hakkındaki düşünceni paylaş.",
            "KÜTÜPHANEM · PAYLAŞIM",
            "Hangi bildirimlerin bildirim merkezinde ve telefonda görüneceğini seç.",
            "Telefona bildirim düşmesi için cihazda uygulama bildirimlerini de açık tut.",
            "Bildirim tercihleri",
            "Bildirim merkezi",
            "Yıllık kitap hedefini, yazı boyutunu ve kitap kartlarını ayarla.",
            "Hedef ve istatistikler her yıl başında sıfırlanır.",
            "Profilinde hangi bilgilerin görünmesini istediğini seç.",
            "Neden buradayız?",
            "BİZ KİMİZ?",
            "Ortak okuma ilerlemesi ve sohbete tek tıkla geçiş.",
            "sesli oturum yok",
            "⌘ K",
            "Bir vücut bilinci",
            "⚑ Nefret, kin, hakaret veya ayrıştırıcı söz yazanların içerikleri kaldırılır",
            "Henüz bir duyuru yok.",
            "Profilime git",
            "Değişiklikleri Kaydet",
            "Değişiklikleri kaydet",
            "Tercihleri kaydet",
            "Giriş Yap",
        )
        for text in removed:
            self.assertNotIn(text, index_html, "removed copy still present: " + text)
            self.assertNotIn(text, app_js, "removed copy still present: " + text)
        self.assertIn("id=\"circle-feed-back\"", index_html)
        self.assertIn('data-i18n="Seçkiler"', index_html)
        self.assertIn("Henüz alıntı paylaşmadın.", app_js)

    def test_back_navigation_filters_and_native_notifications_are_wired(self) -> None:
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        manifest = (PROJECT_ROOT / "android" / "app" / "src" / "main"
                    / "AndroidManifest.xml").read_text(encoding="utf-8")
        activity = (PROJECT_ROOT / "android" / "app" / "src" / "main" / "java"
                    / "com" / "ilimhalkasi" / "app" / "MainActivity.java").read_text(encoding="utf-8")

        self.assertIn("viewHistory", app_js)
        self.assertIn("function goBackView()", app_js)
        self.assertIn("$('#circle-feed-back')?.addEventListener('click'", app_js)
        self.assertIn("id=\"filter-toggle\"", index_html)
        self.assertIn("$('#filter-toggle')?.addEventListener('click'", app_js)
        self.assertIn(".book-filters.is-open { display: grid; }", css)

        self.assertIn("pushNativeNotifications", app_js)
        self.assertIn("bridge.showNotification", app_js)
        self.assertIn("setNotificationPreferences", activity)
        self.assertIn("showNotification", activity)
        self.assertIn("createNotificationChannel", activity)
        self.assertIn("android.permission.POST_NOTIFICATIONS", manifest)

    def test_profile_order_and_mobile_shell_polish_are_wired(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        i18n_js = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")

        profile = index_html.split('<section class="view" id="view-profile"', 1)[1]
        profile = profile.split("</section>", 1)[0]
        self.assertLess(
            profile.index('data-i18n="Halkalarım"'),
            profile.index('data-i18n="İlim Yolculuğum"'),
            "Halkalarım should stay above İlim Yolculuğum",
        )
        self.assertLess(
            profile.index('data-i18n="İlim Yolculuğum"'),
            profile.index(">Etkileşimlerim<"),
            "Etkileşimlerim should be the last profile section",
        )

        self.assertIn("grid-template-columns: minmax(44px, 1fr) auto minmax(44px, 1fr)", css)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", css)
        self.assertIn("justify-self: center;", css)
        self.assertIn("transform: translateY(-10px)", css)
        self.assertIn("bottomNavEl?.addEventListener('click'", app_js)
        self.assertIn("data-i18n-aria=\"Ne paylaşmak istersin?\"", index_html)
        self.assertIn(">Halkalar ve Meclisler<", index_html)
        self.assertIn("grid-template-columns: 86px minmax(0, 1fr) auto", css)
        self.assertIn(".page-head--tight .head-actions {", css)

        self.assertIn('id="notifications-btn"', index_html)
        self.assertIn('id="view-notifications"', index_html)
        self.assertIn('id="notifications-view-list"', index_html)
        self.assertIn('data-view="notifications"', index_html)
        self.assertIn("notifications-panel--page", css)
        self.assertNotIn('id="all-notifications-panel"', index_html)
        self.assertNotIn("function toggleAllNotifications(", app_js)
        self.assertIn("markNotificationsSeen('announcement')", app_js)
        self.assertIn("markNotificationsSeen('all')", app_js)
        self.assertNotIn("bottom-notifications-btn", index_html)
        self.assertNotIn("bottom-notifications-btn", app_js)

        self.assertIn('class="page-head page-head--library"', index_html)
        self.assertIn(".page-head--library {", css)
        self.assertIn("function renderFeedTabs(", app_js)
        self.assertIn("function circleTabKey(", app_js)
        self.assertNotIn('data-tab="circles"', index_html)
        self.assertIn('data-status="approved">${t(\'Takip ediliyor\')}', app_js)

        self.assertIn('id="top-brand" type="button" data-view="home"', index_html)
        self.assertIn('data-i18n-aria="İlim Halkası — ana sayfa"', index_html)
        self.assertIn('data-i18n-title="Ana sayfa"', index_html)
        brand_handler = app_js.split("$('#top-brand')?.addEventListener('click'", 1)[1].split("});", 1)[0]
        self.assertIn("switchView('home')", brand_handler)
        self.assertNotIn("classList.add('is-open')", brand_handler)
        self.assertNotIn("Beğeni, yorum, takip ve halka etkinliklerin burada toplanır.", index_html)
        self.assertNotIn("Beğeni, yorum, takip ve halka etkinliklerin burada toplanır.", i18n_js)

        self.assertIn(".app-shell .bottom-nav .nav-item,", css)
        self.assertIn("line-height: 1.3;", css)

        side_nav = index_html.split('<nav class="side-nav"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(side_nav.count('class="nav-section"'), 4)
        section_positions = []
        for label in ("ANA AKIŞ", "SOSYAL", "KİŞİSEL ALANIM", "HESABIM VE YÖNETİM"):
            self.assertIn('data-i18n="{}">{}<'.format(label, label), side_nav)
            section_positions.append(side_nav.index('data-i18n="{}"'.format(label)))
        self.assertEqual(section_positions, sorted(section_positions))
        self.assertNotIn("SOSYAL VE KİŞİSEL ALAN", index_html)
        self.assertNotIn("SOSYAL VE KİŞİSEL ALAN", i18n_js)
        self.assertIn(".nav-section + .nav-section", css)

        self.assertNotIn('data-theme-choice="gece"', index_html)
        self.assertNotIn("{ key: 'gece'", app_js)
        self.assertIn("state.settings.theme === 'gece'", app_js)
        self.assertNotIn("'Gece': 'Night',", i18n_js)

    def test_mobile_standard_fixes_are_wired(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        manifest = (PROJECT_ROOT / "android" / "app" / "src" / "main"
                    / "AndroidManifest.xml").read_text(encoding="utf-8")
        activity = (PROJECT_ROOT / "android" / "app" / "src" / "main" / "java"
                    / "com" / "ilimhalkasi" / "app" / "MainActivity.java").read_text(encoding="utf-8")

        self.assertIn("viewport-fit=cover", index_html)
        self.assertIn('role="group" aria-label="Keşfet kategorileri"', index_html)
        self.assertNotIn('role="tablist" aria-label="Keşfet kategorileri"', index_html)
        self.assertIn("aria-current", app_js)
        self.assertIn("docEl.style.scrollBehavior = 'auto'", app_js)
        self.assertIn("openModal.querySelector('.modal-close')", app_js)
        self.assertIn("$(input).value = ''", app_js)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)
        self.assertIn("html { scroll-behavior: auto; }", css)

        self.assertIn('android:configChanges="orientation|screenSize|keyboardHidden|uiMode|locale|layoutDirection"', manifest)
        self.assertIn("onReceivedHttpError", activity)
        self.assertIn("webView.saveState(state)", activity)
        self.assertIn("webView.restoreState(savedWebViewState)", activity)
        self.assertIn("protected void onPause()", activity)
        self.assertIn("protected void onResume()", activity)
        self.assertIn("CookieManager.getInstance().flush()", activity)
        self.assertIn("setMediaPlaybackRequiresUserGesture(true)", activity)

    def test_posts_recent_like_and_comment(self) -> None:
        marker = _marker("post")
        status, body = self.post(
            "/api/posts",
            {"text": marker, "book": "Smoke Test Book", "writer": "Tester", "type": "quote"},
        )
        self.assertEqual(status, 201, "post creation failed: {}".format(body))
        post = body.get("post") or {}
        post_id = post.get("id")
        self.assertTrue(post_id)
        self.assertEqual(post.get("text"), marker)

        status, recent = self.get("/api/posts/recent?after=0")
        self.assertEqual(status, 200, "recent posts failed: {}".format(recent))
        self.assertTrue(
            any(int(item.get("id", 0)) == post_id for item in recent.get("posts") or []),
            "newly created post is absent from /api/posts/recent",
        )

        status, like = self.post("/api/posts/{}/like".format(post_id))
        self.assertEqual(status, 200, "post like failed: {}".format(like))
        self.assertIn("active", like)
        self.assertIn("count", like)

        comment_text = _marker("comment")
        status, comment_body = self.post(
            "/api/posts/{}/comments".format(post_id), {"text": comment_text}
        )
        self.assertEqual(status, 201, "comment creation failed: {}".format(comment_body))
        comment = comment_body.get("comment") or {}
        self.assertTrue(comment.get("id"))
        self.assertEqual(comment.get("text"), comment_text)

        status, comment_like = self.post("/api/comments/{}/like".format(comment["id"]))
        self.assertEqual(status, 200, "comment like failed: {}".format(comment_like))
        self.assertIn("active", comment_like)
        self.assertIn("count", comment_like)

    def test_interactions_endpoint_groups_user_activity(self) -> None:
        opener, _ = self.register_user()
        marker = _marker("interaction")
        status, body = self.post(
            "/api/posts",
            {"text": marker, "book": "Interaction Book", "writer": "Tester", "type": "quote"},
            opener=opener,
        )
        self.assertEqual(status, 201, "post creation failed: {}".format(body))
        post_id = (body.get("post") or {}).get("id")
        self.assertTrue(post_id)

        for action in ("like", "favorite"):
            status, result = self.post(
                "/api/posts/{}/{}".format(post_id, action), opener=opener
            )
            self.assertEqual(status, 200, "{} failed: {}".format(action, result))

        status, comment_body = self.post(
            "/api/posts/{}/comments".format(post_id),
            {"text": _marker("interaction-comment")},
            opener=opener,
        )
        self.assertEqual(status, 201, "comment creation failed: {}".format(comment_body))

        status, data = self.get("/api/me/interactions", opener=opener)
        self.assertEqual(status, 200, "interactions endpoint failed: {}".format(data))
        for key in ("liked", "favorited", "commented"):
            self.assertTrue(
                any(int(item.get("id", 0)) == post_id for item in data.get(key) or []),
                "post missing from interactions.{}".format(key),
            )

    def test_ilim_series_counts_real_activity(self) -> None:
        opener, _ = self.register_user()
        self.assertEqual(
            (self.bootstrap(opener=opener).get("stats") or {}).get("ilimSeries"), 0
        )

        status, body = self.post(
            "/api/posts",
            {
                "text": _marker("series-post"), "book": "Series Book",
                "writer": "Tester", "type": "quote",
            },
            opener=opener,
        )
        self.assertEqual(status, 201, "post creation failed: {}".format(body))
        post_id = (body.get("post") or {}).get("id")
        self.assertTrue(post_id)

        book_id = self.book_id()
        for status_name in ("reading", "finished"):
            status, result = self.post(
                "/api/shelf", {"book_id": book_id, "status": status_name, "page": 1},
                opener=opener,
            )
            self.assertEqual(status, 200, "{} failed: {}".format(status_name, result))

        status, comment_body = self.post(
            "/api/posts/{}/comments".format(post_id),
            {"text": _marker("series-comment")}, opener=opener,
        )
        self.assertEqual(status, 201, "comment failed: {}".format(comment_body))

        series = (self.bootstrap(opener=opener).get("stats") or {}).get("ilimSeries")
        self.assertEqual(series, 4, "series must count post, reading, finish and comment")

    def test_feed_window_keeps_old_posts_out_of_feed_but_not_deleted(self) -> None:
        opener, user = self.register_user()
        marker = _marker("feedcap")
        stamp = time.time()
        conn = sqlite3.connect(self.tmp_dir / DB_FILENAME)
        try:
            for index in range(205):
                conn.execute(
                    "INSERT INTO posts (user_id,type,book,writer,text,rating,status,cover,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        int(user["id"]), "quote", "Feed Cap Book", "Tester",
                        "{}-{}".format(marker, index), 0, "", "", stamp - 300 + index,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        data = self.bootstrap(opener=opener)
        feed = data.get("posts") or []
        own_posts = data.get("ownPosts") or []
        self.assertLessEqual(len(feed), 200, "feed must stay within 200 posts")
        self.assertGreaterEqual(len(own_posts), 205, "own older posts must still be loaded")

        oldest = min(own_posts, key=lambda item: float(item.get("created_at", 0) or 0))
        feed_ids = {int(item.get("id", 0)) for item in feed}
        self.assertNotIn(int(oldest.get("id", 0)), feed_ids, "oldest post must leave the feed")

        conn = sqlite3.connect(self.tmp_dir / DB_FILENAME)
        try:
            still_there = conn.execute(
                "SELECT 1 FROM posts WHERE id=?", (int(oldest["id"]),)
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(still_there, "feed eviction must not delete the post")

        viewer_opener, _ = self.register_user()
        status, profile = self.get("/api/users/{}".format(user["id"]), opener=viewer_opener)
        self.assertEqual(status, 200, "profile failed: {}".format(profile))
        profile_ids = {
            int(item.get("id", 0)) for item in (profile.get("user") or {}).get("posts") or []
        }
        self.assertIn(int(oldest["id"]), profile_ids, "old post must remain on its author's profile")

    def test_book_posts_endpoint_returns_quotes_and_reviews(self) -> None:
        opener, _ = self.register_user()
        book = _marker("bookposts")
        created = []
        for ptype in ("quote", "review"):
            status, body = self.post(
                "/api/posts",
                {
                    "text": "{}-{}".format(book, ptype), "book": book,
                    "writer": "Tester", "type": ptype, "rating": 4 if ptype == "review" else 0,
                },
                opener=opener,
            )
            self.assertEqual(status, 201, "{} failed: {}".format(ptype, body))
            created.append(int((body.get("post") or {}).get("id") or 0))

        status, data = self.get(
            "/api/posts/by-book?book={}".format(book), opener=self.anon_opener
        )
        self.assertEqual(status, 200, "book posts endpoint failed: {}".format(data))
        found = {int(item.get("id", 0)) for item in data.get("posts") or []}
        for post_id in created:
            self.assertIn(post_id, found, "book page is missing post {}".format(post_id))
        types = {item.get("type") for item in data.get("posts") or []}
        self.assertIn("quote", types)
        self.assertIn("review", types)

    def test_nav_center_ink_and_book_posts_ui_are_wired(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        i18n_js = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")

        self.assertNotIn('data-i18n="Ekle"', index_html)
        self.assertIn('aria-label="Ne paylaşmak istersin?"', index_html)
        self.assertIn("transform: none;", css)
        self.assertIn(".ink-ripple {", css)
        self.assertIn("@keyframes ink-spread", css)
        self.assertIn("document.addEventListener('pointerdown'", app_js)
        self.assertIn("quickBtn?.querySelector('.nav-add-circle')", app_js)

        self.assertIn('data-detail-tab="posts"', index_html)
        self.assertIn('id="book-posts"', index_html)
        self.assertIn("/api/posts/by-book", app_js)
        self.assertIn("bookPostsRequest", app_js)

        self.assertIn("0 İlim Serisi", index_html)
        self.assertNotIn("Paylaşımlık İlim Serisi", app_js + i18n_js + index_html)
        self.assertNotIn("Favorilerim", app_js + i18n_js + index_html)
        self.assertIn("'Kaydet':", i18n_js)
        self.assertIn("'Kaydettiklerim':", i18n_js)
        self.assertIn("'Paylaşımın kaydedildi':", i18n_js)

    def test_privacy_notice_and_personal_data_export(self) -> None:
        status, notice = self.get("/api/privacy", opener=self.anon_opener)
        self.assertEqual(status, 200, "privacy notice failed: {}".format(notice))
        self.assertTrue(notice.get("contact"), "KVKK contact must be configured")
        self.assertEqual(notice["retention"]["sessions_days"], 30)
        self.assertEqual(notice["retention"]["reset_link_hours"], 1)
        self.assertEqual(notice["retention"]["deleted_post_tombstone_days"], 90)

        status, body = self.get("/api/me/export", opener=self.anon_opener)
        self.assertEqual(status, 401, "anonymous export must be rejected")

        opener, _ = self.register_user()
        marker = _marker("export")
        status, created = self.post(
            "/api/posts",
            {"text": marker, "book": "Export Book", "writer": "Tester", "type": "quote"},
            opener=opener,
        )
        self.assertEqual(status, 201, "post creation failed: {}".format(created))

        status, result = self.get("/api/me/export", opener=opener)
        self.assertEqual(status, 200, "export failed: {}".format(result))
        data = result.get("data") or {}
        raw = json.dumps(data, ensure_ascii=False)
        self.assertIn(marker, raw, "export must include the user's own post")
        self.assertIn("posts", data)
        self.assertIn("shelf", data)
        self.assertIn("user_meta", data)
        self.assertNotIn("password_hash", raw, "password hash must never be exported")
        self.assertNotIn("salt", raw, "password salt must never be exported")
        self.assertNotIn("token_hash", raw, "reset token hash must never be exported")

        status, me = self.get("/api/me", opener=opener)
        self.assertEqual(status, 200)
        self.assertEqual(data["profile"]["email"], me["user"]["email"])

    def test_maintenance_cleanup_backup_and_migration_log(self) -> None:
        opener, user = self.register_user()
        uid = int(user["id"])
        stamp = time.time()
        stale_token = _marker("stale-reset")
        active_token = _marker("active-reset")
        stale_session = _marker("stale-session")
        active_session = _marker("active-session")
        stale_post_id = 2_000_000_000 + int.from_bytes(uuid.uuid4().bytes[:4], "big")
        active_post_id = stale_post_id + 1
        hash_of = lambda token: hashlib.sha256(token.encode("utf-8")).hexdigest()

        conn = sqlite3.connect(self.tmp_dir / DB_FILENAME)
        try:
            conn.execute(
                "INSERT INTO password_resets (token_hash,user_id,expires_at,created_at,used) "
                "VALUES (?,?,?,?,1)",
                (hash_of(stale_token), uid, int(stamp + 3600), int(stamp)),
            )
            conn.execute(
                "INSERT INTO password_resets (token_hash,user_id,expires_at,created_at,used) "
                "VALUES (?,?,?,?,0)",
                (hash_of(active_token), uid, int(stamp + 3600), int(stamp)),
            )
            conn.execute("INSERT INTO sessions (token,user_id,expires_at) VALUES (?,?,?)",
                         (stale_session, uid, int(stamp - 10)))
            conn.execute("INSERT INTO sessions (token,user_id,expires_at) VALUES (?,?,?)",
                         (active_session, uid, int(stamp + 3600)))
            conn.execute("INSERT INTO deleted_posts (id,deleted_at) VALUES (?,?)",
                         (stale_post_id, stamp - 91 * 86400))
            conn.execute("INSERT INTO deleted_posts (id,deleted_at) VALUES (?,?)",
                         (active_post_id, stamp))
            conn.commit()
        finally:
            conn.close()

        link = "http://localhost:8765/?reset="
        outbox = self.tmp_dir / "password_reset_outbox.txt"
        outbox.write_text(
            "2026-01-01 00:00:00 | stale@example.test | {}{}\n"
            "2026-01-01 00:00:00 | active@example.test | {}{}\n".format(
                link, stale_token, link, active_token
            ),
            encoding="utf-8",
        )

        status, result = self.post("/api/admin/maintenance/run", {})
        self.assertEqual(status, 200, "maintenance run failed: {}".format(result))
        self.assertEqual(result.get("integrity"), "ok")
        self.assertGreaterEqual(result.get("removed", {}).get("password_resets", 0), 1)
        self.assertGreaterEqual(result.get("removed", {}).get("sessions", 0), 1)
        self.assertGreaterEqual(result.get("removed", {}).get("deleted_posts", 0), 1)
        self.assertGreaterEqual(result.get("removed", {}).get("outbox_lines", 0), 1)

        status, db_status = self.get("/api/admin/db-status")
        self.assertEqual(status, 200, "db status failed: {}".format(db_status))
        self.assertEqual(db_status.get("integrity"), "ok")
        self.assertIn("008-kvkk-export-maintenance", db_status.get("migrations") or [])
        self.assertGreaterEqual(db_status.get("backupCount", 0), 1)

        conn = sqlite3.connect(self.tmp_dir / DB_FILENAME)
        try:
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM password_resets WHERE token_hash=?", (hash_of(stale_token),)
            ).fetchone())
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM password_resets WHERE token_hash=?", (hash_of(active_token),)
            ).fetchone())
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM sessions WHERE token=?", (stale_session,)
            ).fetchone())
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM sessions WHERE token=?", (active_session,)
            ).fetchone())
            self.assertIsNone(conn.execute(
                "SELECT 1 FROM deleted_posts WHERE id=?", (stale_post_id,)
            ).fetchone())
            self.assertIsNotNone(conn.execute(
                "SELECT 1 FROM deleted_posts WHERE id=?", (active_post_id,)
            ).fetchone())
        finally:
            conn.close()

        kept = outbox.read_text(encoding="utf-8")
        self.assertNotIn(stale_token, kept)
        self.assertIn(active_token, kept)

        backup_name = (db_status.get("backups") or [{}])[0].get("file")
        self.assertTrue(backup_name, "no backup reported")
        backup_path = self.tmp_dir / "backups" / backup_name
        self.assertTrue(backup_path.exists(), "backup file is missing")
        backup_conn = sqlite3.connect(backup_path)
        try:
            self.assertEqual(backup_conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            backup_conn.close()

    def test_kvkk_ui_is_wired(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        i18n_js = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn('id="privacy-open-btn"', index_html)
        self.assertIn('id="export-data-btn"', index_html)
        self.assertIn('id="privacy-modal"', index_html)
        self.assertIn("/api/privacy", app_js)
        self.assertIn("/api/me/export", app_js)
        self.assertIn("PRIVACY_SECTIONS", app_js)
        self.assertIn("JSON.stringify(data, null, 2)", app_js)
        self.assertIn("'Verilerimi dışa aktar (JSON)':", i18n_js)
        self.assertIn("'Toplanan veriler':", i18n_js)
        self.assertIn("'Başvuru':", i18n_js)
        self.assertIn("backups/", gitignore)

    def test_book_request_submission_and_admin_approval(self) -> None:
        opener, _ = self.register_user()
        title = _marker("bookrequest")
        status, body = self.post(
            "/api/book-requests",
            {
                "title": title,
                "author": "Smoke Author",
                "page_count": 321,
                "about": _marker("about"),
            },
            opener=opener,
        )
        self.assertEqual(status, 200, "book request failed: {}".format(body))
        request = body.get("request") or {}
        request_id = request.get("id")
        self.assertTrue(request_id)
        self.assertEqual(request.get("status"), "pending")

        status, data = self.get("/api/bootstrap", opener=opener)
        self.assertEqual(status, 200, data)
        self.assertTrue(
            any(int(item.get("id", 0)) == request_id for item in data.get("book_requests") or []),
            "own book request missing from bootstrap",
        )
        admin_data = self.bootstrap()
        self.assertTrue(
            any(int(item.get("id", 0)) == request_id
                for item in (admin_data.get("admin") or {}).get("book_requests") or []),
            "pending book request missing from admin bootstrap",
        )

        status, reviewed = self.post(
            "/api/admin/book-requests/{}/review".format(request_id), {"approve": True}
        )
        self.assertEqual(status, 200, "book request approval failed: {}".format(reviewed))
        updated = reviewed.get("request") or {}
        self.assertEqual(updated.get("status"), "approved")
        self.assertTrue((updated.get("book") or {}).get("id"), "approved book was not linked")

    def test_curriculum_progress_is_exposed_in_bootstrap(self) -> None:
        data = self.bootstrap()
        curricula = data.get("curricula") or []
        self.assertTrue(curricula, "bootstrap has no curricula")
        curriculum = curricula[0]
        step = curriculum["steps"][0]
        self.assertTrue(step.get("book_id"), "first curriculum step is not linked to the catalogue")
        self.assertIn(" - ", step.get("label", ""), "resolved step should show title - author")

        status, result = self.post(
            "/api/curricula/{}/steps/{}/progress".format(curriculum["key"], step["index"]),
            {"status": "reading", "page": 40},
        )
        self.assertEqual(status, 200, "curriculum progress failed: {}".format(result))

        updated = self.bootstrap()
        updated_step = updated["curricula"][0]["steps"][0]
        self.assertEqual(updated_step.get("status"), "reading")
        self.assertEqual(int(updated_step.get("page", 0)), 40)

    def test_invalid_targets_return_clean_404(self) -> None:
        cases = (
            ("/api/posts/999999/like", {}),
            ("/api/comments/999999/like", {}),
            ("/api/debates/999999/answers", {"text": _marker("answer")}),
            ("/api/follow/999999", {}),
        )
        for path, payload in cases:
            with self.subTest(path=path):
                try:
                    status, body = self.post(path, payload)
                except urllib.error.URLError as exc:
                    self.fail("{} dropped the connection: {}".format(path, exc))
                self.assertEqual(status, 404, "{} returned {} ({})".format(path, status, body))
                self.assertIn("error", body, "{} did not return JSON error: {}".format(path, body))

    def test_post_requires_csrf_token(self) -> None:
        # Copy the authenticated admin cookies but deliberately omit the CSRF
        # header, so the request reaches the CSRF check with a valid session.
        opener, jar = _new_opener()
        for cookie in self.admin_jar:
            jar.set_cookie(cookie)
        status, body = self.post("/api/posts", {}, opener=opener)
        self.assertEqual(status, 403, "missing CSRF token must be rejected: {}".format(body))
        self.assertIn("error", body)

        status, body = self.post(
            "/api/posts",
            {"kind": "note", "text": "", "visibility": "public"},
            opener=self.admin_opener,
        )
        self.assertNotEqual(status, 403, "normal requests with CSRF token must pass the check")

    def test_forgot_password_excludes_admin(self) -> None:
        status, body = self.post("/api/forgot-password", {"email": ADMIN_EMAIL}, opener=self.anon_opener)
        self.assertEqual(status, 200, "forgot-password failed: {}".format(body))
        self.assertTrue(body.get("ok"))
        self.assertNotIn("dev_link", body, "reset links must never be returned to the client")

        # Positive control: an ordinary user receives a generic response too.
        normal_opener, user = self.register_user()
        status, normal_body = self.post(
            "/api/forgot-password", {"email": user["email"]}, opener=normal_opener
        )
        self.assertEqual(status, 200)
        self.assertNotIn("dev_link", normal_body, "reset links must never be returned to the client")
        outbox = (self.tmp_dir / "password_reset_outbox.txt").read_text(encoding="utf-8")
        self.assertIn(user["email"], outbox, "the link should be stored server-side only")

    def test_non_admin_cannot_use_admin_endpoints(self) -> None:
        opener, user = self.register_user()
        self.assertFalse(user.get("is_admin"))

        data = self.bootstrap(opener=opener)
        self.assertNotIn("admin", data, "non-admin bootstrap must not contain admin payload")

        for path, payload in (
            ("/api/admin/announcements", {"title": "nope", "body": "nope"}),
            ("/api/admin/books/1/moderate", {"hidden": 1, "reason": "nope"}),
            ("/api/admin/users/1/block", {}),
        ):
            with self.subTest(path=path):
                status, body = self.post(path, payload, opener=opener)
                self.assertEqual(status, 403, "{} returned {} ({})".format(path, status, body))
                self.assertIn("error", body)

    def test_follow_and_mention_create_notifications(self) -> None:
        """Follows and @mentions appear in the recipient's bootstrap payload."""
        opener_a, user_a = self.register_user()
        opener_b, user_b = self.register_user()

        status, body = self.post(
            "/api/follow", {"user_id": user_b["id"], "action": "follow"}, opener=opener_a
        )
        self.assertEqual(status, 200, "follow failed: {}".format(body))
        self.assertTrue(body.get("following"))

        marker = _marker("mention")
        status, body = self.post(
            "/api/posts",
            {
                "text": "{} @{}".format(marker, user_b["username"]),
                "book": "Smoke Test Book",
                "type": "quote",
            },
            opener=opener_a,
        )
        self.assertEqual(status, 201, "post with mention failed: {}".format(body))

        notes = self.bootstrap(opener=opener_b).get("notifications") or []
        kinds = {item.get("kind") for item in notes}
        self.assertIn("follow", kinds, "follow notification missing: {}".format(notes))
        self.assertIn("mention", kinds, "mention notification missing: {}".format(notes))

        status, endpoint_body = self.get("/api/notifications", opener=opener_b)
        self.assertEqual(status, 200, "notifications endpoint failed: {}".format(endpoint_body))
        self.assertTrue(
            any(item.get("kind") == "mention" for item in endpoint_body.get("notifications") or []),
            "notifications endpoint is missing the mention",
        )

        mention = next(item for item in notes if item.get("kind") == "mention")
        self.assertEqual((mention.get("actor") or {}).get("id"), user_a["id"])
        self.assertIn(marker, mention.get("text", ""))

    def test_circle_post_creates_notification_for_members(self) -> None:
        """A post inside a halka notifies the other members."""
        opener_a, _ = self.register_user()
        opener_b, _ = self.register_user()

        name = _marker("halka")
        status, body = self.post(
            "/api/groups/halka", {"name": name, "description": "Smoke circle"}, opener=opener_a
        )
        self.assertEqual(status, 201, "halka creation failed: {}".format(body))
        group_id = body.get("id")
        self.assertTrue(group_id)

        status, body = self.post(
            "/api/groups/{}/join".format(group_id), opener=opener_b
        )
        self.assertEqual(status, 200, "joining halka failed: {}".format(body))
        self.assertTrue(body.get("ok"))

        marker = _marker("circle-post")
        status, body = self.post(
            "/api/posts",
            {"text": marker, "book": "Smoke Test Book", "group_id": group_id},
            opener=opener_a,
        )
        self.assertEqual(status, 201, "circle post failed: {}".format(body))

        notes = self.bootstrap(opener=opener_b).get("notifications") or []
        circle_note = next((item for item in notes if item.get("kind") == "circle_post"), None)
        self.assertIsNotNone(circle_note, "circle post notification missing: {}".format(notes))
        self.assertEqual((circle_note.get("group") or {}).get("id"), group_id)
        self.assertIn(marker, circle_note.get("text", ""))

    def test_direct_message_creates_notification(self) -> None:
        """A message in a small chat notifies the other participant."""
        opener_a, user_a = self.register_user()
        opener_b, user_b = self.register_user()

        for actor, target in ((opener_a, user_b), (opener_b, user_a)):
            status, body = self.post(
                "/api/follow", {"user_id": target["id"], "action": "follow"}, opener=actor
            )
            self.assertEqual(status, 200, "mutual follow failed: {}".format(body))

        status, body = self.post(
            "/api/groups/direct", {"username": user_b["username"]}, opener=opener_a
        )
        self.assertEqual(status, 201, "direct chat creation failed: {}".format(body))
        group_id = body.get("id")
        self.assertTrue(group_id)

        marker = _marker("dm")
        status, body = self.post(
            "/api/groups/{}/messages".format(group_id), {"text": marker}, opener=opener_a
        )
        self.assertEqual(status, 201, "group message failed: {}".format(body))

        notes = self.bootstrap(opener=opener_b).get("notifications") or []
        message_note = next((item for item in notes if item.get("kind") == "group_message"), None)
        self.assertIsNotNone(message_note, "group message notification missing: {}".format(notes))
        self.assertEqual((message_note.get("group") or {}).get("id"), group_id)
        self.assertIn(marker, message_note.get("text", ""))

    def test_guest_first_browsing_and_account_sheet_are_wired(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        i18n_js = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for marker in (
            'id="account-sheet"', 'id="account-sheet-text"', 'id="account-create-btn"',
            'id="account-login-btn"', 'id="account-later-btn"',
            'data-i18n="Şimdi oluştur"', 'data-i18n="Sonra"',
            'data-guest-auth-btn', 'data-member-only', 'id="quick-add-btn"',
        ):
            self.assertIn(marker, index_html, "missing guest UI marker: " + marker)

        for marker in (
            "function requestAccount(", "function closeAccountSheet(",
            "function maybeRemindGuest(", "const GUEST_FIRST_KEY = 'ilimhalkasi.guest.firstVisit'",
            "const GUEST_WEEK_MS = 7 * 24 * 60 * 60 * 1000",
            "response.status === 401 && !state.user", "requestAccount();",
            "await initAppSession();", "clearGuestReminder();",
        ):
            self.assertIn(marker, app_js, "missing guest flow code: " + marker)

        boot_block = app_js.split("async function boot()", 1)[1].split("\n}", 1)[0]
        self.assertNotIn("showAuth(true)", boot_block, "boot must not force guests to register")
        self.assertNotIn("showAuth(true);\n    authTab('login');", boot_block)

        for key in (
            "Hesap Oluştur", "Şimdi oluştur", "Sonra", "Misafir", "Davet et",
            "Bu işlem için hesap gerekli.", "{action} için hesap gerekli.",
            "Bir haftadır keşfediyorsun. Hesap açarsan takip edebilir ve paylaşabilirsin.",
            "Selamün Aleyküm, hoş geldin",
            "Misafir olarak geziyorsun · Hesap açarak paylaşımlara katılabilirsin",
            "Çıkış yaptın. Keşfetmeye devam edebilirsin.",
            "Hesabın kalıcı olarak silindi. İstersen yeniden kayıt olabilirsin.",
        ):
            self.assertIn("'{}':".format(key), i18n_js, "missing i18n key: " + key)

    def test_button_labels_and_uniform_controls_are_wired(self) -> None:
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        i18n_js = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")

        # The old mobile rule hid every gold button's text and replaced it with ✧.
        self.assertNotIn("\n  .btn-gold { font-size: 0; }", css)
        self.assertNotIn(".btn-gold::after { content: \"✧\";", css)
        self.assertIn(".app-shell.nav-mini .sidebar .btn-gold { font-size: 0; }", css)
        self.assertIn("/* Butonlar artık metinlerini korur; sadece renk/kenarlık değişir. */", css)
        self.assertIn(".btn:hover, .btn:active, .menu-btn:active, .theme-choice:hover { transform: none; }", css)
        self.assertIn(".btn, .btn-sm, .page-head--tight .btn, .greeting-actions .btn, .sheet-actions .btn {", css)
        self.assertIn("/* Simge + yazı birlikte görünsün. */", css)
        self.assertIn(".top-actions .icon-btn,", css)
        self.assertIn(".bottom-nav .nav-add { display: flex; align-items: center; justify-content: center; }", css)
        self.assertNotIn("nav-quick-label", css)
        self.assertNotIn("transform: translateY(-7px);", css)

        self.assertIn('<span data-i18n="Duyurular">Duyurular</span>', index_html)
        self.assertIn('<span data-i18n="Ara">Ara</span>', index_html)
        self.assertIn('<span data-i18n="Okundu">Okundu</span>', index_html)
        self.assertIn('<span data-i18n="Şikayet ve talepler">Şikayet ve talepler</span>', index_html)
        self.assertIn("'Duyurular':", (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8"))
        self.assertIn("'Ara':", app_js + (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8"))

        # Üst panel yalnızca Duyurular + Ara; marka tam ortada.
        top_actions = index_html.split('<div class="top-actions">', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="notifications-btn"', top_actions)
        self.assertIn('id="search-open-btn"', top_actions)
        self.assertNotIn('class="icon-btn mobile-only" id="search-open-btn"', index_html)
        self.assertIn("grid-template-columns: minmax(44px, 1fr) auto minmax(44px, 1fr);", css)
        self.assertNotIn("grid-template-columns: 44px minmax(0, 1fr) auto;", css)
        self.assertIn(".topbar .top-brand { grid-column: 2; justify-self: center; }", css)
        self.assertIn("  .top-brand {\n    position: static;", css)
        self.assertIn(".topbar .search-wrap,", css)
        self.assertIn('.top-actions [data-view="support"],', css)
        self.assertIn(".top-actions .top-logout,", css)
        self.assertIn(".top-actions .top-guest { display: none !important; }", css)
        self.assertNotIn(".top-brand { display: none !important; }", css)

        # Üst panel etiketsiz: Menü / Duyurular / Ara yalnızca simge gösterir.
        self.assertIn(
            ".topbar #menu-btn > span,\n"
            ".topbar #notifications-btn > span:not(.badge-count),\n"
            ".topbar #search-open-btn > span { display: none !important; }",
            css,
        )
        self.assertNotIn("  .topbar #menu-btn span { display: inline; }", css)
        self.assertIn("  .topbar #notifications-btn svg,", css)
        self.assertIn("  .topbar #search-open-btn svg { width: 18px; height: 18px; }", css)

        # Menü simgesi kare alanda ortalanır; önerilen başlıkları hizalar.
        self.assertIn(".menu-btn {\n  display: none;\n  align-items: center;\n  justify-content: center;", css)
        self.assertIn("  .topbar #menu-btn {\n    align-items: center;\n    justify-content: center;\n    width: 44px;", css)
        self.assertIn(".home-book-group > h3 {\n  display: flex;\n  align-items: center;", css)
        self.assertIn("  .home-book-group > h3 svg { width: 16px; height: 16px; flex-basis: 16px; }", css)

        # Karşılama kartındaki aktif kitap ve paylaşım kontrolleri aynı ölçüde.
        self.assertIn("  .greeting-stats .stat-chip,\n  .greeting-actions .btn {", css)
        self.assertIn("    height: 34px;\n    min-height: 34px;\n    padding: 6px 10px;", css)
        self.assertIn("    font-size: 13px;\n    font-weight: 600;\n    line-height: 1.3;", css)

        # Kütüphane düğmeleri arasında nefes alan boşluk var.
        self.assertIn("    gap: 10px;\n    margin-top: 4px;\n  }\n  .page-head--library .head-actions .btn {", css)

        # Hesap davetindeki gereksiz açıklama ve paylaşım gürültüsü kalktı.
        self.assertNotIn("Önce kitapları, halkaları ve akışı keşfedebilirsin.", index_html)
        self.assertNotIn("'Önce kitapları, halkaları ve akışı keşfedebilirsin.':", i18n_js)
        self.assertNotIn('class="fav-summary"', app_js)
        self.assertNotIn("kişi tarafından favorilere eklendi", app_js)
        self.assertNotIn("Kartpostal defterine eklendi ✧", app_js)
        self.assertNotIn("'Kartpostal defterine eklendi ✧':", i18n_js)
        self.assertNotIn(".fav-summary", css)

        # Ana sayfadaki etiketler okunabilir boyutta olmalı; sadece simge kalmasın.
        uniform = css.split("/* ---------- Tek düzen: aynı tür kontrol her yerde aynı ölçüde ---------- */", 1)[1]
        uniform = uniform.split("/* ---------- ", 1)[0]
        for marker in (
            "font-size: 13px;",  # btn / tab
            "font-size: 12px;",  # chip / action / follow
            ".follow-btn { font-size: 12px; min-height: 30px; }",
            ".action { font-size: 12px; }",
            ".bottom-nav .nav-add { display: flex;",
        ):
            self.assertIn(marker, uniform, "missing readable label rule: " + marker)
        self.assertNotIn("nav-quick-label", css)
        self.assertNotIn(".icon-btn > span:not(.badge-count) { font-size: 9px;", css)
        nav_block = css.split(".app-shell .bottom-nav .nav-item,\n  .app-shell .bottom-nav .nav-item:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: 10px;", nav_block, "bottom nav labels are still too small")

        server_py = (PROJECT_ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('self.send_header("Cache-Control", "no-store")', server_py)
        activity = (PROJECT_ROOT / "android" / "app" / "src" / "main" / "java"
                    / "com" / "ilimhalkasi" / "app" / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("settings.setCacheMode(WebSettings.LOAD_NO_CACHE);", activity)
        self.assertIn("webView.clearCache(true);", activity)

    def test_local_typography_is_self_hosted_and_readable(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        server_py = (PROJECT_ROOT / "server.py").read_text(encoding="utf-8")
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

        # Harici font isteği yok; tüm yazı tipleri yerel WOFF2 dosyalarından gelir.
        self.assertNotIn("fonts.googleapis.com", index_html)
        self.assertNotIn("fonts.gstatic.com", index_html)
        self.assertNotIn("family=El+Messiri", index_html)
        self.assertNotIn("Newsreader", css)
        self.assertNotIn("Playfair Display", css)
        self.assertNotIn("Inter", css)

        for marker in (
            '@font-face {',
            'font-family: "El Messiri";',
            'font-weight: 600 700;',
            'src: url("fonts/el-messiri-latin-ext.woff2") format("woff2");',
            'unicode-range: U+0100-02BA',  # İ, ğ, ş için latin-ext
            'src: url("fonts/el-messiri-latin.woff2") format("woff2");',
            'unicode-range: U+0000-00FF, U+0131',  # ç, ı, ö, ü için latin
            'font-family: "Lora";',
            'src: url("fonts/lora-latin-ext.woff2") format("woff2");',
            'font-family: "Amiri";',
            'src: url("fonts/amiri-400-arabic.woff2") format("woff2");',
            'font-family: "Plus Jakarta Sans";',
            'font-display: swap;',
        ):
            self.assertIn(marker, css, "missing local font marker: " + marker)

        for marker in (
            '--brand-font: "El Messiri", "Cormorant Garamond", Georgia, serif;',
            '--serif: "Lora", Georgia, "Times New Roman", serif;',
            '--display: "Lora", Georgia, serif;',
            '--sans: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;',
            '--arabic: "Amiri", "Traditional Arabic", "Noto Naskh Arabic", serif;',
            '--brand-size: clamp(19px, 4.4vw, 21px);',
            '--title-size: clamp(21px, 4.8vw, 25px);',
            '--heading-size: clamp(15px, 3.8vw, 17px);',
            '--card-title-size: clamp(14px, 3.6vw, 15px);',
            '--card-body-size: clamp(12px, 3.3vw, 13px);',
            '--reading-size: clamp(15px, 4vw, 16px);',
            '--reading-line: 1.7;',
            '--button-size: 13px;',
            '--ui-size: 13px;',
            '--meta-size: 11px;',
            '[data-theme="gece"] .top-brand { font-weight: 600; letter-spacing: .8px; }',
        ):
            self.assertIn(marker, css, "missing typography token: " + marker)

        self.assertGreaterEqual(css.count("--brand-ink: var(--accent-primary);"), 4)
        self.assertIn("h2, h3 { font-size: var(--heading-size); line-height: 1.35; }", css)
        self.assertIn("font-size: var(--reading-size);\n  line-height: var(--reading-line);", css)

        # Başlık / açıklama / buton ölçekleri kartlarda ve sayfa başlarında dengeli.
        self.assertIn(
            ".feed-head p, .page-head p { margin: 5px 0 0; color: var(--ink-soft); "
            "font-size: var(--card-body-size); line-height: 1.5; }",
            css,
        )
        self.assertIn(
            ".group-card h3 { margin: 11px 0 5px; font-family: var(--serif); "
            "font-size: var(--card-title-size); color: var(--olive-deep); line-height: 1.35; }",
            css,
        )
        self.assertIn(
            ".group-card p { margin: 0 0 12px; color: var(--ink-soft); "
            "font-size: var(--card-body-size); line-height: 1.5; min-height: 40px; }",
            css,
        )
        self.assertIn("  font-size: 11px;\n  font-weight: 700;\n}\n.group-card-actions", css)
        self.assertIn(".text-btn { font-size: 13px; }", css)
        self.assertIn(
            ".debate-form button, .chat-form button, .answer-form button,\n"
            ".admin-reply button, .goal-edit button, .list-rename-form button,\n"
            ".shelf-add-btn, .search-detail-btn { font-size: 13px; }",
            css,
        )
        self.assertIn(
            ".comment-meta button, .note-actions button, .admin-delete,\n"
            ".auth-forgot, .footer-links button { font-size: 12px; }",
            css,
        )
        self.assertNotIn(".app-shell:not(.nav-mini) .btn-gold { font-size: 12px; }", css)
        self.assertIn(".app-shell:not(.nav-mini) .sidebar .btn-gold { font-size: 12px; }", css)

        # Son söz bloğu tüm metinli kontrolleri tek ölçekte sabitler.
        final = css.split("/* ---------- Son söz: tek etkileşim ve metin ölçeği ---------- */", 1)[1]
        button_block = final.split("/* Kart açıklamaları", 1)[0]
        self.assertIn("button:not([class])", button_block)
        self.assertIn(".chat-profile-link, .side-user, .avatar-choice, .menu-btn,", button_block)
        self.assertIn(".bottom-nav .nav-item", button_block)
        self.assertIn("font-size: var(--button-size) !important;", button_block)
        self.assertNotIn("font-size: 10px", button_block)
        self.assertNotIn("font-size: 11px", button_block)
        self.assertNotIn("font-size: 12px", button_block)
        self.assertIn("font-size: var(--ui-size) !important;", final)
        self.assertIn("font-size: var(--meta-size) !important;", final)
        self.assertIn("#book-detail-title { font-size: var(--title-size) !important;", final)
        self.assertIn("body:not(.text-large) .post-body", final)

        # Unvan merdiveni ve etkileşim alıntıları kart ölçeğiyle aynı ritimde.
        self.assertIn(
            ".ladder-item strong { display: block; margin-top: 7px; font-family: var(--serif); "
            "font-size: var(--card-title-size); line-height: 1.35; color: var(--olive-deep); }",
            css,
        )
        self.assertIn(
            ".ladder-item small { display: block; color: var(--ink-faint); "
            "font-size: var(--meta-size); line-height: 1.45; margin-top: 4px; }",
            css,
        )
        self.assertIn("body:not(.text-large) .writing-item p.interaction-text {", final)
        self.assertIn("font-size: var(--card-body-size) !important;", final)
        self.assertIn(
            "/* Sayfa başı: başlık, açıklama ve işlemler aynı dikey ritimde dizilir. */",
            css,
        )
        self.assertIn(".page-head:not(.page-head--tight) {", css)

        for font_name in (
            "amiri-400-arabic.woff2", "amiri-400-latin-ext.woff2", "amiri-400-latin.woff2",
            "amiri-700-arabic.woff2", "amiri-700-latin-ext.woff2", "amiri-700-latin.woff2",
            "el-messiri-arabic.woff2", "el-messiri-latin-ext.woff2", "el-messiri-latin.woff2",
            "lora-latin-ext.woff2", "lora-latin.woff2",
            "plus-jakarta-sans-latin-ext.woff2", "plus-jakarta-sans-latin.woff2",
        ):
            font_path = PROJECT_ROOT / "fonts" / font_name
            self.assertTrue(font_path.is_file(), "missing font file: " + font_name)
            self.assertGreater(font_path.stat().st_size, 1000, "empty font file: " + font_name)
            self.assertIn(
                '"/fonts/{}": ("fonts/{}", "font/woff2"),'.format(font_name, font_name),
                server_py,
                "server does not serve font: " + font_name,
            )

        self.assertIn("yerel WOFF2", readme)

    def test_section_rhythm_and_compact_actions_are_wired(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")

        for removed in (
            "<p>Bir halkaya katıldığında üstteki listeye eklenir.</p>",
            "<p>Platformdaki diğer ilim yolcularını ara, profillerini incele ve takip et.</p>",
            '<p data-i18n="Altını çizdiklerin ve kaleme aldıkların.">Altını çizdiklerin ve kaleme aldıkların.</p>',
            '<p data-i18n="Her kitap ve paylaşım seni bir sonraki seviyeye taşır.">Her kitap ve paylaşım seni bir sonraki seviyeye taşır.</p>',
        ):
            self.assertNotIn(removed, index_html, "stale helper text still present: " + removed)

        self.assertIn('<h1 id="users-title" data-i18n="Kullanıcılar">Kullanıcılar</h1>', index_html)
        meclis = index_html.split('<div id="community-meclis" hidden>', 1)[1]
        self.assertIn('class="community-functions"', meclis)

        for button_id in (
            "invite-btn",
            "users-invite-btn",
            "new-direct-btn",
            "notifications-view-mark-read",
            "edit-profile-btn",
        ):
            match = re.search(
                r'<button[^>]*id="' + re.escape(button_id) + r'"[^>]*>', index_html
            )
            self.assertIsNotNone(match, "missing button: " + button_id)
            self.assertIn("btn-compact", match.group(0), button_id + " should stay compact")

        for marker in (
            ".page-head { display: flex; align-items: end; justify-content: space-between; gap: 18px; padding-top: 14px; margin-bottom: 14px; }",
            ".page-head.page-head--section { gap: 6px !important; margin-bottom: 16px !important; }",
            "#view-circles .tabs { margin-bottom: 18px; }",
            ".btn.btn-compact {",
            ".page-head > .btn.btn-compact {",
            ".discover-writing-head strong { font-size: var(--card-title-size) !important;",
            ".profile-hero .follow-counts b {",
            "font-size: 13px !important;",
            ".profile-hero .profile-bio { font-size: 14px !important;",
            '". . action"',
            ".profile-hero > #edit-profile-btn { grid-area: action; justify-self: end; margin-top: 0; }",
        ):
            self.assertIn(marker, css, "missing layout marker: " + marker)

    def test_library_filters_rules_and_compact_actions_are_tidy(self) -> None:
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")
        css = (PROJECT_ROOT / "styles.css").read_text(encoding="utf-8")
        i18n_js = (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8")

        for removed in (
            '<p class="modal-desc">Ortak okuma ve yazılı müzakere için bir halka kur.</p>',
            "Halka fotoğrafı <small>(isteğe bağlı)</small>",
            '<p class="modal-desc">Katalogda bulunmayan bir eseri öner. Yönetici inceleyip kataloğa ekleyecek.</p>',
            '<span>Kitap ara</span>',
            'id="book-search-input" type="search" placeholder="Kitap adı veya yazar yaz"',
            'id="filter-author"',
            'id="filter-publisher"',
            "data-filter-search",
        ):
            self.assertNotIn(removed, index_html, "stale markup still present: " + removed)

        for added in (
            '<span data-i18n="Kitap/Yazar Ara">Kitap/Yazar Ara</span>',
            'placeholder="Kitap/Yazar Ara" data-i18n-placeholder="Kitap/Yazar Ara" aria-label="Kitap/Yazar Ara"',
            '<span data-i18n="Halka fotoğrafı">Halka fotoğrafı</span>',
            '<button class="btn btn-outline btn-sm" type="button" id="book-add-btn">Kitap Ekle</button>',
            'data-view="support" data-i18n="Şikayet & Talepler">Şikayet &amp; Talepler</button>',
            'class="btn btn-outline btn-sm btn-compact" type="button" data-view="profile">Profile dön →',
            'class="btn btn-outline btn-sm btn-compact" type="button" data-book-request-open>',
        ):
            source = app_js if "data-book-request-open" in added else index_html
            self.assertIn(added, source, "missing updated markup: " + added)

        settings = index_html.rsplit('<div class="settings-actions">', 1)[1].split("</div>", 1)[0]
        self.assertLess(
            settings.index('id="settings-reset"'),
            settings.index('id="settings-save"'),
            "Varsayılanlara dön should sit left of Kaydet",
        )

        for button_id in ("journal-primary-btn", "settings-reset", "settings-save"):
            match = re.search(r'<button[^>]*id="' + re.escape(button_id) + r'"[^>]*>', index_html)
            self.assertIsNotNone(match, "missing button: " + button_id)
            self.assertIn("btn-compact", match.group(0), button_id + " should stay compact")

        for key in (
            "Ayrıştırma yok:", "Saygılı tartışma:", "İlmî doğruluk:", "Özel bilgiler:",
            "Reklam yok:", "Telif ve kaynak:", "Bildirim:", "Kitap/Yazar Ara",
            "Kütüphanemizde bulunmayan bir kitabı önerebilirsiniz. Ekibimiz inceleyip ekleyecektir.",
        ):
            self.assertIn("'" + key + "':", i18n_js, "missing i18n key: " + key)

        for marker in (
            "  font-size: 17px;\n  box-shadow: none;\n}",
            ".about-rules li strong { color: var(--olive-deep); font-family: var(--sans); font-size: var(--reading-size); font-weight: 700; }",
            ".settings-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; margin-top: 18px; }",
        ):
            self.assertIn(marker, css, "missing layout marker: " + marker)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep 302 responses visible so redirect targets can be asserted."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class EmailVerificationTests(unittest.TestCase):
    """Second isolated server: email verification and rate limits are enabled."""

    @classmethod
    def setUpClass(cls) -> None:
        global _CURRENT_PORT
        cls._tmp = tempfile.TemporaryDirectory(prefix="ilimhalkasi-verify-")
        cls.tmp_dir = Path(cls._tmp.name)
        try:
            _copy_sources(cls.tmp_dir)
            cls.port = _free_port()
            _CURRENT_PORT = cls.port
            cls.base_url = "http://127.0.0.1:{}".format(cls.port)
            cls.proc, cls.log_handle = _launch_server(
                cls.tmp_dir,
                cls.port,
                {
                    "ILIMHALKASI_REQUIRE_EMAIL_VERIFICATION": "1",
                    "ILIMHALKASI_RATE_LIMIT": "1",
                },
            )
            cls.opener, cls.jar = _new_opener()
            cls._wait_until_ready()
        except Exception:
            cls._stop_resources()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stop_resources()

    @classmethod
    def _stop_resources(cls) -> None:
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        handle = getattr(cls, "log_handle", None)
        if handle is not None and not handle.closed:
            handle.close()
        tmp = getattr(cls, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    @classmethod
    def _wait_until_ready(cls) -> None:
        deadline = time.monotonic() + STARTUP_TIMEOUT
        last_error = None
        while time.monotonic() < deadline:
            if cls.proc.poll() is not None:
                raise RuntimeError(
                    "Verification test server exited during startup.\n"
                    + (cls.tmp_dir / "server.log").read_text(encoding="utf-8", errors="replace")
                )
            try:
                with urllib.request.urlopen(cls.base_url + "/api/me", timeout=1) as response:
                    response.read()
                return
            except urllib.error.HTTPError:
                return
            except urllib.error.URLError as exc:
                last_error = exc
                time.sleep(0.1)
        raise RuntimeError("Verification test server did not start: {}".format(last_error))

    def get(self, path: str) -> tuple[int, dict]:
        return _request(self.opener, "GET", path)

    def post(self, path: str, payload: dict) -> tuple[int, dict]:
        return _request(self.opener, "POST", path, payload)

    def _register(self, email: str, password: str) -> None:
        status, body = self.post(
            "/api/register",
            {
                "email": email,
                "username": email.split("@")[0].replace("-", "_")[:20],
                "display_name": "Doğrulama Testi",
                "password": password,
            },
        )
        self.assertEqual(status, 200, "register failed: {}".format(body))
        self.assertTrue(body.get("ok"))
        self.assertNotIn("user", body, "unverified accounts must not be logged in")
        self.assertNotIn("csrfToken", body, "no session means no CSRF token")

    def _verify_token(self, email: str) -> str:
        outbox = self.tmp_dir / "password_reset_outbox.txt"
        lines = outbox.read_text(encoding="utf-8").splitlines()
        match = [line for line in lines if email in line]
        self.assertTrue(match, "no verification link stored for {}".format(email))
        return match[-1].split("?verify=", 1)[1].strip()

    def test_registration_login_and_verification_flow(self) -> None:
        email = _marker("verify") + "@example.test"
        password = "VerifyPass-123"
        self._register(email, password)

        status, body = self.post("/api/login", {"email": email, "password": password})
        self.assertEqual(status, 403, "unverified login must be refused: {}".format(body))

        token = self._verify_token(email)
        no_redirect = urllib.request.build_opener(_NoRedirect)
        with self.assertRaises(urllib.error.HTTPError) as context:
            no_redirect.open(self.base_url + "/?verify=" + token, timeout=REQUEST_TIMEOUT)
        self.assertEqual(context.exception.code, 302)
        self.assertEqual(context.exception.headers.get("Location"), "/?verified=1")
        context.exception.close()

        status, body = self.post("/api/login", {"email": email, "password": password})
        self.assertEqual(status, 200, "verified login failed: {}".format(body))
        self.assertTrue(body.get("csrfToken"), "login must return a CSRF token")
        status, me = self.get("/api/me")
        self.assertEqual(status, 200)
        self.assertTrue(me["user"]["emailVerified"])

    def test_invalid_verification_and_resend(self) -> None:
        email = _marker("resend") + "@example.test"
        self._register(email, "ResendPass-123")

        no_redirect = urllib.request.build_opener(_NoRedirect)
        with self.assertRaises(urllib.error.HTTPError) as context:
            no_redirect.open(self.base_url + "/?verify=not-a-real-token", timeout=REQUEST_TIMEOUT)
        self.assertEqual(context.exception.code, 302)
        self.assertEqual(context.exception.headers.get("Location"), "/?verify_failed=1")
        context.exception.close()

        status, body = self.post("/api/resend-verification", {"email": email})
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        self.assertNotIn("token", body)
        self.assertTrue(self._verify_token(email), "resend must create a fresh link")

    def test_rate_limit_on_forgot_password(self) -> None:
        for index in range(6):
            status, body = self.post(
                "/api/forgot-password", {"email": "nobody{}@example.test".format(index)}
            )
            if index < 5:
                self.assertEqual(status, 200, "early request was limited: {}".format(body))
            else:
                self.assertEqual(status, 429, "sixth request must be rate limited: {}".format(body))


class ProductionConfigTests(unittest.TestCase):
    def test_production_refuses_insecure_defaults(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ilimhalkasi-prod-") as folder:
            tmp_dir = Path(folder)
            shutil.copy2(PROJECT_ROOT / "server.py", tmp_dir / "server.py")
            shutil.copy2(PROJECT_ROOT / "scholars_data.py", tmp_dir / "scholars_data.py")
            env = os.environ.copy()
            for name in (
                "IH_ADMIN_PASSWORD",
                "ILIMHALKASI_KVKK_CONTACT",
                "ILIMHALKASI_DATA_CONTROLLER",
                "ILIMHALKASI_DB_DIR",
                "ILIMHALKASI_PRODUCTION",
                "ILIMHALKASI_REQUIRE_EMAIL_VERIFICATION",
                "ILIMHALKASI_RATE_LIMIT",
                "ILIMHALKASI_CSRF",
                "ILIMHALKASI_TRUST_PROXY",
                "COOKIE_SECURE",
                "APP_BASE_URL",
                "SMTP_HOST",
                "SMTP_PORT",
                "SMTP_USER",
                "SMTP_PASSWORD",
                "SMTP_FROM",
                "SMTP_USE_TLS",
            ):
                env.pop(name, None)
            env["ILIMHALKASI_PRODUCTION"] = "1"
            result = subprocess.run(
                [sys.executable, "server.py"],
                cwd=str(tmp_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0, "production must fail fast on defaults")
            output = result.stdout + result.stderr
            self.assertIn("IH_ADMIN_PASSWORD", output)
            self.assertIn("COOKIE_SECURE", output)

    def test_production_rejects_placeholder_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ilimhalkasi-prod-") as folder:
            tmp_dir = Path(folder)
            shutil.copy2(PROJECT_ROOT / "server.py", tmp_dir / "server.py")
            shutil.copy2(PROJECT_ROOT / "scholars_data.py", tmp_dir / "scholars_data.py")
            env = os.environ.copy()
            for name in (
                "IH_ADMIN_PASSWORD",
                "ILIMHALKASI_KVKK_CONTACT",
                "ILIMHALKASI_DATA_CONTROLLER",
                "ILIMHALKASI_DB_DIR",
                "ILIMHALKASI_PRODUCTION",
                "ILIMHALKASI_REQUIRE_EMAIL_VERIFICATION",
                "ILIMHALKASI_RATE_LIMIT",
                "ILIMHALKASI_CSRF",
                "ILIMHALKASI_TRUST_PROXY",
                "COOKIE_SECURE",
                "APP_BASE_URL",
                "SMTP_HOST",
                "SMTP_PORT",
                "SMTP_USER",
                "SMTP_PASSWORD",
                "SMTP_FROM",
                "SMTP_USE_TLS",
            ):
                env.pop(name, None)
            # Her alan dolu görünüyor ama hepsi şablon değer.
            env.update({
                "ILIMHALKASI_PRODUCTION": "1",
                "COOKIE_SECURE": "1",
                "ILIMHALKASI_DB_DIR": str(tmp_dir / "data"),
                "IH_ADMIN_PASSWORD": "DEGISTIRIN_GUC_BIR_SIFRE",
                "ILIMHALKASI_KVKK_CONTACT": "kvkk@example.com",
                "ILIMHALKASI_DATA_CONTROLLER": "İlim Halkası Derneği",
                "APP_BASE_URL": "https://ilimhalkasi.example.com",
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": "587",
                "SMTP_USER": "noreply@example.com",
                "SMTP_PASSWORD": "DEGISTIRIN_SMTP_SIFRESI",
                "SMTP_FROM": "İlim Halkası <noreply@example.com>",
                "SMTP_USE_TLS": "1",
            })
            result = subprocess.run(
                [sys.executable, "server.py"],
                cwd=str(tmp_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(result.returncode, 0, "placeholders must not pass production")
            output = result.stdout + result.stderr
            for name in (
                "IH_ADMIN_PASSWORD",
                "ILIMHALKASI_KVKK_CONTACT",
                "ILIMHALKASI_DATA_CONTROLLER",
                "APP_BASE_URL",
                "SMTP_HOST",
            ):
                self.assertIn(name, output)


if __name__ == "__main__":
    unittest.main()
