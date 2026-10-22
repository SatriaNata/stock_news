"""
scripts/test_analyzer.py
Pengujian unit untuk modul deteksi saham dan analisis sentimen (src/analyzer.py).
Menguji:
1. Pemuatan kamus emiten dari data/emiten.csv.
2. Deteksi saham lokal (fallback regex & kata kunci nama perusahaan).
3. Validasi penolakan kode yang tidak terdaftar (misal XYZW atau IHSG).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import (
    load_emiten_dict,
    fallback_detect_stocks,
    analyze_news,
)


def test_analyzer():
    print("=" * 60)
    print("MENGUJI MODUL ANALYZER & DETEKSI EMITEN")
    print("=" * 60)

    # 1. Uji pemuatan kamus emiten
    code_to_name, name_to_code = load_emiten_dict()
    print(f"Total emiten termuat: {len(code_to_name)}")
    assert "BBCA" in code_to_name, "BBCA harus ada di emiten.csv!"
    assert "BBRI" in code_to_name, "BBRI harus ada di emiten.csv!"
    assert "ANTM" in code_to_name, "ANTM harus ada di emiten.csv!"
    print(f"Sample: BBCA -> {code_to_name['BBCA']}")
    print("-> LULUS: Kamus emiten berhasil dimuat.")

    # 2. Uji deteksi berita contoh (termasuk aksi korporasi Buyback & Private Placement)
    sample_news = [
        {
            "id": "berita-1",
            "title": "BBRI Umumkan Rencana Buyback Saham Senilai Rp 3 Triliun",
            "description": "Manajemen menyiapkan dana segar untuk melakukan pembelian kembali saham perseroan.",
            "source": "CNBC Indonesia",
            "pub_date_str": "2026-10-22 09:00 WIB",
            "link": "https://example.com/1",
        },
        {
            "id": "berita-2",
            "title": "BRPT Siap Gelar Private Placement (PMTHMETD) untuk Ekspansi Geotermal",
            "description": "Aksi korporasi penambahan modal tanpa hak memesan efek telah disetujui RUPS.",
            "source": "Kontan",
            "pub_date_str": "2026-10-22 09:30 WIB",
            "link": "https://example.com/2",
        },
        {
            "id": "berita-3",
            "title": "Perusahaan XYZW Catat Penurunan Kinerja Signifikan",
            "description": "Kode fiktif yang tidak boleh terdeteksi.",
            "source": "Google News",
            "pub_date_str": "2026-10-22 10:00 WIB",
            "link": "https://example.com/3",
        },
    ]

    detected = fallback_detect_stocks(sample_news, code_to_name, name_to_code)
    print("\nHasil Deteksi Saham (Fallback Mode):")
    for code, items in detected.items():
        print(f"  • {code} ({code_to_name.get(code)}): {len(items)} berita")

    assert "BBRI" in detected, "BBRI harus terdeteksi pada berita 1!"
    assert "BRPT" in detected, "BRPT harus terdeteksi pada berita 2!"
    assert "XYZW" not in detected, "XYZW tidak boleh terdeteksi karena tidak ada di emiten.csv!"
    assert "IHSG" not in detected, "IHSG tidak boleh terdeteksi sebagai saham!"
    print("-> LULUS: Deteksi saham dan validasi emiten tepat.")

    # 3. Uji orkestrasi lengkap dengan analyze_news (mode use_ai=False)
    results = analyze_news(sample_news, use_ai=False)
    print(f"\nHasil Akhir Analisis (Urutan Paling Banyak Diberitakan):")
    for code, data in results.items():
        print(f"  [{code}] Sentimen: {data['sentiment']} | Tags: {data.get('tags')} | Jumlah Berita: {data['news_count']}")

    assert results["BBRI"]["has_buyback"], "BBRI harus terdeteksi memiliki Buyback!"
    assert results["BRPT"]["has_pp"], "BRPT harus terdeteksi memiliki Private Placement!"
    print("-> LULUS: Deteksi aksi korporasi Buyback & Private Placement terverifikasi!")

    print("\n-> SEMUA PENGUJIAN ANALYZER LULUS DENGAN BAIK!")


if __name__ == "__main__":
    test_analyzer()
