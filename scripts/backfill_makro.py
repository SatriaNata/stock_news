"""
scripts/backfill_makro.py
Script sekali jalan untuk mengisi arsip "Berita Makro" (data/makro/YYYY-MM.json) secara historis
dari Google News RSS per hari, dengan saringan yang sama seperti run harian (src/macro.py).

- Hari yang sudah punya cache backfill Berita Lama (temp/backfill/) hanya mengunduh query makro tambahan.
- Hari lain mengunduh query umum + makro.
Unduhan mentah disimpan di temp/backfill-makro/ sehingga script bisa dihentikan dan dilanjutkan.

Contoh:
    python3 scripts/backfill_makro.py
    python3 scripts/backfill_makro.py --start 2026-03-01 --end 2026-03-31
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timedelta
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BASE_DIR, MACRO_NEWS_DIR, MIN_MACRO_DATE, TIMEZONE
from src.scraper import fetch_feed_items
from src.macro import update_macro_store

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("backfill_makro")

GENERAL_QUERIES = ["saham", "IHSG"]
MACRO_QUERIES = [
    '"suku bunga" BI OR "The Fed"',
    "kurs rupiah dolar",
    'inflasi OR "pertumbuhan ekonomi" Indonesia',
    "harga batu bara OR nikel OR CPO OR minyak",
    "APBN OR pajak OR OJK kebijakan",
]
REQUEST_DELAY = 0.7
STOCK_CACHE_DIR = os.path.join(BASE_DIR, "temp", "backfill")
CACHE_DIR = os.path.join(BASE_DIR, "temp", "backfill-makro")


def fetch_queries(day, queries) -> list:
    next_day = day + timedelta(days=1)
    items = {}
    for query in queries:
        q = quote_plus(f"{query} after:{day} before:{next_day}")
        url = f"https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"
        for item in fetch_feed_items({"name": query, "url": url}):
            pub_dt = item["pub_datetime"]
            items.setdefault(item["link"], {**item, "pub_datetime": pub_dt.isoformat() if pub_dt else None})
        time.sleep(REQUEST_DELAY)
    return list(items.values())


def fetch_day(day) -> list:
    """Berita mentah satu hari: cache Berita Lama (jika ada) + query makro (memakai cache sendiri)."""
    stock_cache = os.path.join(STOCK_CACHE_DIR, f"{day}.json")
    stock_items = []
    if os.path.exists(stock_cache):
        with open(stock_cache, "r", encoding="utf-8") as f:
            stock_items = json.load(f)

    cache_path = os.path.join(CACHE_DIR, f"{day}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            macro_items = json.load(f)
    else:
        # Cache Berita Lama sudah memuat query umum ("saham", "IHSG"); selain itu unduh juga
        queries = MACRO_QUERIES if stock_items else GENERAL_QUERIES + MACRO_QUERIES
        macro_items = fetch_queries(day, queries)
        if macro_items:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(macro_items, f, ensure_ascii=False)
    return stock_items + macro_items


def main():
    now = datetime.now(TIMEZONE)
    parser = argparse.ArgumentParser(description="Backfill Berita Makro dari Google News per hari")
    parser.add_argument("--start", default=MIN_MACRO_DATE.strftime("%Y-%m-%d"), help="Tanggal awal (YYYY-MM-DD)")
    parser.add_argument("--end", default=now.strftime("%Y-%m-%d"), help="Tanggal akhir (YYYY-MM-DD)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    os.makedirs(CACHE_DIR, exist_ok=True)
    logging.getLogger("src.scraper").setLevel(logging.WARNING)
    logging.getLogger("src.analyzer").setLevel(logging.WARNING)

    month_items, day = [], start
    while day <= end:
        items = []
        for attempt in range(3):
            items = fetch_day(day)
            if items:
                break
            logger.warning(f"{day}: tidak ada hasil, jeda 120 detik (percobaan {attempt + 1}/3)...")
            time.sleep(120)
        if not items:
            logger.error(f"Berhenti di {day}. Jalankan ulang script nanti untuk melanjutkan (cache tetap tersimpan).")
            break

        logger.info(f"{day}: {len(items)} berita mentah")
        month_items.extend(items)

        next_day = day + timedelta(days=1)
        if next_day.month != day.month or next_day > end:
            update_macro_store(month_items, now)
            with open(os.path.join(MACRO_NEWS_DIR, f"{day:%Y-%m}.json"), "r", encoding="utf-8") as f:
                logger.info(f"Bulan {day:%Y-%m} disimpan: {len(json.load(f)['items'])} berita makro.")
            month_items = []
        day = next_day

    # Simpan sisa bulan berjalan jika berhenti sebelum akhir bulan
    if month_items:
        update_macro_store(month_items, now)
        logger.info(f"Sisa {len(month_items)} berita mentah bulan {month_items[-1]['pub_datetime'][:7]} ikut disimpan.")
    logger.info("Backfill makro selesai.")


if __name__ == "__main__":
    main()
