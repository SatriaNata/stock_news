"""
scripts/test_scraper.py
Script pengujian komprehensif untuk modul pengumpul berita (src/scraper.py).
Bisa dijalankan kapan saja untuk memverifikasi logika waktu sesi, deduplikasi,
serta koneksi ke sumber-sumber RSS aktif.
"""

import sys
import os
from datetime import date, datetime

# Tambahkan path root agar modul src dapat diimpor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TIMEZONE
from src.scraper import (
    get_session_window,
    is_title_duplicate,
    normalize_title,
    clean_html,
    parse_pub_date,
    collect_news,
)


def test_session_windows():
    print("=" * 60)
    print("1. MENGUJI LOGIKA JENDELA WAKTU SESI (WIB)")
    print("=" * 60)

    # Kasus A: Hari Senin (2026-10-19) Sesi Pagi -> Harus mulai dari Jumat 13.20 s/d Senin 07.00
    senin = date(2026, 10, 19)
    start_pagi, end_pagi, label_pagi = get_session_window("pagi", senin)
    print(f"Kasus A (Senin Pagi) :")
    print(f"  Mulai   : {start_pagi}")
    print(f"  Selesai : {end_pagi}")
    print(f"  Label   : {label_pagi}")
    assert start_pagi.day == 16, "Sesi pagi hari Senin harus mulai dari hari Jumat (tanggal 16)!"
    assert start_pagi.hour == 13 and start_pagi.minute == 20, "Sesi pagi hari Senin harus mulai jam 13.20 WIB!"
    assert end_pagi.day == 19 and end_pagi.hour == 7, "Sesi pagi hari Senin harus selesai jam 07.00 WIB!"
    print("  -> LULUS: Logika Senin Pagi tepat.")

    # Kasus B: Hari Selasa (2026-10-20) Sesi Pagi -> Harus mulai dari Senin 13.20 s/d Selasa 07.00
    selasa = date(2026, 10, 20)
    start_selasa, end_selasa, label_selasa = get_session_window("pagi", selasa)
    print(f"\nKasus B (Selasa Pagi) :")
    print(f"  Mulai   : {start_selasa}")
    print(f"  Selesai : {end_selasa}")
    print(f"  Label   : {label_selasa}")
    assert start_selasa.day == 19 and start_selasa.hour == 13 and start_selasa.minute == 20
    assert end_selasa.day == 20 and end_selasa.hour == 7
    print("  -> LULUS: Logika Selasa Pagi tepat.")

    # Kasus C: Hari Rabu (2026-10-21) Sesi Siang -> Harus mulai jam 07.00 s/d 13.20 hari yang sama
    rabu = date(2026, 10, 21)
    start_siang, end_siang, label_siang = get_session_window("siang", rabu)
    print(f"\nKasus C (Rabu Siang) :")
    print(f"  Mulai   : {start_siang}")
    print(f"  Selesai : {end_siang}")
    print(f"  Label   : {label_siang}")
    assert start_siang.day == 21 and start_siang.hour == 7 and start_siang.minute == 0
    assert end_siang.day == 21 and end_siang.hour == 13 and end_siang.minute == 20
    print("  -> LULUS: Logika Sesi Siang tepat.")


def test_deduplication():
    print("\n" + "=" * 60)
    print("2. MENGUJI DEDUPLIKASI JUDUL BERITA")
    print("=" * 60)

    judul_1 = "IHSG Ditutup Menguat Tipis ke Level 7.600 Hari Ini"
    judul_2 = "IHSG Berhasil Ditutup Menguat Tipis ke Level 7.600"
    judul_3 = "Laba Bersih BBCA Kuartal III Melesat 15 Persen"

    mirip = is_title_duplicate(judul_1, judul_2)
    berbeda = is_title_duplicate(judul_1, judul_3)

    print(f"Judul A : {judul_1}")
    print(f"Judul B : {judul_2}")
    print(f"Apakah dianggap duplikat? {mirip}")
    assert mirip, "Judul 1 dan Judul 2 harusnya terdeteksi duplikat!"

    print(f"\nJudul C : {judul_3}")
    print(f"Apakah A dan C dianggap duplikat? {berbeda}")
    assert not berbeda, "Judul 1 dan Judul 3 tidak boleh dianggap duplikat!"
    print("  -> LULUS: Logika kemiripan judul berjalan akurat.")


def test_html_cleaning():
    print("\n" + "=" * 60)
    print("3. MENGUJI PEMBERSIHAN HTML & PARSING TANGGAL")
    print("=" * 60)

    kotor = "<p>PT Bank Central Asia Tbk (&quot;BBCA&quot;) mencatatkan <b>rekor laba</b> baru.</p>"
    bersih = clean_html(kotor)
    print(f"HTML kotor : {kotor}")
    print(f"Hasil bersih: {bersih}")
    assert "<b>" not in bersih and "&quot;" not in bersih
    print("  -> LULUS: Pembersihan teks berhasil.")

    tgl_rss = "Wed, 22 Oct 2026 08:30:00 +0700"
    parsed_dt = parse_pub_date(tgl_rss)
    print(f"\nTeks tanggal: {tgl_rss}")
    print(f"Hasil parse : {parsed_dt} (Zona: {parsed_dt.tzinfo})")
    assert parsed_dt.hour == 8 and parsed_dt.minute == 30
    print("  -> LULUS: Parsing tanggal RFC 2822 berhasil.")


def test_live_feed_fetch():
    print("\n" + "=" * 60)
    print("4. MENGUJI PENGAMBILAN BERITA ASLI (ONLINE / NETWORK)")
    print("=" * 60)
    try:
        data = collect_news(session="pagi", ignore_time_filter=True)
        print(f"Selesai! Berhasil mengumpulkan {data['total_news']} berita dari {data['total_sources']} sumber.")
        print("\nContoh 5 Berita Teratas:")
        for idx, itm in enumerate(data["news_items"][:5], 1):
            print(f"[{idx}] {itm['source']} ({itm['pub_date_str']})")
            print(f"    {itm['title']}")
            print(f"    URL: {itm['link']}")
    except Exception as e:
        print(f"Catatan: Penarikan online belum dapat dijalankan tanpa akses internet ({e}).")


if __name__ == "__main__":
    test_session_windows()
    test_deduplication()
    test_html_cleaning()
    
    # Jalankan live test jika argumen --live diberikan
    if "--live" in sys.argv:
        test_live_feed_fetch()
    else:
        print("\nTip: Jalankan 'python3 scripts/test_scraper.py --live' untuk menguji penarikan berita online.")
