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
    "favicon.svg",
    "logo.svg",
)
DB_FILENAME = "ilimhalkasi.db"

ADMIN_EMAIL = "admin@ilimhalkasi.local"
ADMIN_PASSWORD = "k9Mq-c5gipJRP41-"  # documented in README.md
REQUEST_TIMEOUT = 5
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
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
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
    return status, body if isinstance(body, dict) else {}


# Set by the test class before any request is made.  Keeping the base URL in a
# module-level variable keeps the request helper small and avoids passing the
# port through every single call.
_CURRENT_PORT = 0


def _marker(prefix: str) -> str:
    return "smoke-{}-{}".format(prefix, uuid.uuid4().hex[:10])


class SmokeAPITests(unittest.TestCase):
    """End-to-end checks against an isolated, temporary server instance."""

    @classmethod
    def setUpClass(cls) -> None:
        global _CURRENT_PORT

        cls._tmp = tempfile.TemporaryDirectory(prefix="ilimhalkasi-smoke-")
        cls.tmp_dir = Path(cls._tmp.name)
        try:
            for filename in SOURCE_FILES:
                source = PROJECT_ROOT / filename
                if not source.is_file():
                    raise RuntimeError("Missing source file required by smoke tests: " + filename)
                shutil.copy2(source, cls.tmp_dir / filename)
            shutil.copy2(PROJECT_ROOT / DB_FILENAME, cls.tmp_dir / DB_FILENAME)

            cls.port = _free_port()
            _CURRENT_PORT = cls.port
            cls.base_url = "http://127.0.0.1:{}".format(cls.port)

            server_path = cls.tmp_dir / "server.py"
            source_text = server_path.read_text(encoding="utf-8")
            patched, count = re.subn(
                r"(?m)^PORT(?:\s*:\s*int)?\s*=\s*\d+\s*$",
                "PORT = {}".format(cls.port),
                source_text,
                count=1,
            )
            if count != 1:
                raise RuntimeError("Could not rewrite PORT in the copied server.py")
            # DB_PATH is `BASE / "ilimhalkasi.db"` and BASE is the copied file's
            # directory, so the server now necessarily uses the copied DB.
            server_path.write_text(patched, encoding="utf-8")

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["IH_ADMIN_PASSWORD"] = ADMIN_PASSWORD
            # Deterministic password-reset behaviour: always use the local
            # outbox inside the temporary directory, never a real SMTP server.
            for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_USE_TLS"):
                env.pop(name, None)
            # Enable the development reset link explicitly.  This makes the
            # admin-exclusion assertion meaningful: a normal user DOES get a
            # dev_link, while the admin account must never receive one.
            env["ILIMHALKASI_DEV_RESET_LINK"] = "1"

            cls.log_handle = (cls.tmp_dir / "server.log").open("wb")
            cls.proc = subprocess.Popen(
                [sys.executable, "server.py"],
                cwd=str(cls.tmp_dir),
                stdout=cls.log_handle,
                stderr=subprocess.STDOUT,
                env=env,
            )
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
        self.assertEqual(body["stats"], {"followers": 0, "following": 0, "circles": 0})

    def test_guest_member_actions_are_still_server_gated(self) -> None:
        status, body = self.post("/api/posts", {"text": "guest post"}, opener=self.anon_opener)
        self.assertEqual(status, 401, "anonymous post should be rejected: {}".format(body))
        self.assertEqual(body.get("error"), "Giriş yapmalısın")

        status, _ = self.get("/api/notifications", opener=self.anon_opener)
        self.assertEqual(status, 401, "anonymous notifications should be rejected")

        for path in ("/api/books", "/api/books/filters", "/api/catalog-authors"):
            status, _ = self.get(path, opener=self.anon_opener)
            self.assertEqual(status, 200, "public catalog endpoint failed: " + path)

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
        self.assertIn("Favorilerim", names, "new users should receive a favorites list")

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
            if item.get("name") == "Favorilerim"
        )
        status, body = self.post(
            "/api/lists/delete", {"list_id": favorites["id"]}, opener=opener
        )
        self.assertEqual(status, 200, "deleting favorites failed: {}".format(body))

        names = [item.get("name") for item in self.bootstrap(opener=opener).get("lists") or []]
        self.assertNotIn("Favorilerim", names, "deleted favorites list must not come back")

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

        self.assertIn("grid-template-columns: 34px minmax(0, 1fr) auto", css)
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", css)
        self.assertIn("justify-self: center;", css)
        self.assertIn("transform: translateY(-10px)", css)
        self.assertIn("bottomNavEl?.addEventListener('click'", app_js)
        self.assertIn("data-i18n-aria=\"Ne paylaşmak istersin?\"", index_html)
        self.assertIn(">Halkalar ve Meclisler<", index_html)
        self.assertIn("grid-template-columns: 86px minmax(0, 1fr)", css)
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

    def test_forgot_password_excludes_admin(self) -> None:
        status, body = self.post("/api/forgot-password", {"email": ADMIN_EMAIL}, opener=self.anon_opener)
        self.assertEqual(status, 200, "forgot-password failed: {}".format(body))
        self.assertTrue(body.get("ok"))
        self.assertNotIn("dev_link", body, "admin/system accounts must not get a reset link")

        # Positive control: an ordinary user still gets the local dev link.
        normal_opener, user = self.register_user()
        status, normal_body = self.post(
            "/api/forgot-password", {"email": user["email"]}, opener=normal_opener
        )
        self.assertEqual(status, 200)
        self.assertIn("dev_link", normal_body, "normal users should still get a reset link")

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
            'data-guest-auth-btn', 'data-member-only', 'data-i18n="Ekle"',
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

        # The old mobile rule hid every gold button's text and replaced it with ✧.
        self.assertNotIn("\n  .btn-gold { font-size: 0; }", css)
        self.assertNotIn(".btn-gold::after { content: \"✧\";", css)
        self.assertIn(".app-shell.nav-mini .sidebar .btn-gold { font-size: 0; }", css)
        self.assertIn("/* Butonlar artık metinlerini korur; sadece renk/kenarlık değişir. */", css)
        self.assertIn(".btn:hover, .btn:active, .menu-btn:active, .theme-choice:hover { transform: none; }", css)
        self.assertIn(".btn, .btn-sm, .page-head--tight .btn, .greeting-actions .btn, .sheet-actions .btn {", css)
        self.assertIn("/* Simge + yazı birlikte görünsün. */", css)
        self.assertIn(".top-actions .icon-btn,", css)
        self.assertIn(".nav-quick-label {", css)

        self.assertIn('<span data-i18n="Duyurular">Duyurular</span>', index_html)
        self.assertIn('<span data-i18n="Ara">Ara</span>', index_html)
        self.assertIn('<span data-i18n="Okundu">Okundu</span>', index_html)
        self.assertIn('<span data-i18n="Şikayet ve talepler">Şikayet ve talepler</span>', index_html)
        self.assertIn("'Duyurular':", (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8"))
        self.assertIn("'Ara':", app_js + (PROJECT_ROOT / "i18n.js").read_text(encoding="utf-8"))

        # Ana sayfadaki etiketler okunabilir boyutta olmalı; sadece simge kalmasın.
        uniform = css.split("/* ---------- Tek düzen: aynı tür kontrol her yerde aynı ölçüde ---------- */", 1)[1]
        uniform = uniform.split("/* ---------- ", 1)[0]
        for marker in (
            "font-size: 13px;",  # btn / tab
            "font-size: 12px;",  # chip / action / follow / text-btn
            ".follow-btn { font-size: 12px; min-height: 30px; }",
            ".action { font-size: 12px; }",
            ".nav-quick-label { font-size: 10px;",
        ):
            self.assertIn(marker, uniform, "missing readable label rule: " + marker)
        self.assertNotIn(".nav-quick-label { font-size: 8.5px;", css)
        self.assertNotIn(".icon-btn > span:not(.badge-count) { font-size: 9px;", css)
        nav_block = css.split(".app-shell .bottom-nav .nav-item,\n  .app-shell .bottom-nav .nav-item:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: 10px;", nav_block, "bottom nav labels are still too small")

        server_py = (PROJECT_ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('self.send_header("Cache-Control", "no-store")', server_py)
        activity = (PROJECT_ROOT / "android" / "app" / "src" / "main" / "java"
                    / "com" / "ilimhalkasi" / "app" / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("settings.setCacheMode(WebSettings.LOAD_NO_CACHE);", activity)
        self.assertIn("webView.clearCache(true);", activity)


if __name__ == "__main__":
    unittest.main()
