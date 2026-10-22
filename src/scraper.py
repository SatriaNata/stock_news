"""
src/scraper.py
Modul pengumpulan berita pasar modal Indonesia dari berbagai sumber RSS.
Fitur:
- Mengunduh RSS secara aman dan independen (satu sumber gagal tidak menghentikan yang lain).
- Memfilter berita secara presisi berdasarkan jendela waktu Sesi Pagi atau Sesi Siang (WIB).
- Menghapus tag HTML dan membersihkan deskripsi (hanya metadata ringkas, tanpa isi penuh).
- Menghilangkan duplikasi berita (URL sama atau judul yang sangat mirip).
- Deduplikasi lintas-sesi: berita Sesi Pagi tidak akan muncul lagi di Sesi Siang.
"""

import os
import re
import json
import html
import hashlib
import logging
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
import email.utils
from difflib import SequenceMatcher

try:
    import requests
except ImportError:
    requests = None
    import urllib.request

from config import (
    TIMEZONE,
    SESSION_CONFIG,
    RSS_SOURCES,
    HTTP_HEADERS,
    REQUEST_TIMEOUT,
    DATA_DIR,
)

# Konfigurasi logging agar mudah dibaca di terminal dan file log GitHub Actions
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_session_window(session: str, ref_date: datetime.date = None):
    """
    Menghitung batas awal dan akhir waktu (WIB) untuk sesi yang dipilih.
    Waktu bersifat tetap (fixed hours) sesuai aturan:
    1. Sesi Pagi:
       - Selesai: jam 06.00 WIB hari ini.
       - Mulai: jam 12.00 WIB hari kerja sebelumnya.
       - Khusus hari Senin: mulai dari hari Jumat jam 12.00 WIB.
    2. Sesi Siang:
       - Mulai: jam 06.00 WIB hari ini.
       - Selesai: jam 11.45 WIB hari ini.

    Args:
        session: 'pagi' atau 'siang'
        ref_date: tanggal acuan (datetime.date), default adalah hari ini di WIB.

    Returns:
        tuple (start_dt, end_dt, display_label)
    """
    if ref_date is None:
        ref_date = datetime.now(TIMEZONE).date()

    session = session.lower().strip()
    if session not in SESSION_CONFIG:
        raise ValueError(f"Sesi tidak valid: '{session}'. Pilihan yang tersedia: 'pagi', 'siang'")

    if session == "pagi":
        cfg = SESSION_CONFIG["pagi"]
        end_dt = datetime(
            ref_date.year, ref_date.month, ref_date.day,
            cfg["end_hour"], cfg["end_minute"], 0,
            tzinfo=TIMEZONE
        )

        # Hitung hari kerja sebelumnya
        weekday = ref_date.weekday()  # 0=Senin, 1=Selasa, ..., 6=Minggu
        if weekday == 0:  # Hari Senin -> mundur 3 hari ke hari Jumat
            prev_date = ref_date - timedelta(days=3)
            label = "Jumat 13.20 – Senin 07.00 WIB"
        elif weekday == 6:  # Minggu (eksekusi darurat/uji coba) -> mundur ke Jumat
            prev_date = ref_date - timedelta(days=2)
            label = "Jumat 13.20 – Minggu 07.00 WIB"
        elif weekday == 5:  # Sabtu -> mundur ke Jumat
            prev_date = ref_date - timedelta(days=1)
            label = "Jumat 13.20 – Sabtu 07.00 WIB"
        else:  # Selasa s/d Jumat -> mundur 1 hari (kemarin)
            prev_date = ref_date - timedelta(days=1)
            label = "13.20 – 07.00 WIB"

        start_dt = datetime(
            prev_date.year, prev_date.month, prev_date.day,
            cfg["prev_start_hour"], cfg["prev_start_minute"], 0,
            tzinfo=TIMEZONE
        )

    else:  # Sesi Siang
        cfg = SESSION_CONFIG["siang"]
        start_dt = datetime(
            ref_date.year, ref_date.month, ref_date.day,
            cfg["start_hour"], cfg["start_minute"], 0,
            tzinfo=TIMEZONE
        )
        end_dt = datetime(
            ref_date.year, ref_date.month, ref_date.day,
            cfg["end_hour"], cfg["end_minute"], 0,
            tzinfo=TIMEZONE
        )
        label = "07.00 – 13.20 WIB"

    return start_dt, end_dt, label


def clean_html(raw_html: str) -> str:
    """Membersihkan tag HTML, entitas karakter khusus, dan spasi berlebih."""
    if not raw_html:
        return ""
    # Hapus tag HTML
    clean_text = re.sub(r"<[^>]+>", " ", raw_html)
    # Ubah entitas seperti &amp;, &quot;, &#39;
    clean_text = html.unescape(clean_text)
    # Hapus whitespace ganda
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return clean_text


def parse_pub_date(date_str: str):
    """
    Mengubah teks tanggal RSS menjadi objek datetime dalam zona waktu WIB (Asia/Jakarta).
    Mendukung format RFC 2822 (RSS standar) dan ISO 8601 (Atom).
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    # 1. Coba format RFC 2822 (umum pada RSS 2.0, misal: 'Wed, 22 Oct 2026 09:30:00 +0700')
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TIMEZONE)
            else:
                dt = dt.astimezone(TIMEZONE)
            return dt
    except Exception:
        pass

    # 2. Coba format ISO 8601 (umum pada Atom feed, misal: '2026-10-22T09:30:00Z')
    try:
        iso_clean = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)
        else:
            dt = dt.astimezone(TIMEZONE)
        return dt
    except Exception:
        pass

    return None


def fetch_feed_items(source_info: dict) -> list:
    """
    Mengunduh dan mengekstrak item dari satu sumber RSS.
    Mengembalikan daftar kamus berita mentah.
    Jika sumber gagal diakses, fungsi mencatat pesan peringatan dan mengembalikan list kosong.
    """
    name = source_info["name"]
    url = source_info["url"]

    logger.info(f"Mengunduh feed: {name} ...")
    try:
        if requests is not None:
            response = requests.get(
                url,
                headers=HTTP_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                logger.warning(f"Sumber '{name}' mengembalikan status HTTP {response.status_code}. Dilewati.")
                return []
            xml_content = response.content
        else:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                if resp.status != 200:
                    logger.warning(f"Sumber '{name}' mengembalikan status HTTP {resp.status}. Dilewati.")
                    return []
                xml_content = resp.read()

        root = ET.fromstring(xml_content)
    except Exception as e:
        logger.warning(f"Koneksi atau parsing '{name}' gagal ({e}). Dilewati.")
        return []

    items = []

    # 1. Cek struktur RSS 2.0 (<channel><item>)
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item"):
            title = clean_html(item.findtext("title", ""))
            link = clean_html(item.findtext("link", ""))
            desc = clean_html(item.findtext("description", ""))
            pub_date_str = item.findtext("pubDate", "")

            # Batasi deskripsi hanya cuplikan singkat (maks 250 karakter)
            if len(desc) > 250:
                desc = desc[:247].rstrip() + "..."

            pub_dt = parse_pub_date(pub_date_str)

            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "description": desc,
                    "source": name,
                    "pub_datetime": pub_dt,
                    "pub_date_str": pub_dt.strftime("%Y-%m-%d %H:%M WIB") if pub_dt else pub_date_str,
                })
        return items

    # 2. Cek struktur Atom (<feed><entry>)
    # Atom menggunakan namespace XML
    namespaces = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", namespaces) or root.findall("entry")
    for entry in entries:
        title = clean_html(entry.findtext("atom:title", "", namespaces) or entry.findtext("title", ""))
        
        # Link pada Atom biasanya berupa atribut href pada tag <link>
        link_elem = entry.find("atom:link", namespaces) or entry.find("link")
        link = ""
        if link_elem is not None:
            link = link_elem.attrib.get("href", "")

        desc = clean_html(
            entry.findtext("atom:summary", "", namespaces)
            or entry.findtext("summary", "")
            or entry.findtext("atom:content", "", namespaces)
            or entry.findtext("content", "")
        )
        if len(desc) > 250:
            desc = desc[:247].rstrip() + "..."

        date_str = (
            entry.findtext("atom:published", "", namespaces)
            or entry.findtext("published", "")
            or entry.findtext("atom:updated", "", namespaces)
            or entry.findtext("updated", "")
        )
        pub_dt = parse_pub_date(date_str)

        if title and link:
            items.append({
                "title": title,
                "link": link,
                "description": desc,
                "source": name,
                "pub_datetime": pub_dt,
                "pub_date_str": pub_dt.strftime("%Y-%m-%d %H:%M WIB") if pub_dt else date_str,
            })

    return items


def normalize_title(title: str) -> str:
    """Menormalisasi judul untuk perbandingan kemiripan."""
    # Hapus suffix nama portal umum seperti '- CNBC Indonesia', '| Kontan', dll.
    cleaned = re.sub(
        r"\s*[-|–—]\s*(cnbc indonesia|kontan(\.co\.id)?|bisnis(\.com)?|idx channel|antara|kompas|detik|reuters).*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    # Hanya ambil huruf dan angka, ubah ke huruf kecil
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def is_title_duplicate(title_a: str, title_b: str, threshold: float = 0.78) -> bool:
    """Mengecek apakah dua judul sangat mirip menggunakan SequenceMatcher."""
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    return ratio >= threshold


def load_pagi_session_keys(target_date: datetime.date) -> set:
    """
    Membaca data sesi pagi yang sudah tersimpan di data/YYYY-MM-DD-pagi.json
    untuk deduplikasi agar berita di sesi pagi tidak muncul di sesi siang.
    Mengembalikan kumpulan URL dan judul yang sudah dinormalisasi.
    """
    filename = f"{target_date.strftime('%Y-%m-%d')}-pagi.json"
    filepath = os.path.join(DATA_DIR, filename)

    seen_keys = set()
    if not os.path.exists(filepath):
        logger.info(f"File arsip sesi pagi ({filename}) belum ditemukan. Tidak ada filter lintas-sesi.")
        return seen_keys

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ambil semua berita dari data sesi pagi
            for item in data.get("news_items", []):
                if "link" in item:
                    seen_keys.add(item["link"].strip())
                if "title" in item:
                    seen_keys.add(normalize_title(item["title"]))
        logger.info(f"Berhasil memuat {len(seen_keys)} acuan deduplikasi dari Sesi Pagi ({filename}).")
    except Exception as e:
        logger.warning(f"Gagal membaca file sesi pagi {filename} ({e}). Melanjutkan tanpa filter lintas-sesi.")

    return seen_keys


def collect_news(session: str = "pagi", ref_date: datetime.date = None, ignore_time_filter: bool = False) -> dict:
    """
    Fungsi utama pengumpulan berita:
    1. Tentukan jendela waktu sesi.
    2. Ambil dari seluruh sumber RSS yang aktif.
    3. Filter rentang waktu sesi.
    4. Hilangkan duplikat internal (link sama / judul mirip).
    5. Jika sesi siang, hilangkan berita yang sudah tayang di sesi pagi.

    Returns:
        dict berisi metadata sesi dan daftar berita yang lolos saringan.
    """
    if ref_date is None:
        ref_date = datetime.now(TIMEZONE).date()

    start_dt, end_dt, session_label = get_session_window(session, ref_date)

    logger.info("=" * 60)
    logger.info(f"MEMULAI PENGUMPULAN BERITA: {session.upper()}")
    logger.info(f"Tanggal Acuan   : {ref_date}")
    logger.info(f"Rentang Waktu   : {start_dt.strftime('%Y-%m-%d %H:%M')} s/d {end_dt.strftime('%Y-%m-%d %H:%M')} WIB")
    logger.info(f"Label Tampilan  : {session_label}")
    logger.info("=" * 60)

    # Siapkan filter lintas sesi jika ini sesi siang
    pagi_seen_keys = set()
    if session == "siang":
        pagi_seen_keys = load_pagi_session_keys(ref_date)

    all_raw_items = []
    active_sources_count = 0

    # 1. Unduh dari semua sumber
    for src in RSS_SOURCES:
        if not src.get("enabled", True):
            continue
        active_sources_count += 1
        items = fetch_feed_items(src)
        all_raw_items.extend(items)
        logger.info(f"  -> {src['name']}: {len(items)} item mentah diperoleh.")

    logger.info(f"Total item mentah terkumpul: {len(all_raw_items)} dari {active_sources_count} sumber.")

    # 2. Filter rentang waktu & deduplikasi cepat
    filtered_items = []
    seen_links = set()
    seen_exact_titles = set()
    seen_tokens_list = []  # Menyimpan (tokens_set, title_string)

    for item in all_raw_items:
        link = item["link"].strip()
        title = item["title"].strip()
        pub_dt = item["pub_datetime"]

        # Filter waktu (kecuali jika flag ignore_time_filter aktif)
        if not ignore_time_filter and pub_dt is not None:
            if not (start_dt <= pub_dt <= end_dt):
                continue

        # Cek duplikasi link persis
        if link in seen_links:
            continue

        norm_title = normalize_title(title)
        if not norm_title:
            continue

        # Cek jika sudah muncul di sesi pagi (khusus sesi siang)
        if session == "siang" and pagi_seen_keys:
            if link in pagi_seen_keys or norm_title in pagi_seen_keys:
                continue

        # Cek kesamaan persis judul yang sudah dinormalisasi (O(1))
        if norm_title in seen_exact_titles:
            continue

        # Cek kemiripan fuzzy hanya jika ada irisan kata yang signifikan (mempercepat proses dari detik ke milidetik)
        current_tokens = set(norm_title.split())
        is_duplicate = False
        for prev_tokens, prev_title in seen_tokens_list:
            overlap = len(current_tokens & prev_tokens)
            min_len = min(len(current_tokens), len(prev_tokens))
            if min_len > 0 and (overlap / min_len) >= 0.60:
                if is_title_duplicate(title, prev_title):
                    is_duplicate = True
                    break

        if is_duplicate:
            continue

        # Generate ID hash unik untuk berita
        item_id = hashlib.md5(f"{link}_{title}".encode("utf-8")).hexdigest()[:12]
        item["id"] = item_id

        # Simpan ke daftar acuan
        seen_links.add(link)
        seen_exact_titles.add(norm_title)
        seen_tokens_list.append((current_tokens, title))
        filtered_items.append(item)

    # Urutkan berita dari yang paling baru
    filtered_items.sort(
        key=lambda x: x["pub_datetime"] if x["pub_datetime"] else datetime.min.replace(tzinfo=TIMEZONE),
        reverse=True
    )

    logger.info(f"Berita berhasil disaring untuk {session.upper()}: {len(filtered_items)} berita valid & unik.")

    # Hitung jumlah sumber unik yang beritanya masuk dalam filter
    unique_sources = list({item["source"] for item in filtered_items})

    return {
        "session": session,
        "session_label": session_label,
        "date": ref_date.strftime("%Y-%m-%d"),
        "window_start": start_dt.isoformat(),
        "window_end": end_dt.isoformat(),
        "total_news": len(filtered_items),
        "total_sources": len(unique_sources),
        "sources_list": unique_sources,
        "news_items": filtered_items,
    }


if __name__ == "__main__":
    import sys

    # Pengujian cepat via terminal
    target_session = "pagi"
    if len(sys.argv) > 1 and sys.argv[1] in ["pagi", "siang"]:
        target_session = sys.argv[1]

    result = collect_news(session=target_session, ignore_time_filter=True)
    print("\n--- CONTOH 3 BERITA PERTAMA ---")
    for i, itm in enumerate(result["news_items"][:3], 1):
        print(f"{i}. [{itm['source']}] {itm['title']}")
        print(f"   Waktu: {itm['pub_date_str']}")
        print(f"   Link : {itm['link']}")
        print(f"   Desc : {itm['description'][:100]}...\n")
