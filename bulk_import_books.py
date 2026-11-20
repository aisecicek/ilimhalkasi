#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İlim Halkası — toplu kitap kataloğu aktarımı.

Open Library'yi ana katalog olarak konu bazlı sayfalayarak okur, SQLite
kataloğuna yazar; isteğe bağlı olarak Google Books ile Türkçe kapak/özet/
yayınevi bilgilerini tamamlar. İlerleme `book_import_progress` tablosunda
tutulur; script herhangi bir yerden durdurulup yeniden çalıştırılabilir.

Örnekler:
  python bulk_import_books.py --target 100        # küçük deneme
  python bulk_import_books.py                     # varsayılan 8000 kitap
  GOOGLE_BOOKS_API_KEY=... python bulk_import_books.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from server import (
    book_genre,
    book_year,
    cache_book,
    clean_text,
    connect,
    cover_url,
    init_db,
    now,
)

OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OL_FIELDS = (
    "key,title,author_name,first_publish_year,cover_i,isbn,subject,"
    "genre_name,description,ratings_average,ratings_count,language,publisher"
)

# Önce ilgi alanlarımız, sonra geniş katalog. Konu başına üst sınır varsayılan 400.
SUBJECTS = [
    "Islam", "Quran", "Hadith", "Sufism", "Islamic law", "Islamic education",
    "Ottoman Empire", "Prophet Muhammad", "Turkish literature", "Turkish poetry",
    "Arabic literature", "Persian literature", "World literature", "Classics",
    "Ancient classics", "Philosophy", "Ethics", "Theology", "Comparative religion",
    "Religion", "Fiction", "Novels", "Literary fiction", "Historical fiction",
    "Short stories", "Science fiction", "Fantasy", "Mystery", "Adventure fiction",
    "Romance", "Poetry", "Drama", "Essays", "Biography", "Autobiography",
    "History", "Ancient history", "Medieval history", "Modern history",
    "Psychology", "Self-help", "Education", "Sociology", "Anthropology",
    "Political science", "Economics", "Law", "Science", "Physics", "Biology",
    "Astronomy", "Chemistry", "Medicine", "Mathematics", "Computer science",
    "Technology", "Art", "Music", "Architecture", "Travel", "Nature",
    "Children's literature", "Young adult literature",
]

# Ana sayfadaki "İslami Kitaplar" / "Dünya Klasikleri" seçkileriyle uyumlu kategoriler.
CATEGORY_BY_SUBJECT = {
    "Islam": "İtikad",
    "Quran": "Tefsir",
    "Hadith": "Hadis",
    "Sufism": "Tasavvuf / Ahlak",
    "Islamic law": "Fıkıh",
    "Islamic education": "İtikad",
    "Ottoman Empire": "İslam Tarihi",
    "Prophet Muhammad": "Siyer-i Nebi",
    "Turkish literature": "Türk Edebiyatı",
    "Turkish poetry": "Türk Edebiyatı",
    "World literature": "Dünya Klasikleri",
    "Classics": "Dünya Klasikleri",
    "Ancient classics": "Dünya Klasikleri",
    "Philosophy": "Felsefe",
    "Ethics": "Felsefe",
    "Theology": "İtikad",
    "Comparative religion": "İtikad",
    "Religion": "İtikad",
    "Fiction": "Roman",
    "Novels": "Roman",
    "Literary fiction": "Roman",
    "Historical fiction": "Roman",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Library + Google Books toplu aktarımı")
    parser.add_argument("--target", type=int, default=int(os.environ.get("BOOK_TARGET", "8000")),
                        help="Veritabanındaki toplam kitap hedefi (varsayılan: 8000)")
    parser.add_argument("--per-subject", type=int,
                        default=int(os.environ.get("BOOKS_PER_SUBJECT", "400")),
                        help="Her konudan en fazla kaç kitap (varsayılan: 400)")
    parser.add_argument("--page-size", type=int, default=100,
                        help="Open Library istek başına sonuç (en fazla 100)")
    parser.add_argument("--delay", type=float, default=None,
                        help="Open Library istekleri arası bekleme; iletişim e-postası varsa 0.4, yoksa 1.1 sn")
    parser.add_argument("--contact", default=os.environ.get("IH_CONTACT_EMAIL", ""),
                        help="Open Library User-Agent için iletişim e-postası")
    parser.add_argument("--google-limit", type=int,
                        default=int(os.environ.get("GOOGLE_ENRICH_LIMIT", "200")),
                        help="Google Books ile zenginleştirilecek kayıt sayısı (varsayılan: 200)")
    parser.add_argument("--google-key", default=os.environ.get("GOOGLE_BOOKS_API_KEY", ""),
                        help="Google Books API anahtarı (opsiyonel)")
    parser.add_argument("--subjects", default="",
                        help="Yalnızca belirtilen konuları işle (virgülle ayrılmış)")
    parser.add_argument("--reset", action="store_true",
                        help="Konu bazlı ilerlemeyi sıfırlar (kitapları silmez)")
    return parser.parse_args()


def ascii_user_agent(contact: str) -> str:
    safe = re.sub(r"[^\x20-\x7E]+", "", contact or "").strip()
    return "IlimHalkasi/1.0 (book-catalog; mailto:" + safe + ")" if safe else \
        "IlimHalkasi/1.0 (book-catalog)"


def fetch_json(url: str, headers: dict, retries: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = min(30, 2 ** attempt * (5 if exc.code == 429 else 2))
                print(f"  HTTP {exc.code}; {wait} sn bekleniyor...", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
    raise last_error or RuntimeError("Bilinmeyen ağ hatası")


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def identity(title: str, author: str) -> tuple[str, str]:
    return normalized(title)[:120], normalized(author)[:80]


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, (list, tuple)) else [value]


def doc_sort_key(doc: dict) -> tuple[int, int, int]:
    languages = as_list(doc.get("language"))
    return (
        0 if "tur" in languages else 1,
        0 if doc.get("cover_i") else 1,
        0 if doc.get("description") else 1,
    )


def book_payload(doc: dict, subject: str) -> dict:
    subjects = [clean_text(v) for v in as_list(doc.get("subject"))]
    genres = [clean_text(v) for v in as_list(doc.get("genre_name"))]
    isbns = [clean_text(v) for v in as_list(doc.get("isbn"))]
    authors = [clean_text(v) for v in as_list(doc.get("author_name"))[:3] if clean_text(v)]
    publishers = [clean_text(v) for v in as_list(doc.get("publisher"))]
    cover_id = doc.get("cover_i")
    return {
        "title": doc.get("title"),
        "author": ", ".join(authors),
        "category": CATEGORY_BY_SUBJECT.get(subject, "Keşfedilen"),
        "cover": f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else "",
        "isbn": isbns[0] if isbns else "",
        "description": clean_text(doc.get("description")),
        "genre": book_genre(subjects + genres),
        "year": book_year(doc.get("first_publish_year")),
        "rating": doc.get("ratings_average"),
        "rating_count": doc.get("ratings_count"),
        "publisher": publishers[0] if publishers else "",
        "work_key": clean_text(doc.get("key")),
        "source": "openlibrary",
    }


def load_progress(conn: sqlite3.Connection, subjects: list[str], reset: bool) -> dict:
    if reset:
        conn.execute("DELETE FROM book_import_progress")
    existing = {
        row["subject"]: dict(row)
        for row in conn.execute(
            'SELECT subject, "offset", done, updated_at FROM book_import_progress'
        )
    }
    for subject in subjects:
        if subject not in existing:
            conn.execute(
                'INSERT INTO book_import_progress (subject, "offset", done, updated_at) VALUES (?,0,0,?)',
                (subject, now()),
            )
    conn.commit()
    return {
        row["subject"]: dict(row)
        for row in conn.execute(
            'SELECT subject, "offset", done, updated_at FROM book_import_progress'
        )
    }


def save_progress(conn: sqlite3.Connection, subject: str, offset: int, done: bool) -> None:
    conn.execute(
        'UPDATE book_import_progress SET "offset"=?, done=?, updated_at=? WHERE subject=?',
        (offset, int(done), now(), subject),
    )
    conn.commit()


def google_lookup(title: str, author: str, api_key: str, headers: dict) -> dict | None:
    query = f'intitle:"{title}"'
    if author:
        query += f' inauthor:"{author}"'
    params = {
        "q": query,
        "maxResults": 1,
        "printType": "books",
        "projection": "full",
        "langRestrict": "tr",
    }
    if api_key:
        params["key"] = api_key
    url = GOOGLE_BOOKS_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.load(response)
    items = payload.get("items") or []
    if not items:
        return None
    info = items[0].get("volumeInfo") or {}
    identifiers = info.get("industryIdentifiers") or []
    isbn = next(
        (row.get("identifier", "") for row in identifiers
         if row.get("type") in ("ISBN_13", "ISBN_10")),
        identifiers[0].get("identifier", "") if identifiers else "",
    )
    image = info.get("imageLinks") or {}
    return {
        "cover": cover_url(image.get("thumbnail") or image.get("smallThumbnail")),
        "isbn": isbn,
        "description": clean_text(info.get("description")),
        "genre": book_genre(info.get("categories") or []),
        "year": book_year(info.get("publishedDate")),
        "rating": info.get("averageRating"),
        "rating_count": info.get("ratingsCount"),
        "publisher": clean_text(info.get("publisher")),
        "page_count": info.get("pageCount"),
    }


def enrich_with_google(conn: sqlite3.Connection, limit: int, api_key: str, headers: dict) -> None:
    if limit <= 0:
        return
    rows = conn.execute(
        "SELECT id,title,author FROM books "
        "WHERE source='openlibrary' AND (cover='' OR description='' OR genre='') "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        return
    print(f"\nGoogle Books zenginleştirmesi: {len(rows)} kayıt denenecek...", flush=True)
    enabled = True
    failures = 0
    enriched = 0
    pause = 0.2 if api_key else 1.0
    for index, row in enumerate(rows, 1):
        if not enabled:
            break
        try:
            data = google_lookup(row["title"], row["author"], api_key, headers)
            if data:
                cache_book(conn, dict(data, title=row["title"], author=row["author"],
                                      source="openlibrary"))
                enriched += 1
            failures = 0
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                print("  Google Books 429 (kota/limitsiz anahtar); zenginleştirme durduruldu.",
                      flush=True)
                enabled = False
                break
            failures += 1
            print(f"  Google HTTP {exc.code}; kayıt atlandı.", flush=True)
        except Exception as exc:
            failures += 1
            print(f"  Google hatası ({type(exc).__name__}); kayıt atlandı.", flush=True)
        if failures >= 3:
            print("  Üst üste hata; Google Books zenginleştirmesi durduruldu.", flush=True)
            enabled = False
            break
        if index % 10 == 0:
            conn.commit()
            print(f"  Google: {index}/{len(rows)} kontrol edildi, {enriched} kayıt tamamlandı.",
                  flush=True)
        time.sleep(pause)
    conn.commit()
    print(f"Google Books tamamlandı: {enriched} kayıt zenginleştirildi.", flush=True)


def main() -> None:
    args = parse_args()
    init_db()
    conn = connect()
    try:
        subjects = SUBJECTS
        if args.subjects.strip():
            wanted = {s.strip() for s in args.subjects.split(",") if s.strip()}
            unknown = wanted - set(SUBJECTS)
            if unknown:
                print("Bilinmeyen konular atlandı: " + ", ".join(sorted(unknown)))
            subjects = [s for s in SUBJECTS if s in wanted] or SUBJECTS

        page_size = max(1, min(100, args.page_size))
        per_subject = max(page_size, args.per_subject)
        delay = args.delay
        if delay is None:
            delay = 0.4 if args.contact.strip() else 1.1
        delay = max(0.0, delay)

        user_agent = ascii_user_agent(args.contact)
        ol_headers = {"User-Agent": user_agent}
        google_headers = {"User-Agent": user_agent}

        progress = load_progress(conn, subjects, args.reset)
        active = [s for s in subjects if not progress[s]["done"]]
        start_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        max_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM books").fetchone()[0]
        count = start_count
        seen_work = {
            row[0] for row in conn.execute("SELECT work_key FROM books WHERE work_key<>''")
        }
        seen_ids = {
            identity(row["title"], row["author"])
            for row in conn.execute("SELECT title,author FROM books")
        }

        target = max(1, args.target)
        print(f"Mevcut kitap: {count} · hedef: {target} · konu: {len(active)} · "
              f"sayfa gecikmesi: {delay} sn", flush=True)

        round_no = 0
        while count < target and active:
            round_no += 1
            progressed = False
            for subject in list(active):
                if count >= target:
                    break
                state = progress[subject]
                offset = int(state["offset"])
                limit = min(page_size, per_subject - offset)
                if limit <= 0:
                    save_progress(conn, subject, per_subject, True)
                    progress[subject]["offset"] = per_subject
                    progress[subject]["done"] = 1
                    active.remove(subject)
                    continue
                params = {
                    "subject": subject,
                    "limit": limit,
                    "offset": offset,
                    "fields": OL_FIELDS,
                }
                url = OPEN_LIBRARY_URL + "?" + urllib.parse.urlencode(params)
                try:
                    payload = fetch_json(url, ol_headers)
                except Exception as exc:
                    print(f"  {subject}: istek hatası ({type(exc).__name__}); ilerleme korundu.",
                          flush=True)
                    continue
                docs = payload.get("docs") or []
                if not docs:
                    save_progress(conn, subject, offset, True)
                    progress[subject]["offset"] = offset
                    progress[subject]["done"] = 1
                    active.remove(subject)
                    continue
                docs.sort(key=doc_sort_key)
                for doc in docs:
                    data = book_payload(doc, subject)
                    if not normalized(data["title"]):
                        continue
                    work_key = data["work_key"]
                    key = identity(data["title"], data["author"])
                    if work_key and work_key in seen_work:
                        continue
                    if key in seen_ids:
                        continue
                    cached = cache_book(conn, data)
                    if not cached:
                        continue
                    if cached["id"] > max_id:
                        count += 1
                    if work_key:
                        seen_work.add(work_key)
                    seen_ids.add(key)
                conn.commit()
                offset += len(docs)
                num_found = int(payload.get("numFound") or 0)
                done = offset >= per_subject or offset >= num_found or len(docs) < limit
                save_progress(conn, subject, offset, done)
                progress[subject]["offset"] = offset
                progress[subject]["done"] = int(done)
                if done:
                    active.remove(subject)
                progressed = True
                print(f"  {subject}: sayfa {round_no}, offset {offset}, "
                      f"kitap {count}/{target}", flush=True)
                time.sleep(delay)
            if not progressed:
                print("Open Library'den yeni sayfa alınamadı; aktarım durduruldu.", flush=True)
                break

        print(f"\nOpen Library aktarımı tamamlandı: {count} kitap "
              f"(+{count - start_count} yeni).", flush=True)
        enrich_with_google(conn, args.google_limit, args.google_key, google_headers)

        total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        with_cover = conn.execute("SELECT COUNT(*) FROM books WHERE cover<>''").fetchone()[0]
        with_genre = conn.execute("SELECT COUNT(*) FROM books WHERE genre<>''").fetchone()[0]
        print(f"\nSonuç: {total} kitap · {with_cover} kapak · {with_genre} tür bilgisi.", flush=True)
        if count < target and not active:
            print("Tüm konular işlendi. Daha fazla kitap için yeni konu ekleyin veya "
                  "--reset ile ilerlemeyi sıfırlayın.", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAktarım duraklatıldı; ilerleme kaydedildi.", flush=True)
        sys.exit(130)
