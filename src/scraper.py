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
import glob
import html
import hashlib
import time
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
    FEED_MAX_RETRIES,
    DATA_DIR,
    MIN_NEWS_DATE,
    PAST_NEWS_DIR,
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
    root = None
    # Coba hingga FEED_MAX_RETRIES kali: server sesekali menolak/membatasi permintaan sementara
    for attempt in range(1, FEED_MAX_RETRIES + 1):
        try:
            if requests is not None:
                response = requests.get(
                    url,
                    headers=HTTP_HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code != 200:
                    raise ValueError(f"status HTTP {response.status_code}")
                xml_content = response.content
            else:
                req = urllib.request.Request(url, headers=HTTP_HEADERS)
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    if resp.status != 200:
                        raise ValueError(f"status HTTP {resp.status}")
                    xml_content = resp.read()

            root = ET.fromstring(xml_content)
            break
        except Exception as e:
            if attempt == FEED_MAX_RETRIES:
                logger.warning(f"Koneksi atau parsing '{name}' gagal ({e}) setelah {attempt} percobaan. Dilewati.")
                return []
            logger.warning(f"Koneksi atau parsing '{name}' gagal ({e}). Mencoba lagi ({attempt}/{FEED_MAX_RETRIES})...")
            time.sleep(3 * attempt)

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


def merge_with_saved_session(session: str, ref_date: datetime.date, new_items: list):
    """
    Menggabungkan berita hasil run ini dengan berita sesi yang sama yang sudah tersimpan
    (data/YYYY-MM-DD-{sesi}.json), agar run ulang hanya MENAMBAH berita dan tidak menimpa.
    Duplikat (link atau judul ternormalisasi sama) diabaikan.
    Mengembalikan (daftar berita gabungan, data saham tersimpan untuk mempertahankan hasil AI).
    """
    path = os.path.join(DATA_DIR, f"{ref_date.strftime('%Y-%m-%d')}-{session}.json")
    if not os.path.exists(path):
        return new_items, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except Exception as e:
        logger.warning(f"Gagal membaca data sesi tersimpan {path} ({e}). Tidak digabung.")
        return new_items, {}

    saved_items = saved.get("news_items", [])
    merged, seen_links, seen_titles = [], set(), set()
    for item in saved_items + new_items:
        link = item["link"].strip()
        norm_title = normalize_title(item["title"])
        if link in seen_links or (norm_title and norm_title in seen_titles):
            continue
        seen_links.add(link)
        seen_titles.add(norm_title)
        merged.append({**item, "pub_datetime": _as_datetime(item.get("pub_datetime"))})

    merged.sort(
        key=lambda x: x["pub_datetime"] if x["pub_datetime"] else datetime.min.replace(tzinfo=TIMEZONE),
        reverse=True
    )
    logger.info(
        f"Digabung dengan data tersimpan: {len(saved_items)} berita lama + "
        f"{len(merged) - len(saved_items)} berita baru = {len(merged)} berita."
    )
    return merged, saved.get("stocks", {})

def collect_news(session: str = "pagi", ref_date: datetime.date = None, ignore_time_filter: bool = False) -> dict:
    """
    Fungsi utama pengumpulan berita:
    1. Tentukan jendela waktu sesi.
    2. Ambil dari seluruh sumber RSS yang aktif.
    3. Filter rentang waktu sesi; berita sebelum rentang sesi dipisah ke "past_news_items".
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

    # Pengaman: jika semua sumber gagal, hentikan proses agar data & dashboard sebelumnya tidak tertimpa kosong
    if not all_raw_items:
        raise RuntimeError(
            f"Semua {active_sources_count} sumber RSS gagal diambil (0 berita). "
            "Kemungkinan koneksi diblokir/dibatasi sementara. Data sebelumnya tidak diubah."
        )

    # 2. Filter rentang waktu & deduplikasi cepat
    # Berita yang terbit sebelum awal sesi (tapi setelah MIN_NEWS_DATE) masuk ke daftar "Berita Lama"
    filtered_items = []
    past_items = []
    seen_links = set()
    seen_exact_titles = set()
    seen_tokens_list = []  # Menyimpan (tokens_set, title_string)

    for item in all_raw_items:
        link = item["link"].strip()
        title = item["title"].strip()
        pub_dt = item["pub_datetime"]

        # Buang berita yang terlalu lama (berlaku juga saat ignore_time_filter aktif)
        if pub_dt is not None and pub_dt < MIN_NEWS_DATE:
            continue

        # Tentukan tujuan: sesi ini atau Berita Lama.
        # ignore_time_filter hanya melonggarkan batas akhir (berita setelah jam sesi tetap masuk sesi ini).
        is_past = pub_dt is not None and pub_dt < start_dt
        if pub_dt is not None and pub_dt > end_dt and not ignore_time_filter:
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
        (past_items if is_past else filtered_items).append(item)

    # Urutkan berita dari yang paling baru
    sort_key = lambda x: x["pub_datetime"] if x["pub_datetime"] else datetime.min.replace(tzinfo=TIMEZONE)
    filtered_items.sort(key=sort_key, reverse=True)
    past_items.sort(key=sort_key, reverse=True)

    logger.info(f"Berita berhasil disaring untuk {session.upper()}: {len(filtered_items)} berita valid & unik.")
    logger.info(f"Berita lama (sebelum rentang sesi, sejak {MIN_NEWS_DATE.date()}): {len(past_items)} berita.")

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
        "past_news_items": past_items,
    }


def _as_datetime(value):
    """pub_datetime bisa berupa datetime (hasil scraping) atau string (dari JSON)."""
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return None


def update_past_news_store(candidates: list, ref_date: datetime.date) -> list:
    """
    Memperbarui kumpulan "Berita Lama" per bulan di data/berita-lama/YYYY-MM.json.
    - Kandidat: berita lama dari run ini + berita sesi pagi/siang dari tanggal sebelumnya.
    - Hanya berita sejak MIN_NEWS_DATE sampai sebelum awal sesi pagi ref_date.
    - Setiap bulan yang tersentuh disaring ulang (skor kualitas & maks berita per emiten per hari).
    Mengembalikan daftar bulan yang tersedia (terbaru dulu).
    """
    from src.quality import select_quality_news  # impor lokal: quality bergantung pada modul ini

    cutoff, _, _ = get_session_window("pagi", ref_date)
    date_str = ref_date.strftime("%Y-%m-%d")

    # Berita sesi pagi/siang dari 7 hari sebelumnya ikut menjadi berita lama
    week_ago = (ref_date - timedelta(days=7)).strftime("%Y-%m-%d")
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*-*-*-*.json"))):
        file_date, _, file_session = os.path.basename(path).replace(".json", "").rpartition("-")
        if file_session in ("pagi", "siang") and week_ago <= file_date < date_str:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    candidates = candidates + json.load(f).get("news_items", [])
            except Exception as e:
                logger.warning(f"Gagal membaca {path} ({e}). Dilewati.")

    by_month = {}
    for item in candidates:
        pub_dt = _as_datetime(item.get("pub_datetime"))
        if pub_dt is None or not (MIN_NEWS_DATE <= pub_dt < cutoff):
            continue
        clean = {
            "title": item["title"],
            "link": item["link"].strip(),
            "source": item["source"],
            "pub_datetime": pub_dt.isoformat(),
            "pub_date_str": pub_dt.strftime("%Y-%m-%d %H:%M WIB"),
        }
        by_month.setdefault(pub_dt.strftime("%Y-%m"), {})[clean["link"]] = clean

    os.makedirs(PAST_NEWS_DIR, exist_ok=True)
    for month, new_items in sorted(by_month.items()):
        path = os.path.join(PAST_NEWS_DIR, f"{month}.json")
        existing = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f).get("items", [])
        merged = {n["link"]: n for n in existing}
        added = sum(1 for link in new_items if link not in merged)
        for link, n in new_items.items():
            merged.setdefault(link, n)

        fields = ("title", "link", "source", "pub_datetime", "pub_date_str")
        selected, names = select_quality_news([{k: n[k] for k in fields} for n in merged.values()])
        selected.sort(key=lambda n: n["pub_datetime"], reverse=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "month": month,
                "updated": datetime.now(TIMEZONE).isoformat(),
                "names": names,
                "items": [{k: n[k] for k in fields + ("codes", "score", "category")} for n in selected],
            }, f, ensure_ascii=False, separators=(",", ":"))
        logger.info(f"Berita Lama {month}: {len(selected)} berita lolos saringan ({added} kandidat baru).")

    return list_past_news_months()


def list_past_news_months() -> list:
    """Daftar bulan Berita Lama yang tersedia, terbaru dulu."""
    files = glob.glob(os.path.join(PAST_NEWS_DIR, "*.json"))
    return sorted((os.path.basename(p).replace(".json", "") for p in files), reverse=True)

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
