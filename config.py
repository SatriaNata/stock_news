"""
config.py
Konfigurasi terpusat untuk Dashboard Berita Saham IDX.
Semua pengaturan sumber berita, model AI, dan jadwal sesi didefinisikan di sini
agar mudah diubah sewaktu-waktu tanpa membongkar kode utama.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

# Muat variabel dari file .env jika ada (untuk pengujian lokal)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Cadangan pembaca .env mandiri (jika python-dotenv belum diinstal via pip)
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))

# ==============================================================================
# 1. PENGATURAN ZONA WAKTU & SESI KERJA
# ==============================================================================
TIMEZONE = ZoneInfo("Asia/Jakarta")  # Waktu Indonesia Barat (WIB)

# Definisi rentang waktu untuk 2 sesi harian
# Catatan: Waktu ini bersifat tetap, tidak bergantung pada keterlambatan cron GitHub Actions.
SESSION_CONFIG = {
    "pagi": {
        "name": "Sesi Pagi",
        "description": "13.20 hari kerja sebelumnya – 07.00 WIB",
        "end_hour": 7,
        "end_minute": 0,
        "prev_start_hour": 13,
        "prev_start_minute": 20,
    },
    "siang": {
        "name": "Sesi Siang",
        "description": "07.00 – 13.20 WIB",
        "start_hour": 7,
        "start_minute": 0,
        "end_hour": 13,
        "end_minute": 20,
    }
}

# Batas tanggal terbit paling lama yang diterima (WIB).
# Tetap berlaku meskipun --ignore-time-filter aktif, agar berita lama dari RSS tidak ikut terambil.
MIN_NEWS_DATE = datetime(2025, 7, 1, tzinfo=TIMEZONE)

# ==============================================================================
# 2. DAFTAR SUMBER BERITA (RSS FEEDS)
# ==============================================================================
# Hanya mengambil judul, link, waktu terbit, dan deskripsi singkat.
# Tidak mengambil atau menyimpan isi artikel lengkap.
RSS_SOURCES = [
    {
        "name": "CNBC Indonesia (Market)",
        "url": "https://www.cnbcindonesia.com/market/rss",
        "enabled": True,
    },
    {
        "name": "Kontan via Google News",
        "url": "https://news.google.com/rss/search?q=site:kontan.co.id+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Kontan (Keuangan RSS)",
        "url": "https://rss.kontan.co.id/news/keuangan",
        "enabled": False,  # Dinonaktifkan sementara karena isu sertifikat SSL lawas pada server RSS Kontan
    },
    {
        "name": "Google News (Topik: Saham)",
        "url": "https://news.google.com/rss/search?q=saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Google News (Topik: IHSG)",
        "url": "https://news.google.com/rss/search?q=IHSG&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Bisnis.com via Google News",
        "url": "https://news.google.com/rss/search?q=site:bisnis.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "IDX Channel via Google News",
        "url": "https://news.google.com/rss/search?q=site:idxchannel.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Investor.id via Google News",
        "url": "https://news.google.com/rss/search?q=site:investor.id+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Katadata via Google News",
        "url": "https://news.google.com/rss/search?q=site:katadata.co.id+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Emitennews via Google News",
        "url": "https://news.google.com/rss/search?q=site:emitennews.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Ipotnews via Google News",
        "url": "https://news.google.com/rss/search?q=site:ipotnews.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "IDNFinancials via Google News",
        "url": "https://news.google.com/rss/search?q=site:idnfinancials.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Pasardana.id via Google News",
        "url": "https://news.google.com/rss/search?q=site:pasardana.id+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Infobanknews via Google News",
        "url": "https://news.google.com/rss/search?q=site:infobanknews.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Stockwatch.id via Google News",
        "url": "https://news.google.com/rss/search?q=site:stockwatch.id+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
    {
        "name": "Detik Finance via Google News",
        "url": "https://news.google.com/rss/search?q=site:finance.detik.com+saham&hl=id&gl=ID&ceid=ID:id",
        "enabled": True,
    },
]

# User-Agent untuk HTTP request agar tidak diblokir oleh CDN media berita
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Timeout dalam detik saat menghubungi setiap feed
REQUEST_TIMEOUT = 12

# ==============================================================================
# 3. PENGATURAN AI (GEMINI API)
# ==============================================================================
# Kunci dibaca dari environment variable (lokal: .env, online: GitHub Secrets)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Nama model Gemini yang digunakan (bisa diubah sesuai ketersediaan, misal gemini-2.0-flash / gemini-1.5-flash)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Ukuran kelompok berita per panggilan prompt (untuk menghemat kuota token)
AI_BATCH_SIZE = 20

# Pengaturan retry saat kena rate limit (HTTP 429)
AI_MAX_RETRIES = 3
AI_RETRY_DELAY = 5  # Detik jeda awal antar percobaan

# ==============================================================================
# 4. PENGATURAN TELEGRAM
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://username.github.io/stocks-news/")

# ==============================================================================
# 5. DIREKTORI & JALUR FILE
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ARCHIVE_DIR = os.path.join(BASE_DIR, "arsip")
EMITEN_CSV_PATH = os.path.join(DATA_DIR, "emiten.csv")
INDEX_HTML_PATH = os.path.join(BASE_DIR, "index.html")
