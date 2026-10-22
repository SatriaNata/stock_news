"""
scripts/get_telegram_chat_id.py
Script bantu untuk menemukan TELEGRAM_CHAT_ID Anda secara otomatis.

Cara Penggunaan:
1. Pastikan Anda sudah membuat bot di Telegram lewat @BotFather dan menyalin TOKEN-nya ke file .env (TELEGRAM_BOT_TOKEN=...).
2. Buka aplikasi Telegram, cari bot Anda, lalu kirim pesan apa saja (misal ketik: /start atau halo).
3. Jalankan script ini:
   python3 scripts/get_telegram_chat_id.py
4. Script akan menampilkan CHAT ID Anda untuk disalin ke .env atau GitHub Secrets.
"""

import os
import sys
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TELEGRAM_BOT_TOKEN


def get_chat_id():
    token = TELEGRAM_BOT_TOKEN.strip()

    if not token or token == "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ":
        print("=" * 60)
        print("⚠️ PERINGATAN: TELEGRAM_BOT_TOKEN belum diatur!")
        print("=" * 60)
        token = input("Masukkan Bot Token Anda dari @BotFather: ").strip()
        if not token:
            print("Token kosong. Proses dibatalkan.")
            return

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    print(f"\nMenghubungi Telegram API untuk mencari pesan masuk...")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if not data.get("ok"):
            print(f"❌ Telegram API mengembalikan error: {data.get('description')}")
            return

        results = data.get("result", [])
        if not results:
            print("=" * 60)
            print("ℹ️ BELUM ADA PESAN MASUK DI BOT ANDA")
            print("=" * 60)
            print("Langkah mudah:")
            print("1. Buka aplikasi Telegram.")
            print("2. Cari bot Anda (username bot yang dibuat di @BotFather).")
            print("3. Klik 'START' atau kirim pesan apa saja (misal: halo).")
            print("4. Jalankan script ini lagi: python3 scripts/get_telegram_chat_id.py\n")
            return

        chats = {}
        for item in results:
            msg = item.get("message") or item.get("channel_post") or item.get("my_chat_member")
            if msg and "chat" in msg:
                c = msg["chat"]
                cid = c.get("id")
                cname = c.get("first_name", "") or c.get("title", "")
                cuser = c.get("username", "")
                ctype = c.get("type", "private")
                text = msg.get("text", "")
                chats[cid] = {"name": cname, "username": cuser, "type": ctype, "last_msg": text}

        print("=" * 60)
        print(f"🎉 BERHASIL MENEMUKAN {len(chats)} CHAT:")
        print("=" * 60)
        for cid, info in chats.items():
            print(f"👉 CHAT ID    : {cid}")
            print(f"   Nama Akun  : {info['name']}")
            print(f"   Username   : @{info['username']}" if info['username'] else "   Username   : -")
            print(f"   Tipe Chat  : {info['type']}")
            print(f"   Pesan Akhir: \"{info['last_msg']}\"")
            print("-" * 60)

        print("\n✅ LANGKAH BERIKUTNYA:")
        print(f"Salin CHAT ID di atas ke file .env Anda:")
        primary_id = list(chats.keys())[-1]
        print(f"TELEGRAM_CHAT_ID={primary_id}\n")

    except Exception as e:
        print(f"❌ Terjadi kesalahan koneksi: {e}")


if __name__ == "__main__":
    get_chat_id()
