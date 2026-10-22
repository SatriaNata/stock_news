"""
scripts/test_generator.py
Script pengujian untuk modul pembuatan HTML dashboard (src/generator.py).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generator import generate_dashboard


def test_generator():
    print("=" * 60)
    print("MENGUJI PEMBUATAN FILE DASHBOARD HTML")
    print("=" * 60)

    sample_stocks = {
        "BBCA": {
            "code": "BBCA",
            "company_name": "Bank Central Asia Tbk.",
            "sentiment": "Positif",
            "summary": "Kinerja BBCA melesat didorong pertumbuhan kredit dan laba bersih kuartal III.",
            "news_count": 2,
            "news": [
                {
                    "title": "BBCA Catat Rekor Laba Bersih Baru di Kuartal III",
                    "source": "CNBC Indonesia",
                    "pub_date_str": "2026-10-22 08:30 WIB",
                    "link": "https://example.com/bbca-1",
                },
                {
                    "title": "Analisis Fundamental BBCA: Masih Layak Dikoleksi?",
                    "source": "Kontan",
                    "pub_date_str": "2026-10-22 07:15 WIB",
                    "link": "https://example.com/bbca-2",
                },
            ],
        },
        "ANTM": {
            "code": "ANTM",
            "company_name": "Aneka Tambang Tbk.",
            "sentiment": "Netral",
            "summary": "Saham ANTM bergerak fluktuatif mengikuti dinamika harga nikel global.",
            "news_count": 1,
            "news": [
                {
                    "title": "Harga Komoditas Nikel Menguat, Saham Tambang Bereaksi",
                    "source": "Google News",
                    "pub_date_str": "2026-10-22 08:00 WIB",
                    "link": "https://example.com/antm-1",
                }
            ],
        },
        "GOTO": {
            "code": "GOTO",
            "company_name": "GoTo Gojek Tokopedia Tbk.",
            "sentiment": "Negatif",
            "summary": "Tekanan jual asing membayangi pergerakan saham GOTO hari ini.",
            "news_count": 1,
            "news": [
                {
                    "title": "Asing Catat Net Sell pada Saham Teknologi Termasuk GOTO",
                    "source": "Bisnis.com via Google News",
                    "pub_date_str": "2026-10-22 06:45 WIB",
                    "link": "https://example.com/goto-1",
                }
            ],
        },
    }

    res = generate_dashboard(
        session="pagi",
        session_label="12.00 – 06.00 WIB",
        date_str="2026-10-22",
        total_news=4,
        total_sources=3,
        sorted_stocks=sample_stocks,
    )

    print("Hasil generate:")
    print("  Index HTML  :", res["index_html"])
    print("  Archive HTML:", res["archive_html"])
    print("  Data JSON   :", res["json_path"])

    assert os.path.exists(res["index_html"]), "index.html harus terbuat!"
    assert os.path.exists(res["archive_html"]), "File arsip harus terbuat!"
    assert os.path.exists(res["json_path"]), "File JSON harus terbuat!"

    # Baca isi index.html untuk memvalidasi elemen penting
    with open(res["index_html"], "r", encoding="utf-8") as f:
        content = f.read()
        assert "IBM Plex Mono" in content
        assert "IBM Plex Sans" in content
        assert "BBCA" in content
        assert "pill-positif" in content
        assert "pill-negatif" in content
        assert "RANGKUMAN PAGI" in content
        assert "Sesi Pagi" in content
        assert "Sesi Siang" in content

    print("-> LULUS: Dashboard HTML berhasil dirender dan diverifikasi!")


if __name__ == "__main__":
    test_generator()
