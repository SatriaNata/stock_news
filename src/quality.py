"""
src/quality.py
Penilaian kualitas berita untuk halaman "Berita Lama" (berbasis aturan, tanpa AI).
- Setiap berita diberi skor dari judulnya: posisi emiten, kategori isi, rekap pasar, clickbait, dan sumber.
- Berita dengan skor < QUALITY_THRESHOLD dibuang.
- Per emiten per hari hanya disimpan MAX_NEWS_PER_STOCK_DAY berita dengan skor tertinggi.
"""

import re
from typing import Dict, List, Tuple

from src.analyzer import load_emiten_dict, fallback_detect_stocks, FINANCIAL_REPORT_PATTERN
from src.scraper import is_title_duplicate

QUALITY_THRESHOLD = 4
MAX_NEWS_PER_STOCK_DAY = 3

# Media khusus pasar modal mendapat poin tambahan
CAPITAL_MARKET_MEDIA = [
    "kontan", "bisnis", "cnbc", "investor", "stockwatch", "emitennews", "idx channel", "idxchannel",
    "ipotnews", "idnfinancials", "pasardana",
]

# (label, poin, pola). Kategori dengan poin tertinggi yang dipakai; urutan menentukan pemenang saat seri.
CATEGORIES = [
    ("Laporan Keuangan", 3, FINANCIAL_REPORT_PATTERN),
    ("Aksi Korporasi", 3, r"buyback|buy back|right issue|rights issue|hmetd|private placement|pmthmetd|akuisisi|mengakuisisi|ambil alih|merger|tender offer|stock split|reverse stock|\bipo\b|penawaran umum|obligasi|sukuk|\brups|spin.?off|divestasi|tambah modal|menambah modal|suntik|patungan|anak usaha|anak perusahaan|aksi korporasi|lepas bisnis|jual bisnis|treasuri"),
    ("Kinerja", 3, r"\blaba\b|\brugi\b|pendapatan|penjualan|marketing sales|kinerja|kuartal|semester|dividen|ebitda|\bmargin\b|lapkeu|laporan keuangan|profit|\butang\b"),
    ("Kepemilikan", 3, r"kepemilikan|pemegang saham|pengendali|lepas saham|melepas|\blego\b|borong|memborong|serok|akumulasi|tambah saham|jual saham|beli saham|jual beli|caplok|genggam|investor strategis|investor kakap|\b(jual|lepas|beli|lego|serok|borong|tambah|timbun|kurangi)\b.{0,30}\bsaham\b|\bsaham\b.{0,30}\b(jual|lepas|beli|lego|serok|borong|tambah|timbun|kurangi)\b"),
    ("Manajemen", 3, r"komisaris|direktur|\bdirut\b|direksi|presdir|ditunjuk|mundur|tutup usia|rombak"),
    ("Hukum & Risiko", 3, r"force majeure|\bkahar\b|diaudit|\baudit\b|sanksi|denda|\brkab\b|\bkpk\b|tersangka|\bgugat|gugatan|\bpkpu\b|pailit|banding|sidang|\bott\b|kasus|sengketa"),
    ("Status Bursa", 3, r"\buma\b|unusual market|suspensi|suspend|gembok|delisting|full call auction|\bfca\b|papan pemantauan|hentikan sementara|cooling down|free float|indeks (ftse|msci|lq45)|dicoret|ftse|msci"),
    ("Transaksi Asing", 2, r"\basing\b|net buy|net sell|foreign"),
    ("Bisnis", 2, r"kontrak|proyek|ekspansi|pabrik|produksi|capex|belanja modal|kerja ?sama|gandeng|\bmou\b|tender\b|izin|smelter|komersialisasi|operasikan|garap|perluas|kolaborasi|cadangan"),
    ("Pergerakan Harga", 1, r"menguat|melemah|\bara\b|\barb\b|melonjak|anjlok|meroket|ambles|ambrol|terbang|rebound|longsor|naik|turun|terkerek"),
]
RECOMMENDATION = r"rekomendasi|target harga|trading buy|buy on weakness|speculative buy|teknikal|analisa|analisis|support|resistance|saham pilihan|cermati|layak (dikoleksi|dicermati|dilirik)|prospek"
MARKET_RECAP = r"top gainer|top loser|market recap|ihsg (ditutup|dibuka|sesi|diprediksi|berpotensi|melemah|menguat|berbalik|naik|turun)|pemberat|penopang|harga emas hari ini|crossing"
CLICKBAIT = r"^(ini dia|simak|wajib|cek |intip|jangan lewatkan|deretan|bocoran|segini|luar biasa)|\bini dia\b|ini (daftar|deretan)"


def split_media(title: str) -> Tuple[str, str]:
    """Judul Google News berakhiran ' - Nama Media'. Mengembalikan (judul tanpa media, nama media)."""
    if " - " in title:
        head, media = title.rsplit(" - ", 1)
        return head.strip(), media.strip()
    return title.strip(), ""


def score_news(title: str, media: str, stock_count: int) -> Tuple[int, str]:
    """Menghitung skor kualitas satu berita. Mengembalikan (skor, kategori utama)."""
    text = title.lower()
    score = 2  # emiten disebut di judul
    if stock_count >= 5:
        score -= 4
    elif stock_count >= 3:
        score -= 2

    category, best = "Umum", 0
    for label, points, pattern in CATEGORIES:
        if points > best and re.search(pattern, text):
            category, best = label, points
    score += best

    if re.search(RECOMMENDATION, text):
        score -= 1
        if category == "Umum":
            category = "Rekomendasi"
    if re.search(MARKET_RECAP, text):
        score -= 2
    if re.search(CLICKBAIT, text):
        score -= 2
    if any(m in media.lower() for m in CAPITAL_MARKET_MEDIA):
        score += 1
    return score, category


def select_quality_news(news_items: List[dict]) -> Tuple[List[dict], Dict[str, str]]:
    """
    Menyaring berita: emiten harus disebut di judul, buang judul mirip, skor >= QUALITY_THRESHOLD,
    lalu maksimal MAX_NEWS_PER_STOCK_DAY berita terbaik per emiten per hari.
    Mengembalikan (berita lolos dengan field codes/score/category, peta kode -> nama emiten).
    """
    code_to_name, name_to_code = load_emiten_dict()

    # Deteksi emiten hanya dari judul (tanpa nama media)
    stripped = [{**n, "title": split_media(n["title"])[0], "description": "", "_link": n["link"]} for n in news_items]
    codes_of: Dict[str, List[str]] = {}
    for code, items in fallback_detect_stocks(stripped, code_to_name, name_to_code).items():
        for n in items:
            codes_of.setdefault(n["_link"], []).append(code)

    # Buang judul mirip lintas sumber (dibandingkan per hari)
    candidates = sorted((n for n in news_items if n["link"] in codes_of), key=lambda n: n["title"])
    kept_by_day: Dict[str, List[dict]] = {}
    scored = []
    for n in candidates:
        day = (n.get("pub_datetime") or "")[:10]
        same_day = kept_by_day.setdefault(day, [])
        if any(is_title_duplicate(n["title"], k["title"]) for k in same_day[-30:]):
            continue
        same_day.append(n)
        title, media = split_media(n["title"])
        codes = sorted(codes_of[n["link"]])
        score, category = score_news(title, media, len(codes))
        if score >= QUALITY_THRESHOLD:
            scored.append({**n, "source": media or n["source"], "codes": codes, "score": score, "category": category})

    # Maksimal N berita terbaik per emiten per hari
    selected = set()
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for n in scored:
        for code in n["codes"]:
            groups.setdefault((code, (n.get("pub_datetime") or "")[:10]), []).append(n)
    for items in groups.values():
        items.sort(key=lambda n: (-n["score"], n.get("pub_datetime") or ""))
        selected.update(n["link"] for n in items[:MAX_NEWS_PER_STOCK_DAY])

    result = [n for n in scored if n["link"] in selected]
    names = {code: code_to_name.get(code, code) for n in result for code in n["codes"]}
    return result, names
