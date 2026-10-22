"""
main.py
Titik masuk utama (entrypoint) sistem otomatisasi Dashboard Berita Saham IDX.
Mengorkestrasi seluruh alur kerja:
1. Menentukan sesi dan batas waktu (Sesi Pagi: 12.00–06.00 WIB, Sesi Siang: 06.00–11.45 WIB).
2. Mengumpulkan dan menyaring berita RSS (src/scraper.py).
3. Mendeteksi saham dan menganalisis sentimen & ringkasan AI Gemini (src/analyzer.py).
4. Menghasilkan web dashboard statis index.html & arsip (src/generator.py).
5. Mengirimkan ringkasan hasil ke bot Telegram (src/notifier.py).

Dukungan Argumen CLI:
  --sesi [pagi|siang]       : Menentukan sesi secara manual (otomatis jika tidak disebutkan).
  --dry-run                 : Mode uji coba lokal (membuat HTML, tidak mengirim Telegram sungguhan).
  --ignore-time-filter      : Mengabaikan batas jam (sangat berguna untuk uji coba kapan saja).
  --skip-ai                 : Memaksa deteksi kata kunci lokal tanpa memanggil Gemini API.
  --skip-telegram           : Melewati pengiriman pesan Telegram.
  --date YYYY-MM-DD         : Mengatur tanggal acuan tertentu.
"""

import os
import sys
import argparse
import logging
from datetime import datetime

from config import TIMEZONE
from src.scraper import collect_news, get_session_window
from src.analyzer import analyze_news
from src.generator import generate_dashboard
from src.notifier import notify_success, notify_failure

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def determine_default_session() -> str:
    """
    Menentukan sesi otomatis berdasarkan jam saat ini di zona WIB jika user tidak menyatakannya.
    Sebelum pukul 11.00 WIB -> 'pagi'
    Pukul 11.00 WIB ke atas -> 'siang'
    """
    now_hour = datetime.now(TIMEZONE).hour
    if now_hour < 11:
        return "pagi"
    return "siang"


def main():
    parser = argparse.ArgumentParser(description="Otomasi Dashboard Berita Saham IDX")
    parser.add_argument(
        "--sesi",
        choices=["pagi", "siang"],
        default=None,
        help="Pilihan sesi kerja: 'pagi' (12.00-06.00 WIB) atau 'siang' (06.00-11.45 WIB).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mode uji coba lokal: buat dashboard tanpa mengirim notifikasi Telegram ke server.",
    )
    parser.add_argument(
        "--ignore-time-filter",
        action="store_true",
        help="Abaikan filter jam sesi (berguna saat uji coba lokal di luar jam bursa).",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Gunakan deteksi regex lokal (hemat kuota / tanpa Gemini API).",
    )
    parser.add_argument(
        "--skip-telegram",
        action="store_true",
        help="Lewati pengiriman pesan ke Telegram.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Tanggal acuan (format: YYYY-MM-DD). Default: hari ini.",
    )

    args = parser.parse_args()

    # 1. Tentukan tanggal & sesi kerja
    if args.date:
        try:
            ref_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Format --date tidak valid. Gunakan YYYY-MM-DD.")
            sys.exit(1)
    else:
        ref_date = datetime.now(TIMEZONE).date()

    target_session = args.sesi if args.sesi else determine_default_session()
    date_str = ref_date.strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info("DASHBOARD BERITA SAHAM IDX - OTOMASI PIPELINE")
    logger.info(f"Tanggal Acuan : {date_str}")
    logger.info(f"Sesi Terpilih : {target_session.upper()}")
    logger.info(f"Mode Dry Run  : {'AKTIF (Uji Coba)' if args.dry_run else 'TIDAK (Produksi)'}")
    logger.info("=" * 60)

    try:
        # 2. Pengumpulan Berita
        news_data = collect_news(
            session=target_session,
            ref_date=ref_date,
            ignore_time_filter=args.ignore_time_filter,
        )
        news_items = news_data["news_items"]
        session_label = news_data["session_label"]
        total_sources = news_data["total_sources"]

        # 3. Analisis Saham & Sentimen AI
        use_ai = not args.skip_ai
        sorted_stocks = analyze_news(news_items, use_ai=use_ai)

        # 4. Pembuatan Dashboard Web Statis (HTML & JSON)
        files_created = generate_dashboard(
            session=target_session,
            session_label=session_label,
            date_str=date_str,
            total_news=len(news_items),
            total_sources=total_sources,
            sorted_stocks=sorted_stocks,
            news_items=news_items,
        )
        logger.info(f"Dashboard utama diperbarui: {files_created['index_html']}")
        logger.info(f"Arsip sesi disimpan      : {files_created['archive_html']}")
        logger.info(f"Data JSON disimpan       : {files_created['json_path']}")

        # 5. Notifikasi Telegram
        if args.skip_telegram or args.dry_run:
            logger.info("Pengiriman Telegram dilewati karena mode --dry-run atau --skip-telegram aktif.")
            # Cetak simulasi pesan ke terminal
            top_3 = list(sorted_stocks.values())[:3]
            top_3_str = ", ".join([f"${s['code']} ({s['news_count']})" for s in top_3])
            print("\n[SIMULASI PESAN TELEGRAM]")
            print(f"📊 Rangkuman Saham — {target_session.upper()} ({session_label})")
            print(f"📅 Tanggal: {date_str} | Total Berita: {len(news_items)} | Emiten: {len(sorted_stocks)}")
            print(f"🔥 Top 3: {top_3_str if top_3_str else 'N/A'}")
            print(f"🌐 Link Dashboard: (Lihat index.html di browser Anda)\n")
        else:
            notify_success(
                session=target_session,
                session_label=session_label,
                date_str=date_str,
                total_news=len(news_items),
                sorted_stocks=sorted_stocks,
            )

        logger.info("SELURUH PROSES SELESAI DENGAN SUKSES! 🎉")

    except Exception as e:
        logger.critical(f"Proses pipeline gagal total: {e}", exc_info=True)
        # Kirim notifikasi darurat jika bukan mode dry run
        if not args.dry_run and not args.skip_telegram:
            try:
                notify_failure(target_session, date_str, str(e))
            except Exception as notify_err:
                logger.error(f"Gagal mengirim notifikasi darurat ke Telegram: {notify_err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
