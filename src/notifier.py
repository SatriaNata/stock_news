"""
src/notifier.py
Modul pengiriman notifikasi ringkasan berita saham ke Telegram via Telegram Bot API.
Fitur:
- Mengirim ringkasan sesi (nama sesi & jam di baris pertama, statistik, 3 saham terpopuler, tautan dashboard).
- Mengirim pesan darurat jika proses pembuatan dashboard mengalami kegagalan total.
- Aman: jika token atau chat ID belum diatur, fungsi mencatat peringatan tanpa membuat sistem error.
"""

import json
import logging
from typing import Dict, List

try:
    import requests
except ImportError:
    requests = None
    import urllib.request

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DASHBOARD_URL,
)

logger = logging.getLogger(__name__)


def send_telegram_message(text: str) -> bool:
    """
    Mengirim pesan teks ke Telegram melalui HTTP API.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum diatur. Melewati pengiriman notifikasi Telegram.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        if requests is not None:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                logger.info("Notifikasi Telegram berhasil terkirim.")
                return True
            else:
                logger.error(f"Telegram API gagal dengan status {resp.status_code}: {resp.text}")
                return False
        else:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    logger.info("Notifikasi Telegram berhasil terkirim.")
                    return True
                else:
                    logger.error(f"Telegram API gagal dengan status {resp.status}.")
                    return False
    except Exception as e:
        logger.error(f"Kesalahan saat mengirim pesan Telegram: {e}")
        return False


def notify_success(
    session: str,
    session_label: str,
    date_str: str,
    total_news: int,
    sorted_stocks: Dict[str, dict],
    dashboard_url: str = None,
) -> bool:
    """
    Menyusun dan mengirim pesan notifikasi sukses setelah dashboard berhasil diperbarui.
    Format pesan sesuai spesifikasi:
    - Baris 1: Nama sesi dan rentang jam
    - Tanggal, jumlah berita & saham
    - 3 saham paling ramai diberitakan
    - Tautan ke dashboard GitHub Pages
    """
    target_url = dashboard_url or DASHBOARD_URL
    session_name = "Sesi Pagi" if session == "pagi" else "Sesi Siang"
    total_stocks = len(sorted_stocks)

    # Ambil 3 saham teratas yang paling ramai
    top_3 = list(sorted_stocks.values())[:3]
    top_3_lines = []
    for idx, itm in enumerate(top_3, 1):
        code = itm["code"]
        count = itm["news_count"]
        sent = itm.get("sentiment", "Netral")
        top_3_lines.append(f"{idx}. <b>${code}</b> ({count} berita) — <i>{sent}</i>")

    top_3_text = "\n".join(top_3_lines) if top_3_lines else "<i>Tidak ada saham dominan</i>"

    message = (
        f"📊 <b>Rangkuman Saham — {session_name} ({session_label})</b>\n"
        f"📅 Tanggal: {date_str}\n"
        f"📈 {total_news} Berita Disaring • {total_stocks} Emiten Terdeteksi\n\n"
        f"🔥 <b>3 Saham Paling Ramai:</b>\n"
        f"{top_3_text}\n\n"
        f"🌐 <b>Buka Dashboard Lengkap:</b>\n"
        f"{target_url}"
    )

    return send_telegram_message(message)


def notify_failure(session: str, date_str: str, error_message: str) -> bool:
    """
    Mengirim pesan darurat singkat jika proses harian gagal total.
    """
    session_name = "Sesi Pagi" if session == "pagi" else "Sesi Siang"
    message = (
        f"⚠️ <b>PERINGATAN: Dashboard Berita Saham Gagal Dibuat</b>\n\n"
        f"Sesi    : {session_name}\n"
        f"Tanggal : {date_str}\n"
        f"Keterangan: {error_message[:200]}\n\n"
        f"Silakan periksa log eksekusi di GitHub Actions untuk penanganan lebih lanjut."
    )
    return send_telegram_message(message)
