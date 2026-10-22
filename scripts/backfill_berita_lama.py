"""
scripts/backfill_berita_lama.py
Script sekali jalan untuk mengisi "Berita Lama" secara historis dari Google News RSS.

RSS biasa hanya berisi berita terbaru, jadi script ini mengambil berita per hari
memakai filter tanggal Google News (after:/before:) untuk setiap sumber, lalu
menyaringnya dengan aturan skor kualitas yang sama (src/quality.py) ke
data/berita-lama/YYYY-MM.json.

Hasil unduhan mentah per hari disimpan di temp/backfill/ sehingga script bisa
dihentikan dan dilanjutkan kapan saja tanpa mengunduh ulang.

Contoh:
    python3 scripts/backfill_berita_lama.py
    python3 scripts/backfill_berita_lama.py --start 2026-09-01 --end 2026-09-30
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

from config import BASE_DIR, MIN_NEWS_DATE, PAST_NEWS_DIR, TIMEZONE
from src.scraper import fetch_feed_items, get_session_window, update_past_news_store

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("backfill")

# Sumber yang bisa difilter per tanggal lewat Google News (situs + kata kunci umum)
SITES = [
    "kontan.co.id", "bisnis.com", "cnbcindonesia.com", "idxchannel.com", "investor.id", "katadata.co.id",
    "emitennews.com", "ipotnews.com", "idnfinancials.com", "pasardana.id", "infobanknews.com",
    "stockwatch.id", "finance.detik.com",
]
QUERIES = [f"site:{s} saham" for s in SITES] + ["saham", "IHSG"]
REQUEST_DELAY = 0.7  # detik antar permintaan agar tidak dibatasi Google
CACHE_DIR = os.path.join(BASE_DIR, "temp", "backfill")


def fetch_day(day: datetime.date) -> list:
    """Mengambil semua berita satu hari dari seluruh query, memakai cache jika sudah pernah diunduh."""
    cache_path = os.path.join(CACHE_DIR, f"{day}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    next_day = day + timedelta(days=1)
    items = {}
    for query in QUERIES:
        q = quote_plus(f"{query} after:{day} before:{next_day}")
        url = f"https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"
        for item in fetch_feed_items({"name": query, "url": url}):
            pub_dt = item["pub_datetime"]
            items.setdefault(item["link"], {**item, "pub_datetime": pub_dt.isoformat() if pub_dt else None})
        time.sleep(REQUEST_DELAY)

    result = list(items.values())
    if result:  # hari kosong tidak disimpan agar dicoba lagi saat dilanjutkan
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    return result


def main():
    today = datetime.now(TIMEZONE).date()
    cutoff, _, _ = get_session_window("pagi", today)

    parser = argparse.ArgumentParser(description="Backfill Berita Lama dari Google News per hari")
    parser.add_argument("--start", default=MIN_NEWS_DATE.strftime("%Y-%m-%d"), help="Tanggal awal (YYYY-MM-DD)")
    parser.add_argument("--end", default=cutoff.strftime("%Y-%m-%d"), help="Tanggal akhir (YYYY-MM-DD)")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    os.makedirs(CACHE_DIR, exist_ok=True)
    logging.getLogger("src.scraper").setLevel(logging.WARNING)

    month_items, day = [], start
    while day <= end:
        items = []
        for attempt in range(3):
            items = fetch_day(day)
            if items:
                break
            # Hari tanpa hasil sama sekali biasanya tanda dibatasi Google: jeda lalu coba lagi
            logger.warning(f"{day}: tidak ada hasil, jeda 120 detik (percobaan {attempt + 1}/3)...")
            time.sleep(120)
        if not items:
            logger.error(f"Berhenti di {day}. Jalankan ulang script nanti untuk melanjutkan (cache tetap tersimpan).")
            break

        logger.info(f"{day}: {len(items)} berita mentah")
        month_items.extend(items)

        # Saring & simpan setiap kali satu bulan selesai (atau di hari terakhir)
        next_day = day + timedelta(days=1)
        if next_day.month != day.month or next_day > end:
            update_past_news_store(month_items, today)
            with open(os.path.join(PAST_NEWS_DIR, f"{day:%Y-%m}.json"), "r", encoding="utf-8") as f:
                logger.info(f"Bulan {day:%Y-%m} disimpan: {len(json.load(f)['items'])} berita lolos saringan.")
            month_items = []
        day = next_day

    if month_items:
        update_past_news_store(month_items, today)
    logger.info("Backfill selesai.")


if __name__ == "__main__":
    main()
