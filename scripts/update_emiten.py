"""
scripts/update_emiten.py
Script untuk mengunduh dan memperbarui daftar emiten saham Bursa Efek Indonesia (IDX)
ke dalam file data/emiten.csv.

Data diambil dari seluruh 11 sektor resmi BEI:
- Basic Materials
- Consumer Cyclicals
- Consumer Non-Cyclicals
- Energy
- Financials
- Healthcare
- Industrials
- Infrastructures
- Properties & Real Estate
- Technology
- Transportation & Logistic

Jalankan script ini kapan saja BEI kedatangan emiten baru (IPO):
    python3 scripts/update_emiten.py
"""

import os
import sys
import csv
import io
import urllib.request
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATA_DIR, EMITEN_CSV_PATH

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SECTORS = [
    "Basic%20Materials",
    "Consumer%20Cyclicals",
    "Consumer%20Non-Cyclicals",
    "Energy",
    "Financials",
    "Healthcare",
    "Industrials",
    "Infrastructures",
    "Properties%20%26%20Real%20Estate",
    "Technology",
    "Transportation%20%26%20Logistic",
]

BASE_URL = "https://raw.githubusercontent.com/wildangunawan/Dataset-Saham-IDX/master/List%20Emiten/Sectors/{sector}.csv"


def update_emiten_list():
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info("Memulai pembaruan daftar emiten BEI (11 Sektor)...")

    emiten_map = {}

    # Jika file lama ada, baca dulu agar tidak kehilangan data jika koneksi internet terputus di tengah jalan
    if os.path.exists(EMITEN_CSV_PATH):
        try:
            with open(EMITEN_CSV_PATH, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 2:
                        emiten_map[row[0].strip().upper()] = row[1].strip()
            logger.info(f"Memuat {len(emiten_map)} emiten yang sudah ada sebagai basis awal.")
        except Exception as e:
            logger.warning(f"Gagal membaca emiten lama ({e}). Melanjutkan download baru.")

    # Unduh dari masing-masing sektor
    success_count = 0
    for s in SECTORS:
        url = BASE_URL.format(sector=s)
        sector_name = s.replace("%20", " ").replace("%26", "&")
        logger.info(f"Mengunduh sektor: {sector_name} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                sector_items = 0
                for row in reader:
                    code = row.get("code", "").strip().upper()
                    name = row.get("name", "").strip()
                    if code and name:
                        emiten_map[code] = name
                        sector_items += 1
                logger.info(f"  -> Sektor '{sector_name}': {sector_items} emiten.")
                success_count += 1
        except Exception as e:
            logger.warning(f"Gagal mengunduh sektor '{sector_name}': {e}")

    if not emiten_map:
        logger.error("Tidak ada data emiten yang berhasil dikumpulkan!")
        return False

    # Urutkan berdasarkan kode saham secara alfabetis
    sorted_emitens = sorted(emiten_map.items(), key=lambda x: x[0])

    # Tulis ke data/emiten.csv
    with open(EMITEN_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Code", "Name"])
        for code, name in sorted_emitens:
            writer.writerow([code, name])

    logger.info("=" * 60)
    logger.info(f"BERHASIL: Menyimpan {len(sorted_emitens)} emiten IDX ke '{EMITEN_CSV_PATH}'.")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    update_emiten_list()
