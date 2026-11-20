"""Kütüphaneye eklenen yerli/eser kayıtlarına Open Library kapakları ekler.

Yalnızca http ile başlamayan cover alanlarını günceller; tekrar çalıştırılabilir.
"""
from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import urllib.parse
import urllib.request

DB_PATH = "ilimhalkasi.db"
UA = "IlimHalkasi/1.0 (book-catalog)"


def lookup_cover(query: str) -> str:
    url = (
        "https://openlibrary.org/search.json?limit=1&fields=cover_i&q="
        + urllib.parse.quote(query)
    )
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    docs = payload.get("docs") or []
    cover_id = docs[0].get("cover_i") if docs else None
    return f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else ""


def find_cover(row: tuple[int, str, str]) -> tuple[int, str] | None:
    book_id, title, author = row
    for query in (f'"{title}" {author}'.strip(), f'"{title}"'):
        try:
            cover = lookup_cover(query)
            if cover:
                return book_id, cover
        except Exception:
            continue
    return None


def main() -> None:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    rows = conn.execute(
        "SELECT id,title,author FROM books "
        "WHERE source='curated' AND (cover='' OR cover NOT LIKE 'http%')"
    ).fetchall()
    print(f"Kapak aranacak kayıt: {len(rows)}", flush=True)
    found = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(find_cover, rows):
            if not result:
                continue
            book_id, cover = result
            conn.execute("UPDATE books SET cover=? WHERE id=?", (cover, book_id))
            found += 1
            if found % 25 == 0:
                conn.commit()
                print(f"bulunan {found}", flush=True)
    conn.commit()
    print(f"Tamamlandı: {found} kapak eklendi.", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
