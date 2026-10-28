"""
src/macro.py
Berita Makro: berita pasar & ekonomi yang tidak menyebut emiten tertentu
(suku bunga, inflasi, rupiah, arus asing, komoditas, kebijakan, ekonomi domestik, global, IHSG).
- Setiap berita digolongkan ke satu topik berdasarkan kata kunci judul (tanpa AI).
- Per topik per hari hanya disimpan MAX_MACRO_PER_TOPIC_DAY berita dengan skor tertinggi.
- Disimpan per bulan di data/makro/YYYY-MM.json dan ditampilkan di halaman makro.html.
"""

import os
import re
import json
import glob
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from config import MACRO_NEWS_DIR, MIN_MACRO_DATE, TIMEZONE
from src.analyzer import load_emiten_dict, fallback_detect_stocks
from src.quality import split_media, CAPITAL_MARKET_MEDIA, CLICKBAIT, RECOMMENDATION
from src.scraper import is_title_duplicate, _as_datetime

logger = logging.getLogger(__name__)

MAX_MACRO_PER_TOPIC_DAY = 5
MACRO_THRESHOLD = 2

# (topik, keterangan singkat untuk kartu, pola). Dicek dari atas: topik pertama yang cocok dipakai,
# sehingga topik spesifik didahulukan dan "IHSG & Pasar" menjadi penampung terakhir.
MACRO_TOPICS = [
    ("Suku Bunga", "BI Rate, The Fed, bunga acuan", r"suku bunga|bi rate|bi-rate|the fed|\bfomc\b|\bfed\b|pemangkasan bunga|kenaikan bunga|bunga acuan"),
    ("Inflasi", "Inflasi & harga konsumen", r"inflasi|deflasi|indeks harga konsumen|\bihk\b"),
    ("Rupiah & Kurs", "Nilai tukar rupiah & dolar", r"rupiah|\bkurs\b|dolar as|\bdxy\b|nilai tukar"),
    ("Arus Asing", "Aliran dana investor asing", r"net (buy|sell) asing|dana asing|investor asing|outflow|inflow|asing (net|catat|lepas|borong|kabur|masuk)"),
    ("Komoditas", "Batu bara, nikel, emas, CPO, minyak", r"harga (batu bara|batubara|nikel|emas|minyak|cpo|timah|tembaga|komoditas)|\bcpo\b|\bbrent\b|\bwti\b|komoditas"),
    ("Ekonomi Domestik", "PDB, neraca dagang, devisa, daya beli", r"pertumbuhan ekonomi|\bpdb\b|neraca (dagang|perdagangan|pembayaran)|ekspor|impor|cadangan devisa|daya beli|\bpmi\b|konsumsi rumah tangga"),
    ("Kebijakan & APBN", "APBN, pajak, regulasi, OJK, BUMN", r"\bapbn\b|pajak|\bppn\b|kemenkeu|menkeu|\bojk\b|regulasi|kebijakan (fiskal|moneter|ekonomi|pasar)|subsidi|danantara|\bbumn\b|stimulus|defisit"),
    ("Global", "Wall Street, AS, China, geopolitik", r"wall street|dow jones|nasdaq|s&p 500|resesi|geopolitik|perang (dagang|tarif)|tarif (trump|impor|as\b)|"
               r"(amerika serikat|\bas\b|china|tiongkok|eropa|jepang|global).{0,50}(ekonomi|pasar|saham|bursa|tarif|dagang|bunga|yield|obligasi|minyak|dolar)"),
    ("IHSG & Pasar", "IHSG, indeks, bursa", r"\bihsg\b|indeks harga saham gabungan|\blq45\b|bursa efek|\bbei\b|pasar saham|pasar modal|\bmsci\b|\bftse\b"),
]

# Artikel edukasi / tips umum tidak dianggap berita
EDUCATIONAL = r"^(pahami|apa itu|cara |tips|mengenal|panduan)|bagi (anak muda|pemula)|untuk pemula"

# Media ekonomi umum ikut mendapat poin sumber terpercaya
MACRO_MEDIA = CAPITAL_MARKET_MEDIA + ["katadata", "kompas", "tempo", "antara", "detik", "bloomberg", "reuters", "infobank"]


def classify_macro(title: str) -> Optional[str]:
    """Mengembalikan nama topik makro dari judul, atau None jika bukan berita makro."""
    text = title.lower()
    return next((topic for topic, _, pattern in MACRO_TOPICS if re.search(pattern, text)), None)


def score_macro(title: str, media: str) -> int:
    """Skor kualitas berita makro: topik cocok, sumber terpercaya, ada angka konkret; dikurangi clickbait/rekomendasi."""
    text = title.lower()
    score = 2
    if any(m in media.lower() for m in MACRO_MEDIA):
        score += 1
    if re.search(r"\d", text):  # judul berisi data (persen, level indeks, kurs) biasanya lebih informatif
        score += 1
    if re.search(CLICKBAIT, text):
        score -= 2
    if re.search(RECOMMENDATION, text):
        score -= 1
    if re.search(EDUCATIONAL, text):
        score -= 2
    return score


def select_macro_news(news_items: List[dict]) -> List[dict]:
    """
    Menyaring berita makro: tidak menyebut emiten di judul, cocok dengan salah satu topik,
    tanpa judul mirip (per hari), skor >= MACRO_THRESHOLD, lalu maks. MAX_MACRO_PER_TOPIC_DAY
    berita terbaik per topik per hari. Field codes/category diisi topik agar bisa memakai tampilan kartu yang sama.
    """
    code_to_name, name_to_code = load_emiten_dict()
    stripped = [{**n, "title": split_media(n["title"])[0], "description": "", "_link": n["link"]} for n in news_items]
    with_stock = {n["_link"] for items in fallback_detect_stocks(stripped, code_to_name, name_to_code).values() for n in items}

    kept_by_day: Dict[str, List[dict]] = {}
    scored = []
    for n in sorted((n for n in news_items if n["link"] not in with_stock), key=lambda n: n["title"]):
        title, media = split_media(n["title"])
        topic = classify_macro(title)
        if not topic:
            continue
        day = (n.get("pub_datetime") or "")[:10]
        same_day = kept_by_day.setdefault(day, [])
        if any(is_title_duplicate(n["title"], k["title"]) for k in same_day[-30:]):
            continue
        same_day.append(n)
        score = score_macro(title, media)
        if score >= MACRO_THRESHOLD:
            scored.append({**n, "source": media or n["source"], "codes": [topic], "category": topic, "score": score})

    groups: Dict[Tuple[str, str], List[dict]] = {}
    for n in scored:
        groups.setdefault((n["category"], n["pub_datetime"][:10]), []).append(n)
    selected = []
    for items in groups.values():
        items.sort(key=lambda n: n["pub_datetime"], reverse=True)   # terbaru dulu saat skor sama
        items.sort(key=lambda n: -n["score"])
        selected.extend(items[:MAX_MACRO_PER_TOPIC_DAY])
    return selected


def update_macro_store(candidates: list, now: datetime) -> List[str]:
    """
    Menambahkan berita makro baru ke data/makro/YYYY-MM.json (sejak MIN_MACRO_DATE sampai `now`).
    Bulan yang tersentuh disaring ulang agar tetap maks. MAX_MACRO_PER_TOPIC_DAY per topik per hari.
    Mengembalikan daftar bulan yang tersedia (terbaru dulu).
    """
    by_month: Dict[str, Dict[str, dict]] = {}
    for item in candidates:
        pub_dt = _as_datetime(item.get("pub_datetime"))
        if pub_dt is None or not (MIN_MACRO_DATE <= pub_dt <= now):
            continue
        clean = {
            "title": item["title"],
            "link": item["link"].strip(),
            "source": item["source"],
            "pub_datetime": pub_dt.isoformat(),
            "pub_date_str": pub_dt.strftime("%Y-%m-%d %H:%M WIB"),
        }
        by_month.setdefault(pub_dt.strftime("%Y-%m"), {})[clean["link"]] = clean

    os.makedirs(MACRO_NEWS_DIR, exist_ok=True)
    fields = ("title", "link", "source", "pub_datetime", "pub_date_str")
    for month, new_items in sorted(by_month.items()):
        path = os.path.join(MACRO_NEWS_DIR, f"{month}.json")
        existing = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f).get("items", [])
        merged = {n["link"]: {k: n[k] for k in fields} for n in existing}
        for link, n in new_items.items():
            merged.setdefault(link, n)

        selected = select_macro_news(list(merged.values()))
        selected.sort(key=lambda n: n["pub_datetime"], reverse=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "month": month,
                "updated": datetime.now(TIMEZONE).isoformat(),
                "names": {topic: desc for topic, desc, _ in MACRO_TOPICS},
                "items": [{k: n[k] for k in fields + ("codes", "score", "category")} for n in selected],
            }, f, ensure_ascii=False, separators=(",", ":"))
        logger.info(f"Berita Makro {month}: {len(selected)} berita tersimpan.")

    return list_macro_months()


def list_macro_months() -> List[str]:
    """Daftar bulan Berita Makro yang tersedia, terbaru dulu."""
    files = glob.glob(os.path.join(MACRO_NEWS_DIR, "*.json"))
    return sorted((os.path.basename(p).replace(".json", "") for p in files), reverse=True)
