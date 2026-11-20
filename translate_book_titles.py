"""Kitap başlıklarını Türkçe'ye çevirir ve özgün adı original_title alanında saklar.

Tek seferlik göç betiğidir; kaldığı yerden devam eder. Çeviri başarısız olan
kayıtlar işaretlenmez, bir sonraki çalıştırmada tekrar denenir.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

DB_PATH = "ilimhalkasi.db"
GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_ENDPOINT = "https://api.mymemory.translated.net/get"
USER_AGENT = "IlimHalkasi/1.0 (book-catalog)"

TURKISH_LETTERS = set("ışğçöüâîûİŞĞÇÖÜÂÎÛ")
# Yalnızca Türkçe'ye özgü sözcükler. "islam", "imam", "allah" gibi Arapça kökenli
# kelimeler İngilizce akademik başlıklarda da geçtiği için dil tespitini bozuyordu.
TURKISH_WORDS = re.compile(
    r"\b(ve|bir|kitap|kitabı|hakkında|için|ile|olan|bu|şu|nasıl|neden|yeni|eski|"
    r"gönül|yiğit)\b",
    re.IGNORECASE,
)


def ensure_column(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
    if "original_title" not in columns:
        conn.execute("ALTER TABLE books ADD COLUMN original_title TEXT NOT NULL DEFAULT ''")
        conn.commit()


def looks_turkish(title: str) -> bool:
    return any(ch in TURKISH_LETTERS for ch in title) or bool(TURKISH_WORDS.search(title))


def google_translate(title: str) -> tuple[str, str]:
    url = GOOGLE_ENDPOINT + "?client=gtx&sl=auto&tl=tr&dt=t&q=" + urllib.parse.quote(title)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
    translated = "".join(part[0] for part in data[0] if part and part[0]).strip()
    detected = ""
    try:
        detected = data[8][0][0] or ""
    except (IndexError, TypeError):
        pass
    return translated, detected


def mymemory_translate(title: str) -> str:
    url = MYMEMORY_ENDPOINT + "?q=" + urllib.parse.quote(title) + "&langpair=en|tr"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("quotaFinished") or data.get("responseStatus") != 200:
        raise RuntimeError("MyMemory kotası doldu")
    return str(data["responseData"]["translatedText"]).strip()


def translate_one(title: str) -> tuple[str, str, bool]:
    """(çeviri, algılanan dil, başarı) döndürür."""
    if looks_turkish(title):
        return title, "tr", True
    try:
        translated = mymemory_translate(title)
        if translated:
            return translated, "en", True
    except Exception:
        pass
    for attempt in range(3):
        try:
            translated, detected = google_translate(title)
            if translated:
                return translated, detected, True
            return title, detected, True
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return title, "", False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="Test için kayıt sınırı")
    parser.add_argument("--reset", action="store_true", help="original_title değerlerini sıfırla")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_column(conn)
    if args.reset:
        conn.execute("UPDATE books SET original_title=''")
        conn.commit()
    sql = "SELECT id,title,author FROM books WHERE hidden=0 AND original_title='' AND title<>'' ORDER BY id"
    if args.limit:
        sql += " LIMIT ?"
    rows = conn.execute(sql, (args.limit,) if args.limit else ()).fetchall()
    print(f"Çevrilecek kayıt: {len(rows)}", flush=True)
    if not rows:
        conn.close()
        return

    seen = {(row[0], row[1]) for row in conn.execute("SELECT title,author FROM books")}
    updates: list[tuple[str, str, int]] = []
    done = 0
    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = pool.map(lambda row: translate_one(row[1]), rows)
        for (book_id, title, author), (translated, detected, ok) in zip(rows, results):
            done += 1
            if not ok:
                failed += 1
                continue
            new_title = title
            if not (detected.startswith("tr") or not translated or translated == title):
                candidate = translated[:300].strip()
                if candidate and (candidate, author) not in seen:
                    new_title = candidate
                    seen.add((candidate, author))
            updates.append((new_title, title, book_id))
            if len(updates) >= 100:
                conn.executemany(
                    "UPDATE books SET title=?, original_title=? WHERE id=?", updates
                )
                conn.commit()
                updates.clear()
                print(f"{done}/{len(rows)}", flush=True)

    if updates:
        conn.executemany("UPDATE books SET title=?, original_title=? WHERE id=?", updates)
        conn.commit()

    # Eski başlıklarla tutan kullanıcı içeriklerini yeni başlıklara taşı.
    mapping = conn.execute(
        "SELECT original_title,title FROM books WHERE original_title<>'' AND original_title<>title"
    ).fetchall()
    for table, column in (("posts", "book"), ("notes", "book"), ("debates", "book_title")):
        for old_title, new_title in mapping:
            conn.execute(
                f"UPDATE {table} SET {column}=? WHERE {column}=?", (new_title, old_title)
            )
    conn.commit()
    print(f"Tamamlandı: {done} kayıt denendi, {failed} kayıt tekrar denenecek.", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
