"""Kitap kataloğundaki page_count alanını Open Library verisiyle doldurur.

Kullanım:
    python backfill_book_pages.py            # tüm eksik kitaplar
    python backfill_book_pages.py --limit 5  # ilk 5 grup (deneme için)

Open Library arama API'si ``key:/works/OL...W`` sorgularını OR ile birleştirmeyi
destekler; böylece kitaplar_groupwise olarak çekilir ve istek sayısı azalır.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Windows konsolunda Türkçe karakterlerin yazdırılabilmesi için.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB = Path(__file__).with_name("ilimhalkasi.db")
SEARCH_URL = "https://openlibrary.org/search.json"
HEADERS = {"User-Agent": "IlimHalkasi/1.0 (local reading app)"}


def fetch_json(url: str, retries: int = 4) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception as exc:  # ağ/API hatalarında yeniden dene
            last = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Open Library isteği başarısız: {last}")


def chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def backfill(conn: sqlite3.Connection, batch_size: int, delay: float, limit: int) -> tuple[int, int]:
    rows = conn.execute(
        "SELECT id, work_key FROM books WHERE work_key<>'' AND page_count=0 ORDER BY id"
    ).fetchall()
    groups = list(chunks(rows, batch_size))
    if limit > 0:
        groups = groups[:limit]

    updated = 0
    checked = 0
    for index, group in enumerate(groups, 1):
        query = " OR ".join(f"key:{row['work_key']}" for row in group)
        url = SEARCH_URL + "?" + urllib.parse.urlencode({
            "q": query,
            "fields": "key,title,number_of_pages_median",
            "limit": len(group) + 10,
        })
        payload = fetch_json(url)
        pages = {
            doc.get("key"): int(doc["number_of_pages_median"])
            for doc in payload.get("docs", [])
            if doc.get("number_of_pages_median")
        }
        found = [(pages[row["work_key"]], row["id"]) for row in group if row["work_key"] in pages]
        if found:
            conn.executemany("UPDATE books SET page_count=? WHERE id=?", found)
            conn.commit()
            updated += len(found)
        checked += len(group)
        print(
            f"[{index}/{len(groups)}] {checked} kitap kontrol edildi, {updated} sayfa sayısı yazıldı",
            flush=True,
        )
        if delay:
            time.sleep(delay)
    return checked, updated


def sync_shelf_snapshots(conn: sqlite3.Connection) -> int:
    before = conn.total_changes
    conn.execute(
        "UPDATE shelf_books SET page_count = "
        "COALESCE((SELECT page_count FROM books WHERE books.id=shelf_books.book_id), 0)"
    )
    conn.commit()
    return conn.total_changes - before


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, default=40, help="grup başına kitap sayısı")
    parser.add_argument("--delay", type=float, default=0.2, help="istekler arası bekleme (saniye)")
    parser.add_argument("--limit", type=int, default=0, help="deneme için grup sayısı (0 = tümü)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        checked, updated = backfill(conn, args.batch, args.delay, args.limit)
        synced = sync_shelf_snapshots(conn)
        remaining = conn.execute("SELECT COUNT(*) FROM books WHERE page_count=0").fetchone()[0]
        print(f"\nBitti: {checked} kitap kontrol edildi, {updated} sayfa sayısı eklendi.")
        print(f"Raf anlık görüntüleri güncellendi: {synced} kayıt.")
        print(f"Katalogda sayfa sayısı olmayan kitap: {remaining}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
