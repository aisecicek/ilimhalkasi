#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İlim Halkası — yerel API sunucusu.

Yalnızca Python standart kütüphanesi kullanır; ek kurulum gerekmez.
Çalıştırma:  python server.py    →    http://localhost:8765
Veritabanı:  ilimhalkasi.db (ilk açılışta otomatik oluşturulur)
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import socket
import smtplib
import sqlite3
import ssl
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scholars_data import SCHOLARS_EXTRA

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "ilimhalkasi.db"
PORT = 8765
SESSION_DAYS = 30
PBKDF2_ROUNDS = 210_000
ADMIN_EMAIL = "admin@ilimhalkasi.local"
ADMIN_USERNAME = "admin"
RESET_TTL_SECONDS = 3600
APP_BASE_URL = os.environ.get("APP_BASE_URL", f"http://localhost:{PORT}").rstrip("/")
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "") or SMTP_USER or "İlim Halkası <noreply@ilimhalkasi.local>"
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1").strip() not in ("0", "false", "False", "no")
RESET_OUTBOX = BASE / "password_reset_outbox.txt"
# Yalnızca yerel geliştirmede, e-posta olmadan sıfırlama bağlantısını yanıtta döndürür.
DEV_RESET_LINK = os.environ.get("ILIMHALKASI_DEV_RESET_LINK", "0").strip() == "1"
# Ters proxy (Caddy/Nginx) HTTPS sonlandırdığında oturum çerezini Secure yap.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0").strip().lower() in ("1", "true", "yes")

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/logo.svg": ("logo.svg", "image/svg+xml"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/fonts/amiri-400-arabic.woff2": ("fonts/amiri-400-arabic.woff2", "font/woff2"),
    "/fonts/amiri-400-latin-ext.woff2": ("fonts/amiri-400-latin-ext.woff2", "font/woff2"),
    "/fonts/amiri-400-latin.woff2": ("fonts/amiri-400-latin.woff2", "font/woff2"),
    "/fonts/amiri-700-arabic.woff2": ("fonts/amiri-700-arabic.woff2", "font/woff2"),
    "/fonts/amiri-700-latin-ext.woff2": ("fonts/amiri-700-latin-ext.woff2", "font/woff2"),
    "/fonts/amiri-700-latin.woff2": ("fonts/amiri-700-latin.woff2", "font/woff2"),
    "/fonts/el-messiri-arabic.woff2": ("fonts/el-messiri-arabic.woff2", "font/woff2"),
    "/fonts/el-messiri-latin-ext.woff2": ("fonts/el-messiri-latin-ext.woff2", "font/woff2"),
    "/fonts/el-messiri-latin.woff2": ("fonts/el-messiri-latin.woff2", "font/woff2"),
    "/fonts/lora-latin-ext.woff2": ("fonts/lora-latin-ext.woff2", "font/woff2"),
    "/fonts/lora-latin.woff2": ("fonts/lora-latin.woff2", "font/woff2"),
    "/fonts/plus-jakarta-sans-latin-ext.woff2": ("fonts/plus-jakarta-sans-latin-ext.woff2", "font/woff2"),
    "/fonts/plus-jakarta-sans-latin.woff2": ("fonts/plus-jakarta-sans-latin.woff2", "font/woff2"),
}

# ---------------------------------------------------------------------------
# Şema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
  username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  salt          TEXT NOT NULL,
  display_name  TEXT NOT NULL,
  bio           TEXT NOT NULL DEFAULT '',
  avatar        TEXT NOT NULL DEFAULT 'olive',
  avatar_image  TEXT NOT NULL DEFAULT '',
  title         TEXT NOT NULL DEFAULT 'Talebe',
  is_community  INTEGER NOT NULL DEFAULT 0,
  is_admin      INTEGER NOT NULL DEFAULT 0,
  is_system     INTEGER NOT NULL DEFAULT 0,
  blocked       INTEGER NOT NULL DEFAULT 0,
  created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
  token_hash TEXT PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS books (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT NOT NULL,
  original_title TEXT NOT NULL DEFAULT '',
  author       TEXT NOT NULL DEFAULT '',
  category     TEXT NOT NULL DEFAULT 'Genel',
  cover        TEXT NOT NULL DEFAULT '',
  isbn         TEXT NOT NULL DEFAULT '',
  description  TEXT NOT NULL DEFAULT '',
  genre        TEXT NOT NULL DEFAULT '',
  year         INTEGER,
  rating       REAL,
  rating_count INTEGER NOT NULL DEFAULT 0,
  publisher    TEXT NOT NULL DEFAULT '',
  work_key     TEXT NOT NULL DEFAULT '',
  page_count   INTEGER NOT NULL DEFAULT 0,
  volume_count INTEGER NOT NULL DEFAULT 1,
  source       TEXT NOT NULL DEFAULT 'curated',
  hidden       INTEGER NOT NULL DEFAULT 0,
  hidden_reason TEXT NOT NULL DEFAULT '',
  created_at   REAL NOT NULL,
  UNIQUE(title, author)
);

CREATE TABLE IF NOT EXISTS posts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type       TEXT NOT NULL CHECK(type IN ('quote','review')),
  book       TEXT NOT NULL,
  writer     TEXT NOT NULL DEFAULT '',
  text       TEXT NOT NULL,
  rating     INTEGER NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT '',
  cover      TEXT NOT NULL DEFAULT '',
  group_id   INTEGER REFERENCES groups(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS deleted_posts (
  id          INTEGER PRIMARY KEY,
  deleted_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS post_likes (
  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS post_favorites (
  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  parent_id  INTEGER REFERENCES comments(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS comment_likes (
  comment_id INTEGER NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (comment_id, user_id)
);

CREATE TABLE IF NOT EXISTS notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title      TEXT NOT NULL,
  book       TEXT NOT NULL,
  visibility TEXT NOT NULL CHECK(visibility IN ('private','circle','public')),
  text       TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS shelf_books (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  status     TEXT NOT NULL CHECK(status IN ('reading','finished','wishlist','abandoned')),
  page       INTEGER NOT NULL DEFAULT 0,
  progress   INTEGER NOT NULL DEFAULT 0,
  rating     INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  finished_at REAL NOT NULL DEFAULT 0,
  page_count INTEGER NOT NULL DEFAULT 0,
  volume INTEGER NOT NULL DEFAULT 1,
  UNIQUE (user_id, book_id, status)
);

CREATE TABLE IF NOT EXISTS book_lists (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  created_at REAL NOT NULL,
  UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS book_list_items (
  list_id    INTEGER NOT NULL REFERENCES book_lists(id) ON DELETE CASCADE,
  book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  PRIMARY KEY (list_id, book_id)
);

CREATE TABLE IF NOT EXISTS user_meta (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key     TEXT NOT NULL,
  value   TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (user_id, key)
);

-- Kullanıcıların katalogda olmayan bir eser için gönderdiği öneriler.
CREATE TABLE IF NOT EXISTS book_requests (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title        TEXT NOT NULL,
  author       TEXT NOT NULL DEFAULT '',
  page_count   INTEGER NOT NULL DEFAULT 0,
  about        TEXT NOT NULL DEFAULT '',
  cover        TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
  reason       TEXT NOT NULL DEFAULT '',
  book_id      INTEGER REFERENCES books(id) ON DELETE SET NULL,
  created_at   REAL NOT NULL,
  reviewed_at  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS debates (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  book_title TEXT NOT NULL,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS debate_answers (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  debate_id  INTEGER NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  is_guide   INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  circle     TEXT NOT NULL,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at REAL NOT NULL
);

-- Halka, meclis ve özel sohbetler için ortak grup modeli.
CREATE TABLE IF NOT EXISTS groups (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kind          TEXT NOT NULL CHECK(kind IN ('halka','meclis','direct')),
  name          TEXT NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  creator_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  avatar_image  TEXT NOT NULL DEFAULT '',
  avatar_color  TEXT NOT NULL DEFAULT 'olive',
  max_members   INTEGER NOT NULL DEFAULT 500,
  created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
  group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  joined_at  REAL NOT NULL,
  PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS group_messages (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
  sender_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at REAL NOT NULL
);

-- Toplu kitap aktarımında konu bazlı sayfalama durumu (devam/edilebilir).
CREATE TABLE IF NOT EXISTS book_import_progress (
  subject    TEXT PRIMARY KEY,
  "offset"   INTEGER NOT NULL DEFAULT 0,
  done       INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS follows (
  follower_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  followed_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (follower_id, followed_id)
);

-- Takip, halka paylaşımı, yorum, anma ve meclis mesajları için kalıcı bildirimler.
CREATE TABLE IF NOT EXISTS notifications (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK(kind IN ('follow','circle_post','comment','mention','group_message','like','favorite','book_request')),
  actor_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
  post_id    INTEGER REFERENCES posts(id) ON DELETE SET NULL,
  group_id   INTEGER REFERENCES groups(id) ON DELETE SET NULL,
  text       TEXT NOT NULL DEFAULT '',
  target     TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS blocks (
  blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  REAL NOT NULL,
  PRIMARY KEY (blocker_id, blocked_id)
);

CREATE TABLE IF NOT EXISTS curriculum_follows (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  c_key   TEXT NOT NULL,
  PRIMARY KEY (user_id, c_key)
);

CREATE TABLE IF NOT EXISTS assembly_rsvps (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  a_key   TEXT NOT NULL,
  PRIMARY KEY (user_id, a_key)
);

CREATE TABLE IF NOT EXISTS announcements (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  admin_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL DEFAULT 'duyuru',
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS support_tickets (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK(kind IN ('sikayet','talep')),
  subject    TEXT NOT NULL,
  body       TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open',
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_replies (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id  INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
  admin_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body       TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_reports (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reported_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason      TEXT NOT NULL,
  detail      TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'open',
  admin_reply TEXT NOT NULL DEFAULT '',
  created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scholars (
  slug          TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL DEFAULT 'alim',
  category      TEXT NOT NULL DEFAULT 'Genel',
  full_name     TEXT NOT NULL DEFAULT '',
  years         TEXT NOT NULL DEFAULT '',
  era           TEXT NOT NULL DEFAULT '',
  avatar        TEXT NOT NULL DEFAULT 'olive',
  bio           TEXT NOT NULL DEFAULT '',
  contribution  TEXT NOT NULL DEFAULT '',
  importance    TEXT NOT NULL DEFAULT '',
  books_json    TEXT NOT NULL DEFAULT '[]',
  recommended_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS scholar_comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  slug       TEXT NOT NULL REFERENCES scholars(slug) ON DELETE CASCADE,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text       TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scholar_books (
  slug       TEXT NOT NULL REFERENCES scholars(slug) ON DELETE CASCADE,
  book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK(role IN ('work','recommended')),
  PRIMARY KEY (slug, book_id, role)
);

CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
CREATE INDEX IF NOT EXISTS idx_shelf_user ON shelf_books(user_id);
CREATE INDEX IF NOT EXISTS idx_announcements_created ON announcements(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_group_messages_group ON group_messages(group_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
"""

# ---------------------------------------------------------------------------
# Sabit içerikler (örnek/kürasyonlu veri)
# ---------------------------------------------------------------------------

CIRCLES = [
    {"name": "İmam Gazali Okumaları", "desc": "Haftada birlikte okuma · herkes katılabilir", "dot": "olive"},
    {"name": "30 Günde 30 Hadis", "desc": "Her gün bir hadis · herkes katılabilir", "dot": "copper"},
    {"name": "Dostoyevski & Ahlak Felsefesi", "desc": "Ayda bir müzakere · herkes katılabilir", "dot": "gold"},
]

CURRICULA = [
    {
        "key": "c1", "title": "Temel Akaide Giriş Müfredatı", "guide": "İlim Halkası", "guide_slug": "ilim-halkasi-akaid",
        "guideTitle": "Kürasyon · Kelam ve İtikad", "avatar": "olive",
        "meta": "3 ay · 6 eser · 214 takipçi",
        "desc": "İman esaslarını kaynağından ve sırayla öğrenmek isteyenler için yapılandırılmış bir yol.",
        "steps": ["Tezveren (giriş bölümleri)", "İlcamü’l-Avam",
                  "Sahih-i Buhari — İman Kitabı", "Şerhu’l-Akide"],
    },
    {
        "key": "c2", "title": "Siyer Okumalarına Başlangıç: 5 Temel Eser", "guide": "İlim Halkası", "guide_slug": "ilim-halkasi-siyer",
        "guideTitle": "Kürasyon · Siyer ve Tarih", "avatar": "copper",
        "meta": "2 ay · 5 eser · 389 takipçi",
        "desc": "Siyer-i Nebi’ye farklı açılardan yaklaşan, kronolojik ilerleyen bir okuma rotası.",
        "steps": ["Siyer-i Nebi (muhtasar)", "El-Bidaye ve’n-Nihaye (seçmeler)",
                  "İslam Peygamberi", "İnsanü’l-Ayn"],
    },
    {
        "key": "c3", "title": "Klasik Eserler", "guide": "İlim Halkası", "guide_slug": "ilim-halkasi",
        "guideTitle": "Kürasyon · Klasik Eserler", "avatar": "olive",
        "meta": "3 ay · 5 eser · 214 takipçi",
        "desc": "Dünya edebiyatının en çok okunan beş eseri; dostluk, umut, adalet ve insanın iç dünyası üzerine.",
        "steps": ["Fareler ve İnsanlar", "Hayvan Çiftliği",
                  "Şeker Portakalı (José Mauro de Vasconcelos)", "Satranç (Stefan Zweig)",
                  "Beyaz Diş (Jack London)"],
    },
]

_TR_FOLD = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s",
                          "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
                          "ö": "o", "Ö": "o", "ç": "c", "Ç": "c"})


def normalize_book_title(value) -> str:
    """Kitap adını müfredat adımlarıyla eşleştirmek için sadeleştirir."""
    text = re.sub(r"\s*\([^)]*\)", "", str(value or ""))
    text = re.split(r"\s+[—–-]\s+", text)[0]
    text = unicodedata.normalize("NFKD", text.casefold().translate(_TR_FOLD))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def find_curriculum_book(conn: sqlite3.Connection, raw_title: str) -> dict | None:
    needle = normalize_book_title(raw_title)
    if not needle:
        return None
    for row in conn.execute("SELECT * FROM books WHERE hidden=0"):
        if normalize_book_title(row["title"]) == needle:
            return dict(row)
    words = needle.split()
    if len(words) >= 2:
        prefix = " ".join(words[:2]) + "%"
        for row in conn.execute(
            "SELECT * FROM books WHERE hidden=0 AND lower(title) LIKE ? LIMIT 1", (prefix.lower(),)
        ):
            return dict(row)
    return None


def curriculum_step_label(raw_title: str, book: dict | None) -> str:
    """Çözülen adımlarda 'Başlık - Yazar' biçimini tutarlı biçimde kullanır."""
    if book and book.get("author"):
        title = re.sub(r"\s*\([^)]*\)", "", str(book.get("title") or "")).strip()
        return f"{title} - {book['author']}".strip()
    return re.sub(r"\s*\([^)]*\)\s*$", "", str(raw_title or "")).strip()


def curriculum_with_progress(conn: sqlite3.Connection, user_id: int, curriculum: dict) -> dict:
    followed = conn.execute(
        "SELECT 1 FROM curriculum_follows WHERE user_id=? AND c_key=?",
        (user_id, curriculum["key"]),
    ).fetchone() is not None
    shelf_rows = conn.execute(
        "SELECT * FROM shelf_books WHERE user_id=?", (user_id,)
    ).fetchall()
    by_book: dict[int, list[sqlite3.Row]] = {}
    for row in shelf_rows:
        by_book.setdefault(row["book_id"], []).append(row)

    steps = []
    for index, raw in enumerate(curriculum.get("steps", [])):
        book = find_curriculum_book(conn, raw)
        row = None
        if book:
            candidates = by_book.get(book["id"], [])
            rank = {"reading": 0, "finished": 1, "wishlist": 2, "abandoned": 3}
            row = sorted(candidates, key=lambda r: rank.get(r["status"], 9))[0] if candidates else None
        pct = int(row["progress"] or 0) if row else 0
        if row and row["status"] == "finished":
            pct = 100
        steps.append({
            "index": index,
            "raw": raw,
            "label": curriculum_step_label(raw, book),
            "book_id": book["id"] if book else None,
            "book": ({
                "id": book["id"], "title": book["title"], "author": book.get("author", ""),
                "cover": book.get("cover", ""), "page_count": int(book.get("page_count") or 0),
                "volume_count": int(book.get("volume_count") or 1),
            } if book else None),
            "status": row["status"] if row else "",
            "page": int(row["page"] or 0) if row else 0,
            "volume": int(row["volume"] or 1) if row else 1,
            "pct": max(0, min(100, pct)),
        })
    total = len(steps)
    completed = sum(1 for step in steps if step["status"] == "finished")
    average = round(sum(step["pct"] for step in steps) / total) if total else 0
    return {
        **curriculum,
        "steps": steps,
        "followed": followed,
        "progress": {"completed": completed, "total": total, "pct": average},
    }


FIGURE_ACCOUNTS = [
    {
        "email": "hzali@figures.ilimhalkasi.local",
        "username": "hzali",
        "display_name": "Hz. Ali (r.a.)",
        "bio": "İlim, adalet ve hikmet sözleriyle anılan İslam'ın dördüncü halifesi.",
        "avatar": "olive",
        "title": "Rehber",
        "quotes": [
            ("Nehcü'l-Belâğa", "İlim, seni korur; malı ise sen korursun."),
            ("Nehcü'l-Belâğa", "İnsanların en hayırlısı, insanlara faydalı olandır."),
            ("Nehcü'l-Belâğa", "Konuşmadan önce sözünü tart; çünkü insan dilinin altında gizlidir."),
            ("Nehcü'l-Belâğa", "Sabır iki türlüdür: Hoşlanmadığın şeye sabretmek ve hoşlandığından kendini alıkoymak."),
            ("Nehcü'l-Belâğa", "Kişinin değeri, yapmayı bildiği işlerdedir."),
            ("Nehcü'l-Belâğa", "Öfkeni yenersen, o senin esirin olur; yenemezsen sen onun esiri olursun."),
            ("Nehcü'l-Belâğa", "Nefsini tanıyan Rabbini tanır."),
            ("Nehcü'l-Belâğa", "Düşmanının kötülüğünden sakınmak için dostunun iyiliğini artır."),
            ("Nehcü'l-Belâğa", "İnsan, dili altında gizlidir."),
            ("Nehcü'l-Belâğa", "Kalpler ancak kendilerine sevgiyle davranıldığında ısınır."),
            ("Nehcü'l-Belâğa", "Bugün ilim öğren, yarın onunla amel et."),
            ("Nehcü'l-Belâğa", "Güzel ahlak, en güzel mirastır."),
        ],
    },
    {
        "email": "dostoyevski@figures.ilimhalkasi.local",
        "username": "dostoyevski",
        "display_name": "Fyodor Dostoyevski",
        "bio": "İnsanın vicdanını, acısını ve umudunu derinlikli romanlarıyla anlatan Rus yazar.",
        "avatar": "copper",
        "title": "Yazar",
        "quotes": [
            ("Suç ve Ceza", "Acı çekmek ve ıştırap duymak, her zaman geniş bir şuur ve derin bir kalp için kaçınılmazdır."),
            ("Karamazov Kardeşler", "İnsanları sevmek, onlardan uzakta durmayı öğrenmekle başlar."),
            ("İnsancıklar", "Dünya güzeldir, hatta acılar içinde bile."),
            ("Karamazov Kardeşler", "Herkes herkesten her şeyden sorumludur."),
            ("Suç ve Ceza", "Dünyada hiçbir şey, insanın kendini kandırmasından daha zor değildir."),
            ("Yeraltından Notlar", "Acı, şuurun tek nedenidir."),
            ("Budala", "Güzellik dünyayı kurtaracaktır."),
            ("Karamazov Kardeşler", "Cehalet korkunç bir şeydir ama bilgeliğin getirdiği yalnızlık da öyledir."),
            ("Suç ve Ceza", "İnsanı insan yapan, düştükten sonra kalkabilme gücüdür."),
            ("Karamazov Kardeşler", "Kalbini temiz tut; çünkü dünyayı ancak temiz bir kalp doğru görebilir."),
            ("İnsancıklar", "Merhamet, insan ruhunun en yüce ifadesidir."),
            ("Ecinniler", "Doğruyu aramak, bazen karanlıkta yürümeyi göze almaktır."),
        ],
    },
    {
        "email": "imamgazali@figures.ilimhalkasi.local",
        "username": "imamgazali",
        "display_name": "İmam Gazali",
        "bio": "İlim ile kalp terbiyesini birleştiren, İslam düşüncesinin büyük âlimi.",
        "avatar": "sand",
        "title": "Rehber",
        "quotes": [
            ("İhyau Ulumi'd-Din", "İlim bir ağaç, amel ise onun meyvesidir."),
            ("İhyau Ulumi'd-Din", "Kalp, ilmin aynasıdır; onu kötü huylardan arındırmayan, ilmin nurunu göremez."),
            ("Kimyâ-yı Saâdet", "İnsanın asıl zenginliği, gönül zenginliğidir."),
            ("İhyau Ulumi'd-Din", "Nefsini bilen, Rabbini bilmeye giden yolu bulur."),
            ("Kimyâ-yı Saâdet", "Konuşmadan önce düşün; söz, geri alınmaz bir oktur."),
            ("İhyau Ulumi'd-Din", "Amelsiz ilim, yapraksız ağaç gibidir."),
            ("İhyau Ulumi'd-Din", "İnsan, bildiğiyle amel etmeye başladığında gerçek ilme yaklaşır."),
            ("Kimyâ-yı Saâdet", "Dünya bir köprüdür; onu yurt edinme, üzerinden geç."),
            ("İhyau Ulumi'd-Din", "Mücadele edilmeden terbiye edilmemiş bir nefis, sahibini yanıltır."),
            ("Kimyâ-yı Saâdet", "Sükût, çoğu zaman en güzel cevaptır."),
            ("İhyau Ulumi'd-Din", "Kardeşinin ayıbını ört; çünkü sen de örtülmeye muhtaçsın."),
            ("İhyau Ulumi'd-Din", "Hikmet, kaybolmuş müminin malıdır; nerede bulursa alır."),
        ],
    },
    {
        "email": "mevlana@figures.ilimhalkasi.local",
        "username": "mevlana",
        "display_name": "Mevlânâ Celâleddîn-i Rûmî",
        "bio": "Sevgi, sabır ve hoşgörü öğretisiyle yüzyıllardır okunan sûfî ve şair.",
        "avatar": "gold",
        "title": "Şair",
        "quotes": [
            ("Mesnevî", "Gel, ne olursan ol yine gel."),
            ("Mesnevî", "Dün dünde kaldı cancağızım, bugün yeni şeyler söylemek lazım."),
            ("Mesnevî", "Yara, ışığın sana girdiği yerdir."),
            ("Mesnevî", "Sabır acıdır, ama meyvesi tatlıdır."),
            ("Mesnevî", "Gönül, kırılınca değil, kırılınca da sevebilince büyür."),
            ("Dîvân-ı Kebîr", "Başkalarının kusurunu örtenin kusurunu Allah örter."),
            ("Mesnevî", "Ya olduğun gibi görün, ya göründüğün gibi ol."),
            ("Dîvân-ı Kebîr", "Sevgi, aklın sustuğu yerde başlar."),
            ("Mesnevî", "Suya yazılan yazı değil, kalbe yazılan söz kalıcıdır."),
            ("Mesnevî", "Mum olmak kolay değildir; ışık saçmak için önce yanmak gerekir."),
            ("Dîvân-ı Kebîr", "Her gün bir yerden göçmek ne iyi; her gün bir yere konmak ne güzel."),
            ("Mesnevî", "İçindeki sesi dinle; hakikat çoğu zaman orada fısıldar."),
        ],
    },
    {
        "email": "yunusemre@figures.ilimhalkasi.local",
        "username": "yunusemre",
        "display_name": "Yunus Emre",
        "bio": "Sade diliyle sevgi, kardeşlik ve insanı anlatan Anadolu sûfî şairi.",
        "avatar": "rose",
        "title": "Şair",
        "quotes": [
            ("Divan", "Yaradılanı hoş gör, Yaradan’dan ötürü."),
            ("Divan", "Sevelim sevilelim, dünya kimseye kalmaz."),
            ("Divan", "Söz ola kese savaşı, söz ola kestire başı; söz ola ağulu aşı, yağ ile bal ede bir söz."),
            ("Divan", "Bir kez gönül yıktın ise, bu kıldığın namaz değil."),
            ("Divan", "İlim ilim bilmektir, ilim kendin bilmektir."),
            ("Risaletü'n-Nushiyye", "Gönül Çalab’ın tahtı, Çalab gönüle baktı."),
            ("Divan", "Dost yüzüne bakmağa, bir dem yetmez bin yıl gerek."),
            ("Divan", "Miskin Yunus biçareyim, baştan ayağa yareyim; dost ilinden avareyim, gel gör beni aşk neyledi."),
            ("Divan", "Her ne arar isen kendinde ara."),
            ("Divan", "Cümle yaratılanlara bir göz ile bakmayan, halka müderris olsa hakikatte âsidir."),
            ("Divan", "Aşkın aldı benden beni, bana seni gerek seni."),
            ("Divan", "Biz dünyadan gider olduk, kalanlara selam olsun."),
        ],
    },
]

SCHOLARS = [
    {
        "slug": "imam-gazali", "name": "İmam Gazali", "full_name": "Ebu Hamid Muhammed bin Muhammed el-Gazali",
        "years": "1058 – 1111", "era": "Selçuklu dönemi · Horasan", "avatar": "olive",
        "bio": "İslam düşüncesinin en güçlü kalemlerinden biri. Gençliğinde felsefe ve kelamı derinlemesine öğrendi; bir iç buhranın ardından ilmi, kalbin terbiyesiyle birleştiren bir yola yöneldi.",
        "contribution": "Felsefi eleştirisiyle meşhur olsa da asıl eseri İhyau Ulumi’d-Din, ibadetin iç yüzünü, ahlakı ve kalbin hastalıklarını işleyen dev bir ansiklopedidir.",
        "importance": "İlimle ameli birbirinden ayırmayan anlayışı, yüzyıllar boyunca medrese geleneğinin ahlaki yönünü belirledi. Öğrencileri arasında pek çok âlim yetişti.",
        "books": ["İhyau Ulumi’d-Din", "İlcamü’l-Avam", "Mizanu’l-Amel", "Tahafüte’l-Felasife", "el-Munkizu min ed-Dalal"],
        "recommended": ["Sahih-i Buhari", "Tezveren", "Mesnevi", "Küçük Prens"],
    },
    {
        "slug": "imam-maturidi", "name": "İmam Maturidi", "full_name": "Ebu Mansur Muhammed bin Mahmud el-Maturudi",
        "years": "y. 852 – 944", "era": "Semerkant · Maveraünnehir", "avatar": "sand",
        "bio": "Hanefi kelamının kurucu isimlerinden. Aklı vahyin hizmetinde kullanmayı savundu; imanın mahiyeti ve Allah’ın sıfatları üzerine sistematik bir ekol oluşturdu.",
        "contribution": "Tezveren (Kitabü’t-Tevhid) adlı eseri, akaid meselelerini delilleriyle birlikte ele alan en erken sistematik metinlerden biridir.",
        "importance": "Maturidîlik, Hanefi mezhebinin itikadî temeli olarak Anadolu’da geniş kabul gördü; âlim yetiştiren medreselerde temel kaynak oldu.",
        "books": ["Tezveren", "Şerhu’l-Fıkhu’l-Ekber", "Ta’vilatu’l-Kur’an"],
        "recommended": ["İmam Gazali — İlcamü’l-Avam", "Sahih-i Buhari", "Felsefe"],
    },
    {
        "slug": "ibn-hisam", "name": "İbn Hişam", "full_name": "Ebu Muhammed Abdurrahman bin Abdillah el-Himyari",
        "years": "ö. 833", "era": "Medine · Abbasi dönemi", "avatar": "copper",
        "bio": "Siyer geleneğinin en meşhur aktarıcısı. Peygamberimiz’in hayatını, seferlerini ve savaşlarını kronolojik bir bütünlükle derledi.",
        "contribution": "Siyer-i Nebi, İbn İshak’ın rivayetlerini düzenleyip genişleterek bugün elimizdeki klasik siyer metninin ana çatısını oluşturdu.",
        "importance": "Siyer okumak isteyen herkesin ilk durağı hâlâ bu eserdir; Hudeybiye, Bedir ve Uhud anlatıları nesiller boyu buradan okundu.",
        "books": ["Siyer-i Nebi", "el-Ağani (derleme katkısı)"],
        "recommended": ["İbn Kesir — El-Bidaye ve’n-Nihaye", "Sahih-i Buhari", "Muhammed Hamidullah — İslam Peygamberi"],
    },
    {
        "slug": "ibn-kesir", "name": "İbn Kesir", "full_name": "Ebu’l-Fida İsmail bin Ömer ed-Dimaşki",
        "years": "1301 – 1374", "era": "Şam · Memlük dönemi", "avatar": "rose",
        "bio": "Tefsir, tarih ve hadis alanlarında çalışan çok yönlü bir âlim. İbn Teymiyye’nin öğrencisi, İbnü’l-Kesir olarak da bilinir.",
        "contribution": "El-Bidaye ve’n-Nihaye, yaratılıştan kıyamete kadar uzanan kronolojik bir tarih eseridir; Tefsirü’l-Kur’an ise oldukça okunan bir tefsirdir.",
        "importance": "Tarihi rivayetleri tek çatı altında toplaması, siyer ve İslam tarihi çalışmalarının vazgeçilmez kaynaklarından biri olmasını sağladı.",
        "books": ["El-Bidaye ve’n-Nihaye", "Tefsirü’l-Kur’an", "El-Fikru’l-Hadis"],
        "recommended": ["Siyer-i Nebi", "Sahih-i Buhari", "Tutunamayanlar"],
    },
    {
        "slug": "mevlana", "name": "Mevlana", "full_name": "Celaleddin Rumi",
        "years": "1207 – 1273", "era": "Konya · Selçuklu Anadolusu", "avatar": "gold",
        "bio": "Şair, âlim ve sufî. Farsça yazdığı Mesnevi ile tasavvufun en tanınan seslerinden biri oldu; Tilavet ve sema onun yolunda özel bir yer tutar.",
        "contribution": "Mesnevi, hikâyeler içinde ahlak ve kalb terbiyesini işler; 25 bin beyitlik bu eser 'İkinci Kur’an' diye de anılmıştır.",
        "importance": "Anadolu’nun manevi iklimini şekillendirdi; Gazali’nin ilim ile amel vurgusunu şiir ve hikâyeyle tamamladı.",
        "books": ["Mesnevi", "Divan-ı Kebir", "Mektubat"],
        "recommended": ["İhyau Ulumi’d-Din", "Fususu’l-Hikem (şerhle)", "Sofie’nin Dünyası"],
    },
    {
        "slug": "ibn-arabi", "name": "İbnü’l-Arabi", "full_name": "Ebu Bekir Muhammed bin Ali el-Hatmi et-Taî",
        "years": "1165 – 1240", "era": "Endülüs · Selçuklu ve Eyyubi dönemi", "avatar": "ink",
        "bio": "Tasavvuf metafiziğinin en derin isimlerinden. 'Vahdet-i vücud' tartışmalarının merkezinde yer alan eserler kaleme aldı.",
        "contribution": "Fususu’l-Hikem ve Futuhâtu’l-Mekkiyye, varlık ve bilgi anlayışını sembolik bir dille işler; şerh geleneği yüzyıllar sürmüştür.",
        "importance": "Sonraki yüzyıllarda tasavvuf düşüncesinin hem hayranlık hem eleştiriyle okunan en etkili kaynağı oldu.",
        "books": ["Fususu’l-Hikem", "Futuhâtu’l-Mekkiyye", "Divan"],
        "recommended": ["Mesnevi", "İhyau Ulumi’d-Din", "Tezveren"],
    },
    {
        "slug": "imam-buhari", "name": "İmam Buhari", "kind": "alim",
        "full_name": "Ebu Abdullah Muhammed bin İsmail el-Buhari", "years": "810 – 870",
        "era": "Buhara · Abbasi dönemi", "avatar": "sand",
        "bio": "Hadis ilminin en meşhur ismi. Sahih adlı eserini on yıllık bir titizlikle derledi; rivayet zincirlerini ve râvîlerin güvenilirliğini ölçüt aldı.",
        "contribution": "Sahih-i Buhari, akîde ve fıkıh delillerinin en sağlam kaynaklarından biri olarak kabul edilir. Ayrıca tarih ve tefsir alanında eserleri vardır.",
        "importance": "Müslümanlar için Kur’an’dan sonra en güvenilir yazılı kaynaklardan biri olması, onu ilim meclislerinin vazgeçilmez rehberi yapmıştır.",
        "books": ["Sahih-i Buhari", "el-Edebu’l-Müfred", "et-Tarihu’l-Kebir"],
        "recommended": ["Sahih-i Müslim", "Tezveren", "İhyau Ulumi’d-Din"],
    },
    {
        "slug": "imam-muslim", "name": "İmam Müslim", "kind": "alim",
        "full_name": "Ebu’l-Hüseyin Müslim bin el-Haccac en-Nişaburi", "years": "821 – 875",
        "era": "Nişabur · Abbasi dönemi", "avatar": "olive",
        "bio": "Buhari’den sonra hadis derlemesinin en önemli isimlerinden. Rivayetleri konu ve zincir yönünden sınıflandırarak okuru kolaylaştıran bir yöntem izledi.",
        "contribution": "Sahih-i Müslim, Buhari ile birlikte 'iki sahih' olarak anılır; hadis metinlerinin düzeni ve tekrarlardan kaçınma konusunda örnek alınmıştır.",
        "importance": "İki sahih arasındaki farkları inceleyen çalışmalar, hadis usulünün gelişmesinde belirleyici olmuştur.",
        "books": ["Sahih-i Müslim", "el-Künya ve’l-Esmā"],
        "recommended": ["Sahih-i Buhari", "İmam Nevevi — Şerhu Sahih-i Müslim", "Tezveren"],
    },
    {
        "slug": "imam-ebu-hanife", "name": "İmam Ebu Hanife", "kind": "alim",
        "full_name": "Ebu Hanife Nu’man bin Sabit", "years": "699 – 767",
        "era": "Kufe · Emevi ve Abbasi dönemi", "avatar": "copper",
        "bio": "Hanefi mezhebinin kurucusu. Akıl ile nakli birlikte kullanan yaklaşımıyla fıkıh düşüncesinde yeni bir çığır açtı.",
        "contribution": "Kıyas ve içtihadı sistemleştirdi; öğrencileri aracılığıyla mezhebi geniş coğrafyalara taşındı. Anadolu’da yaygın olan fıkıh anlayışının temelidir.",
        "importance": "Fıkhın bir ezber değil, yaşayan bir düşünce disiplini olduğunu göstermesi bakımından önemlidir.",
        "books": ["el-Mebsut (rivayet)", "Kitabü’l-Âlim ve’l-Müteallim"],
        "recommended": ["Tezveren", "Sahih-i Buhari", "İmam Maturidi — Tezveren"],
    },
    {
        "slug": "imam-safii", "name": "İmam Şafii", "kind": "alim",
        "full_name": "Ebu Abdullah Muhammed bin İdris eş-Şafii", "years": "767 – 820",
        "era": "Mekke · Abbasi dönemi", "avatar": "rose",
        "bio": "Hadis, fıkıh ve usul alanlarında derin iz bırakan âlim. Rivayet ile akıl arasındaki dengeyi sistematik bir usule bağladı.",
        "contribution": "er-Risale adlı eseri, hadis usulünün ilk sistematik metinlerinden biridir; Şafii mezhebinin temelini oluşturdu.",
        "importance": "Usul düşüncesini disiplin haline getirmesi, sonraki bütün mezhep çalışmalarını etkilemiştir.",
        "books": ["er-Risale", "el-Umm", "Müsnedü’ş-Şafii"],
        "recommended": ["Sahih-i Buhari", "Tezveren", "İhyau Ulumi’d-Din"],
    },
    {
        "slug": "imam-malik", "name": "İmam Malik", "kind": "alim",
        "full_name": "Ebu Abdullah Malik bin Enes el-Asbahi", "years": "711 – 795",
        "era": "Medine · Emevi ve Abbasi dönemi", "avatar": "gold",
        "bio": "Maliki mezhebinin kurucusu. Medine’nin yaşayan sünnetini esas alan yaklaşımıyla tanınır.",
        "contribution": "el-Muvatta, hadis ve fıkhı bir araya getiren en erken düzenli eserlerden biridir.",
        "importance": "Medine uygulamasını delil sayan anlayışı, İslam hukukunda önemli bir ekolün doğmasını sağladı.",
        "books": ["el-Muvatta", "el-Medhale"],
        "recommended": ["Sahih-i Buhari", "Siyer-i Nebi", "Tezveren"],
    },
    {
        "slug": "imam-ahmed-bin-hanbel", "name": "İmam Ahmed bin Hanbel", "kind": "alim",
        "full_name": "Ebu Abdullah Ahmed bin Muhammed bin Hanbel", "years": "780 – 855",
        "era": "Bağdat · Abbasi dönemi", "avatar": "ink",
        "bio": "Hanbeli mezhebinin kurucusu. Hadis rivayetindeki titizliği ve zorluk karşısındaki duruşuyla tanınır.",
        "contribution": "el-Müsned, hacimli bir hadis derlemesidir; râvî ve metin yönünden geniş bir malzeme sunar.",
        "importance": "Hadise bağlılığı ve bağımsız içtihad anlayışı sonraki âlimler üzerinde derin etki bıraktı.",
        "books": ["el-Müsned", "Kitabü’s-Sünne"],
        "recommended": ["Sahih-i Buhari", "Sahih-i Müslim", "İbn Teymiyye — Kitaplar"],
    },
    {
        "slug": "imam-tirmizi", "name": "İmam Tirmizi", "kind": "alim",
        "full_name": "Ebu İsa Muhammed bin İsa et-Tirmizi", "years": "824 – 892",
        "era": "Tirmiz · Abbasi dönemi", "avatar": "sand",
        "bio": "Sunen sahibi, hadis ve fıkıh âlimi. Rivayetleri derecelendirme konusundaki çalışmalarıyla bilinir.",
        "contribution": "el-Camiu’s-Sahih (Sunenü’t-Tirmizi), hadislerin sahihlik derecelerini de bildiren özel bir derlemedir.",
        "importance": "Hadis usulünde 'hasen' kavramının sistematik kullanımı onunla yaygınlaştı.",
        "books": ["Sunenü’t-Tirmizi", "Şemailü’n-Nebi"],
        "recommended": ["Sahih-i Buhari", "Siyer-i Nebi", "Tezveren"],
    },
    {
        "slug": "ebu-davud", "name": "Ebu Davud", "kind": "alim",
        "full_name": "Ebu Davud Süleyman bin el-Eş’as es-Sicistani", "years": "817 – 889",
        "era": "Basra · Abbasi dönemi", "avatar": "olive",
        "bio": "Hadis ve fıkıh âlimi. Özellikle hüküm bildiren rivayetleri bir araya getirmesiyle tanınır.",
        "contribution": "Sunenü Ebi Davud, fıkhî meselelerde delil arayanlar için temel başvuru kaynaklarından biridir.",
        "importance": "Hadisleri konulara göre düzenleyip zayıf olanlarını ayırt etmesi, uygulamacıya yol göstermiştir.",
        "books": ["Sunenü Ebi Davud", "Kitabü’l-Merasil"],
        "recommended": ["Sahih-i Buhari", "Sunenü’t-Tirmizi", "Tezveren"],
    },
    {
        "slug": "ibn-mace", "name": "İbn Mace", "kind": "alim",
        "full_name": "Ebu Abdullah Muhammed bin Yezid İbn Mace", "years": "824 – 887",
        "era": "Kazvin · Abbasi dönemi", "avatar": "copper",
        "bio": "Hadis âlimi. 'Altı kitap' olarak anılan en meşhur hadis derlemelerinden birini oluşturdu.",
        "contribution": "Sunenü İbn Mace, diğer sunenleri tamamlayan rivayetleri içerir.",
        "importance": "Altı hadis kitabı arasında yer alması, onu medrese müfredatında kalıcı kılmıştır.",
        "books": ["Sunenü İbn Mace"],
        "recommended": ["Sahih-i Buhari", "Sahih-i Müslim", "Sunenü Ebi Davud"],
    },
    {
        "slug": "imam-nesai", "name": "İmam Nesai", "kind": "alim",
        "full_name": "Ebu Abdurrahman Ahmed bin Şuayb en-Nesai", "years": "829 – 915",
        "era": "Nesaf · Abbasi dönemi", "avatar": "rose",
        "bio": "Hadis âlimi; rivayetleri sadeleştirme ve ayıklama konusundaki titizliğiyle bilinir.",
        "contribution": "Sunenü’n-Nesai, hadis metinlerinin dili ve sıralanışı bakımından okunması kolay derlemelerdendir.",
        "importance": "Râvî tenkidi ve metin analizindeki hassasiyeti sonraki hadisçilere örnek oldu.",
        "books": ["Sunenü’n-Nesai", "el-Hasais"],
        "recommended": ["Sahih-i Buhari", "Sahih-i Müslim", "Tezveren"],
    },
    {
        "slug": "ibn-ishak", "name": "İbn İshak", "kind": "alim",
        "full_name": "Ebu Abdullah Muhammed bin İshak", "years": "704 – 761",
        "era": "Medine · Emevi dönemi", "avatar": "sand",
        "bio": "Siyer geleneğinin ilk büyük isimlerinden. Peygamber’in hayatını derleyen erken bir eser kaleme aldı.",
        "contribution": "Kitabü’s-Siyer, İbn Hişam başta olmak üzere sonraki siyer yazarlarının ana kaynağı oldu.",
        "importance": "Siyer yazıcılığının bir ilim dalı olarak şekillenmesinde öncü rol oynadı.",
        "books": ["Kitabü’s-Siyer", "el-Mağazi"],
        "recommended": ["Siyer-i Nebi", "Sahih-i Buhari", "Muhammed Hamidullah — İslam Peygamberi"],
    },
    {
        "slug": "taberi", "name": "Taberi", "kind": "alim",
        "full_name": "Ebu Cafer Muhammed bin Cerir et-Taberi", "years": "839 – 923",
        "era": "Amul / Bağdat · Abbasi dönemi", "avatar": "ink",
        "bio": "Tefsir, tarih ve fıkıh alanlarında çalışan çok yönlü bir âlim. Rivayetleri geniş bir yelpazede bir araya getirdi.",
        "contribution": "Camiu’l-Beyan tefsiri ve Tarihu’r-Rusul ve’l-Muluk adlı eseri, İslam düşüncesinin en geniş kaynaklarındandır.",
        "importance": "Farklı görüşleri aktarma konusundaki tarafsız tutumu, sonraki çalışmalar için güvenilir bir zemin hazırladı.",
        "books": ["Camiu’l-Beyan", "Tarihu’r-Rusul ve’l-Muluk"],
        "recommended": ["Tefsirü’l-Kur’an", "El-Bidaye ve’n-Nihaye", "Siyer-i Nebi"],
    },
    {
        "slug": "imam-nevevi", "name": "İmam Nevevi", "kind": "alim",
        "full_name": "Ebu Zekeriya Yahya bin Şeref en-Nevevi", "years": "1233 – 1277",
        "era": "Şam · Memlük dönemi", "avatar": "olive",
        "bio": "Hadis, fıkıh ve ahlak âlimi. Sade ve öğretici üslubuyla tanınan eserler yazdı.",
        "contribution": "Sahih-i Müslim şerhi, Kırk Hadis ve el-Erbaun gibi eserleri hadis öğreniminin vazgeçilmezleri arasındadır.",
        "importance": "İlim ile ameli birleştiren ahlaki vurgusu, ilim talebelerinin yetişmesinde büyük rol oynadı.",
        "books": ["Şerhu Sahih-i Müslim", "Kırk Hadis", "Riyazu’s-Salihin"],
        "recommended": ["Sahih-i Müslim", "Sahih-i Buhari", "İhyau Ulumi’d-Din"],
    },
    {
        "slug": "fahreddin-er-razi", "name": "Fahreddin er-Razi", "kind": "alim",
        "full_name": "Ebu Abdullah Muhammed bin Ömer er-Razi", "years": "1149 – 1209",
        "era": "Rey / Herat · Selçuklu dönemi", "avatar": "copper",
        "bio": "Tefsir, kelam, felsefe ve tıp alanlarında eser veren ansiklopedik bir âlim.",
        "contribution": "Mefatihu’l-Gayb adlı tefsiri, ayetleri akıl ve ilimlerle ilişkilendiren geniş bir yorum geleneği kurdu.",
        "importance": "Kelamı felsefi argümanlarla zenginleştirmesi, medrese düşüncesinde yeni bir tartışma alanı açtı.",
        "books": ["Mefatihu’l-Gayb", "el-Mahsul", "Kitabü’l-Mesail"],
        "recommended": ["Tezveren", "Tefsirü’l-Kur’an", "İhyau Ulumi’d-Din"],
    },
    {
        "slug": "ibn-teymiyye", "name": "İbn Teymiyye", "kind": "alim",
        "full_name": "Takiyyüddin Ahmed bin İbn Teymiyye", "years": "1263 – 1328",
        "era": "Şam · Memlük dönemi", "avatar": "ink",
        "bio": "Fıkıh, hadis ve kelam alanlarında çalışan, görüşleriyle geniş tartışma yaratan bir âlim.",
        "contribution": "Delile dönüş vurgusu ve mezhep taassubuna karşı duruşu, birçok öğrenci yetiştirdi; İbnü’l-Kayyim onun en tanınmış talebesidir.",
        "importance": "Fikirleri sonraki yüzyıllarda farklı coğrafyalarda yeniden okulmuş ve tartışılmıştır.",
        "books": ["Kitabü’l-Fetava", "Der’u Teâruzi’l-Akl ve’n-Nakl"],
        "recommended": ["İbnü’l-Kayyim — Zadü’l-Maad", "Sahih-i Buhari", "El-Bidaye ve’n-Nihaye"],
    },
    {
        "slug": "ibnu-l-kayyim", "name": "İbnü’l-Kayyim", "kind": "alim",
        "full_name": "Ebu Bekir Şemsüddin Muhammed bin Ebu Bekir el-Cevziyye", "years": "1292 – 1350",
        "era": "Şam · Memlük dönemi", "avatar": "sand",
        "bio": "İbn Teymiyye’nin öğrencisi; fıkıh, siyer ve kalb terbiyesi üzerine eserler verdi.",
        "contribution": "Zadü’l-Maad siyeri ibadet ve ahlakla birleştiren bir okuma sunar; ahlaki eserleri geniş okur kitlesine ulaştı.",
        "importance": "Kalbin hastalıkları ve ilaçları üzerine yazdıkları, tasavvuf ile şeriat ölçüsünü bir arada arayan okurlara hitap eder.",
        "books": ["Zadü’l-Maad", "Medaricu’s-Salikin", "el-Cevabu’l-Kafi"],
        "recommended": ["Siyer-i Nebi", "İhyau Ulumi’d-Din", "Sahih-i Buhari"],
    },
    {
        "slug": "ibn-haldun", "name": "İbn Haldun", "kind": "alim",
        "full_name": "Ebu Zeyde Abdurrahman bin Haldun", "years": "1332 – 1406",
        "era": "Tunus / Kahire · Memlük dönemi", "avatar": "gold",
        "bio": "Tarihçi ve sosyolog. Toplumların doğuşu, gelişimi ve çöküşünü inceleyen bir yöntem geliştirdi.",
        "contribution": "Mukaddime, tarihi olayları toplumsal bağlamıyla açıklayan ilk sistematik eserlerden biridir.",
        "importance": "Asabiyye kavramı ve tarih felsefesi, hem İslam düşüncesinde hem modern sosyal bilimlerde ilgi görmüştür.",
        "books": ["Mukaddime", "el-İber"],
        "recommended": ["El-Bidaye ve’n-Nihaye", "Siyer-i Nebi", "Sofie’nin Dünyası"],
    },
    {
        "slug": "imam-shatibi", "name": "İmam Şatibi", "kind": "alim",
        "full_name": "Ebu İshak İbrahim bin Musa eş-Şatibi", "years": "y. 1140 – 1194",
        "era": "Endülüs · Murabitun dönemi", "avatar": "rose",
        "bio": "Maliki fıkıh usulcüsü. Şeriatın amaçları (makâsıd) üzerine yaptığı çalışmalarla tanınır.",
        "contribution": "el-Muvafakat, hükümlerin arkasındaki hikmet ve amaçları sistematik biçimde ele alır.",
        "importance": "Makâsıd düşüncesinin fıkhî bir disiplin olarak gelişmesinde öncü oldu.",
        "books": ["el-Muvafakat", "el-İ’tisam"],
        "recommended": ["el-Muvatta", "Tezveren", "Sahih-i Buhari"],
    },
    {
        "slug": "ibnu-l-cevzi", "name": "İbnü’l-Cevzi", "kind": "alim",
        "full_name": "Ebu’l-Ferec Abdurrahman bin Ali İbnü’l-Cevzi", "years": "1116 – 1201",
        "era": "Bağdat · Abbasi dönemi", "avatar": "copper",
        "bio": "Vaiz, tarihçi ve tefsir âlimi. Sade anlatımıyla geniş halk kitlelerine hitap etti.",
        "contribution": "Zadu’l-Mesir tefsiri ve çok sayıda vaaz/ahlak eseri, ilmi günlük hayata taşıdı.",
        "importance": "İlmi sadeleştirerek anlatma konusundaki yeteneği, halka hitap eden ilk örneklerden biri oldu.",
        "books": ["Zadu’l-Mesir", "Kitabü’l-Hamis", "Sıfatü’s-Safve"],
        "recommended": ["İhyau Ulumi’d-Din", "Sahih-i Buhari", "Mesnevi"],
    },
    {
        "slug": "hasan-el-basri", "name": "Hasan el-Basri", "kind": "alim",
        "full_name": "Ebu Said el-Hasan bin Ebi’l-Hasan el-Basri", "years": "642 – 728",
        "era": "Basra · Emevi dönemi", "avatar": "olive",
        "bio": "Tabiun neslinin önde gelen âlimlerinden. Zühdü ve vaazlarıyla tanınır.",
        "contribution": "Kelam, tefsir ve ahlak alanlarındaki görüşleri sonraki nesillere aktarıldı; Basra’da ilim meclisleri kurdu.",
        "importance": "Kader ve iman tartışmalarındaki duruşu, İslam düşüncesinin erken dönemine damgasını vurdu.",
        "books": ["Risale fi’l-Kader", "Mecmuu’t-Tefsir"],
        "recommended": ["Sahih-i Buhari", "İhyau Ulumi’d-Din", "Tezveren"],
    },
    {
        "slug": "kadi-iyaz", "name": "Kadı Iyaz", "kind": "alim",
        "full_name": "Ebu’l-Fadl İyaz bin Musa el-Yahsubi", "years": "1083 – 1149",
        "era": "Endülüs · Murabitun dönemi", "avatar": "sand",
        "bio": "Maliki âlim ve kadı. Hadis, fıkıh ve edebiyat alanlarında eserler verdi.",
        "contribution": "eş-Şifa, Peygamber’in hayatı, ahlakı ve mucizeleri üzerine yazılmış en tanınmış eserlerden biridir.",
        "importance": "Siyer ve šemail literatüründe geniş bir okur kitlesine ulaşan bir kaynak oluşturdu.",
        "books": ["eş-Şifa", "Müşkilü’l-Mesabih"],
        "recommended": ["Siyer-i Nebi", "Sunenü’t-Tirmizi", "Sahih-i Buhari"],
    },
    {
        "slug": "yunus-emre", "name": "Yunus Emre", "kind": "alim",
        "full_name": "Yunus Emre", "years": "y. 1240 – 1321",
        "era": "Anadolu · Selçuklu sonrası", "avatar": "gold",
        "bio": "Anadolu’nun en tanınmış tasavvuf şairi. Sade Türkçesiyle sevgi ve hoşgörüyü anlattı.",
        "contribution": "Şiirleriyle tasavvufu halkın diline taşıdı; 'sözümün özü yâr'dır' anlayışıyla tanınır.",
        "importance": "Türk edebiyatının temel isimlerinden biri olarak Anadolu’nun manevi hafızasını şekillendirdi.",
        "books": ["Divan", "Risaletü’n-Nushiyye"],
        "recommended": ["Mesnevi", "İhyau Ulumi’d-Din", "Mevlana — Divan-ı Kebir"],
    },
    {
        "slug": "said-nursi", "name": "Said Nursî", "kind": "alim",
        "full_name": "Bediüzzaman Said Nursî", "years": "1877 – 1960",
        "era": "Anadolu · Osmanlı sonrası", "avatar": "ink",
        "bio": "Kur’an ilimleri üzerine çalışan çağdaş bir âlim. Risale-i Nur külliyatını kaleme aldı.",
        "contribution": "İman meselelerini çağın diliyle ele alan Risale-i Nur, geniş bir okur kitlesine ulaştı.",
        "importance": "İlim ile gönül ilişkisini yeniden gündeme getirmesi, modern Anadolu düşüncesinde iz bıraktı.",
        "books": ["Risale-i Nur", "Sözler", "Mektubat"],
        "recommended": ["Sahih-i Buhari", "İhyau Ulumi’d-Din", "Tezveren"],
    },
    {
        "slug": "seyyid-kutup", "name": "Seyyid Kutup", "kind": "alim",
        "full_name": "Seyyid Kutup", "years": "1906 – 1966",
        "era": "Mısır · 20. yüzyıl", "avatar": "copper",
        "bio": "Kur’an tefsiri ve İslam düşüncesi üzerine yazan çağdaş bir yazar-âlim.",
        "contribution": "Fi Zılalil Kur’an adlı tefsiri, Kur’an’ı sosyal ve siyasi bağlamıyla okuyan bir yorum geleneğini temsil eder.",
        "importance": "20. yüzyılda İslamî düşüncenin yeniden tartışılmasında etkili oldu; görüşleri farklı yorumlarla karşılandı.",
        "books": ["Fi Zılalil Kur’an", "Maalim fi’t-Tariq"],
        "recommended": ["Tezveren", "Sahih-i Buhari", "Muhammed Hamidullah — İslam Peygamberi"],
    },
    {
        "slug": "muhammad-hamidullah", "name": "Muhammed Hamidullah", "kind": "alim",
        "full_name": "Muhammad Hamidullah", "years": "1908 – 2002",
        "era": "Haydarabad / Paris · 20. yüzyıl", "avatar": "sand",
        "bio": "Hadis ve siyer alanında çalışan âlim; İslam’ı Batı dillerinde tanıtan eserleriyle bilinir.",
        "contribution": "İslam Peygamberi adlı eseri ve hadis derlemeleri, akademik ve genel okur için güvenilir bir giriş sunar.",
        "importance": "Kaynakları doğrudan okuyup farklı dillerde sunması, İslam ilimlerinin uluslararası alanda tanınmasına katkı verdi.",
        "books": ["İslam Peygamberi", "Muhammed’in Sözleri", "el-Vesâiku’s-Siyasiyye"],
        "recommended": ["Siyer-i Nebi", "Sahih-i Buhari", "Sahih-i Müslim"],
    },
    {
        "slug": "necip-fazil", "name": "Necip Fazıl Kısakürek", "kind": "alim",
        "full_name": "Ahmed Necib bin Şemseddin", "years": "1904 – 1983",
        "era": "Anadolu · 20. yüzyıl", "avatar": "rose",
        "bio": "Şair ve düşünür. İslamî kimlik ve modernite tartışmalarında etkili bir kalem oldu.",
        "contribution": "Şiirleri ve fikir yazılarıyla genç nesillerde İslam bilinci üzerine düşünme uyandırdı.",
        "importance": "Edebiyat ile fikri birlikte taşıması, kültür tartışmalarında kalıcı bir yer edinmesini sağladı.",
        "books": ["Sahip-siz", "Çile", "İdeolocya Örgüsü"],
        "recommended": ["İhyau Ulumi’d-Din", "Said Nursî — Sözler", "Tezveren"],
    },
    {
        "slug": "nurettin-topcu", "name": "Nurettin Topçu", "kind": "alim",
        "full_name": "Nurettin Topçu", "years": "1909 – 1975",
        "era": "Anadolu · 20. yüzyıl", "avatar": "olive",
        "bio": "Felsefeci ve eğitim düşünürü. Ahlak ve irade üzerine yazdıklarıyla tanınır.",
        "contribution": "İsyan Ahlakı ve Türkiye’nin Manevi Meseleleri gibi eserlerinde ahlaki direnci işledi.",
        "importance": "İlimi yalnızca bilgi değil, karakter meselesi olarak görmesi bu topluluğun anlayışıyla uyumludur.",
        "books": ["İsyan Ahlakı", "Türkiye’nin Manevi Meseleleri"],
        "recommended": ["İhyau Ulumi’d-Din", "Mevlana — Mesnevi", "Sofie’nin Dünyası"],
    },
    {
        "slug": "suleyman-hayri-bolay", "name": "Süleyman Hayri Bolay", "kind": "alim",
        "full_name": "Süleyman Hayri Bolay", "years": "1937 – 2021",
        "era": "Anadolu · 20. yüzyıl", "avatar": "gold",
        "bio": "Felsefe âlimi ve eğitimci. İslam felsefesi ve tasavvuf düşüncesi üzerine çalışmalar yaptı.",
        "contribution": "Tasavvuf Düşüncesi ve İslam Felsefesi alanındaki eserleri, konuyu akademik bir düzenle anlatır.",
        "importance": "Klasik metinleri modern okura açan anlatımıyla ilim halkaları için uygun bir rehberdir.",
        "books": ["Tasavvuf Düşüncesi", "İslam Felsefesi"],
        "recommended": ["Fususu’l-Hikem (şerhle)", "İhyau Ulumi’d-Din", "Mesnevi"],
    },
    {
        "slug": "dostoyevski", "name": "Fyodor Dostoyevski", "kind": "yazar",
        "full_name": "Fyodor Mihayloviç Dostoyevski", "years": "1821 – 1881",
        "era": "Rus edebiyatı · Dünya klasikleri", "avatar": "ink",
        "bio": "İnsanın vicdanı, suçluluk duygusu ve inanç arayışı üzerine yazan büyük Rus yazarı.",
        "contribution": "Suç ve Ceza, Kardeşler Karamazov ve Budala gibi eserlerde ahlaki soruları kurguyla işledi.",
        "importance": "İlim Halkası’nda dünya klasikleri, ahlak ve vicdan meselelerini birlikte düşünmek için okunur; bu yazar dini bir rehber değil, edebî bir muhataptır.",
        "books": ["Suç ve Ceza", "Kardeşler Karamazov", "Budala"],
        "recommended": ["Tutunamayanlar", "Sofie’nin Dünyası", "İhyau Ulumi’d-Din"],
    },
    {
        "slug": "oguz-atay", "name": "Oğuz Atay", "kind": "yazar",
        "full_name": "Oğuz Atay", "years": "1934 – 1977",
        "era": "Türk edebiyatı · Dünya klasikleri", "avatar": "copper",
        "bio": "Türk edebiyatının en özgün romanlarından biri olan Tutunamayanlar’ın yazarı.",
        "contribution": "Bireyin yabancılaşması, anlam arayışı ve iletişim sorunlarını modern bir dille anlattı.",
        "importance": "Klasikler kategorisinde, çağdaş insanın iç dünyasını anlamak için okunur.",
        "books": ["Tutunamayanlar", "Tehlikeli Oyunlar"],
        "recommended": ["Suç ve Ceza", "Sofie’nin Dünyası", "Mesnevi"],
    },
    {
        "slug": "jostein-gaarder", "name": "Jostein Gaarder", "kind": "yazar",
        "full_name": "Jostein Gaarder", "years": "1952 –", "era": "Norveç edebiyatı · Dünya klasikleri", "avatar": "sand",
        "bio": "Felsefe tarihini romanla anlatan Norveçli yazar.",
        "contribution": "Sofie’nin Dünyası, felsefi soruları geniş bir okur kitlesiyle tanıştırdı.",
        "importance": "Felsefeye ilk adım atmak isteyenler için ilham verici bir giriş metnidir.",
        "books": ["Sofie’nin Dünyası", "Maya"],
        "recommended": ["Sofie’nin Dünyası", "Suç ve Ceza", "Tezveren"],
    },
    {
        "slug": "saint-exupery", "name": "Antoine de Saint-Exupéry", "kind": "yazar",
        "full_name": "Antoine Marie Roger de Saint-Exupéry", "years": "1900 – 1944",
        "era": "Fransız edebiyatı · Dünya klasikleri", "avatar": "gold",
        "bio": "Pilot ve yazar. Küçük Prens ile çocukluk ve bilgelik üzerine evrensel bir metin bıraktı.",
        "contribution": "Küçük Prens, görünmeyenin değeri, sorumluluk ve sadakat temalarını sade bir dille işler.",
        "importance": "Kısa ama derin anlatımıyla ilim halkalarında birlikte okumaya çok uygun bir klasiktir.",
        "books": ["Küçük Prens", "Gece Uçuşu"],
        "recommended": ["Mesnevi", "Sofie’nin Dünyası", "Tutunamayanlar"],
    },
]

# Kullanıcının paylaştığı 200 âlim listesi Rehberler'e eklenir.
ORIGINAL_SCHOLAR_CATEGORIES = {
    "imam-gazali": "Kelam ve İslam Düşüncesi", "imam-maturidi": "Kelam ve İslam Düşüncesi",
    "ibn-hisam": "Tasavvuf, Siyer ve Diğer İlimler", "ibn-kesir": "Tefsir ve Kıraat",
    "mevlana": "Tasavvuf, Siyer ve Diğer İlimler", "ibn-arabi": "Tasavvuf, Siyer ve Diğer İlimler",
    "imam-buhari": "Hadis", "imam-muslim": "Hadis", "imam-ebu-hanife": "Fıkıh ve Usul",
    "imam-safii": "Fıkıh ve Usul", "imam-malik": "Fıkıh ve Usul",
    "imam-ahmed-bin-hanbel": "Fıkıh ve Usul", "imam-tirmizi": "Hadis", "ebu-davud": "Hadis",
    "ibn-mace": "Hadis", "imam-nesai": "Hadis", "ibn-ishak": "Tasavvuf, Siyer ve Diğer İlimler",
    "taberi": "Tefsir ve Kıraat", "imam-nevevi": "Fıkıh ve Usul", "fahreddin-er-razi": "Tefsir ve Kıraat",
    "ibn-teymiyye": "Kelam ve İslam Düşüncesi", "ibnu-l-kayyim": "Kelam ve İslam Düşüncesi",
    "ibn-haldun": "Tasavvuf, Siyer ve Diğer İlimler", "imam-shatibi": "Fıkıh ve Usul",
    "ibnu-l-cevzi": "Tefsir ve Kıraat", "hasan-el-basri": "Tasavvuf, Siyer ve Diğer İlimler",
    "kadi-iyaz": "Hadis", "yunus-emre": "Tasavvuf, Siyer ve Diğer İlimler",
    "said-nursi": "Kelam ve İslam Düşüncesi", "seyyid-kutup": "Kelam ve İslam Düşüncesi",
    "muhammad-hamidullah": "Hadis", "necip-fazil": "Kelam ve İslam Düşüncesi",
    "nurettin-topcu": "Kelam ve İslam Düşüncesi", "suleyman-hayri-bolay": "Kelam ve İslam Düşüncesi",
}
for _scholar in SCHOLARS:
    _scholar.setdefault("kind", "alim")
    _scholar.setdefault("category", ORIGINAL_SCHOLAR_CATEGORIES.get(
        _scholar["slug"], "Edebiyat" if _scholar["kind"] == "yazar" else "Genel"
    ))
_existing_slugs = {s["slug"] for s in SCHOLARS}
for _extra in SCHOLARS_EXTRA:
    if _extra["slug"] in _existing_slugs:
        _extra["slug"] = _extra["slug"] + "-ilim-listesi"
    _existing_slugs.add(_extra["slug"])
SCHOLARS.extend(SCHOLARS_EXTRA)

BOOKS_SEED = [
    ("İhyau Ulumi’d-Din", "İmam Gazali", "Tasavvuf / Ahlak", ""),
    ("Sahih-i Buhari", "İmam Buhari", "Hadis", "sand"),
    ("Siyer-i Nebi", "İbn Hişam", "Siyer-i Nebi", "copper"),
    ("Suç ve Ceza", "Dostoyevski", "Dünya Klasikleri", "ink"),
    ("Mesnevi", "Mevlana", "Tasavvuf / Ahlak", "copper"),
    ("Tutunamayanlar", "Oğuz Atay", "Türk Edebiyatı", "ink"),
    ("Sofie’nin Dünyası", "Jostein Gaarder", "Felsefe", "sand"),
    ("Tezveren", "İmam Maturidi", "İtikad", ""),
]

# Yerel katalogda yer alan eserler için TMDB benzeri "Hakkında" metinleri ve türler.
BOOK_DETAILS = {
    "İhyau Ulumi’d-Din": {
        "genre": "Tasavvuf, İlim ve Ahlak",
        "description": "İmam Gazali’nin ilmin fazileti, kalbin temizliği ve ilimle amel arasındaki bağ üzerine kaleme aldığı başyapıtı. İhyau Ulumi’d-Din, ibadetin görünüşünden çok niyetin ve kalbin derinliğine iniş üzerine odaklanır; talibin ilmi hayata dönüştürmesini ister.",
    },
    "Sahih-i Buhari": {
        "genre": "Hadis",
        "year": 870,
        "description": "İmam Buhari’nin titiz bir isnad ve metin değerlendirmesiyle derlediği hadis mecmuası. Âlimlerin en güvenilir kaynaklardan biri kabul ettiği eser, Peygamberimiz (s.a.v.)’in söz, fiil ve onaylarını konu başlıkları altında toplar.",
    },
    "Siyer-i Nebi": {
        "genre": "Siyer, İslam Tarihi",
        "year": 834,
        "description": "İbn Hişam’ın Peygamberimiz (s.a.v.)’in hayatını nesil zinciriyle aktardığı klasik siyer eseri. Mekke dönemi, Hicret, gazveler ve Hudeybiye gibi dönüm noktaları, ashabın tanıklıklarıyla birlikte okura aktarılır.",
    },
    "Suç ve Ceza": {
        "genre": "Roman, Psikoloji",
        "year": 1866,
        "description": "Dostoyevski’nin vicdan, özgürlük ve sorumluluk arasındaki çatışmayı Raskolnikov’un gözünden anlattığı roman. Cinayetin ardından başlayan iç sorgulama, insanın kendisinden kaçamayacağını gösteren psikolojik bir derinliğe sahiptir.",
    },
    "Mesnevi": {
        "genre": "Tasavvuf, Şiir",
        "year": 1273,
        "description": "Mevlana Celaleddin Rumi’nin hikâyeler, benzetmeler ve şiirlerle örülü manzum eseri. Aşk, ilim, nefis ve hakikat arayışı; okuru görünenden görünmeyene doğru yol almaya davet eder.",
    },
    "Tutunamayanlar": {
        "genre": "Roman, Türk Edebiyatı",
        "year": 1972,
        "description": "Oğuz Atay’ın modern Türk edebiyatının en özgün seslerinden biri olarak kabul edilen romanı. Selim Işık’ın ardından bıraktığı izleri süren anlatı, yabancılaşma, dostluk ve anlam arayışını katmanlı bir yapıda işler.",
    },
    "Sofie’nin Dünyası": {
        "genre": "Felsefe, Roman",
        "year": 1991,
        "description": "Jostein Gaarder’ın felsefe tarihini bir genç kızın merakı etrafında anlattığı eser. Sokrates’ten modern düşünceye uzanan sorular, okuru kendi varoluşunu yeniden sorgulamaya teşvik eder.",
    },
    "Tezveren": {
        "genre": "İtikad, Kelam",
        "description": "İmam Maturidi’nin kelam ilmindeki temel yaklaşımını yansıtan eser. Akıl ile vahyin uyumu, imanın mahiyeti ve ilahî sıfatlar gibi konuları sistematik biçimde ele alır.",
    },
}

COMMUNITY_USERS = [
    ("Selma Yıldırım", "selmayildirim", "sand", "Tefsir ve tarih okuru. Yavaş okur, çok düşünür.", "Müntesip"),
    ("Kerem Aydın", "keramahmet", "ink", "Felsefe ve edebiyat arasında gidip geliyor.", "Müntesip"),
    ("Hz. Ali (r.a.)", "hikmet_damgasi", "copper", "Hikmet damgası.", "Allâme"),
    ("Ayşe Karaca", "aysekaraca", "rose", "Siyer ve hadis çalışmaları.", "Muallim"),
    ("Mert Kılıç", "mertkilics", "olive", "Klasiklerden ilham alıyor.", "Talebe"),
    ("Nurten Şahin", "nurtensahin", "sand", "Tasavvuf yolunda yeni başlayan.", "Talebe"),
    ("Emre Yalçın", "emreyalcin", "ink", "Dostoyevski hayranı.", "Müntesip"),
    ("Buse Aydın", "buseadin", "copper", "Tefsir okumaları üzerine.", "Talebe"),
    ("Ahmed Yılmaz", "ahmedyilmaz", "olive", "Rehber · İtikad Uzmanı", "Muallim"),
    ("Dr. Emine Şahin", "eminesahin", "rose", "Rehber · İslam Tarihi", "Muallim"),
    ("Yusuf Demir", "yusufdemir", "olive", "Halka üyesi.", "Talebe"),
    ("Deniz Aksoy", "denizaksoy", "rose", "Halka üyesi.", "Talebe"),
]

# (user_index, type, book, writer, text, rating, status, cover, hours_ago)
POSTS_SEED = [
    (0, "quote", "İhyau Ulumi’d-Din", "İmam Gazali",
     "İlim, kalbin hayatıdır; amelin ise nuru. İlim ile amel, bir ağacın kökü ile meyvesi gibidir.",
     0, "", "", 2),
    (1, "review", "Suç ve Ceza", "Fyodor Dostoyevski",
     "Raskolnikov’un vicdanıyla verdiği mücadele, insanın kendi içindeki mahkemeyi hatırlatıyor. Ahlak felsefesiyle birlikte okumak bambaşka bir kapı araladı; “Dostoyevski & Ahlak Felsefesi” halkasında da bunu konuştuk.",
     5, "Okudum", "ink", 5),
    (2, "quote", "Nahcu’l-Belağa", "Hz. Ali (r.a.)",
     "İnsanlar, sıkıntıya düştüklerinde Allah’a yönelir; rahatlıkta ise O’nu unuturlar. Bilinçli olan, rahatlığında da şükreder.",
     0, "", "", 26),
    (3, "review", "Siyer-i Nebi", "İbn Hişam",
     "Siyer okumak, sadece geçmişi öğrenmek değil; bugünün ölçüsünü de yanında taşımak. Hudeybiye bölümü sabır ve ümit üzerine uzun uzun düşündürdü.",
     5, "Okuyorum", "sand", 30),
    (4, "quote", "Küçük Prens", "Antoine de Saint-Exupéry",
     "Gözle görülmeyen şeyler, görünenlerden daha değerlidir. Çünkü onlar bizim içimizdeki izleri taşır.",
     0, "", "", 50),
    (5, "review", "Mesnevi", "Mevlana Celaleddin Rumi",
     "Mesnevi’ye başlamadan önce bir tasavvuf sözlüğü okumak işimi kolaylaştırdı. Her hikâyenin bir kapısı var; acele etmeden okumak gerekiyor.",
     4, "Okuma Listemde", "copper", 58),
    (6, "quote", "Dostoyevski Koleksiyonu", "Fyodor Dostoyevski",
     "Cehennem, birbirimizi anlayamamaktan doğan azaptır.",
     0, "", "", 76),
    (7, "review", "Tefsir-i Cabir", "İbn Cabir",
     "Başlangıçta oldukça akıcı ilerledi ama ilerleyen bölümlerde tekrarlar beni yordu. Yine de ayetlerin iniş sebeplerini öğrenmek çok kıymetliydi.",
     4, "Yarım Bırakıldı", "sand", 96),
]

# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def now() -> float:
    return time.time()


def ago(hours: float) -> float:
    return now() - hours * 3600


TR_TITLE_ORDER = {ch: i for i, ch in enumerate("abcçdefgğhıijklmnoöprsştuüvyz")}


def book_title_sort_key(value) -> tuple:
    """Harf ile başlayan başlıkları önce, Türkçe alfabe sırasıyla sıralar."""
    text = str(value or "").strip()
    normalized = text.replace("İ", "i").replace("I", "ı").casefold()
    if not text[:1].isalpha():
        return (1, normalized)
    return (0, tuple(TR_TITLE_ORDER.get(ch, 100 + ord(ch)) for ch in normalized))


def book_title_collate(a, b) -> int:
    left = book_title_sort_key(a)
    right = book_title_sort_key(b)
    return (left > right) - (left < right)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_collation("BOOKTITLE", book_title_collate)
    return conn


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected: str) -> bool:
    _, actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def clean_text(value) -> str:
    """API'den gelen HTML/boşluk gürültüsünü tek satır metne çevirir."""
    if isinstance(value, dict):
        value = value.get("value") or value.get("text") or ""
    if isinstance(value, (list, tuple)):
        value = " ".join(clean_text(part) for part in value)
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:2000]


def book_year(value) -> int | None:
    match = re.search(r"(\d{4})", str(value or ""))
    return int(match.group(1)) if match else None


# Open Library/Google Books konu etiketleri binlerce farklı değer üretir.
# Kütüphane filtrelerinin kullanılabilir kalması için bunları sabit bir
# Türkçe tür taksonomisine indirgeriz.
GENRE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Kur'an", ("quran", "koran", "tafsir", "tefsir")),
    ("Hadis", ("hadith", "hadis", "sunnah")),
    ("Tasavvuf", ("sufism", "sufi", "tasavvuf", "mysticism", "mystic")),
    ("İslam Tarihi", ("ottoman", "osmanlı", "islamic history", "muhammad", "siyer")),
    ("İslam", ("islam", "muslim", "sharia", "mosque", "religious education")),
    ("Türk Edebiyatı", ("turkish literature", "turkish poetry", "türk edebiyatı", "turkish")),
    ("Dünya Klasikleri", ("classics", "ancient classics", "world classics", "klasik")),
    ("Dünya Edebiyatı", ("world literature", "literature", "edebiyat")),
    ("Bilim Kurgu", ("science fiction", "sci-fi", "dystopian", "utopian", "fantasy", "fantastik")),
    ("Roman", ("historical fiction", "fiction", "novel", "literary", "roman")),
    ("Öykü", ("short story", "short stor", "öykü", "hikaye", "tales", "fairy")),
    ("Şiir", ("poetry", "poem", "şiir", "verse")),
    ("Tiyatro", ("drama", "theatre", "theater", "play")),
    ("Deneme", ("essay", "deneme")),
    ("Biyografi", ("biography", "autobiography", "memoir", "biographical")),
    ("Tarih", ("history", "historic", "archaeology", "tarih")),
    ("Felsefe", ("philosophy", "ethics", "metaphysics", "logic", "felsefe")),
    ("Psikoloji", ("psychology", "psychiatry", "psikoloji")),
    ("Din", ("religion", "theology", "christian", "judaism", "buddhism", "hinduism", "church")),
    ("Sosyoloji", ("sociology", "anthropology", "society", "culture", "toplum")),
    ("Eğitim", ("education", "teaching", "learning", "eğitim")),
    ("Ekonomi", ("economics", "business", "finance", "management", "ekonomi")),
    ("Hukuk", ("law", "legal", "justice", "hukuk")),
    ("Siyaset", ("political science", "politics", "government", "democracy", "siyaset")),
    ("Bilgisayar", ("computer", "computing", "software", "programming", "artificial intelligence")),
    ("Fizik", ("physics", "fizik")),
    ("Biyoloji", ("biology", "botany", "zoology", "genetics", "biyoloji")),
    ("Astronomi", ("astronomy", "astrophysics", "space")),
    ("Kimya", ("chemistry", "kimya")),
    ("Tıp", ("medicine", "medical", "health", "nursing", "pharmacy", "tıp")),
    ("Matematik", ("mathematics", "math", "statistics", "geometry", "matematik")),
    ("Teknoloji", ("technology", "engineering", "machines", "teknoloji")),
    ("Sanat", ("art", "painting", "sculpture", "design", "photography", "sanat")),
    ("Müzik", ("music", "musical", "müzik")),
    ("Mimari", ("architecture", "mimari")),
    ("Coğrafya", ("geography", "travel", "tourism", "coğrafya", "seyahat")),
    ("Doğa", ("nature", "environment", "ecology", "animals", "plants", "doğa")),
    ("Çocuk", ("children", "juvenile", "young adult", "kids", "çocuk")),
    ("Spor", ("sport", "football", "athletics", "spor")),
    ("Yemek", ("cooking", "food", "cuisine", "yemek")),
    ("Bilim", ("science", "scientific", "bilim")),
]

CANONICAL_GENRES = {name for name, _ in GENRE_RULES} | {
    "Hadis", "Siyer-i Nebi", "Tasavvuf / Ahlak", "İtikad", "Tefsir", "Fıkıh",
    "Akaid", "İslam Tarihi", "Dünya Klasikleri", "Türk Edebiyatı", "Felsefe",
    "Keşfedilen", "Genel",
}

ISLAMIC_CATEGORIES = (
    "Hadis", "Siyer-i Nebi", "Tasavvuf / Ahlak", "İtikad", "Tefsir", "Fıkıh",
    "Akaid", "İslam Tarihi", "Kur'an", "İslam", "Hadis", "Tasavvuf",
)

FOCUS_SQL = {
    "islamic": (
        " AND (category IN (" + ",".join("?" for _ in ISLAMIC_CATEGORIES) + ")"
        " OR genre LIKE '%İslam%' OR genre LIKE '%Kur%an%' OR genre LIKE '%Hadis%'"
        " OR genre LIKE '%Tasavvuf%' OR genre LIKE '%Tefsir%')"
    ),
    "classics": " AND (category='Dünya Klasikleri' OR genre LIKE '%Dünya Klasikleri%')",
    "turkish": " AND (category='Türk Edebiyatı' OR genre LIKE '%Türk Edebiyatı%')",
    "science": (
        " AND (genre LIKE '%Bilim%' OR category LIKE '%Bilim%'"
        " OR genre LIKE '%Teknoloji%' OR genre LIKE '%Matematik%')"
    ),
}

BOOK_SORT_SQL = {
    "title": "title COLLATE BOOKTITLE ASC",
    "year_desc": "year IS NULL, year DESC, title ASC",
    "rating": "rating IS NULL, rating DESC, rating_count DESC, title ASC",
    "newest": "id DESC",
}


def book_genre(values) -> str:
    """Google/Open Library etiketlerini sabit bir Türkçe tür listesine indirger."""
    if isinstance(values, str):
        values = values.split(",")
    genres: list[str] = []
    for value in values or []:
        text = clean_text(value).strip(" /")
        if not text:
            continue
        if text in CANONICAL_GENRES:
            canonical = text
        else:
            low = text.casefold()
            canonical = next(
                (name for name, keywords in GENRE_RULES
                 if any(keyword in low for keyword in keywords)),
                "Genel",
            )
        if canonical not in genres:
            genres.append(canonical)
    return ", ".join(genres[:4])


def normalize_book_genres(conn: sqlite3.Connection) -> None:
    """Önceki ham aktarımların tür alanlarını yeni taksonomiye taşır."""
    for row in conn.execute(
        "SELECT id,genre FROM books WHERE source<>'curated' AND genre<>''"
    ).fetchall():
        normalized = book_genre(row["genre"].split(","))
        if normalized and normalized != row["genre"]:
            conn.execute("UPDATE books SET genre=? WHERE id=?", (normalized, row["id"]))


def cover_url(value) -> str:
    text = str(value or "").strip()
    return "https://" + text[7:] if text.startswith("http://") else text


def enrich_curated_books(conn: sqlite3.Connection) -> None:
    """Mevcut yerel katalog kayıtlarını yeni tür/özet alanlarıyla tamamlar."""
    for title, info in BOOK_DETAILS.items():
        row = conn.execute("SELECT id FROM books WHERE title=?", (title,)).fetchone()
        if not row:
            continue
        conn.execute(
            "UPDATE books SET genre=CASE WHEN genre='' THEN ? ELSE genre END, "
            "description=CASE WHEN description='' THEN ? ELSE description END, "
            "year=COALESCE(year, ?), publisher=CASE WHEN publisher='' THEN ? ELSE publisher END "
            "WHERE id=?",
            (info.get("genre", ""), info.get("description", ""), info.get("year"),
             info.get("publisher", ""), row["id"]),
        )


def title_key(value) -> str:
    """Başlık eşleştirmede Türkçe karakter ve noktalama farklarını tolere eder."""
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    replacements = {"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"}
    text = "".join(replacements.get(ch, ch) for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


SCHOLAR_BOOK_GENRES = {
    "Fıkıh ve Usul": "Fıkıh, İslam Hukuku",
    "Hadis": "Hadis",
    "Tefsir ve Kıraat": "Tefsir, Kıraat",
    "Kelam ve İslam Düşüncesi": "Kelam, İslam Düşüncesi",
    "Tasavvuf, Siyer ve Diğer İlimler": "Tasavvuf, Siyer, İslam Tarihi",
    "Edebiyat": "Edebiyat",
    "Genel": "İslami İlimler",
}


def ensure_scholar_books(conn: sqlite3.Connection) -> None:
    """Âlimlerin eserlerini kitap tablosunda karşılık bulacak şekilde hazırlar."""
    catalog: dict[str, int] = {}
    for row in conn.execute("SELECT id,title,original_title FROM books WHERE hidden=0"):
        for value in (row["title"], row["original_title"]):
            key = title_key(value)
            if key:
                catalog.setdefault(key, row["id"])

    def resolve(title: str, author: str, category: str) -> int | None:
        clean = str(title or "").strip(" ()")
        key = title_key(clean)
        if not key:
            return None
        if key in catalog:
            return catalog[key]
        genre = SCHOLAR_BOOK_GENRES.get(category, "İslami İlimler")
        description = (
            f"{clean}, {author} tarafından kaleme alınan eserler arasında anılır. "
            f"İlim Halkası kütüphanesinde {genre} kategorisinde okurlarla buluşur; "
            "kapak, tür ve yayımlanma bilgileri bu sayfada toplanmıştır."
        )
        cover = ["olive", "sand", "copper", "ink"][len(key) % 4]
        cur = conn.execute(
            "INSERT OR IGNORE INTO books (title,author,category,cover,description,genre,source,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (clean[:300], author[:200], "İslami İlimler", cover, description, genre, "curated", now()),
        )
        row = conn.execute(
            "SELECT id FROM books WHERE title=? AND author=?", (clean[:300], author[:200])
        ).fetchone()
        book_id = row["id"] if row else cur.lastrowid
        catalog[key] = book_id
        return book_id

    for scholar in SCHOLARS:
        slug = scholar["slug"]
        author = scholar.get("full_name") or scholar["name"]
        category = scholar.get("category", "Genel")
        for role, field in (("work", "books"), ("recommended", "recommended")):
            for entry in scholar.get(field, []):
                book_id = resolve(str(entry), author, category)
                if book_id:
                    conn.execute(
                        "INSERT OR IGNORE INTO scholar_books (slug,book_id,role) VALUES (?,?,?)",
                        (slug, book_id, role),
                    )


def cache_book(conn: sqlite3.Connection, data: dict) -> dict | None:
    """API sonucunu SQLite kataloğuna yazar/tazeliklerini doldurur."""
    title = clean_text(data.get("title")).strip()
    if not title:
        return None
    author = clean_text(data.get("author")).strip()
    try:
        rating = float(data.get("rating") or 0) or None
    except (TypeError, ValueError):
        rating = None
    try:
        rating_count = int(data.get("rating_count") or 0)
        page_count = int(data.get("page_count") or 0)
    except (TypeError, ValueError):
        rating_count = page_count = 0

    existing = conn.execute(
        "SELECT * FROM books WHERE title=? AND author=?", (title, author)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE books SET "
            "cover=CASE WHEN cover='' THEN ? ELSE cover END, "
            "genre=CASE WHEN genre='' THEN ? ELSE genre END, "
            "year=COALESCE(year, ?), rating=COALESCE(rating, ?), "
            "rating_count=CASE WHEN rating_count=0 THEN ? ELSE rating_count END, "
            "publisher=CASE WHEN publisher='' THEN ? ELSE publisher END, "
            "work_key=CASE WHEN work_key='' THEN ? ELSE work_key END, "
            "description=CASE WHEN description='' THEN ? ELSE description END, "
            "page_count=CASE WHEN page_count=0 THEN ? ELSE page_count END, "
            "isbn=CASE WHEN isbn='' THEN ? ELSE isbn END WHERE id=?",
            (data.get("cover", ""), data.get("genre", ""), data.get("year"), rating,
             rating_count, data.get("publisher", ""), data.get("work_key", ""),
             data.get("description", ""), page_count, data.get("isbn", ""), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO books (title,author,category,cover,isbn,description,genre,year,rating,"
            "rating_count,publisher,work_key,page_count,source,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, author, data.get("category") or "Keşfedilen", data.get("cover", ""),
             data.get("isbn", ""), data.get("description", ""), data.get("genre", ""),
             data.get("year"), rating, rating_count, data.get("publisher", ""),
             data.get("work_key", ""), page_count, data.get("source") or "google", now()),
        )
    row = conn.execute(
        "SELECT * FROM books WHERE title=? AND author=?", (title, author)
    ).fetchone()
    return dict(row) if row else None


FIGURE_POST_INTERVAL = 12 * 60 * 60


def seed_figure_accounts(conn: sqlite3.Connection) -> None:
    """Kalıcı ilham hesaplarını oluşturur ve eksikse ilk alıntılarını ekler."""
    ts = now()
    for figure in FIGURE_ACCOUNTS:
        row = conn.execute(
            "SELECT id FROM users WHERE email=?", (figure["email"],)
        ).fetchone()
        if row:
            uid = row["id"]
            conn.execute(
                "UPDATE users SET display_name=?, username=?, bio=?, avatar=?, title=?, "
                "is_system=1, is_community=0, blocked=0 WHERE id=?",
                (figure["display_name"], figure["username"], figure["bio"],
                 figure["avatar"], figure["title"], uid),
            )
        else:
            salt, digest = hash_password(secrets.token_urlsafe(24))
            cur = conn.execute(
                "INSERT INTO users (email,username,password_hash,salt,display_name,bio,avatar,title,"
                "is_community,is_admin,is_system,blocked,created_at) VALUES (?,?,?,?,?,?,?,?,0,0,1,0,?)",
                (figure["email"], figure["username"], digest, salt, figure["display_name"],
                 figure["bio"], figure["avatar"], figure["title"], ts),
            )
            uid = cur.lastrowid
        # İlk akış girdisi yoksa hemen bir alıntı ekle.
        has_post = conn.execute(
            "SELECT 1 FROM posts WHERE user_id=? LIMIT 1", (uid,)
        ).fetchone()
        if not has_post and figure["quotes"]:
            book, text = figure["quotes"][0]
            conn.execute(
                "INSERT INTO posts (user_id,type,book,writer,text,rating,status,cover,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (uid, "quote", book, figure["display_name"], text, 0, "", "", ts),
            )


def post_figure_quotes_if_due(conn: sqlite3.Connection) -> int:
    """12 saat dolan kalıcı hesaplar için sıradaki alıntıyı paylaşır."""
    created = 0
    current = now()
    for figure in FIGURE_ACCOUNTS:
        user = conn.execute(
            "SELECT id, display_name FROM users WHERE email=? AND is_system=1", (figure["email"],)
        ).fetchone()
        if not user or not figure["quotes"]:
            continue
        row = conn.execute(
            "SELECT COUNT(*) AS cnt, MAX(created_at) AS last_at FROM posts WHERE user_id=?",
            (user["id"],)
        ).fetchone()
        count = int(row["cnt"] or 0)
        last_at = float(row["last_at"] or 0)
        # İlk alıntı seed sırasında eklenir; sonrakiler 12 saat arayla.
        if count == 0:
            index = 0
            due = True
        else:
            due = (current - last_at) >= FIGURE_POST_INTERVAL
            index = count % len(figure["quotes"])
        if not due:
            continue
        book, text = figure["quotes"][index]
        conn.execute(
            "INSERT INTO posts (user_id,type,book,writer,text,rating,status,cover,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user["id"], "quote", book, figure["display_name"], text, 0, "", "", current),
        )
        created += 1
    return created


def start_figure_scheduler() -> None:
    def loop() -> None:
        # İlk kontrol: sunucu açılışında süresi dolmuşsa tamamla.
        while True:
            try:
                conn = connect()
                try:
                    if post_figure_quotes_if_due(conn):
                        conn.commit()
                finally:
                    conn.close()
            except Exception:
                pass
            time.sleep(10 * 60)

    thread = threading.Thread(target=loop, name="figure-quotes", daemon=True)
    thread.start()


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    # Eski veritabanlarında bildirim türleri sınırlıydı; like/favorite eklemek için tabloyu yenile.
    notif_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='notifications'"
    ).fetchone()[0]
    if any(f"'{kind}'" not in notif_sql for kind in ("like", "favorite", "book_request")):
        conn.execute("ALTER TABLE notifications RENAME TO notifications_old")
        conn.execute("""
            CREATE TABLE notifications (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              kind       TEXT NOT NULL CHECK(kind IN
                ('follow','circle_post','comment','mention','group_message','like','favorite','book_request')),
              actor_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
              post_id    INTEGER REFERENCES posts(id) ON DELETE SET NULL,
              group_id   INTEGER REFERENCES groups(id) ON DELETE SET NULL,
              text       TEXT NOT NULL DEFAULT '',
              target     TEXT NOT NULL DEFAULT '',
              created_at REAL NOT NULL
            )
        """)
        conn.execute("INSERT INTO notifications SELECT * FROM notifications_old")
        conn.execute("DROP TABLE notifications_old")
    # Eski veritabanları için sütun göçü.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "is_admin" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "blocked" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0")
    if "avatar_image" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_image TEXT NOT NULL DEFAULT ''")
    if "is_system" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")
    scholar_columns = {row[1] for row in conn.execute("PRAGMA table_info(scholars)")}
    if "kind" not in scholar_columns:
        conn.execute("ALTER TABLE scholars ADD COLUMN kind TEXT NOT NULL DEFAULT 'alim'")
    if "category" not in scholar_columns:
        conn.execute("ALTER TABLE scholars ADD COLUMN category TEXT NOT NULL DEFAULT 'Genel'")
    shelf_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='shelf_books'"
    ).fetchone()[0]
    if "'abandoned'" not in shelf_sql:
        conn.execute("ALTER TABLE shelf_books RENAME TO shelf_books_old")
        conn.execute("""
            CREATE TABLE shelf_books (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
              status     TEXT NOT NULL CHECK(status IN ('reading','finished','wishlist','abandoned')),
              page       INTEGER NOT NULL DEFAULT 0,
              progress   INTEGER NOT NULL DEFAULT 0,
              rating     INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              UNIQUE (user_id, book_id, status)
            )
        """)
        conn.execute("INSERT INTO shelf_books SELECT * FROM shelf_books_old")
        conn.execute("DROP TABLE shelf_books_old")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shelf_user ON shelf_books(user_id)")
    # Bitirme tarihi: eski kayıtlar için raf kaydının oluşturulma tarihiyle geriye dönük doldurulur.
    shelf_columns = {row[1] for row in conn.execute("PRAGMA table_info(shelf_books)")}
    if "finished_at" not in shelf_columns:
        conn.execute("ALTER TABLE shelf_books ADD COLUMN finished_at REAL NOT NULL DEFAULT 0")
        conn.execute("UPDATE shelf_books SET finished_at = created_at WHERE status='finished'")
    if "page_count" not in shelf_columns:
        conn.execute("ALTER TABLE shelf_books ADD COLUMN page_count INTEGER NOT NULL DEFAULT 0")
    if "volume" not in shelf_columns:
        conn.execute("ALTER TABLE shelf_books ADD COLUMN volume INTEGER NOT NULL DEFAULT 1")
    book_columns = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
    book_migrations = {
        "original_title": "TEXT NOT NULL DEFAULT ''",
        "genre": "TEXT NOT NULL DEFAULT ''",
        "year": "INTEGER",
        "rating": "REAL",
        "rating_count": "INTEGER NOT NULL DEFAULT 0",
        "publisher": "TEXT NOT NULL DEFAULT ''",
        "work_key": "TEXT NOT NULL DEFAULT ''",
        "page_count": "INTEGER NOT NULL DEFAULT 0",
        "volume_count": "INTEGER NOT NULL DEFAULT 1",
        "hidden": "INTEGER NOT NULL DEFAULT 0",
        "hidden_reason": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in book_migrations.items():
        if column not in book_columns:
            conn.execute(f"ALTER TABLE books ADD COLUMN {column} {definition}")
    post_columns = {row[1] for row in conn.execute("PRAGMA table_info(posts)")}
    if "group_id" not in post_columns:
        conn.execute("ALTER TABLE posts ADD COLUMN group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE")
    if "updated_at" not in post_columns:
        conn.execute("ALTER TABLE posts ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_group ON posts(group_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_updated ON posts(updated_at)")
    # Silinen paylaşımların kimliği, istemcilerin akıştan kaldırabilmesi için saklanır.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS deleted_posts ("
        "id INTEGER PRIMARY KEY, deleted_at REAL NOT NULL)"
    )
    if conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0:
        seed(conn)
    enrich_curated_books(conn)
    normalize_book_genres(conn)
    ensure_admin(conn)
    seed_scholars(conn)
    ensure_scholar_books(conn)
    seed_groups(conn)
    seed_figure_accounts(conn)
    conn.commit()
    conn.close()
    ensure_favorites_list()


def ensure_favorites_list() -> None:
    """Her kullanıcıya bir kez 'Favorilerim' listesi verir; silinirse tekrar gelmez."""
    conn = connect()
    try:
        for row in conn.execute("SELECT id FROM users").fetchall():
            uid = row["id"]
            marker = conn.execute(
                "SELECT 1 FROM user_meta WHERE user_id=? AND key='favorites_seeded'", (uid,)
            ).fetchone()
            if marker:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO book_lists (user_id,name,created_at) VALUES (?,?,?)",
                (uid, "Favorilerim", now()),
            )
            conn.execute(
                "INSERT OR REPLACE INTO user_meta (user_id,key,value) VALUES (?,?,?)",
                (uid, "favorites_seeded", "1"),
            )
        conn.commit()
    finally:
        conn.close()


def seed_groups(conn: sqlite3.Connection) -> None:
    """Açık ilim halkaları; meclis ise kullanıcılar kurar, hazır meclis yoktur."""
    if conn.execute("SELECT 1 FROM groups WHERE kind='halka' LIMIT 1").fetchone():
        return
    admin = conn.execute("SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
    if not admin:
        return
    ts = now()
    for c in CIRCLES:
        cur = conn.execute(
            "INSERT INTO groups (kind,name,description,creator_id,avatar_color,max_members,created_at) "
            "VALUES ('halka',?,?,?,?,500,?)",
            (c["name"], c["desc"], admin["id"], c["dot"], ts),
        )
        conn.execute(
            "INSERT OR IGNORE INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
            (cur.lastrowid, admin["id"], ts),
        )


def ensure_admin(conn: sqlite3.Connection) -> None:
    """Sabit yönetici hesabını oluşturur; şifre üretildiye konsola yazar."""
    if conn.execute("SELECT 1 FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone():
        return
    password = os.environ.get("IH_ADMIN_PASSWORD")
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    salt, digest = hash_password(password)
    cur = conn.execute(
        "INSERT INTO users (email,username,password_hash,salt,display_name,bio,avatar,title,is_admin,is_community,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,1,0,?)",
        (ADMIN_EMAIL, ADMIN_USERNAME, digest, salt, "İlim Halkası Yönetimi",
         "Topluluğun düzeninden ve duyurulardan sorumlu yönetici.", "olive", "Yönetici", now()),
    )
    admin_id = cur.lastrowid
    conn.execute(
        "INSERT INTO announcements (admin_id,kind,title,body,created_at) VALUES (?,?,?,?,?)",
        (admin_id, "duyuru", "Hoş geldin",
         "İlim Halkası, birlikte okumak ve birlikte anlamak için kuruldu. Burada herkes birbirinin emeğini kollar. Biz Kimiz? sayfasındaki hadisi birlikte hatırlayalım.",
         now()),
    )
    if generated:
        print("ADMIN LOGIN: " + ADMIN_EMAIL)
        print("ADMIN PASSWORD: " + password)


def seed_scholars(conn: sqlite3.Connection) -> None:
    for s in SCHOLARS:
        conn.execute(
            "INSERT OR IGNORE INTO scholars (slug,name,kind,category,full_name,years,era,avatar,bio,contribution,importance,books_json,recommended_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s["slug"], s["name"], s.get("kind", "alim"), s.get("category", "Genel"),
             s["full_name"], s["years"], s["era"], s["avatar"], s["bio"],
             s["contribution"], s["importance"], json.dumps(s["books"], ensure_ascii=False),
             json.dumps(s["recommended"], ensure_ascii=False)),
        )
        conn.execute(
            "UPDATE scholars SET category=?, kind=? WHERE slug=?",
            (s.get("category", "Genel"), s.get("kind", "alim"), s["slug"]),
        )


def seed(conn: sqlite3.Connection) -> None:
    ts = now()
    for title, author, category, cover in BOOKS_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO books (title,author,category,cover,source,created_at) VALUES (?,?,?,?,?,?)",
            (title, author, category, cover, "curated", ts),
        )

    user_ids: list[int] = []
    for name, username, avatar, bio, title in COMMUNITY_USERS:
        salt, digest = hash_password(secrets.token_urlsafe(24))
        cur = conn.execute(
            "INSERT INTO users (email,username,password_hash,salt,display_name,bio,avatar,title,is_community,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,1,?)",
            (f"{username}@community.local", username, digest, salt, name, bio, avatar, title, ts),
        )
        user_ids.append(cur.lastrowid)

    post_ids: list[int] = []
    for ui, ptype, book, writer, text, rating, status, cover, hours in POSTS_SEED:
        cur = conn.execute(
            "INSERT INTO posts (user_id,type,book,writer,text,rating,status,cover,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_ids[ui], ptype, book, writer, text, rating, status, cover, ago(hours)),
        )
        post_ids.append(cur.lastrowid)

    def comment(post_i: int, user_i: int, text: str, hours: float, parent: int | None = None) -> int:
        cur = conn.execute(
            "INSERT INTO comments (post_id,parent_id,user_id,text,created_at) VALUES (?,?,?,?,?)",
            (post_ids[post_i], parent, user_ids[user_i], text, ago(hours)),
        )
        return cur.lastrowid

    r1 = comment(0, 11, "Kök ve meyve benzetmesi çok yerinde. Bugünkü halka okumasında tam da bu geçiyordu.", 1)
    comment(0, 0, "Gazali’nin bu sözü üzerine yarın halkada birlikte konuşalım istersen 🤍", 0.75, r1)
    comment(1, 11, "Sokratik sorgulama ile Raskolnikov’un sorgulanması arasındaki paralellik harika.", 3)
    comment(2, 10, "Kartpostal olarak kaydettim, duvara asmalık.", 20)
    comment(4, 0, "Bu cümleyi küçük kızıma da okudum, çok sevdi.", 24)

    # Müzakere masası
    d1 = conn.execute(
        "INSERT INTO debates (book_title,user_id,text,created_at) VALUES (?,?,?,?)",
        ("İhyau Ulumi’d-Din", user_ids[0],
         "İlim ve amel ayrımında Gazali tam olarak nerede çizgiyi çekiyor? İlim tek başına kurtuluş için yeterli mi?", ago(3)),
    ).lastrowid
    conn.execute(
        "INSERT INTO debate_answers (debate_id,user_id,text,is_guide,created_at) VALUES (?,?,?,1,?)",
        (d1, user_ids[8],
         "Gazali’ye göre ilim, amelin ön şartıdır; fakat amelle desteklenmeyen ilim kıyamette hüccet olmaz. İhyau’nun “Kitabü’l-İlm” bölümünde bu ayrımı örneklerle görürüz.", ago(2)),
    )
    conn.execute(
        "INSERT INTO debate_answers (debate_id,user_id,text,is_guide,created_at) VALUES (?,?,?,0,?)",
        (d1, user_ids[1], "Beni en çok etkileyen tarafı, ilmin kalpteki etkisini gözlemlemesiydi.", ago(1)),
    )
    conn.execute(
        "INSERT INTO debates (book_title,user_id,text,created_at) VALUES (?,?,?,?)",
        ("İhyau Ulumi’d-Din", user_ids[10],
         "Halka olarak “Kitabü’l-İlm”deki hangi alt başlığı birlikte çalışalım? Önerisi olan var mı?", ago(24)),
    )
    d3 = conn.execute(
        "INSERT INTO debates (book_title,user_id,text,created_at) VALUES (?,?,?,?)",
        ("Suç ve Ceza", user_ids[1],
         "Raskolnikov’un “olağanüstü insan” fikriyle vicdanı arasındaki çelişki, ahlak felsefesinde hangi kavrama karşılık gelir?", ago(5)),
    ).lastrowid
    conn.execute(
        "INSERT INTO debate_answers (debate_id,user_id,text,is_guide,created_at) VALUES (?,?,?,1,?)",
        (d3, user_ids[9],
         "Nietzsche’nin üstinsan fikriyle karşılaştırılabilir; ancak Dostoyevski’nin asıl vurgusu bu fikrin insan vicdanında yarattığı yıkımdadır.", ago(4)),
    )

    for user_i, text, hours in [
        (0, "Bugün 12/30 sayfadayım, “Kitabü’l-İlm” çok kıymetli.", 6),
        (8, "Perşembe meclisinde bu bölümü birlikte tahlil edeceğiz ❖", 5),
    ]:
        conn.execute(
            "INSERT INTO chat_messages (circle,user_id,text,created_at) VALUES (?,?,?,?)",
            ("İmam Gazali Okumaları", user_ids[user_i], text, ago(hours)),
        )


def clean_avatar_image(value) -> str:
    """Tarayıcıda daire içine kırpılmış PNG veri URL'sini doğrular."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("data:image/png;base64,") or len(text) > 400_000:
        raise ValueError("Fotoğraf PNG olarak yüklenmeli ve 300 KB'dan küçük olmalı")
    return text


def clean_book_image(value) -> str:
    """Kitap önerisi kapağı için PNG veri URL'sini doğrular."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("data:image/png;base64,") or len(text) > 600_000:
        raise ValueError("Kapak PNG olarak yüklenmeli ve 450 KB'dan küçük olmalı")
    return text


def serialize_book_request(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    book = None
    if row["book_id"]:
        b = conn.execute(
            "SELECT id,title,author,cover FROM books WHERE id=?", (row["book_id"],)
        ).fetchone()
        if b:
            book = dict(b)
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "page_count": int(row["page_count"] or 0),
        "about": row["about"],
        "cover": row["cover"],
        "status": row["status"],
        "reason": row["reason"],
        "book": book,
        "requester": user_public(conn.execute(
            "SELECT * FROM users WHERE id=?", (row["user_id"],)
        ).fetchone()),
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
    }


def user_public(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "username": row["username"],
        "avatar": row["avatar"],
        "avatar_image": row["avatar_image"] if "avatar_image" in row.keys() else "",
        "bio": row["bio"],
        "title": row["title"],
        "is_admin": bool(row["is_admin"]) if "is_admin" in row.keys() else False,
    }


def user_me(row: sqlite3.Row) -> dict:
    data = user_public(row)
    data["email"] = row["email"]
    data["created_at"] = row["created_at"]
    return data


def author_of(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return user_public(row) or {"display_name": "Bilinmeyen", "username": "", "avatar": "olive",
                                "avatar_image": "", "bio": "", "title": ""}


def user_interests(conn: sqlite3.Connection, user_id: int) -> list[str]:
    """Rafındaki kitapların tür/kategorisinden kısa ilgi etiketleri çıkarır."""
    counts: Counter[str] = Counter()
    for row in conn.execute(
        "SELECT b.genre,b.category FROM shelf_books s JOIN books b ON b.id=s.book_id "
        "WHERE s.user_id=?", (user_id,)
    ):
        for part in (row["genre"] or "").split(","):
            value = part.strip()
            if value:
                counts[value] += 2
        if row["category"]:
            counts[row["category"]] += 1
    return [name for name, _ in counts.most_common(4)]


def is_blocked_pair(conn: sqlite3.Connection, a: int, b: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) "
        "OR (blocker_id=? AND blocked_id=?) LIMIT 1", (a, b, b, a)
    ).fetchone() is not None


def is_mutual_follow(conn: sqlite3.Connection, a: int, b: int) -> bool:
    for follower, followed in ((a, b), (b, a)):
        if not conn.execute(
            "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (follower, followed)
        ).fetchone():
            return False
    return True


def public_user_state(conn: sqlite3.Connection, viewer_id: int, row: sqlite3.Row) -> dict:
    data = user_public(row) or {}
    following = conn.execute(
        "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (viewer_id, row["id"])
    ).fetchone() is not None
    followed_by = conn.execute(
        "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (row["id"], viewer_id)
    ).fetchone() is not None
    data["following"] = following
    data["followed_by"] = followed_by
    data["mutual"] = following and followed_by
    data["blocked"] = conn.execute(
        "SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?", (viewer_id, row["id"])
    ).fetchone() is not None
    data["interests"] = user_interests(conn, row["id"])
    return data


def serialize_public_profile(conn: sqlite3.Connection, viewer_id: int, row: sqlite3.Row) -> dict:
    data = public_user_state(conn, viewer_id, row)
    created = row["created_at"] if "created_at" in row.keys() else 0
    data["year"] = time.localtime(created).tm_year if created else 0
    data["stats"] = {
        "followers": conn.execute(
            "SELECT COUNT(*) FROM follows WHERE followed_id=?", (row["id"],)
        ).fetchone()[0],
        "following": conn.execute(
            "SELECT COUNT(*) FROM follows WHERE follower_id=?", (row["id"],)
        ).fetchone()[0],
    }
    data["shelf"] = [dict(s) for s in conn.execute(
        "SELECT s.status,s.rating,s.progress,s.page,s.page_count,s.volume,b.volume_count,"
        "b.id AS book_id,b.title,b.author,b.cover,b.category,b.genre "
        "FROM shelf_books s JOIN books b ON b.id=s.book_id WHERE s.user_id=? AND b.hidden=0 "
        "ORDER BY s.created_at DESC", (row["id"],)
    )]
    data["posts"] = [serialize_post(conn, p, viewer_id) for p in conn.execute(
        "SELECT * FROM posts WHERE user_id=? ORDER BY created_at DESC LIMIT 60", (row["id"],)
    )]
    return data


def serialize_comment(conn: sqlite3.Connection, row: sqlite3.Row, viewer_id: int) -> dict:
    liked = conn.execute(
        "SELECT 1 FROM comment_likes WHERE comment_id=? AND user_id=?", (row["id"], viewer_id)
    ).fetchone() is not None
    replies = conn.execute(
        "SELECT * FROM comments WHERE parent_id=? ORDER BY created_at", (row["id"],)
    ).fetchall()
    return {
        "id": row["id"],
        "author": author_of(conn, row["user_id"]),
        "text": row["text"],
        "created_at": row["created_at"],
        "likes": conn.execute("SELECT COUNT(*) FROM comment_likes WHERE comment_id=?", (row["id"],)).fetchone()[0],
        "liked": liked,
        "replies": [serialize_comment(conn, r, viewer_id) for r in replies],
    }


def serialize_post(conn: sqlite3.Connection, row: sqlite3.Row, viewer_id: int) -> dict:
    author = author_of(conn, row["user_id"])
    liked = conn.execute("SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?", (row["id"], viewer_id)).fetchone() is not None
    favorited = conn.execute("SELECT 1 FROM post_favorites WHERE post_id=? AND user_id=?", (row["id"], viewer_id)).fetchone() is not None
    followed = row["user_id"] != viewer_id and conn.execute(
        "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (viewer_id, row["user_id"])
    ).fetchone() is not None
    comments = conn.execute(
        "SELECT * FROM comments WHERE post_id=? AND parent_id IS NULL ORDER BY created_at", (row["id"],)
    ).fetchall()
    return {
        "id": row["id"],
        "type": row["type"],
        "book": row["book"],
        "writer": row["writer"],
        "text": row["text"],
        "rating": row["rating"],
        "status": row["status"],
        "cover": row["cover"],
        "group_id": row["group_id"] if "group_id" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else row["created_at"],
        "author": author,
        "author_id": row["user_id"],
        "likes": conn.execute("SELECT COUNT(*) FROM post_likes WHERE post_id=?", (row["id"],)).fetchone()[0],
        "favorites": conn.execute("SELECT COUNT(*) FROM post_favorites WHERE post_id=?", (row["id"],)).fetchone()[0],
        "liked": liked,
        "favorited": favorited,
        "followed": followed,
        "comments": [serialize_comment(conn, c, viewer_id) for c in comments],
    }


def serialize_ticket(conn: sqlite3.Connection, row: sqlite3.Row, with_owner: bool = False) -> dict:
    replies = conn.execute(
        "SELECT * FROM ticket_replies WHERE ticket_id=? ORDER BY created_at", (row["id"],)
    ).fetchall()
    data = {
        "id": row["id"], "kind": row["kind"], "subject": row["subject"], "body": row["body"],
        "status": row["status"], "created_at": row["created_at"],
        "replies": [{"body": r["body"], "created_at": r["created_at"],
                     "admin": author_of(conn, r["admin_id"])} for r in replies],
    }
    if with_owner:
        data["owner"] = author_of(conn, row["user_id"])
    return data


def serialize_report(conn: sqlite3.Connection, row: sqlite3.Row, with_users: bool = False) -> dict:
    data = {
        "id": row["id"], "reason": row["reason"], "detail": row["detail"],
        "status": row["status"], "admin_reply": row["admin_reply"], "created_at": row["created_at"],
    }
    if with_users:
        data["reporter"] = author_of(conn, row["reporter_id"])
        data["reported"] = author_of(conn, row["reported_id"])
    return data


def serialize_scholar(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    comments = conn.execute(
        "SELECT * FROM scholar_comments WHERE slug=? ORDER BY created_at DESC", (row["slug"],)
    ).fetchall()
    linked: dict[str, list[dict]] = {"work": [], "recommended": []}
    for book in conn.execute(
        "SELECT b.*, sb.role AS role FROM scholar_books sb JOIN books b ON b.id=sb.book_id "
        "WHERE sb.slug=? AND b.hidden=0 ORDER BY b.id", (row["slug"],)
    ):
        linked[book["role"]].append(dict(book))
    return {
        "slug": row["slug"], "name": row["name"], "kind": row["kind"],
        "category": row["category"] if "category" in row.keys() else "Genel",
        "full_name": row["full_name"],
        "years": row["years"], "era": row["era"], "avatar": row["avatar"],
        "bio": row["bio"], "contribution": row["contribution"], "importance": row["importance"],
        "books": json.loads(row["books_json"] or "[]"),
        "recommended": json.loads(row["recommended_json"] or "[]"),
        "bookItems": linked["work"],
        "recommendedItems": linked["recommended"],
        "comments": [{"id": c["id"], "author": author_of(conn, c["user_id"]),
                      "text": c["text"], "created_at": c["created_at"]} for c in comments],
    }


def serialize_group(conn: sqlite3.Connection, row: sqlite3.Row, viewer_id: int) -> dict:
    members = [user_public(u) for u in conn.execute(
        "SELECT u.* FROM group_members m JOIN users u ON u.id=m.user_id "
        "WHERE m.group_id=? ORDER BY m.joined_at", (row["id"],)
    )]
    is_member = any(m["id"] == viewer_id for m in members)
    last = conn.execute(
        "SELECT * FROM group_messages WHERE group_id=? ORDER BY created_at DESC LIMIT 1", (row["id"],)
    ).fetchone()
    return {
        "id": row["id"], "kind": row["kind"], "name": row["name"],
        "description": row["description"], "avatar_image": row["avatar_image"],
        "avatar_color": row["avatar_color"], "max_members": row["max_members"],
        "created_at": row["created_at"], "is_creator": row["creator_id"] == viewer_id,
        "is_member": is_member,
        "members": members, "member_count": len(members),
        "last_message": last["text"] if last else "",
        "last_at": last["created_at"] if last else 0,
    }


def group_messages_for(conn: sqlite3.Connection, group_ids: list[int], viewer_id: int) -> dict:
    result: dict[str, list] = {str(gid): [] for gid in group_ids}
    if not group_ids:
        return result
    marks = ",".join("?" for _ in group_ids)
    for m in conn.execute(
        f"SELECT * FROM group_messages WHERE group_id IN ({marks}) ORDER BY created_at", group_ids
    ):
        result[str(m["group_id"])].append({
            "id": m["id"], "author": author_of(conn, m["sender_id"]),
            "text": m["text"], "created_at": m["created_at"],
            "is_me": m["sender_id"] == viewer_id,
        })
    return result


MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,32})")


def add_notification(conn: sqlite3.Connection, user_id: int, kind: str,
                     actor_id: int | None = None, post_id: int | None = None,
                     group_id: int | None = None, text: str = "", target: str = "") -> None:
    """Kullanıcıya tek bir bildirim kaydı ekler (sistem/kilitli/kendini hariç tutar)."""
    if not user_id or user_id == actor_id:
        return
    recipient = conn.execute(
        "SELECT is_system, blocked FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not recipient or recipient["is_system"] or recipient["blocked"]:
        return
    if actor_id and is_blocked_pair(conn, actor_id, user_id):
        return
    conn.execute(
        "INSERT INTO notifications (user_id,kind,actor_id,post_id,group_id,text,target,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, kind, actor_id, post_id, group_id, str(text)[:180], str(target)[:120], now()),
    )


def notify_mentions(conn: sqlite3.Connection, text: str, actor_id: int,
                    post_id: int | None = None, group_id: int | None = None,
                    exclude_ids: set[int] | None = None) -> None:
    """Metinde @kullanıcı adı geçen gerçek kullanıcılara anma bildirimi gönderir."""
    sent: set[int] = set(exclude_ids or ())
    for username in MENTION_RE.findall(text or ""):
        row = conn.execute(
            "SELECT id FROM users WHERE lower(username)=? AND is_system=0 AND id<>?",
            (username.casefold(), actor_id),
        ).fetchone()
        if row and row["id"] not in sent:
            sent.add(row["id"])
            add_notification(conn, row["id"], "mention", actor_id, post_id, group_id, text)


def serialize_notification(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    kind = row["kind"]
    group = None
    if row["group_id"]:
        g = conn.execute("SELECT id,kind,name FROM groups WHERE id=?", (row["group_id"],)).fetchone()
        if g:
            group = {"id": g["id"], "kind": g["kind"], "name": g["name"]}
    post = None
    if row["post_id"]:
        p = conn.execute("SELECT id,book,type FROM posts WHERE id=?", (row["post_id"],)).fetchone()
        if p:
            post = {"id": p["id"], "book": p["book"], "type": p["type"]}

    if kind == "follow":
        view = "users"
    elif kind == "circle_post":
        view = "circles" if not group or group["kind"] == "halka" else "messages"
    elif kind == "comment":
        view = "journal"
    elif kind in ("like", "favorite"):
        view = "journal"
    elif kind == "book_request":
        view = "admin"
    elif kind == "group_message":
        view = "messages"
    else:
        view = "messages" if group else ("journal" if post else "home")

    return {
        "id": f"server-{row['id']}",
        "kind": kind,
        "icon": {"follow": "＋", "circle_post": "◎", "comment": "✎",
                 "mention": "@", "group_message": "✉",
                 "like": "♥", "favorite": "★", "book_request": "✧"}.get(kind, "◈"),
        "ts": row["created_at"],
        "created_at": row["created_at"],
        "view": view,
        "target": row["target"] or "",
        "actor": author_of(conn, row["actor_id"]) if row["actor_id"] else None,
        "group": group,
        "post": post,
        "text": row["text"],
    }


def notifications_for(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
        (user_id,),
    ).fetchall()
    return [serialize_notification(conn, r) for r in rows]


def build_bootstrap(conn: sqlite3.Connection, user_id: int | None) -> dict:
    # Misafirler de herkese açık akışı/kataloğu görebilir; kişisel alanlar boş kalır.
    user_id = user_id or 0
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    posts = conn.execute("SELECT * FROM posts ORDER BY created_at DESC").fetchall()
    shelf = conn.execute(
        "SELECT s.*, b.volume_count, b.title, b.author, b.cover FROM shelf_books s JOIN books b ON b.id=s.book_id "
        "WHERE s.user_id=? ORDER BY s.created_at DESC", (user_id,)
    ).fetchall()
    debates_rows = conn.execute("SELECT * FROM debates ORDER BY created_at DESC").fetchall()
    debates: dict[str, list] = {}
    for d in debates_rows:
        answers = conn.execute(
            "SELECT * FROM debate_answers WHERE debate_id=? ORDER BY created_at", (d["id"],)
        ).fetchall()
        debates.setdefault(d["book_title"], []).append({
            "id": d["id"],
            "author": author_of(conn, d["user_id"]),
            "text": d["text"],
            "created_at": d["created_at"],
            "answers": [{
                "author": author_of(conn, a["user_id"]),
                "text": a["text"],
                "is_guide": bool(a["is_guide"]),
            } for a in answers],
        })
    chat_rows = conn.execute("SELECT * FROM chat_messages ORDER BY created_at").fetchall()
    chat: dict[str, list] = {}
    for m in chat_rows:
        chat.setdefault(m["circle"], []).append({
            "author": author_of(conn, m["user_id"]),
            "text": m["text"],
            "created_at": m["created_at"],
            "is_me": m["user_id"] == user_id,
        })

    my_group_rows = conn.execute(
        "SELECT g.* FROM groups g JOIN group_members m ON m.group_id=g.id "
        "WHERE m.user_id=? ORDER BY g.created_at DESC", (user_id,)
    ).fetchall()
    groups = [serialize_group(conn, g, user_id) for g in my_group_rows]
    groups.sort(key=lambda g: g["last_at"], reverse=True)
    group_messages = group_messages_for(conn, [g["id"] for g in groups], user_id)
    joined_ids = {g["id"] for g in groups}
    discover = [
        serialize_group(conn, g, user_id)
        for g in conn.execute("SELECT * FROM groups WHERE kind='halka' ORDER BY created_at DESC")
        if g["id"] not in joined_ids
    ]

    curricula = [curriculum_with_progress(conn, user_id, c) for c in CURRICULA]
    curriculum_titles_by_book: dict[int, list[str]] = {}
    for item in curricula:
        for step in item["steps"]:
            if step["book_id"]:
                titles = curriculum_titles_by_book.setdefault(step["book_id"], [])
                if item["title"] not in titles:
                    titles.append(item["title"])
    shelf_data = []
    for row in shelf:
        item = dict(row)
        item["curricula"] = curriculum_titles_by_book.get(row["book_id"], [])
        shelf_data.append(item)

    announcements = [
        {**dict(a), "admin": author_of(conn, a["admin_id"])}
        for a in conn.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 30")
    ]
    scholars = [serialize_scholar(conn, s) for s in conn.execute("SELECT * FROM scholars ORDER BY name")]
    my_tickets = [
        serialize_ticket(conn, t) for t in conn.execute(
            "SELECT * FROM support_tickets WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        )
    ]
    my_reports = [
        serialize_report(conn, r) for r in conn.execute(
            "SELECT * FROM user_reports WHERE reporter_id=? ORDER BY created_at DESC", (user_id,)
        )
    ]
    lists = []
    for row in conn.execute(
        "SELECT * FROM book_lists WHERE user_id=? ORDER BY name", (user_id,)
    ):
        items = [dict(b) for b in conn.execute(
            "SELECT b.* FROM book_list_items li JOIN books b ON b.id=li.book_id "
            "WHERE li.list_id=? AND b.hidden=0 ORDER BY li.created_at DESC", (row["id"],)
        )]
        lists.append({"id": row["id"], "name": row["name"], "books": items})
    report_targets = [
        user_public(u) for u in conn.execute(
            "SELECT * FROM users WHERE id<>? AND is_community=0 AND is_admin=0 AND blocked=0 ORDER BY display_name",
            (user_id,),
        )
    ]

    result = {
        "user": user_me(user) if user else None,
        "serverTime": now(),
        "notifications": notifications_for(conn, user_id),
        # Katalog büyüdükçe bootstrap'ı hafif tut; kütüphane /api/books ile sayfalanır.
        "books": [dict(b) for b in conn.execute(
            "SELECT * FROM books WHERE hidden=0 "
            "ORDER BY CASE WHEN source='curated' THEN 0 ELSE 1 END, id LIMIT 300"
        )],
        "posts": [serialize_post(conn, p, user_id) for p in posts],
        "shelf": shelf_data,
        "lists": lists,
        "book_requests": [serialize_book_request(conn, r) for r in conn.execute(
            "SELECT * FROM book_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user_id,)
        )],
        "debates": debates,
        "chat": chat,
        "groups": groups,
        "group_messages": group_messages,
        "discover_circles": discover,
        "curricula": curricula,
        "announcements": announcements,
        "scholars": scholars,
        "tickets": my_tickets,
        "reports": my_reports,
        "report_targets": report_targets,
        "follows": [r[0] for r in conn.execute("SELECT followed_id FROM follows WHERE follower_id=?", (user_id,))],
        "blocked": [r[0] for r in conn.execute("SELECT blocked_id FROM blocks WHERE blocker_id=?", (user_id,))],
        "stats": {
            "followers": conn.execute("SELECT COUNT(*) FROM follows WHERE followed_id=?", (user_id,)).fetchone()[0],
            "following": conn.execute("SELECT COUNT(*) FROM follows WHERE follower_id=?", (user_id,)).fetchone()[0],
            "circles": conn.execute(
                "SELECT COUNT(*) FROM group_members m JOIN groups g ON g.id=m.group_id "
                "WHERE m.user_id=? AND g.kind='halka'", (user_id,)
            ).fetchone()[0],
        },
    }

    if user and user["is_admin"]:
        recent_comments = []
        for c in conn.execute("SELECT * FROM comments ORDER BY created_at DESC LIMIT 20"):
            recent_comments.append({"kind": "post", "id": c["id"], "author": author_of(conn, c["user_id"]),
                                    "text": c["text"], "created_at": c["created_at"]})
        for c in conn.execute("SELECT * FROM scholar_comments ORDER BY created_at DESC LIMIT 20"):
            recent_comments.append({"kind": "scholar", "id": c["id"], "author": author_of(conn, c["user_id"]),
                                    "text": c["text"], "created_at": c["created_at"], "slug": c["slug"]})
        recent_comments.sort(key=lambda x: x["created_at"], reverse=True)
        result["admin"] = {
            "tickets": [serialize_ticket(conn, t, True) for t in conn.execute(
                "SELECT * FROM support_tickets ORDER BY created_at DESC"
            )],
            "reports": [serialize_report(conn, r, True) for r in conn.execute(
                "SELECT * FROM user_reports ORDER BY created_at DESC"
            )],
            "users": [{**user_public(u), "blocked": bool(u["blocked"]), "is_admin": bool(u["is_admin"])}
                      for u in conn.execute("SELECT * FROM users WHERE is_community=0 ORDER BY display_name")],
            "comments": recent_comments[:30],
            "hidden_books": [dict(b) for b in conn.execute(
                "SELECT id,title,author,hidden_reason FROM books WHERE hidden=1 ORDER BY id DESC LIMIT 100"
            )],
            "book_requests": [serialize_book_request(conn, r) for r in conn.execute(
                "SELECT * FROM book_requests ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, created_at DESC LIMIT 100"
            )],
        }
    return result


# ---------------------------------------------------------------------------
# Katalog yazarı sıralaması: Türk alfabesine göre A→Z, semboller en sonda
# ---------------------------------------------------------------------------

TR_AUTHOR_ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"
TR_AUTHOR_LOWER = str.maketrans({"I": "ı", "İ": "i"})
TR_AUTHOR_RANK = {ch: index for index, ch in enumerate(TR_AUTHOR_ALPHABET)}


def tr_author_fold(value) -> str:
    return str(value or "").translate(TR_AUTHOR_LOWER).lower()


def tr_author_char(value: str) -> str:
    """Bir karakteri Türk alfabesindeki karşılığına indirger (Â→a, É→e)."""
    folded = tr_author_fold(value)
    if folded in TR_AUTHOR_RANK:
        return folded
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", folded)
        if not unicodedata.combining(ch)
    )
    stripped = tr_author_fold(stripped)
    return stripped[:1] or folded


def catalog_author_sort_key(name: str) -> tuple:
    text = str(name or "").strip()
    folded = tr_author_fold(text)
    first = tr_author_char(folded[:1]) if folded else ""
    bucket = 0 if first in TR_AUTHOR_RANK else 1
    ranks = tuple(
        TR_AUTHOR_RANK.get(tr_author_char(ch), len(TR_AUTHOR_RANK) + ord(ch))
        for ch in folded
    )
    return (bucket, ranks, folded, text)


# ---------------------------------------------------------------------------
# HTTP sunucusu
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "IlimHalkasi/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # Konsolu temiz tut; sadece hataları göster.
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    # ---- yanıt yardımcıları ----

    def secure_cookie_suffix(self) -> str:
        forwarded = self.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower()
        return "; Secure" if (COOKIE_SECURE or forwarded == "https") else ""

    def send_json(self, data: dict, status: int = 200, cookie: str | None = None, clear_cookie: bool = False) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header(
                "Set-Cookie",
                f"ih_session={cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}"
                f"{self.secure_cookie_suffix()}",
            )
        if clear_cookie:
            self.send_header(
                "Set-Cookie",
                "ih_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + self.secure_cookie_suffix(),
            )
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        item = STATIC_FILES.get(path)
        if not item:
            self.send_json({"error": "Sayfa bulunamadı"}, 404)
            return
        filename, content_type = item
        file_path = BASE / filename
        if not file_path.exists():
            self.send_json({"error": "Dosya bulunamadı: " + filename}, 404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # WebView eski CSS/JS'yi önbellekten okumasın; buton yazıları hemen güncellensin.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if not length:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def current_user(self) -> sqlite3.Row | None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get("ih_session")
        if not morsel:
            return None
        conn = connect()
        try:
            row = conn.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
                "WHERE s.token=? AND s.expires_at>?",
                (morsel.value, int(now())),
            ).fetchone()
            return row if row and not row["blocked"] else None
        finally:
            conn.close()

    def require_user(self) -> sqlite3.Row | None:
        user = self.current_user()
        if not user:
            self.send_json({"error": "Giriş yapmalısın"}, 401)
        return user

    # ---- GET ----

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if not path.startswith("/api/"):
            self.serve_static(path)
            return

        if path == "/api/me":
            user = self.current_user()
            return self.send_json({"user": user_me(user) if user else None})

        if path == "/api/bootstrap":
            # Giriş yapmasa da herkese açık içerik yüklenir; state.user null olur.
            user = self.current_user()
            conn = connect()
            try:
                return self.send_json(build_bootstrap(conn, user["id"] if user else None))
            finally:
                conn.close()

        if path == "/api/posts/recent":
            viewer = self.require_user()
            if not viewer:
                return
            params = urllib.parse.parse_qs(parsed.query)
            try:
                after = float(params.get("after", ["0"])[0])
            except (TypeError, ValueError):
                after = 0
            conn = connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM posts WHERE created_at>? OR COALESCE(NULLIF(updated_at,0),created_at)>? "
                    "ORDER BY created_at DESC LIMIT 50",
                    (after, after),
                ).fetchall()
                deleted = [
                    r[0] for r in conn.execute(
                        "SELECT id FROM deleted_posts WHERE deleted_at>? ORDER BY deleted_at DESC LIMIT 200",
                        (after,),
                    ).fetchall()
                ]
                return self.send_json({
                    "posts": [serialize_post(conn, p, viewer["id"]) for p in rows],
                    "deleted": deleted,
                    "serverTime": now(),
                })
            finally:
                conn.close()

        if path == "/api/me/interactions":
            viewer = self.require_user()
            if not viewer:
                return
            return self.list_interactions(viewer["id"])

        if path == "/api/book-requests":
            viewer = self.require_user()
            if not viewer:
                return
            conn = connect()
            try:
                return self.send_json({"book_requests": [serialize_book_request(conn, r) for r in conn.execute(
                    "SELECT * FROM book_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 50",
                    (viewer["id"],)
                )]})
            finally:
                conn.close()

        if path == "/api/notifications":
            viewer = self.require_user()
            if not viewer:
                return
            conn = connect()
            try:
                return self.send_json({
                    "notifications": notifications_for(conn, viewer["id"]),
                    "serverTime": now(),
                })
            finally:
                conn.close()

        if path in ("/api/users/search", "/api/users/recommended"):
            viewer = self.current_user() or {"id": 0}
            conn = connect()
            try:
                if path == "/api/users/search":
                    query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
                    if len(query) < 2:
                        return self.send_json({"users": []})
                    needle = query.casefold()
                    rows = conn.execute(
                        "SELECT * FROM users WHERE id<>? AND is_community=0 AND blocked=0 "
                        "ORDER BY display_name COLLATE NOCASE",
                        (viewer["id"],)
                    ).fetchall()
                    matches = [
                        row for row in rows
                        if needle in (row["display_name"] or "").casefold()
                        or needle in (row["username"] or "").casefold()
                        or needle in (row["email"] or "").split("@")[0].casefold()
                    ]
                    users = []
                    for row in matches:
                        if is_blocked_pair(conn, viewer["id"], row["id"]):
                            continue
                        data = public_user_state(conn, viewer["id"], row)
                        data["shared"] = []
                        users.append(data)
                        if len(users) >= 12:
                            break
                    return self.send_json({"users": users})

                mine = set(user_interests(conn, viewer["id"]))
                followed = {
                    r[0] for r in conn.execute(
                        "SELECT followed_id FROM follows WHERE follower_id=?", (viewer["id"],)
                    )
                }
                candidates = conn.execute(
                    "SELECT * FROM users WHERE id<>? AND is_community=0 "
                    "AND blocked=0 ORDER BY created_at DESC LIMIT 40", (viewer["id"],)
                ).fetchall()
                scored = []
                for row in candidates:
                    if row["id"] in followed or is_blocked_pair(conn, viewer["id"], row["id"]):
                        continue
                    interests = user_interests(conn, row["id"])
                    shared = [value for value in interests if value in mine]
                    if shared:
                        scored.append((len(shared), row, shared[:3]))
                scored.sort(key=lambda item: (-item[0], item[1]["display_name"].casefold()))
                if not scored:
                    scored = [(0, row, []) for row in candidates[:6]
                              if row["id"] not in followed and not is_blocked_pair(conn, viewer["id"], row["id"])]
                users = []
                for _, row, shared in scored[:8]:
                    data = public_user_state(conn, viewer["id"], row)
                    data["shared"] = shared
                    users.append(data)
                return self.send_json({"users": users})
            finally:
                conn.close()

        match = re.fullmatch(r"/api/users/(\d+)/(followers|following)", path)
        if match:
            viewer = self.current_user() or {"id": 0}
            target_id = int(match.group(1))
            mode = match.group(2)
            conn = connect()
            try:
                target = conn.execute(
                    "SELECT id FROM users WHERE id=? AND is_community=0 AND blocked=0", (target_id,)
                ).fetchone()
                if not target:
                    return self.send_json({"error": "Kullanıcı bulunamadı"}, 404)
                if target_id != viewer["id"] and is_blocked_pair(conn, viewer["id"], target_id):
                    return self.send_json({"error": "Bu kullanıcıya erişilemiyor"}, 403)
                if mode == "followers":
                    rows = conn.execute(
                        "SELECT u.* FROM follows f JOIN users u ON u.id=f.follower_id "
                        "WHERE f.followed_id=? AND u.is_community=0 AND u.blocked=0 ORDER BY u.display_name COLLATE NOCASE ASC",
                        (target_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT u.* FROM follows f JOIN users u ON u.id=f.followed_id "
                        "WHERE f.follower_id=? AND u.is_community=0 AND u.blocked=0 ORDER BY u.display_name COLLATE NOCASE ASC",
                        (target_id,),
                    ).fetchall()
                users = []
                for row in rows:
                    if row["id"] == viewer["id"]:
                        users.append(user_me(row))
                    elif is_blocked_pair(conn, viewer["id"], row["id"]):
                        continue
                    else:
                        users.append(public_user_state(conn, viewer["id"], row))
                return self.send_json({"users": users})
            finally:
                conn.close()

        match = re.fullmatch(r"/api/users/(\d+)", path)
        if match:
            viewer = self.current_user() or {"id": 0}
            target_id = int(match.group(1))
            conn = connect()
            try:
                row = conn.execute(
                    "SELECT * FROM users WHERE id=? AND is_community=0 AND blocked=0", (target_id,)
                ).fetchone()
                if not row or target_id == viewer["id"]:
                    return self.send_json({"error": "Kullanıcı bulunamadı"}, 404)
                if conn.execute(
                    "SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?",
                    (target_id, viewer["id"])
                ).fetchone():
                    return self.send_json({"error": "Bu kullanıcı engelli"}, 403)
                return self.send_json({"user": serialize_public_profile(conn, viewer["id"], row)})
            finally:
                conn.close()

        if path == "/api/books":
            params = urllib.parse.parse_qs(parsed.query)
            query = params.get("q", [""])[0].strip()
            genre = params.get("genre", [""])[0].strip()
            category = params.get("category", [""])[0].strip()
            author = params.get("author", [""])[0].strip()
            publisher = params.get("publisher", [""])[0].strip()
            focus = params.get("focus", [""])[0].strip()
            try:
                limit = max(1, min(200, int(params.get("limit", ["100"])[0])))
                offset = max(0, int(params.get("offset", ["0"])[0]))
            except ValueError:
                limit, offset = 100, 0
            try:
                decade = int(params.get("decade", [""])[0].strip())
                decade = min(2990, max(1000, decade // 10 * 10))
            except ValueError:
                decade = None
            sort = BOOK_SORT_SQL.get(params.get("sort", ["title"])[0].strip(), BOOK_SORT_SQL["title"])

            sql = "SELECT * FROM books WHERE hidden=0"
            args: list = []
            if query:
                sql += " AND (title LIKE ? OR original_title LIKE ? OR author LIKE ? OR genre LIKE ?)"
                args.extend([f"%{query}%"] * 4)
            if author:
                if params.get("author_exact", [""])[0].strip() == "1":
                    sql += " AND author=?"
                    args.append(author)
                else:
                    sql += " AND author LIKE ?"
                    args.append(f"%{author}%")
            if genre and genre != "all":
                sql += " AND (genre LIKE ? OR category LIKE ?)"
                args.extend([f"%{genre}%", f"%{genre}%"])
            if category and category != "all":
                sql += " AND category=?"
                args.append(category)
            if publisher:
                if params.get("publisher_exact", [""])[0].strip() == "1":
                    sql += " AND publisher=?"
                    args.append(publisher)
                else:
                    sql += " AND publisher LIKE ?"
                    args.append(f"%{publisher}%")
            if decade is not None:
                sql += " AND year BETWEEN ? AND ?"
                args.extend([decade, decade + 9])
            if focus in FOCUS_SQL:
                sql += FOCUS_SQL[focus]
                if focus == "islamic":
                    args.extend(ISLAMIC_CATEGORIES)

            conn = connect()
            try:
                total = conn.execute(
                    "SELECT COUNT(*) FROM (" + sql + ")", args
                ).fetchone()[0]
                books = [dict(r) for r in conn.execute(
                    sql + " ORDER BY " + sort + " LIMIT ? OFFSET ?", args + [limit, offset]
                )]
                genres = sorted({
                    part.strip()
                    for row in conn.execute("SELECT genre FROM books WHERE hidden=0")
                    for part in (row["genre"] or "").split(",")
                    if part.strip()
                }, key=catalog_author_sort_key)
                return self.send_json({
                    "books": books, "genres": genres,
                    "total": total, "offset": offset, "limit": limit
                })
            finally:
                conn.close()

        if path == "/api/books/filters":
            conn = connect()
            try:
                genres = sorted({
                    part.strip()
                    for row in conn.execute("SELECT genre FROM books WHERE hidden=0")
                    for part in (row["genre"] or "").split(",")
                    if part.strip()
                }, key=catalog_author_sort_key)
                decades = sorted({
                    (row[0] // 10) * 10 for row in conn.execute(
                        "SELECT year FROM books WHERE hidden=0 AND year BETWEEN 1000 AND 2100"
                    )
                }, reverse=True)
                return self.send_json({
                    "authors": sorted({(row[0] or "").strip() for row in conn.execute(
                        "SELECT DISTINCT author FROM books WHERE hidden=0 AND author<>''"
                    ) if (row[0] or "").strip()}, key=catalog_author_sort_key),
                    "publishers": sorted({(row[0] or "").strip() for row in conn.execute(
                        "SELECT DISTINCT publisher FROM books WHERE hidden=0 AND publisher<>''"
                    ) if (row[0] or "").strip()}, key=catalog_author_sort_key),
                    "categories": sorted({(row[0] or "").strip() for row in conn.execute(
                        "SELECT DISTINCT category FROM books WHERE hidden=0"
                    ) if (row[0] or "").strip()}, key=catalog_author_sort_key),
                    "genres": genres,
                    "decades": decades,
                })
            finally:
                conn.close()

        if path == "/api/catalog-authors":
            conn = connect()
            try:
                counts: dict[str, int] = {}
                for row in conn.execute(
                    "SELECT author FROM books WHERE hidden=0 AND author<>''"
                ):
                    name = (row["author"] or "").strip()
                    if name:
                        counts[name] = counts.get(name, 0) + 1
                authors = [
                    {"name": name, "count": count}
                    for name, count in sorted(
                        counts.items(), key=lambda item: catalog_author_sort_key(item[0])
                    )
                ]
                return self.send_json({"authors": authors, "total": len(authors)})
            finally:
                conn.close()

        if path == "/api/books/search":
            query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
            if len(query) < 2:
                return self.send_json({"books": [], "source": "local"})
            return self.search_books(query)

        self.send_json({"error": "Bulunamadı"}, 404)

    def search_books(self, query: str) -> None:
        conn = connect()
        contact = re.sub(r"[^\x20-\x7E]+", "", os.environ.get("IH_CONTACT_EMAIL", "")).strip()
        agent = {"User-Agent": "IlimHalkasi/1.0 (book-catalog; mailto:" + contact + ")"
                 if contact else "IlimHalkasi/1.0 (book-catalog)"}
        google_key = os.environ.get("GOOGLE_BOOKS_API_KEY", "").strip()
        try:
            local = [dict(r) for r in conn.execute(
                "SELECT * FROM books WHERE hidden=0 AND "
                "(title LIKE ? OR original_title LIKE ? OR author LIKE ? OR genre LIKE ?) LIMIT 20",
                (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
            )]
            if len(local) >= 5:
                return self.send_json({"books": local, "source": "local"})

            results = local
            source = "local"
            seen = {b["id"] for b in results}

            def merge(found: list[dict], name: str) -> None:
                nonlocal source
                added = [b for b in found if b["id"] not in seen]
                for book in added:
                    seen.add(book["id"])
                if added:
                    results.extend(added)
                    source = name

            # 1) Google Books — Türkçe ticari kitaplar için tür + kapak + özet tek istekte gelir.
            try:
                url = ("https://www.googleapis.com/books/v1/volumes?maxResults=10&langRestrict=tr"
                       "&printType=books&projection=full&q=" + urllib.parse.quote(query))
                if google_key:
                    url += "&key=" + urllib.parse.quote(google_key)
                request = urllib.request.Request(url, headers=agent)
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.load(response)
                found = []
                for item in payload.get("items", []):
                    info = item.get("volumeInfo", {})
                    identifiers = info.get("industryIdentifiers") or []
                    isbn = next(
                        (row.get("identifier", "") for row in identifiers
                         if row.get("type") in ("ISBN_13", "ISBN_10")),
                        identifiers[0].get("identifier", "") if identifiers else "",
                    )
                    image = info.get("imageLinks") or {}
                    cached = cache_book(conn, {
                        "title": info.get("title"),
                        "author": ", ".join(info.get("authors") or []),
                        "category": "Keşfedilen",
                        "cover": cover_url(image.get("thumbnail") or image.get("smallThumbnail")),
                        "isbn": isbn,
                        "description": clean_text(info.get("description")),
                        "genre": book_genre(info.get("categories") or []),
                        "year": book_year(info.get("publishedDate")),
                        "rating": info.get("averageRating"),
                        "rating_count": info.get("ratingsCount"),
                        "publisher": info.get("publisher"),
                        "page_count": info.get("pageCount"),
                        "source": "google",
                    })
                    if cached and not cached.get("hidden"):
                        found.append(cached)
                conn.commit()
                merge(found, "google")
            except Exception:
                pass  # Google erişilemezse Open Library'ye geç.

            # 2) Open Library — anahtarsız yedek katalog; konu, puan ve kapak bilgisi de gelir.
            if len(results) < 5:
                try:
                    fields = ("key,title,author_name,first_publish_year,cover_i,isbn,subject,"
                              "genre_name,description,ratings_average,ratings_count,language,publisher")
                    url = ("https://openlibrary.org/search.json?limit=10&fields="
                           + urllib.parse.quote(fields) + "&q=" + urllib.parse.quote(query))
                    request = urllib.request.Request(url, headers=agent)
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = json.load(response)
                    docs = payload.get("docs", [])
                    tokens = [part for part in re.split(r"\s+", query.casefold()) if len(part) > 2]
                    def rank(doc: dict) -> int:
                        title = str(doc.get("title") or "").casefold()
                        language = doc.get("language") or []
                        return (0 if "tur" in language else 1) + (0 if any(t in title for t in tokens) else 1)
                    docs.sort(key=rank)
                    found = []
                    for doc in docs[:10]:
                        cover_id = doc.get("cover_i")
                        subjects = doc.get("subject") or []
                        genre_names = doc.get("genre_name") or []
                        isbns = doc.get("isbn") or []
                        if isinstance(subjects, str):
                            subjects = [subjects]
                        if isinstance(genre_names, str):
                            genre_names = [genre_names]
                        if isinstance(isbns, str):
                            isbns = [isbns]
                        cached = cache_book(conn, {
                            "title": doc.get("title"),
                            "author": ", ".join((doc.get("author_name") or [])[:3]),
                            "category": "Keşfedilen",
                            "cover": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else "",
                            "isbn": isbns[0] if isbns else "",
                            "description": clean_text(doc.get("description")),
                            "genre": book_genre(subjects + genre_names),
                            "year": book_year(doc.get("first_publish_year")),
                            "rating": doc.get("ratings_average"),
                            "rating_count": doc.get("ratings_count"),
                            "publisher": (doc.get("publisher") or [""])[0],
                            "work_key": doc.get("key", ""),
                            "source": "openlibrary",
                        })
                        if cached and not cached.get("hidden"):
                            found.append(cached)
                    conn.commit()
                    merge(found, "openlibrary")
                except Exception:
                    pass

            return self.send_json({"books": results[:20], "source": source})
        finally:
            conn.close()

    # ---- POST ----

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        body = self.read_json()

        if path == "/api/register":
            return self.register(body)
        if path == "/api/login":
            return self.login(body)
        if path == "/api/forgot-password":
            return self.forgot_password(body)
        if path == "/api/reset-password":
            return self.reset_password(body)
        if path == "/api/logout":
            token = self.session_token()
            if token:
                conn = connect()
                conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                conn.commit()
                conn.close()
            return self.send_json({"ok": True}, clear_cookie=True)

        user = self.require_user()
        if not user:
            return
        uid = user["id"]

        if path == "/api/posts":
            return self.create_post(uid, body)
        if path == "/api/notes":
            return self.create_note(uid, body)
        if path == "/api/shelf":
            return self.upsert_shelf(uid, body)
        if path == "/api/lists":
            return self.create_list(uid, body)
        if path == "/api/lists/add":
            return self.add_to_list(uid, body)
        if path == "/api/lists/update":
            return self.update_list(uid, body)
        if path == "/api/lists/delete":
            return self.delete_list(uid, body)
        if path == "/api/debates":
            return self.create_debate(uid, body)
        if path == "/api/chat":
            return self.send_chat(uid, body)
        if path == "/api/support":
            return self.create_ticket(uid, body)
        if path == "/api/book-requests":
            return self.create_book_request(uid, body)
        if path == "/api/reports":
            return self.create_report(uid, body)
        if path == "/api/follow":
            return self.toggle_follow_user(uid, body)
        if path == "/api/block":
            return self.toggle_block_user(uid, body)
        if path == "/api/profile":
            return self.update_profile(uid, body)
        if path == "/api/account/delete":
            return self.delete_account(uid, body)
        if path == "/api/groups/halka":
            return self.create_halka(uid, body)
        if path == "/api/groups/meclis":
            return self.create_meclis(uid, body)
        if path == "/api/groups/direct":
            return self.create_direct(uid, body)

        match = re.fullmatch(r"/api/groups/(\d+)/messages", path)
        if match:
            return self.send_group_message(uid, int(match.group(1)), body)
        match = re.fullmatch(r"/api/groups/(\d+)/(join|leave)", path)
        if match:
            return self.toggle_membership(uid, int(match.group(1)), match.group(2))

        match = re.fullmatch(r"/api/scholars/([a-z0-9-]+)/comments", path)
        if match:
            return self.add_scholar_comment(uid, match.group(1), body)
        match = re.fullmatch(r"/api/admin/announcements", path)
        if match:
            return self.create_announcement(uid, body)
        match = re.fullmatch(r"/api/admin/announcements/(\d+)/delete", path)
        if match:
            return self.delete_announcement(uid, int(match.group(1)))
        match = re.fullmatch(r"/api/admin/tickets/(\d+)/(reply|close)", path)
        if match:
            return self.handle_ticket(uid, int(match.group(1)), match.group(2), body)
        match = re.fullmatch(r"/api/admin/reports/(\d+)/(reply|close)", path)
        if match:
            return self.handle_report(uid, int(match.group(1)), match.group(2), body)
        match = re.fullmatch(r"/api/admin/comments/(post|scholar)/(\d+)/delete", path)
        if match:
            return self.delete_comment(uid, match.group(1), int(match.group(2)))
        match = re.fullmatch(r"/api/admin/book-requests/(\d+)/review", path)
        if match:
            return self.review_book_request(uid, int(match.group(1)), body)
        match = re.fullmatch(r"/api/admin/books/(\d+)/moderate", path)
        if match:
            return self.moderate_book(uid, int(match.group(1)), body)
        match = re.fullmatch(r"/api/admin/books/(\d+)/volumes", path)
        if match:
            return self.set_book_volumes(uid, int(match.group(1)), body)
        match = re.fullmatch(r"/api/admin/users/(\d+)/block", path)
        if match:
            return self.toggle_block(uid, int(match.group(1)))

        match = re.fullmatch(r"/api/posts/(\d+)/(like|favorite)", path)
        if match:
            return self.toggle_post_flag(uid, int(match.group(1)), match.group(2))
        match = re.fullmatch(r"/api/posts/(\d+)/(update|delete)", path)
        if match:
            if match.group(2) == "update":
                return self.update_own_post(uid, int(match.group(1)), body)
            return self.delete_own_post(uid, int(match.group(1)))
        match = re.fullmatch(r"/api/posts/(\d+)/comments", path)
        if match:
            return self.add_comment(uid, int(match.group(1)), body)
        match = re.fullmatch(r"/api/comments/(\d+)/like", path)
        if match:
            return self.toggle_comment_like(uid, int(match.group(1)))
        match = re.fullmatch(r"/api/notes/(\d+)/share", path)
        if match:
            return self.share_note(uid, int(match.group(1)))
        match = re.fullmatch(r"/api/notes/(\d+)/(update|delete)", path)
        if match:
            if match.group(2) == "update":
                return self.update_own_note(uid, int(match.group(1)), body)
            return self.delete_own_note(uid, int(match.group(1)))
        match = re.fullmatch(r"/api/debates/(\d+)/answers", path)
        if match:
            return self.add_answer(uid, int(match.group(1)), body)
        match = re.fullmatch(r"/api/follows/(\d+)", path)
        if match:
            return self.toggle_follow(uid, int(match.group(1)))
        match = re.fullmatch(r"/api/curricula/([a-z0-9_-]+)/steps/(\d+)/progress", path)
        if match:
            return self.set_curriculum_progress(uid, match.group(1), int(match.group(2)), body)
        match = re.fullmatch(r"/api/curricula/([a-z0-9_-]+)/follow", path)
        if match:
            return self.toggle_key(uid, "curriculum_follows", "c_key", match.group(1))
        match = re.fullmatch(r"/api/assemblies/([a-z0-9_-]+)/rsvp", path)
        if match:
            return self.toggle_key(uid, "assembly_rsvps", "a_key", match.group(1))

        self.send_json({"error": "Bulunamadı"}, 404)

    def session_token(self) -> str | None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get("ih_session")
        return morsel.value if morsel else None

    # ---- kimlik ----

    def register(self, body: dict) -> None:
        email = str(body.get("email", "")).strip().lower()
        username = str(body.get("username", "")).strip().lower()
        display_name = str(body.get("display_name", "")).strip()
        password = str(body.get("password", ""))

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return self.send_json({"error": "Geçerli bir e-posta adresi gir"}, 400)
        if not re.fullmatch(r"[a-z0-9_]{3,20}", username):
            return self.send_json({"error": "Kullanıcı adı 3-20 karakter, sadece harf/rakam/alt çizgi olabilir"}, 400)
        if len(password) < 8:
            return self.send_json({"error": "Şifre en az 8 karakter olmalı"}, 400)
        display_name = display_name or username

        salt, digest = hash_password(password)
        conn = connect()
        try:
            if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                return self.send_json({"error": "Bu e-posta zaten kayıtlı"}, 409)
            if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                return self.send_json({"error": "Bu kullanıcı adı alınmış"}, 409)
            cur = conn.execute(
                "INSERT INTO users (email,username,password_hash,salt,display_name,bio,avatar,title,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (email, username, digest, salt, display_name, "", "olive", "Talebe", now()),
            )
            uid = cur.lastrowid
            # Yeni hesaplar boş başlar: örnek raf, not veya otomatik takip eklenmez.
            expires = int(now() + SESSION_DAYS * 86400)
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions (token,user_id,expires_at) VALUES (?,?,?)", (token, uid, expires))
            conn.execute(
                "INSERT OR IGNORE INTO book_lists (user_id,name,created_at) VALUES (?,?,?)",
                (uid, "Favorilerim", now()),
            )
            conn.execute(
                "INSERT OR REPLACE INTO user_meta (user_id,key,value) VALUES (?,?,?)",
                (uid, "favorites_seeded", "1"),
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return self.send_json({"user": user_me(user)}, cookie=token)
        finally:
            conn.close()

    def login(self, body: dict) -> None:
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        conn = connect()
        try:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if user and user["blocked"]:
                return self.send_json({"error": "Hesabın yönetici tarafından askıya alındı"}, 403)
            if not user or user["is_community"] or not verify_password(password, user["salt"], user["password_hash"]):
                return self.send_json({"error": "E-posta veya şifre hatalı"}, 401)
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO sessions (token,user_id,expires_at) VALUES (?,?,?)",
                (token, user["id"], int(now() + SESSION_DAYS * 86400)),
            )
            conn.commit()
            return self.send_json({"user": user_me(user)}, cookie=token)
        finally:
            conn.close()

    def send_reset_email(self, email: str, name: str, link: str) -> tuple[bool, str]:
        message = EmailMessage()
        message["Subject"] = "İlim Halkası — Şifre sıfırlama"
        message["From"] = SMTP_FROM
        message["To"] = email
        message.set_content(
            f"Merhaba {name},\n\n"
            "Şifreni sıfırlamak için aşağıdaki bağlantıyı kullanabilirsin "
            f"(1 saat geçerli):\n\n{link}\n\n"
            "Bu isteği sen yapmadıysan bu e-postayı yok sayabilirsin.\n\n"
            "İlim Halkası"
        )
        if SMTP_HOST:
            try:
                context = ssl.create_default_context()
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
                    if SMTP_USE_TLS:
                        smtp.starttls(context=context)
                    if SMTP_USER:
                        smtp.login(SMTP_USER, SMTP_PASSWORD)
                    smtp.send_message(message)
                return True, ""
            except Exception as exc:  # SMTP hatası yerel kutuya düşer.
                detail = f"E-posta gönderilemedi: {exc}"
        else:
            detail = "SMTP ayarlanmadı; bağlantı yerel kutuya kaydedildi."
        try:
            with RESET_OUTBOX.open("a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {email} | {link}\n")
        except OSError as exc:
            detail += f" Yerel kayıt yazılamadı: {exc}"
        return False, detail

    def forgot_password(self, body: dict) -> None:
        email = str(body.get("email", "")).strip().lower()
        conn = connect()
        try:
            user = conn.execute(
                "SELECT * FROM users WHERE email=? AND is_community=0 AND is_admin=0 AND is_system=0", (email,)
            ).fetchone()
            # Kullanıcı yoksayılamadığında da aynı yanıt döner; hesap varlığı sızmaz.
            if not user:
                return self.send_json({
                    "ok": True,
                    "message": "E-posta kayıtlıysa sıfırlama bağlantısı gönderildi."
                })
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            created = now()
            conn.execute(
                "UPDATE password_resets SET used=1 WHERE user_id=? AND used=0", (user["id"],)
            )
            conn.execute(
                "INSERT INTO password_resets (token_hash,user_id,expires_at,created_at) "
                "VALUES (?,?,?,?)",
                (token_hash, user["id"], int(created + RESET_TTL_SECONDS), int(created)),
            )
            conn.commit()
            link = f"{APP_BASE_URL}/?reset={token}"
            sent, detail = self.send_reset_email(email, user["display_name"], link)
            result = {
                "ok": True,
                "message": "E-posta kayıtlıysa sıfırlama bağlantısı gönderildi."
            }
            if not sent and DEV_RESET_LINK:
                result["dev_link"] = link
                result["note"] = detail
            return self.send_json(result)
        finally:
            conn.close()

    def reset_password(self, body: dict) -> None:
        token = str(body.get("token", "")).strip()
        password = str(body.get("password", ""))
        if not token:
            return self.send_json({"error": "Sıfırlama bağlantısı geçersiz"}, 400)
        if len(password) < 8:
            return self.send_json({"error": "Yeni şifre en az 8 karakter olmalı"}, 400)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM password_resets WHERE token_hash=? AND used=0 AND expires_at>?",
                (token_hash, int(now())),
            ).fetchone()
            if not row:
                return self.send_json({"error": "Sıfırlama bağlantısı geçersiz veya süresi dolmuş"}, 400)
            user = conn.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
            if not user:
                return self.send_json({"error": "Kullanıcı bulunamadı"}, 400)
            if user["is_admin"] or (user["is_system"] if "is_system" in user.keys() else 0):
                return self.send_json({"error": "Bu hesabın şifresi sıfırlanamaz"}, 403)
            salt, digest = hash_password(password)
            conn.execute("UPDATE users SET salt=?, password_hash=? WHERE id=?", (salt, digest, user["id"]))
            conn.execute("UPDATE password_resets SET used=1 WHERE token_hash=?", (token_hash,))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            conn.commit()
            return self.send_json({
                "ok": True,
                "message": "Şifren güncellendi. Yeniden giriş yapabilirsin."
            })
        finally:
            conn.close()

    def update_profile(self, uid: int, body: dict) -> None:
        display_name = str(body.get("display_name", "")).strip()
        username = str(body.get("username", "")).strip().lower()
        avatar = str(body.get("avatar", "")).strip()
        bio = str(body.get("bio", "")).strip()
        try:
            avatar_image = clean_avatar_image(body.get("avatar_image", ""))
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        if len(display_name) < 2 or len(display_name) > 60:
            return self.send_json({"error": "Görünen ad 2–60 karakter olmalı"}, 400)
        if not re.fullmatch(r"[a-z0-9_]{3,24}", username):
            return self.send_json({"error": "Kullanıcı adı 3–24 karakter, yalnızca küçük harf, rakam ve alt çizgi olabilir"}, 400)
        if avatar not in {"olive", "sand", "copper", "rose", "ink", "gold"}:
            return self.send_json({"error": "Geçerli bir avatar seç"}, 400)
        if len(bio) > 500:
            return self.send_json({"error": "Biyografi en fazla 500 karakter olabilir"}, 400)
        conn = connect()
        try:
            if conn.execute("SELECT 1 FROM users WHERE username=? AND id<>?", (username, uid)).fetchone():
                return self.send_json({"error": "Bu kullanıcı adı alınmış"}, 409)
            conn.execute(
                "UPDATE users SET display_name=?, username=?, avatar=?, avatar_image=?, bio=? WHERE id=?",
                (display_name, username, avatar, avatar_image, bio, uid),
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return self.send_json({"user": user_me(user), "message": "Profil güncellendi"})
        finally:
            conn.close()

    def delete_account(self, uid: int, body: dict) -> None:
        """Kullanıcının kendi hesabını kalıcı olarak silmesini sağlar."""
        password = str(body.get("password", ""))
        confirmation = str(body.get("confirmation", "")).strip().casefold()
        conn = connect()
        try:
            user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            if not user:
                return self.send_json({"error": "Hesap bulunamadı"}, 404)
            is_system = bool(user["is_system"]) if "is_system" in user.keys() else False
            if user["is_admin"] or is_system or user["is_community"]:
                return self.send_json({"error": "Bu hesap silinemez"}, 403)
            if not verify_password(password, user["salt"], user["password_hash"]):
                return self.send_json({"error": "Şifre hatalı"}, 401)
            if confirmation != str(user["username"]).casefold():
                return self.send_json({"error": "Onay için kullanıcı adını doğru yazmalısın"}, 400)

            # Özel sohbetler kullanıcıyla birlikte kaldırılır. Açık halka/meclis
            # sahipliği kalan üyeye devredilir; kimse kalmadıysa grup silinir.
            conn.execute(
                "DELETE FROM groups WHERE kind='direct' AND id IN "
                "(SELECT group_id FROM group_members WHERE user_id=?)", (uid,)
            )
            groups = conn.execute(
                "SELECT id FROM groups WHERE creator_id=? AND kind IN ('halka','meclis')", (uid,)
            ).fetchall()
            for group in groups:
                successor = conn.execute(
                    "SELECT user_id FROM group_members WHERE group_id=? AND user_id<>? "
                    "ORDER BY joined_at LIMIT 1", (group["id"], uid)
                ).fetchone()
                if successor:
                    conn.execute(
                        "UPDATE groups SET creator_id=? WHERE id=?",
                        (successor["user_id"], group["id"]),
                    )
            conn.execute("DELETE FROM users WHERE id=?", (uid,))
            conn.commit()
            return self.send_json({"ok": True, "message": "Hesabın kalıcı olarak silindi"}, clear_cookie=True)
        finally:
            conn.close()

    def require_admin(self, uid: int) -> bool:
        conn = connect()
        try:
            row = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        finally:
            conn.close()
        if not row or not row["is_admin"]:
            self.send_json({"error": "Bu işlem için yönetici yetkisi gerekli"}, 403)
            return False
        return True

    # ---- içerik ----

    def create_post(self, uid: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        book = str(body.get("book", "")).strip()
        if not text or not book:
            return self.send_json({"error": "Kitap ve alıntı alanları gerekli"}, 400)
        ptype = "review" if body.get("type") == "review" else "quote"
        try:
            rating = max(0, min(5, int(body.get("rating", 0) or 0)))
        except (ValueError, TypeError):
            rating = 0
        conn = connect()
        try:
            group_id = None
            if body.get("group_id") not in (None, "", 0, "0"):
                try:
                    group_id = int(body["group_id"])
                except (TypeError, ValueError):
                    return self.send_json({"error": "Geçersiz halka"}, 400)
                group = conn.execute("SELECT kind FROM groups WHERE id=?", (group_id,)).fetchone()
                joined = conn.execute(
                    "SELECT 1 FROM group_members WHERE group_id=? AND user_id=?", (group_id, uid)
                ).fetchone() is not None
                if not group or group["kind"] != "halka" or not joined:
                    return self.send_json({"error": "Bu halkada paylaşım yapmak için üye olmalısın"}, 403)
            cur = conn.execute(
                "INSERT INTO posts (user_id,type,book,writer,text,rating,status,cover,group_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uid, ptype, book, str(body.get("writer", ""))[:200], text[:5000], rating,
                 str(body.get("status", ""))[:60], str(body.get("cover", ""))[:30], group_id, now()),
            )
            post_id = cur.lastrowid
            if group_id:
                for member in conn.execute(
                    "SELECT user_id FROM group_members WHERE group_id=? AND user_id<>?",
                    (group_id, uid),
                ).fetchall():
                    add_notification(conn, member["user_id"], "circle_post", uid,
                                     post_id, group_id, text, str(group_id))
            notify_mentions(conn, text, uid, post_id, group_id)
            conn.commit()
            row = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
            return self.send_json({"post": serialize_post(conn, row, uid)}, 201)
        finally:
            conn.close()

    def update_own_post(self, uid: int, post_id: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        book = str(body.get("book", "")).strip()
        if not text or not book:
            return self.send_json({"error": "Kitap ve metin alanları gerekli"}, 400)
        try:
            rating = max(0, min(5, int(body.get("rating", 0) or 0)))
        except (ValueError, TypeError):
            rating = 0
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM posts WHERE id=? AND user_id=?", (post_id, uid)
            ).fetchone()
            if not row:
                return self.send_json({"error": "İnceleme veya alıntı bulunamadı"}, 404)
            conn.execute(
                "UPDATE posts SET book=?, writer=?, text=?, rating=?, updated_at=? WHERE id=? AND user_id=?",
                (book[:200], str(body.get("writer", row["writer"]))[:200],
                 text[:5000], rating, now(), post_id, uid),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
            return self.send_json({"post": serialize_post(conn, updated, uid)})
        finally:
            conn.close()

    def delete_own_post(self, uid: int, post_id: int) -> None:
        conn = connect()
        try:
            cur = conn.execute("DELETE FROM posts WHERE id=? AND user_id=?", (post_id, uid))
            if not cur.rowcount:
                return self.send_json({"error": "İnceleme veya alıntı bulunamadı"}, 404)
            conn.execute(
                "INSERT OR REPLACE INTO deleted_posts (id,deleted_at) VALUES (?,?)",
                (post_id, now()),
            )
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def create_note(self, uid: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            return self.send_json({"error": "Not boş olamaz"}, 400)
        visibility = str(body.get("visibility", "private"))
        if visibility not in ("private", "circle", "public"):
            visibility = "private"
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO notes (user_id,title,book,visibility,text,created_at) VALUES (?,?,?,?,?,?)",
                (uid, str(body.get("title", ""))[:200] or "Adsız not",
                 str(body.get("book", ""))[:200] or "Genel", visibility, text[:5000], now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM notes WHERE id=?", (cur.lastrowid,)).fetchone()
            return self.send_json({"note": dict(row)}, 201)
        finally:
            conn.close()

    def update_own_note(self, uid: int, note_id: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            return self.send_json({"error": "Not boş olamaz"}, 400)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM notes WHERE id=? AND user_id=?", (note_id, uid)
            ).fetchone()
            if not row:
                return self.send_json({"error": "Not bulunamadı"}, 404)
            visibility = str(body.get("visibility", row["visibility"]))
            if visibility not in ("private", "circle", "public"):
                visibility = row["visibility"]
            conn.execute(
                "UPDATE notes SET title=?, book=?, visibility=?, text=? WHERE id=? AND user_id=?",
                (str(body.get("title", row["title"]))[:200] or row["title"],
                 str(body.get("book", row["book"]))[:200] or row["book"],
                 visibility, text[:5000], note_id, uid),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            return self.send_json({"note": dict(updated)})
        finally:
            conn.close()

    def delete_own_note(self, uid: int, note_id: int) -> None:
        conn = connect()
        try:
            cur = conn.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, uid))
            if not cur.rowcount:
                return self.send_json({"error": "Not bulunamadı"}, 404)
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def upsert_shelf(self, uid: int, body: dict) -> None:
        try:
            book_id = int(body.get("book_id", 0))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz kitap"}, 400)
        status = str(body.get("status", "reading"))
        if status not in ("reading", "finished", "wishlist", "abandoned"):
            return self.send_json({"error": "Geçersiz raf"}, 400)
        try:
            rating = max(0, min(5, int(body.get("rating", 0) or 0)))
        except (ValueError, TypeError):
            rating = 0
        conn = connect()
        try:
            book_row = conn.execute(
                "SELECT page_count,volume_count FROM books WHERE id=?", (book_id,)
            ).fetchone()
            if not book_row:
                return self.send_json({"error": "Kitap bulunamadı"}, 404)
            # Toplam sayfa ve cilt sayısı katalogdan gelir; kullanıcı yalnızca güncel sayfayı girer.
            page_count = max(0, min(100000, int(book_row["page_count"] or 0)))
            volume_count = max(1, min(1000, int(book_row["volume_count"] or 1)))
            previous = conn.execute(
                "SELECT rating,page,progress,status,finished_at,volume FROM shelf_books "
                "WHERE user_id=? AND book_id=? LIMIT 1",
                (uid, book_id),
            ).fetchone()
            try:
                if previous:
                    rating = rating or previous["rating"]
                    page = int(body.get("page", previous["page"]) or 0)
                    volume = int(body.get("volume", previous["volume"] or 1) or 1)
                    progress = int(body.get("progress", previous["progress"]) or 0)
                else:
                    page = int(body.get("page", 0) or 0)
                    volume = int(body.get("volume", 1) or 1)
                    progress = int(body.get("progress", 0) or 0)
            except (ValueError, TypeError):
                return self.send_json({"error": "Geçersiz sayfa veya cilt değeri"}, 400)
            volume = max(1, min(volume_count, volume))
            page = max(0, min(page_count or 100000, page))
            if page_count > 0 and "page" in body:
                read_pages = (volume - 1) * page_count + page
                progress = min(100, round(read_pages * 100 / (page_count * volume_count)))
            if status == 'finished' and "page" not in body:
                progress = 100
            progress = max(0, min(100, progress))
            if status == 'finished':
                # Zaten bitirilmişse ilk bitirme tarihini koru; yeni bitirmede şimdiyi yaz.
                finished_at = (previous["finished_at"] if previous and previous["status"] == 'finished'
                               and previous["finished_at"] else now())
            else:
                finished_at = 0
            stamp = now()
            conn.execute("DELETE FROM shelf_books WHERE user_id=? AND book_id=?", (uid, book_id))
            conn.execute(
                "INSERT OR REPLACE INTO shelf_books "
                "(user_id,book_id,status,page,progress,rating,created_at,finished_at,page_count,volume) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uid, book_id, status, page, progress, rating, stamp, finished_at, page_count, volume),
            )
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def list_interactions(self, uid: int) -> None:
        """Beğenilen, favorilenen ve yorumlanan paylaşımları viewer'a göre döndürür."""
        conn = connect()
        try:
            groups = {
                "liked": (
                    "SELECT p.* FROM post_likes l JOIN posts p ON p.id=l.post_id "
                    "WHERE l.user_id=? ORDER BY p.created_at DESC LIMIT 100"
                ),
                "favorited": (
                    "SELECT p.* FROM post_favorites f JOIN posts p ON p.id=f.post_id "
                    "WHERE f.user_id=? ORDER BY p.created_at DESC LIMIT 100"
                ),
                "commented": (
                    "SELECT DISTINCT p.* FROM comments c JOIN posts p ON p.id=c.post_id "
                    "WHERE c.user_id=? ORDER BY p.created_at DESC LIMIT 100"
                ),
            }
            result = {}
            for key, sql in groups.items():
                result[key] = [serialize_post(conn, row, uid) for row in conn.execute(sql, (uid,))]
            return self.send_json(result)
        finally:
            conn.close()

    def create_book_request(self, uid: int, body: dict) -> None:
        title = clean_text(body.get("title")).strip()[:200]
        author = clean_text(body.get("author")).strip()[:200]
        about = clean_text(body.get("about")).strip()[:2000]
        try:
            page_count = int(body.get("page_count", 0) or 0)
        except (TypeError, ValueError):
            return self.send_json({"error": "Geçersiz sayfa sayısı"}, 400)
        page_count = max(0, min(page_count, 50000))
        if len(title) < 2 or not author:
            return self.send_json({"error": "Kitap adı ve yazarı gerekli"}, 400)
        try:
            cover = clean_book_image(body.get("cover", ""))
        except ValueError as error:
            return self.send_json({"error": str(error)}, 400)

        conn = connect()
        try:
            duplicate = conn.execute(
                "SELECT 1 FROM book_requests WHERE user_id=? AND lower(title)=lower(?) "
                "AND lower(author)=lower(?) AND status='pending'",
                (uid, title, author),
            ).fetchone()
            if duplicate:
                return self.send_json({"error": "Bu kitap önerisi zaten incelemede"}, 409)
            cur = conn.execute(
                "INSERT INTO book_requests (user_id,title,author,page_count,about,cover,status,created_at) "
                "VALUES (?,?,?,?,?,?,'pending',?)",
                (uid, title, author, page_count, about, cover, now()),
            )
            row = conn.execute("SELECT * FROM book_requests WHERE id=?", (cur.lastrowid,)).fetchone()
            actor = author_of(conn, uid).get("display_name") or "Bir kullanıcı"
            for admin in conn.execute(
                "SELECT id FROM users WHERE is_admin=1 AND blocked=0 AND is_system=0"
            ):
                add_notification(
                    conn, admin["id"], "book_request", uid, None, None,
                    f"{actor} kitap önerisi gönderdi: {title}", str(row["id"]),
                )
            conn.commit()
            return self.send_json({"request": serialize_book_request(conn, row)})
        finally:
            conn.close()

    def review_book_request(self, uid: int, request_id: int, body: dict) -> None:
        """Yönetici öneriyi onaylar (kitabı kataloğa ekler) veya reddeder."""
        if not self.require_admin(uid):
            return
        approve = bool(body.get("approve"))
        reason = clean_text(body.get("reason"))[:300]
        if not approve and not reason:
            return self.send_json({"error": "Ret gerekçesi gerekli"}, 400)
        conn = connect()
        try:
            row = conn.execute("SELECT * FROM book_requests WHERE id=?", (request_id,)).fetchone()
            if not row:
                return self.send_json({"error": "Kitap önerisi bulunamadı"}, 404)
            if row["status"] != "pending":
                return self.send_json({"error": "Bu öneri zaten incelendi"}, 409)
            book_id = row["book_id"]
            if approve:
                existing = conn.execute(
                    "SELECT * FROM books WHERE lower(title)=lower(?) AND lower(author)=lower(?)",
                    (row["title"], row["author"]),
                ).fetchone()
                if existing:
                    book_id = existing["id"]
                    if existing["hidden"]:
                        conn.execute(
                            "UPDATE books SET hidden=0, hidden_reason='' WHERE id=?", (book_id,)
                        )
                else:
                    book = cache_book(conn, {
                        "title": row["title"], "author": row["author"],
                        "category": "Keşfedilen", "cover": row["cover"],
                        "description": row["about"], "page_count": row["page_count"],
                        "source": "user_request",
                    })
                    if not book:
                        return self.send_json({"error": "Kitap kataloğa eklenemedi"}, 500)
                    book_id = book["id"]
            conn.execute(
                "UPDATE book_requests SET status=?, reason=?, book_id=?, reviewed_at=? WHERE id=?",
                ("approved" if approve else "rejected", reason, book_id, now(), request_id),
            )
            verb = "onaylandı ve kataloğa eklendi" if approve else f"reddedildi: {reason}"
            add_notification(
                conn, row["user_id"], "book_request", uid, None, None,
                f"“{row['title']}” önerin {verb}", str(request_id),
            )
            conn.commit()
            updated = conn.execute("SELECT * FROM book_requests WHERE id=?", (request_id,)).fetchone()
            return self.send_json({"ok": True, "request": serialize_book_request(conn, updated)})
        finally:
            conn.close()

    def set_curriculum_progress(self, uid: int, key: str, index: int, body: dict) -> None:
        curriculum = next((c for c in CURRICULA if c["key"] == key), None)
        if not curriculum or index < 0 or index >= len(curriculum["steps"]):
            return self.send_json({"error": "Müfredat adımı bulunamadı"}, 404)
        conn = connect()
        try:
            book = find_curriculum_book(conn, curriculum["steps"][index])
        finally:
            conn.close()
        if not book:
            return self.send_json({"error": "Bu adımın kitabı katalogda yok"}, 404)
        status = str(body.get("status", "")).strip()
        if status not in ("wishlist", "reading", "finished"):
            return self.send_json({"error": "Geçersiz okuma durumu"}, 400)
        try:
            page = max(0, int(body.get("page", 0) or 0))
        except (TypeError, ValueError):
            return self.send_json({"error": "Geçersiz sayfa değeri"}, 400)
        payload = {"book_id": book["id"], "status": status}
        if status != "finished" or page > 0:
            payload["page"] = page
        return self.upsert_shelf(uid, payload)

    def create_list(self, uid: int, body: dict) -> None:
        name = str(body.get("name", "")).strip()[:80]
        if not name:
            return self.send_json({"error": "Liste adı gerekli"}, 400)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM book_lists WHERE user_id=? AND name=?", (uid, name)
            ).fetchone()
            if not row:
                cur = conn.execute(
                    "INSERT INTO book_lists (user_id,name,created_at) VALUES (?,?,?)",
                    (uid, name, now()),
                )
                row = conn.execute("SELECT * FROM book_lists WHERE id=?", (cur.lastrowid,)).fetchone()
                conn.commit()
            return self.send_json({"list": {"id": row["id"], "name": row["name"], "books": []}})
        finally:
            conn.close()

    def update_list(self, uid: int, body: dict) -> None:
        try:
            list_id = int(body.get("list_id", 0))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz liste"}, 400)
        name = str(body.get("name", "")).strip()[:80]
        if not name:
            return self.send_json({"error": "Liste adı gerekli"}, 400)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT id FROM book_lists WHERE id=? AND user_id=?", (list_id, uid)
            ).fetchone()
            if not row:
                return self.send_json({"error": "Liste bulunamadı"}, 404)
            clash = conn.execute(
                "SELECT 1 FROM book_lists WHERE user_id=? AND name=? AND id<>?", (uid, name, list_id)
            ).fetchone()
            if clash:
                return self.send_json({"error": "Bu adda bir listen zaten var"}, 409)
            conn.execute("UPDATE book_lists SET name=? WHERE id=?", (name, list_id))
            conn.commit()
            return self.send_json({"ok": True, "list": {"id": list_id, "name": name}})
        finally:
            conn.close()

    def delete_list(self, uid: int, body: dict) -> None:
        try:
            list_id = int(body.get("list_id", 0))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz liste"}, 400)
        conn = connect()
        try:
            cur = conn.execute(
                "DELETE FROM book_lists WHERE id=? AND user_id=?", (list_id, uid)
            )
            if not cur.rowcount:
                return self.send_json({"error": "Liste bulunamadı"}, 404)
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def add_to_list(self, uid: int, body: dict) -> None:
        try:
            book_id = int(body.get("book_id", 0))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz kitap"}, 400)
        name = str(body.get("name", "")).strip()[:80]
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM books WHERE id=?", (book_id,)).fetchone():
                return self.send_json({"error": "Kitap bulunamadı"}, 404)
            try:
                list_id = int(body.get("list_id", 0))
            except (ValueError, TypeError):
                list_id = 0
            row = conn.execute(
                "SELECT * FROM book_lists WHERE id=? AND user_id=?", (list_id, uid)
            ).fetchone() if list_id else None
            if not row and name:
                row = conn.execute(
                    "SELECT * FROM book_lists WHERE user_id=? AND name=?", (uid, name)
                ).fetchone()
                if not row:
                    cur = conn.execute(
                        "INSERT INTO book_lists (user_id,name,created_at) VALUES (?,?,?)",
                        (uid, name, now()),
                    )
                    row = conn.execute("SELECT * FROM book_lists WHERE id=?", (cur.lastrowid,)).fetchone()
            if not row:
                return self.send_json({"error": "Liste seç veya yeni bir liste adı yaz"}, 400)
            conn.execute(
                "INSERT OR IGNORE INTO book_list_items (list_id,book_id,created_at) VALUES (?,?,?)",
                (row["id"], book_id, now()),
            )
            conn.commit()
            return self.send_json({"ok": True, "list_id": row["id"]})
        finally:
            conn.close()

    def create_debate(self, uid: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        book = str(body.get("book_title", "")).strip()
        if not text or not book:
            return self.send_json({"error": "Kitap ve soru gerekli"}, 400)
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO debates (book_title,user_id,text,created_at) VALUES (?,?,?,?)",
                (book, uid, text[:5000], now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def send_chat(self, uid: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        circle = str(body.get("circle", "")).strip()
        if not text or not circle:
            return self.send_json({"error": "Mesaj boş olamaz"}, 400)
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO chat_messages (circle,user_id,text,created_at) VALUES (?,?,?,?)",
                (circle[:120], uid, text[:2000], now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def _group_fields(self, body: dict) -> tuple[str, str, str]:
        name = str(body.get("name", "")).strip()
        description = str(body.get("description", "")).strip()
        if not 3 <= len(name) <= 60:
            raise ValueError("Grup adı 3–60 karakter olmalı")
        return name, description[:300], clean_avatar_image(body.get("avatar_image", ""))

    def _member_ids(self, conn: sqlite3.Connection, uid: int, body: dict) -> list[int]:
        raw_ids = body.get("member_ids", [])
        if not isinstance(raw_ids, list):
            raise ValueError("Geçerli bir üye listesi gönder")
        result: list[int] = []
        for raw in raw_ids:
            try:
                other = int(raw)
            except (ValueError, TypeError):
                continue
            if other == uid or other in result:
                continue
            row = conn.execute(
                "SELECT 1 FROM users WHERE id=? AND is_community=0 AND is_admin=0 AND blocked=0", (other,)
            ).fetchone()
            if row:
                result.append(other)
        return result

    def create_halka(self, uid: int, body: dict) -> None:
        """Halka: herkesin katılabileceği, sesli oturum olmayan geniş grup."""
        try:
            name, description, image = self._group_fields(body)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO groups (kind,name,description,creator_id,avatar_image,avatar_color,max_members,created_at) "
                "VALUES ('halka',?,?,?,?,'olive',500,?)",
                (name, description, uid, image, now()),
            )
            conn.execute(
                "INSERT INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
                (cur.lastrowid, uid, now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def create_meclis(self, uid: int, body: dict) -> None:
        """Meclis: en az 3, en fazla 50 kişilik özel grup; sesli dersler için ayrılmıştır."""
        try:
            name, description, image = self._group_fields(body)
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        conn = connect()
        try:
            others = self._member_ids(conn, uid, body)
            if not 2 <= len(others) <= 49:
                return self.send_json({"error": "Meclis için en az 2, en fazla 49 başka üye seçmelisin (toplam 3–50)"}, 400)
            cur = conn.execute(
                "INSERT INTO groups (kind,name,description,creator_id,avatar_image,avatar_color,max_members,created_at) "
                "VALUES ('meclis',?,?,?,?,'gold',50,?)",
                (name, description, uid, image, now()),
            )
            gid = cur.lastrowid
            ts = now()
            for member in [uid] + others:
                conn.execute(
                    "INSERT OR IGNORE INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
                    (gid, member, ts),
                )
            conn.commit()
            return self.send_json({"id": gid}, 201)
        finally:
            conn.close()

    def create_direct(self, uid: int, body: dict) -> None:
        username = str(body.get("username", "")).strip().lstrip("@").lower()
        conn = connect()
        try:
            other = conn.execute(
                "SELECT * FROM users WHERE username=? AND id<>? AND blocked=0", (username, uid)
            ).fetchone()
            if not other:
                return self.send_json({"error": "Bu kullanıcı bulunamadı"}, 400)
            if is_blocked_pair(conn, uid, other["id"]):
                return self.send_json({"error": "Bu kullanıcıyla mesajlaşamazsın"}, 400)
            existing = conn.execute(
                "SELECT g.id FROM groups g "
                "JOIN group_members a ON a.group_id=g.id AND a.user_id=? "
                "JOIN group_members b ON b.group_id=g.id AND b.user_id=? "
                "WHERE g.kind='direct' LIMIT 1", (uid, other["id"]),
            ).fetchone()
            if existing:
                return self.send_json({"id": existing["id"]})
            if not is_mutual_follow(conn, uid, other["id"]):
                return self.send_json({
                    "error": "Mesaj göndermek için karşılıklı takip etmen gerekir"
                }, 403)
            cur = conn.execute(
                "INSERT INTO groups (kind,name,description,creator_id,avatar_image,avatar_color,max_members,created_at) "
                "VALUES ('direct',?,?,?,?,?,2,?)",
                (other["display_name"][:60], "Özel mesaj", uid,
                 other["avatar_image"] if "avatar_image" in other.keys() else "", other["avatar"], now()),
            )
            gid = cur.lastrowid
            for member in (uid, other["id"]):
                conn.execute(
                    "INSERT OR IGNORE INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
                    (gid, member, now()),
                )
            conn.commit()
            return self.send_json({"id": gid}, 201)
        finally:
            conn.close()

    def toggle_membership(self, uid: int, group_id: int, action: str) -> None:
        conn = connect()
        try:
            group = conn.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
            if not group or group["kind"] != "halka":
                return self.send_json({"error": "Bu gruba katılım açık değil"}, 400)
            joined = conn.execute(
                "SELECT 1 FROM group_members WHERE group_id=? AND user_id=?", (group_id, uid)
            ).fetchone() is not None
            if action == "join":
                if joined:
                    return self.send_json({"ok": True})
                count = conn.execute(
                    "SELECT COUNT(*) FROM group_members WHERE group_id=?", (group_id,)
                ).fetchone()[0]
                if count >= group["max_members"]:
                    return self.send_json({"error": "Bu halka dolu"}, 400)
                conn.execute(
                    "INSERT INTO group_members (group_id,user_id,joined_at) VALUES (?,?,?)",
                    (group_id, uid, now()),
                )
            else:
                conn.execute(
                    "DELETE FROM group_members WHERE group_id=? AND user_id=?", (group_id, uid)
                )
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def send_group_message(self, uid: int, group_id: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            return self.send_json({"error": "Mesaj boş olamaz"}, 400)
        conn = connect()
        try:
            joined = conn.execute(
                "SELECT 1 FROM group_members WHERE group_id=? AND user_id=?", (group_id, uid)
            ).fetchone()
            if not joined:
                return self.send_json({"error": "Bu sohbete üye değilsin"}, 403)
            group = conn.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()
            if group and group["kind"] == "direct":
                other = conn.execute(
                    "SELECT user_id FROM group_members WHERE group_id=? AND user_id<>?", (group_id, uid)
                ).fetchone()
                if other and not is_mutual_follow(conn, uid, other["user_id"]):
                    return self.send_json({
                        "error": "Mesaj göndermek için karşılıklı takip etmen gerekir"
                    }, 403)
            cur = conn.execute(
                "INSERT INTO group_messages (group_id,sender_id,text,created_at) VALUES (?,?,?,?)",
                (group_id, uid, text[:2000], now()),
            )
            if group and group["kind"] != "halka":
                for member in conn.execute(
                    "SELECT user_id FROM group_members WHERE group_id=? AND user_id<>?",
                    (group_id, uid),
                ).fetchall():
                    add_notification(conn, member["user_id"], "group_message", uid,
                                     None, group_id, text, str(group_id))
            notify_mentions(conn, text, uid, None, group_id)
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def toggle_post_flag(self, uid: int, post_id: int, kind: str) -> None:
        table = "post_likes" if kind == "like" else "post_favorites"
        column = "post_id"
        conn = connect()
        try:
            post = conn.execute("SELECT user_id FROM posts WHERE id=?", (post_id,)).fetchone()
            if not post:
                return self.send_json({"error": "Paylaşım bulunamadı"}, 404)
            exists = conn.execute(f"SELECT 1 FROM {table} WHERE {column}=? AND user_id=?", (post_id, uid)).fetchone()
            if exists:
                conn.execute(f"DELETE FROM {table} WHERE {column}=? AND user_id=?", (post_id, uid))
            else:
                conn.execute(f"INSERT INTO {table} ({column},user_id) VALUES (?,?)", (post_id, uid))
                actor = author_of(conn, uid).get("display_name") or "Bir kullanıcı"
                verb = "paylaşımını beğendi" if kind == "like" else "paylaşımını favorilerine ekledi"
                add_notification(conn, post["user_id"], kind, uid, post_id, None,
                                 f"{actor} {verb}", str(post_id))
            conn.execute("UPDATE posts SET updated_at=? WHERE id=?", (now(), post_id))
            conn.commit()
            count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (post_id,)).fetchone()[0]
            return self.send_json({"active": not bool(exists), "count": count})
        finally:
            conn.close()

    def add_comment(self, uid: int, post_id: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            return self.send_json({"error": "Yorum boş olamaz"}, 400)
        parent = body.get("reply_to")
        try:
            parent_id = int(parent) if parent else None
        except (ValueError, TypeError):
            parent_id = None
        conn = connect()
        try:
            post = conn.execute("SELECT user_id,book FROM posts WHERE id=?", (post_id,)).fetchone()
            if not post:
                return self.send_json({"error": "Paylaşım bulunamadı"}, 404)
            cur = conn.execute(
                "INSERT INTO comments (post_id,parent_id,user_id,text,created_at) VALUES (?,?,?,?,?)",
                (post_id, parent_id, uid, text[:2000], now()),
            )
            notify_ids = {post["user_id"]}
            if parent_id:
                parent_row = conn.execute(
                    "SELECT user_id FROM comments WHERE id=?", (parent_id,)
                ).fetchone()
                if parent_row:
                    notify_ids.add(parent_row["user_id"])
            notify_ids.discard(uid)
            for target_uid in notify_ids:
                add_notification(conn, target_uid, "comment", uid, post_id,
                                 None, text, str(post_id))
            notify_mentions(conn, text, uid, post_id, None, notify_ids)
            conn.execute("UPDATE posts SET updated_at=? WHERE id=?", (now(), post_id))
            conn.commit()
            row = conn.execute("SELECT * FROM comments WHERE id=?", (cur.lastrowid,)).fetchone()
            return self.send_json({"comment": serialize_comment(conn, row, uid)}, 201)
        finally:
            conn.close()

    def toggle_comment_like(self, uid: int, comment_id: int) -> None:
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM comments WHERE id=?", (comment_id,)).fetchone():
                return self.send_json({"error": "Yorum bulunamadı"}, 404)
            exists = conn.execute(
                "SELECT 1 FROM comment_likes WHERE comment_id=? AND user_id=?", (comment_id, uid)
            ).fetchone()
            if exists:
                conn.execute("DELETE FROM comment_likes WHERE comment_id=? AND user_id=?", (comment_id, uid))
            else:
                conn.execute("INSERT INTO comment_likes (comment_id,user_id) VALUES (?,?)", (comment_id, uid))
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM comment_likes WHERE comment_id=?", (comment_id,)).fetchone()[0]
            return self.send_json({"active": not bool(exists), "count": count})
        finally:
            conn.close()

    def share_note(self, uid: int, note_id: int) -> None:
        conn = connect()
        try:
            note = conn.execute("SELECT * FROM notes WHERE id=? AND user_id=?", (note_id, uid)).fetchone()
            if not note:
                return self.send_json({"error": "Not bulunamadı"}, 404)
            conn.execute("UPDATE notes SET visibility='public' WHERE id=?", (note_id,))
            cur = conn.execute(
                "INSERT INTO posts (user_id,type,book,writer,text,created_at) VALUES (?,?,?,?,?,?)",
                (uid, "quote", note["book"], "Hatıratım", note["text"], now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM posts WHERE id=?", (cur.lastrowid,)).fetchone()
            return self.send_json({"post": serialize_post(conn, row, uid)}, 201)
        finally:
            conn.close()

    def add_answer(self, uid: int, debate_id: int, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            return self.send_json({"error": "Yanıt boş olamaz"}, 400)
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM debates WHERE id=?", (debate_id,)).fetchone():
                return self.send_json({"error": "Müzakere bulunamadı"}, 404)
            cur = conn.execute(
                "INSERT INTO debate_answers (debate_id,user_id,text,created_at) VALUES (?,?,?,?)",
                (debate_id, uid, text[:3000], now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def toggle_follow(self, uid: int, other_id: int) -> None:
        if uid == other_id:
            return self.send_json({"error": "Kendini takip edemezsin"}, 400)
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (other_id,)).fetchone():
                return self.send_json({"error": "Kullanıcı bulunamadı"}, 404)
            exists = conn.execute(
                "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (uid, other_id)
            ).fetchone()
            if exists:
                conn.execute("DELETE FROM follows WHERE follower_id=? AND followed_id=?", (uid, other_id))
            else:
                conn.execute("INSERT INTO follows (follower_id,followed_id) VALUES (?,?)", (uid, other_id))
                add_notification(conn, other_id, "follow", uid, None, None, "", str(uid))
            conn.commit()
            return self.send_json({"active": not bool(exists)})
        finally:
            conn.close()

    def toggle_key(self, uid: int, table: str, column: str, key: str) -> None:
        conn = connect()
        try:
            exists = conn.execute(
                f"SELECT 1 FROM {table} WHERE user_id=? AND {column}=?", (uid, key)
            ).fetchone()
            if exists:
                conn.execute(f"DELETE FROM {table} WHERE user_id=? AND {column}=?", (uid, key))
            else:
                conn.execute(f"INSERT INTO {table} (user_id,{column}) VALUES (?,?)", (uid, key))
            conn.commit()
            return self.send_json({"active": not bool(exists)})
        finally:
            conn.close()

    # ---- destek, şikayet, yönetim ----

    def create_ticket(self, uid: int, body: dict) -> None:
        kind = "talep" if body.get("kind") == "talep" else "sikayet"
        subject = str(body.get("subject", "")).strip()
        text = str(body.get("body", "")).strip()
        if not subject or not text:
            return self.send_json({"error": "Konu ve mesaj alanları gerekli"}, 400)
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO support_tickets (user_id,kind,subject,body,created_at) VALUES (?,?,?,?,?)",
                (uid, kind, subject[:200], text[:4000], now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def toggle_follow_user(self, uid: int, body: dict) -> None:
        try:
            target_id = int(body.get("user_id", 0))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz kullanıcı"}, 400)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id=? AND id<>? AND is_community=0 AND blocked=0",
                (target_id, uid)
            ).fetchone()
            if not row or is_blocked_pair(conn, uid, target_id):
                return self.send_json({"error": "Bu kullanıcı takip edilemez"}, 400)
            following = conn.execute(
                "SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?", (uid, target_id)
            ).fetchone() is not None
            action = str(body.get("action", "toggle"))
            if action == "unfollow" or (action == "toggle" and following):
                conn.execute(
                    "DELETE FROM follows WHERE follower_id=? AND followed_id=?", (uid, target_id)
                )
                following = False
            else:
                if not following:
                    add_notification(conn, target_id, "follow", uid, None, None, "", str(uid))
                conn.execute(
                    "INSERT OR IGNORE INTO follows (follower_id,followed_id) VALUES (?,?)",
                    (uid, target_id)
                )
                following = True
            conn.commit()
            followers = conn.execute(
                "SELECT COUNT(*) FROM follows WHERE followed_id=?", (target_id,)
            ).fetchone()[0]
            return self.send_json({"following": following, "followers": followers})
        finally:
            conn.close()

    def toggle_block_user(self, uid: int, body: dict) -> None:
        try:
            target_id = int(body.get("user_id", 0))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz kullanıcı"}, 400)
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id=? AND id<>? AND is_community=0",
                (target_id, uid)
            ).fetchone()
            if not row:
                return self.send_json({"error": "Bu kullanıcı bulunamadı"}, 400)
            if row["is_system"]:
                return self.send_json({"error": "Bu kullanıcı engellenemez"}, 400)
            action = str(body.get("action", "toggle"))
            blocked = conn.execute(
                "SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?", (uid, target_id)
            ).fetchone() is not None
            if action == "unblock" or (action == "toggle" and blocked):
                conn.execute(
                    "DELETE FROM blocks WHERE blocker_id=? AND blocked_id=?", (uid, target_id)
                )
                blocked = False
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO blocks (blocker_id,blocked_id,created_at) VALUES (?,?,?)",
                    (uid, target_id, now())
                )
                conn.execute(
                    "DELETE FROM follows WHERE (follower_id=? AND followed_id=?) "
                    "OR (follower_id=? AND followed_id=?)", (uid, target_id, target_id, uid)
                )
                blocked = True
            conn.commit()
            return self.send_json({"blocked": blocked})
        finally:
            conn.close()

    def create_report(self, uid: int, body: dict) -> None:
        raw_user = str(body.get("username", "")).strip().lstrip("@").lower()
        conn = connect()
        try:
            if raw_user:
                target = conn.execute(
                    "SELECT id FROM users WHERE username=? AND id<>?", (raw_user, uid)
                ).fetchone()
                reported_id = target["id"] if target else 0
            else:
                try:
                    reported_id = int(body.get("reported_id", 0))
                except (ValueError, TypeError):
                    reported_id = 0
        finally:
            conn.close()
        reason = str(body.get("reason", "")).strip()
        detail = str(body.get("detail", "")).strip()
        if not reason:
            return self.send_json({"error": "Şikayet nedenini seç"}, 400)
        conn = connect()
        try:
            other = conn.execute("SELECT 1 FROM users WHERE id=?", (reported_id,)).fetchone()
            if not other or reported_id == uid:
                return self.send_json({"error": "Bu kullanıcı bulunamadı veya kendin şikayet edilemez"}, 400)
            cur = conn.execute(
                "INSERT INTO user_reports (reporter_id,reported_id,reason,detail,created_at) VALUES (?,?,?,?,?)",
                (uid, reported_id, reason[:120], detail[:3000], now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def add_scholar_comment(self, uid: int, slug: str, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            return self.send_json({"error": "Yorum boş olamaz"}, 400)
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM scholars WHERE slug=?", (slug,)).fetchone():
                return self.send_json({"error": "Alim profili bulunamadı"}, 404)
            cur = conn.execute(
                "INSERT INTO scholar_comments (slug,user_id,text,created_at) VALUES (?,?,?,?)",
                (slug, uid, text[:2000], now()),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM scholar_comments WHERE id=?", (cur.lastrowid,)).fetchone()
            return self.send_json({"comment": {"id": row["id"], "author": author_of(conn, uid),
                                               "text": row["text"], "created_at": row["created_at"]}}, 201)
        finally:
            conn.close()

    def create_announcement(self, uid: int, body: dict) -> None:
        if not self.require_admin(uid):
            return
        title = str(body.get("title", "")).strip()
        text = str(body.get("body", "")).strip()
        kind = str(body.get("kind", "duyuru"))
        if kind not in ("duyuru", "bayram", "bilgi"):
            kind = "duyuru"
        if not title or not text:
            return self.send_json({"error": "Başlık ve metin gerekli"}, 400)
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO announcements (admin_id,kind,title,body,created_at) VALUES (?,?,?,?,?)",
                (uid, kind, title[:200], text[:4000], now()),
            )
            conn.commit()
            return self.send_json({"id": cur.lastrowid}, 201)
        finally:
            conn.close()

    def delete_announcement(self, uid: int, announcement_id: int) -> None:
        if not self.require_admin(uid):
            return
        conn = connect()
        try:
            conn.execute("DELETE FROM announcements WHERE id=?", (announcement_id,))
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def handle_ticket(self, uid: int, ticket_id: int, action: str, body: dict) -> None:
        if not self.require_admin(uid):
            return
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM support_tickets WHERE id=?", (ticket_id,)).fetchone():
                return self.send_json({"error": "Talep bulunamadı"}, 404)
            if action == "reply":
                text = str(body.get("body", "")).strip()
                if not text:
                    return self.send_json({"error": "Yanıt boş olamaz"}, 400)
                conn.execute(
                    "INSERT INTO ticket_replies (ticket_id,admin_id,body,created_at) VALUES (?,?,?,?)",
                    (ticket_id, uid, text[:3000], now()),
                )
                conn.execute("UPDATE support_tickets SET status='replied' WHERE id=?", (ticket_id,))
            else:
                conn.execute("UPDATE support_tickets SET status='closed' WHERE id=?", (ticket_id,))
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def handle_report(self, uid: int, report_id: int, action: str, body: dict) -> None:
        if not self.require_admin(uid):
            return
        conn = connect()
        try:
            if not conn.execute("SELECT 1 FROM user_reports WHERE id=?", (report_id,)).fetchone():
                return self.send_json({"error": "Şikayet bulunamadı"}, 404)
            if action == "reply":
                text = str(body.get("body", "")).strip()
                if not text:
                    return self.send_json({"error": "Yanıt boş olamaz"}, 400)
                conn.execute("UPDATE user_reports SET admin_reply=?, status='replied' WHERE id=?",
                             (text[:3000], report_id))
            else:
                conn.execute("UPDATE user_reports SET status='closed' WHERE id=?", (report_id,))
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def delete_comment(self, uid: int, kind: str, comment_id: int) -> None:
        if not self.require_admin(uid):
            return
        table = "comments" if kind == "post" else "scholar_comments"
        conn = connect()
        try:
            conn.execute(f"DELETE FROM {table} WHERE id=?", (comment_id,))
            conn.commit()
            return self.send_json({"ok": True})
        finally:
            conn.close()

    def moderate_book(self, uid: int, book_id: int, body: dict) -> None:
        """Yönetici onayıyla kitabı katalogdan gizler veya geri getirir."""
        if not self.require_admin(uid):
            return
        hidden = bool(body.get("hidden"))
        reason = clean_text(body.get("reason"))[:300] if hidden else ""
        if hidden and not reason:
            return self.send_json({"error": "Gizleme gerekçesi gerekli"}, 400)
        conn = connect()
        try:
            row = conn.execute("SELECT id,title FROM books WHERE id=?", (book_id,)).fetchone()
            if not row:
                return self.send_json({"error": "Kitap bulunamadı"}, 404)
            conn.execute(
                "UPDATE books SET hidden=?, hidden_reason=? WHERE id=?",
                (int(hidden), reason, book_id),
            )
            conn.commit()
            return self.send_json({"ok": True, "hidden": hidden, "title": row["title"]})
        finally:
            conn.close()

    def set_book_volumes(self, uid: int, book_id: int, body: dict) -> None:
        """Yönetici, katalogdaki bir eserin toplam cilt sayısını belirler."""
        if not self.require_admin(uid):
            return
        try:
            volume_count = int(body.get("volume_count", 1))
        except (ValueError, TypeError):
            return self.send_json({"error": "Geçersiz cilt sayısı"}, 400)
        volume_count = max(1, min(1000, volume_count))
        conn = connect()
        try:
            row = conn.execute("SELECT title FROM books WHERE id=?", (book_id,)).fetchone()
            if not row:
                return self.send_json({"error": "Kitap bulunamadı"}, 404)
            conn.execute("UPDATE books SET volume_count=? WHERE id=?", (volume_count, book_id))
            conn.commit()
            return self.send_json({"ok": True, "volume_count": volume_count, "title": row["title"]})
        finally:
            conn.close()

    def toggle_block(self, uid: int, other_id: int) -> None:
        if not self.require_admin(uid):
            return
        if uid == other_id:
            return self.send_json({"error": "Kendini engelleyemezsin"}, 400)
        conn = connect()
        try:
            target = conn.execute("SELECT * FROM users WHERE id=? AND is_community=0", (other_id,)).fetchone()
            if not target or target["is_admin"] or target["is_system"]:
                return self.send_json({"error": "Bu kullanıcı engellenemez"}, 400)
            blocked = 0 if target["blocked"] else 1
            conn.execute("UPDATE users SET blocked=? WHERE id=?", (blocked, other_id))
            if blocked:
                conn.execute("DELETE FROM sessions WHERE user_id=?", (other_id,))
            conn.commit()
            return self.send_json({"blocked": bool(blocked)})
        finally:
            conn.close()


def main() -> None:
    init_db()
    start_figure_scheduler()
    # Telefon/apk aynı Wi-Fi'den bağlanabildiği için tüm arayüzlere aç.
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, PORT), Handler)

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        lan_ip = probe.getsockname()[0]
    except OSError:
        lan_ip = host
    finally:
        probe.close()

    print(f"Ilim Halkasi ready -> http://localhost:{PORT}")
    print(f"LAN erisim -> http://{lan_ip}:{PORT}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
