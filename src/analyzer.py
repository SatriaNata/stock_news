"""
src/analyzer.py
Modul deteksi kode saham IDX dan analisis sentimen serta ringkasan berita menggunakan Gemini API.
Fitur:
- Memuat kamus kode & nama emiten IDX dari data/emiten.csv.
- Deteksi saham per berita secara berkelompok (batching) untuk menghemat kuota token.
- Validasi ketat: hanya kode saham yang terdaftar resmi di emiten.csv yang diproses.
- Analisis sentimen ('Positif', 'Netral', 'Negatif') dan ringkasan 1-2 kalimat per saham.
- Retry otomatis dengan exponential backoff jika terkena batas kuota (HTTP 429).
- Mekanisme Cadangan (Fallback): jika API gagal/tanpa kunci, sistem otomatis beralih
  ke pencocokan kata kunci/regex lokal dengan sentimen 'Netral' tanpa menghentikan sistem.
"""

import os
import re
import csv
import json
import time
import logging
from typing import Dict, List, Tuple

try:
    import requests
except ImportError:
    requests = None
    import urllib.request

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    AI_BATCH_SIZE,
    AI_MAX_RETRIES,
    AI_RETRY_DELAY,
    EMITEN_CSV_PATH,
)

logger = logging.getLogger(__name__)


def load_emiten_dict() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Memuat daftar emiten dari data/emiten.csv.
    Mengembalikan:
    - code_to_name: {'BBCA': 'Bank Central Asia Tbk', ...}
    - name_to_code: {'bank central asia': 'BBCA', ...}
    """
    code_to_name = {}
    name_to_code = {}

    if not os.path.exists(EMITEN_CSV_PATH):
        logger.warning(f"File '{EMITEN_CSV_PATH}' tidak ditemukan. Deteksi saham akan terbatas.")
        return code_to_name, name_to_code

    try:
        with open(EMITEN_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)  # Lewati baris judul
            for row in reader:
                if len(row) >= 2:
                    code = row[0].strip().upper()
                    name = row[1].strip()
                    if code and name:
                        code_to_name[code] = name

                        # Bersihkan nama untuk pencarian kata kunci
                        clean_name = re.sub(r"\b(pt|tbk|\(persero\))\b", "", name, flags=re.IGNORECASE)
                        clean_name = re.sub(r"[^a-zA-Z0-9\s]", " ", clean_name)
                        clean_name = re.sub(r"\s+", " ", clean_name).strip().lower()
                        if len(clean_name) >= 4:
                            name_to_code[clean_name] = code
    except Exception as e:
        logger.error(f"Gagal membaca emiten.csv ({e}).")

    return code_to_name, name_to_code


def call_gemini_api(prompt: str) -> str:
    """
    Memanggil Gemini REST API dengan payload JSON.
    Menangani status 429 (rate limit) dengan jeda bertingkat (exponential backoff).
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY belum dikonfigurasi di file .env atau environment variable.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,  # Suhu rendah untuk akurasi fakta & konsistensi JSON
            "responseMimeType": "application/json",
        }
    }

    last_error = None
    for attempt in range(1, AI_MAX_RETRIES + 1):
        try:
            if requests is not None:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                status_code = resp.status_code
                resp_text = resp.text
            else:
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data_bytes, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        status_code = resp.status
                        resp_text = resp.read().decode("utf-8")
                except urllib.error.HTTPError as he:
                    status_code = he.code
                    resp_text = he.read().decode("utf-8")

            if status_code == 200:
                result = json.loads(resp_text)
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return ""

            if status_code == 429:
                wait_time = AI_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Batas kuota Gemini tercapai (HTTP 429). Menunggu {wait_time} detik (Percobaan {attempt}/{AI_MAX_RETRIES})...")
                time.sleep(wait_time)
                continue

            # Status error lainnya (400, 403, 500)
            logger.error(f"Gemini API mengembalikan status {status_code}: {resp_text[:200]}")
            last_error = Exception(f"HTTP {status_code}: {resp_text[:200]}")
            break

        except Exception as e:
            last_error = e
            wait_time = AI_RETRY_DELAY * (2 ** (attempt - 1))
            logger.warning(f"Kesalahan panggilan API ({e}). Menunggu {wait_time} detik...")
            time.sleep(wait_time)

    raise last_error or Exception("Gemini API gagal dipanggil setelah retry.")


def fallback_detect_stocks(news_items: List[dict], code_to_name: Dict[str, str], name_to_code: Dict[str, str]) -> Dict[str, List[dict]]:
    """
    Sistem Cadangan (Fallback) jika AI tidak aktif atau kuota habis:
    Mendeteksi saham menggunakan aturan kata kunci huruf kapital berdiri sendiri
    dan nama perusahaan resmi dari emiten.csv.
    """
    logger.info("Menggunakan sistem deteksi cadangan lokal (Regex & Kata Kunci)...")
    stock_news = {}

    # Kata-kata singkatan umum yang harus diabaikan meskipun ada 4 huruf kapital
    IGNORED_WORDS = {
        "IHSG", "LQ45", "BEI", "IDX", "OJK", "KSEI", "RUPS", "APBN", "BUMN",
        "FED", "INFLASI", "USDT", "SBN", "SURAT", "DANA", "PASAR", "MODAL"
    }

    # Filter nama perusahaan yang cukup unik dan spesifik (panjang >= 6)
    valid_name_items = [(k, v) for k, v in name_to_code.items() if len(k) >= 6]

    for item in news_items:
        text = f"{item['title']} {item.get('description', '')}"
        detected_for_item = set()

        # 1. Cari kode saham 4 huruf kapital berdiri sendiri (\b[A-Z]{4}\b) - Sangat cepat
        potential_codes = re.findall(r"\b[A-Z]{4}\b", text)
        for code in potential_codes:
            if code in IGNORED_WORDS:
                continue
            if code in code_to_name:
                detected_for_item.add(code)

        # 2. Cari nama perusahaan hanya jika belum banyak kode ditemukan
        if len(detected_for_item) < 3:
            text_lower = text.lower()
            for name_key, code in valid_name_items:
                if name_key in text_lower:
                    detected_for_item.add(code)

        # Kelompokkan berita ke saham yang terdeteksi
        for code in detected_for_item:
            if code not in stock_news:
                stock_news[code] = []
            stock_news[code].append(item)

    return stock_news


def detect_stocks_with_ai(news_items: List[dict], code_to_name: Dict[str, str]) -> Dict[str, List[dict]]:
    """
    Mendeteksi saham IDX di setiap berita secara berkelompok (batch) menggunakan Gemini.
    Hanya saham yang benar-benar dibahas yang dicatat.
    """
    stock_news = {}
    total_batches = (len(news_items) + AI_BATCH_SIZE - 1) // AI_BATCH_SIZE

    logger.info(f"Mengirim {len(news_items)} berita ke Gemini dalam {total_batches} kelompok...")

    for i in range(0, len(news_items), AI_BATCH_SIZE):
        batch = news_items[i : i + AI_BATCH_SIZE]
        batch_idx = (i // AI_BATCH_SIZE) + 1

        news_text_list = []
        for itm in batch:
            news_text_list.append(
                f"- [ID: {itm['id']}] Judul: {itm['title']}\n  Deskripsi: {itm.get('description', '')}"
            )

        prompt = (
            "Kamu adalah analis pasar modal Indonesia yang sangat teliti.\n"
            "Tugasmu: Dari daftar berita pasar modal berikut, identifikasi KODE SAHAM IDX (4 huruf kapital, misalnya BBCA, BBRI, ASII, ANTM, BMRI) "
            "yang BENAR-BENAR DIBAHAS secara substansial di setiap berita.\n\n"
            "Aturan ketat:\n"
            "1. JANGAN masukkan IHSG, LQ45, atau istilah umum.\n"
            "2. Saham harus menjadi subjek utama berita, bukan sekadar disebut sekilas sebagai pemanis kalimat.\n"
            "3. Format keluaran HANYA berupa array JSON dengan struktur berikut:\n"
            "[\n"
            "  {\"id\": \"id_berita\", \"stocks\": [\"KODE1\", \"KODE2\"]}\n"
            "]\n\n"
            "Daftar Berita:\n" + "\n".join(news_text_list)
        )

        try:
            raw_response = call_gemini_api(prompt)
            # Bersihkan markdown formatting jika model menyertakan ```json ... ```
            clean_json = re.sub(r"^```json\s*", "", raw_response.strip(), flags=re.MULTILINE)
            clean_json = re.sub(r"```$", "", clean_json.strip(), flags=re.MULTILINE)
            parsed = json.loads(clean_json)

            # Buat mapping id berita ke objek berita
            batch_map = {itm["id"]: itm for itm in batch}

            for entry in parsed:
                b_id = entry.get("id")
                codes = entry.get("stocks", [])
                target_item = batch_map.get(b_id)
                if not target_item:
                    continue

                for code in codes:
                    code_clean = str(code).strip().upper()
                    # Validasi: buang kode saham yang tidak ada di emiten.csv
                    if code_clean in code_to_name:
                        if code_clean not in stock_news:
                            stock_news[code_clean] = []
                        stock_news[code_clean].append(target_item)

            logger.info(f"  -> Kelompok {batch_idx}/{total_batches} selesai diproses.")

        except Exception as e:
            logger.warning(f"  -> Kelompok {batch_idx}/{total_batches} gagal diproses oleh AI ({e}). Mencoba fallback untuk kelompok ini.")
            # Fallback lokal khusus untuk batch yang gagal
            batch_fallback = fallback_detect_stocks(batch, code_to_name, {})
            for code, items in batch_fallback.items():
                if code not in stock_news:
                    stock_news[code] = []
                stock_news[code].extend(items)

    return stock_news


# Berita hasil laporan keuangan: laba/rugi/pendapatan + periode laporan, atau istilah laporan keuangan langsung
_FIN_METRIC = r"(\blaba\b|\brugi\b|pendapatan|penjualan|ebitda)"
_FIN_PERIOD = r"(kuartal|kuarter|\bq[1-4]\b|semester|\b1h\b|\b9m\b|sembilan bulan|9 bulan|enam bulan|6 bulan|tahun buku|triwulan|\btw ?[1-4]\b|sepanjang (tahun|20\d\d))"
FINANCIAL_REPORT_PATTERN = (
    r"lapkeu|laporan keuangan|laporan tahunan|rilis kinerja|kinerja (keuangan|kuartal|semester|9 bulan|sembilan bulan)"
    rf"|{_FIN_METRIC}.{{0,60}}{_FIN_PERIOD}|{_FIN_PERIOD}.{{0,60}}{_FIN_METRIC}"
)


def detect_corporate_actions(news_items: List[dict]) -> List[str]:
    """
    Mendeteksi aksi korporasi khusus (Buyback dan Private Placement) serta berita
    Laporan Keuangan dari kumpulan judul dan deskripsi berita untuk saham tertentu.
    """
    tags = []
    all_text = " ".join([f"{itm['title']} {itm.get('description', '')}" for itm in news_items]).lower()

    # 1. Deteksi Buyback Saham
    if re.search(r"\b(buyback|buy-back|buy back|pembelian kembali saham|beli kembali saham)\b", all_text):
        tags.append("Buyback")

    # 2. Deteksi Private Placement (PMTHMETD)
    if re.search(r"\b(private placement|pmthmetd|tanpa hak memesan efek|penambahan modal tanpa hak|non-preemptive)\b", all_text):
        tags.append("Private Placement")

    # 3. Deteksi berita hasil Laporan Keuangan (kuartalan / semesteran / tahunan)
    if re.search(FINANCIAL_REPORT_PATTERN, all_text):
        tags.append("Laporan Keuangan")

    return tags


def analyze_sentiments_and_summaries(stock_news: Dict[str, List[dict]], code_to_name: Dict[str, str]) -> Dict[str, dict]:
    """
    Membuat label sentimen (Positif / Netral / Negatif), ringkasan 1-2 kalimat,
    serta mendeteksi aksi korporasi (Buyback / Private Placement) untuk setiap saham.
    Mengirimkan seluruh saham dalam batch hemat kuota ke Gemini API.
    """
    analyzed_stocks = {}

    if not stock_news:
        return analyzed_stocks

    # Siapkan data saham untuk prompt
    stocks_prompt_data = []
    for code, items in stock_news.items():
        company_name = code_to_name.get(code, "")
        headlines = [f"• {itm['title']}: {itm.get('description', '')}" for itm in items[:4]]
        stocks_prompt_data.append(
            f"Kode Saham: {code} ({company_name})\n" + "\n".join(headlines)
        )

    prompt = (
        "Kamu adalah analis pasar modal Indonesia profesional.\n"
        "Berdasarkan judul dan deskripsi berita terkini berikut, tentukan SENTIMEN, RINGKASAN SINGKAT, dan AKSI KORPORASI untuk setiap saham.\n\n"
        "Aturan:\n"
        "1. sentiment: Pilih salah satu dari 'Positif', 'Netral', atau 'Negatif'.\n"
        "2. summary: Tulis ringkasan padat dan informatif sebanyak 1–2 kalimat dalam bahasa Indonesia mengenai inti sentimen atau peristiwa yang dialami saham tersebut.\n"
        "3. corporate_actions: Array string aksi korporasi (hanya isi 'Buyback' atau 'Private Placement' jika benar-benar dibahas dalam berita, kosongkan [] jika tidak ada).\n"
        "4. Keluaran HANYA berupa objek JSON dengan kode saham sebagai key, contoh:\n"
        "{\n"
        "  \"BBRI\": {\"sentiment\": \"Positif\", \"summary\": \"BBRI mengumumkan rencana buyback saham senilai triliunan rupiah.\", \"corporate_actions\": [\"Buyback\"]}\n"
        "}\n\n"
        "Data Berita Saham:\n\n" + "\n\n".join(stocks_prompt_data)
    )

    ai_results = {}
    try:
        raw_response = call_gemini_api(prompt)
        clean_json = re.sub(r"^```json\s*", "", raw_response.strip(), flags=re.MULTILINE)
        clean_json = re.sub(r"```$", "", clean_json.strip(), flags=re.MULTILINE)
        ai_results = json.loads(clean_json)
        logger.info(f"Berhasil menganalisis sentimen & ringkasan untuk {len(ai_results)} saham menggunakan Gemini AI.")
    except Exception as e:
        logger.warning(f"Gagal menganalisis sentimen via Gemini AI ({e}). Menggunakan nilai bawaan (Sentimen: Netral, Ringkasan kosong).")

    # Susun hasil akhir
    for code, items in stock_news.items():
        ai_info = ai_results.get(code, {})
        sentiment = ai_info.get("sentiment", "Netral")
        if sentiment not in ["Positif", "Netral", "Negatif"]:
            sentiment = "Netral"
        summary = ai_info.get("summary", "")

        # Gabungkan deteksi aksi korporasi dari regex kata kunci + AI
        regex_tags = detect_corporate_actions(items)
        ai_tags = ai_info.get("corporate_actions", [])
        if isinstance(ai_tags, list):
            for t in ai_tags:
                if t in ["Buyback", "Private Placement"] and t not in regex_tags:
                    regex_tags.append(t)

        analyzed_stocks[code] = {
            "code": code,
            "company_name": code_to_name.get(code, code),
            "sentiment": sentiment,
            "summary": summary,
            "tags": regex_tags,
            "has_buyback": "Buyback" in regex_tags,
            "has_pp": "Private Placement" in regex_tags,
            "has_lapkeu": "Laporan Keuangan" in regex_tags,
            "news_count": len(items),
            "news": items,
        }

    return analyzed_stocks


def analyze_news(news_items: List[dict], use_ai: bool = True) -> Dict[str, dict]:
    """
    Fungsi orkestrasi analisis berita:
    1. Membaca kamus emiten.
    2. Mendeteksi saham (via AI atau fallback).
    3. Menganalisis sentimen dan ringkasan per saham.
    4. Mengurutkan saham berdasarkan jumlah berita terbanyak.
    """
    logger.info("=" * 60)
    logger.info("MEMULAI ANALISIS SAHAM & SENTIMEN")
    logger.info("=" * 60)

    code_to_name, name_to_code = load_emiten_dict()
    logger.info(f"Kamus emiten aktif: {len(code_to_name)} saham terdaftar.")

    if not news_items:
        logger.info("Tidak ada berita untuk dianalisis.")
        return {}

    # 1. Deteksi saham
    stock_news = {}
    can_use_ai = use_ai and bool(GEMINI_API_KEY)

    if can_use_ai:
        try:
            stock_news = detect_stocks_with_ai(news_items, code_to_name)
        except Exception as e:
            logger.warning(f"Deteksi AI gagal total ({e}). Berpindah ke fallback lokal.")
            stock_news = fallback_detect_stocks(news_items, code_to_name, name_to_code)
    else:
        if not GEMINI_API_KEY:
            logger.info("GEMINI_API_KEY tidak ditemukan. Menggunakan deteksi kata kunci lokal.")
        stock_news = fallback_detect_stocks(news_items, code_to_name, name_to_code)

    logger.info(f"Total saham terdeteksi: {len(stock_news)} saham dari {len(news_items)} berita.")

    # 2. Sentimen & Ringkasan
    if can_use_ai and stock_news:
        analyzed_stocks = analyze_sentiments_and_summaries(stock_news, code_to_name)
    else:
        analyzed_stocks = {}
        for code, items in stock_news.items():
            tags = detect_corporate_actions(items)
            analyzed_stocks[code] = {
                "code": code,
                "company_name": code_to_name.get(code, code),
                "sentiment": "Netral",
                "summary": "",
                "tags": tags,
                "has_buyback": "Buyback" in tags,
                "has_pp": "Private Placement" in tags,
                "has_lapkeu": "Laporan Keuangan" in tags,
                "news_count": len(items),
                "news": items,
            }

    # 3. Urutkan berdasarkan saham yang paling ramai diberitakan (descending)
    sorted_stocks = dict(
        sorted(analyzed_stocks.items(), key=lambda x: x[1]["news_count"], reverse=True)
    )

    return sorted_stocks

