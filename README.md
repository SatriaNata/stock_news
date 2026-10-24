# 📈 IDX Stock News Dashboard

Automated twice-daily news dashboard for the Indonesian stock market (IDX). Every trading day it collects market news from 15+ RSS sources, detects which listed companies (emiten) are mentioned, summarizes and scores sentiment with Google Gemini, publishes a static dashboard to GitHub Pages, and sends a summary to Telegram.

🔗 **Live dashboard:** [LINK_GITHUB_PAGES_KAMU](LINK_GITHUB_PAGES_KAMU)

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Google_Gemini-8E75B2?style=flat&logo=googlegemini&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat&logo=githubactions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-222222?style=flat&logo=githubpages&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram_Bot-26A5E4?style=flat&logo=telegram&logoColor=white)

## ✨ Highlights

- **Two sessions per trading day**: a morning brief before the market opens (07.05 WIB) and a midday brief before Session 2 (13.25 WIB), each with a fixed news time window
- **Emiten detection** against a dictionary of ~934 IDX tickers, with a regex fallback when the AI is unavailable
- **AI summaries & sentiment** per news item using Google Gemini
- **Resilient scraping**: deduplication, retries per RSS source, and the run stops safely if every source fails
- **Archive & history**: every session is saved as JSON and HTML, plus a "Berita Lama" page with monthly data and per-ticker pagination
- **Fully serverless**: scheduled with GitHub Actions cron, secrets stored in GitHub Secrets, hosted on GitHub Pages

## 🤖 How this project was built

This project was built with **AI-assisted development**: most of the code was generated with Claude and Antigravity.

My role:
- Defined the idea and requirements based on my own stock-market routine (investing in IDX since 2020)
- TULIS_PERANMU_DI_SINI (contoh: menentukan jadwal sesi & sumber berita, menguji hasil, memperbaiki bug, men-deploy ke GitHub Actions)

---


# 📈 Dashboard Berita Saham IDX (Otomatis 2 Sesi Harian)

Proyek otomatisasi untuk memantau berita pasar modal Indonesia (Bursa Efek Indonesia / IDX). Setiap hari kerja (Senin–Jumat), sistem otomatis mengumpulkan berita, mendeteksi emiten saham yang dibahas, menganalisis sentimen & ringkasan berita menggunakan AI (Google Gemini), menerbitkan web dashboard statis ke **GitHub Pages**, dan mengirim ringkasan langsung ke akun **Telegram** Anda.

---

## ⏰ Jadwal & Sistem 2 Sesi Harian (WIB)

Sistem bekerja dalam **2 sesi per hari kerja** untuk membedakan sentimen sebelum pembukaan bursa dan saat jeda siang:

| Sesi | Jam Eksekusi (Cron) | Rentang Berita yang Diambil | Keterangan |
| :--- | :--- | :--- | :--- |
| **Sesi Pagi** | **07.05 WIB** | **13.20** hari kerja sebelumnya s/d **07.00** hari ini | Merangkum berita Wall Street semalam & rekomendasi analis broker pagi sebelum bursa buka jam 09.00 WIB. |
| **Sesi Siang** | **13.25 WIB** | **07.00** hari ini s/d **13.20** hari ini | Merangkum seluruh berita penutupan Sesi 1 BEI tepat sebelum Sesi 2 bursa dibuka jam 13.30 WIB. |

> **Catatan:** Rentang jam berita ditentukan secara statis sesuai jadwal di atas, sehingga tetap akurat meskipun antrean server GitHub Actions terlambat beberapa menit.

---

## 📁 Struktur File & Folder Proyek

```text
Stocks News/
├── .github/
│   └── workflows/
│       └── daily_dashboard.yml   # Konfigurasi cron otomatisasi GitHub Actions
├── data/
│   ├── emiten.csv                # Kamus ~934 kode & nama emiten IDX
│   ├── YYYY-MM-DD-pagi.json      # Data mentah hasil sesi pagi
│   └── YYYY-MM-DD-siang.json     # Data mentah hasil sesi siang
├── arsip/
│   ├── YYYY-MM-DD-pagi.html      # Halaman dashboard arsip sesi pagi
│   └── YYYY-MM-DD-siang.html     # Halaman dashboard arsip sesi siang
├── src/
│   ├── scraper.py                # Pengumpul RSS, deduplikasi & filter jendela waktu
│   ├── analyzer.py               # Deteksi emiten, prompt Gemini AI & fallback regex
│   ├── generator.py              # Pembangun dashboard web HTML statis
│   └── notifier.py               # Pengirim pesan ringkasan ke Telegram
├── scripts/
│   ├── get_telegram_chat_id.py   # Script bantu menemukan Chat ID Telegram Anda
│   ├── update_emiten.py          # Script memperbarui daftar emiten resmi BEI
│   ├── test_scraper.py           # Script penguji unit pengumpulan berita
│   ├── test_analyzer.py          # Script penguji unit deteksi saham & emiten
│   └── test_generator.py         # Script penguji unit pembuatan halaman web
├── config.py                     # Pengaturan sumber berita, model AI & jadwal sesi
├── main.py                       # Titik masuk utama program
├── requirements.txt              # Daftar dependensi Python
├── .env.example                  # Template konfigurasi rahasia
├── .gitignore                    # Berkas yang diabaikan Git (.env, cache, dll)
├── README.md                     # Panduan penggunaan (file ini)
└── index.html                    # Dashboard utama (selalu menampilkan sesi terbaru)
```

---

## 🚀 Panduan Setup & Uji Coba di Komputer Lokal

Bagi Anda yang pemula, ikuti langkah sederhana ini untuk menjalankan proyek di komputer Anda sendiri:

### 1. Pasang Dependensi Python
Buka aplikasi **Terminal** di komputer Anda, pastikan berada di folder proyek ini, lalu jalankan:
```bash
pip install -r requirements.txt
```

### 2. Buat File Konfigurasi `.env`
Salin template `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```
Buka file `.env` dengan teks editor, lalu lengkapi kunci-kunci rahasia berikut:

1. **`GEMINI_API_KEY`**:
   - Buka [Google AI Studio](https://aistudio.google.com/).
   - Masuk dengan akun Google Anda dan klik tombol **Get API Key** > **Create API Key**.
   - Salin kunci tersebut dan tempel di `.env`. *(Gratis tanpa kartu kredit)*.

2. **`TELEGRAM_BOT_TOKEN`**:
   - Buka aplikasi Telegram di HP/laptop Anda.
   - Cari akun **`@BotFather`**, lalu ketik perintah `/newbot`.
   - Ikuti petunjuk untuk memberi nama bot Anda.
   - Anda akan mendapatkan token berupa kombinasi angka dan huruf (contoh: `123456789:ABCdefGhIJK...`). Salin ke `.env`.

3. **`TELEGRAM_CHAT_ID`**:
   - Buka bot baru yang baru saja Anda buat di Telegram, lalu klik **START** atau ketik pesan apa saja (misal: "halo").
   - Kembali ke Terminal komputer Anda, lalu jalankan script pembantu:
     ```bash
     python3 scripts/get_telegram_chat_id.py
     ```
   - Script akan otomatis mendeteksi pesan Anda dan menampilkan **CHAT ID** Anda. Salin angka tersebut ke `.env`.

4. **`DASHBOARD_URL`**:
   - Masukkan alamat GitHub Pages Anda nanti (contoh: `https://username.github.io/nama-repo/`).

---

## 🧪 Menjalankan Mode Uji Coba (Dry-Run)

Anda bisa menguji sistem secara aman di komputer tanpa perlu mengirim pesan Telegram sungguhan atau menunggu jadwal bursa:

### Menguji Sesi Pagi (Dengan Berita Terkini)
```bash
python3 main.py --sesi pagi --ignore-time-filter --dry-run
```
### Menguji Sesi Siang
```bash
python3 main.py --sesi siang --ignore-time-filter --dry-run
```

**Hasil Pengujian:**
- Sistem akan mengunduh berita terkini, menganalisis emiten dengan Gemini AI, dan membuat file `index.html`.
- Anda dapat mengklik dua kali file `index.html` di komputer Anda untuk membukanya di browser (Chrome/Safari) dan melihat tampilannya!

---

## ☁️ Menjalankan Otomatis di GitHub Actions & GitHub Pages

Agar sistem berjalan sendiri setiap pagi jam **06.00 WIB** dan siang jam **11.50 WIB** tanpa perlu menyalakan komputer:

### 1. Inisialisasi Git & Upload ke GitHub
```bash
git init
git add .
git commit -m "feat: inisialisasi sistem dashboard berita saham 2 sesi"
git branch -M main
git remote add origin https://github.com/USERNAME_ANDA/NAMA_REPO_ANDA.git
git push -u origin main
```

### 2. Mengisi GitHub Secrets
Supaya GitHub Actions dapat mengakses API Gemini dan Telegram secara aman:
1. Buka repositori Anda di situs **GitHub.com**.
2. Masuk ke tab **Settings** > **Secrets and variables** > **Actions**.
3. Klik tombol **New repository secret** untuk menambahkan:
   - `GEMINI_API_KEY`: Kunci API dari Google AI Studio.
   - `TELEGRAM_BOT_TOKEN`: Token bot dari @BotFather.
   - `TELEGRAM_CHAT_ID`: ID chat Telegram Anda.
   - `DASHBOARD_URL`: URL GitHub Pages (misal `https://USERNAME.github.io/REPO/`).

### 3. Mengaktifkan GitHub Pages
1. Di repositori GitHub Anda, buka menu **Settings** > **Pages** (di kolom kiri).
2. Pada bagian **Build and deployment** > **Source**, ubah dari *Deploy from a branch* menjadi **GitHub Actions**.

### 4. Menjalankan Manual / Update Kapan Saja (Misal Malam Hari)
Selain berjalan otomatis jam **07.05** dan **13.25 WIB**, Anda bisa meminta update data terbaru kapan pun (misalnya jam 20.00 malam saat santai):

- **Dari HP (Tanpa Komputer Nyala)**:
  1. Buka browser di HP Anda, buka link repositori GitHub Anda.
  2. Buka tab **Actions** > pilih **Otomasi Dashboard Berita Saham IDX**.
  3. Klik tombol **Run workflow**. Centang opsi `ignore_time_filter` jika ingin menarik berita terkini saat itu juga, lalu klik tombol hijau **Run workflow**.
  4. Dalam 1–2 menit, sistem akan memproses berita, mengupdate web dashboard, dan mengirimkan pesan Telegram terbaru ke HP Anda!

- **Dari Laptop / Komputer**:
  Cukup jalankan di terminal:
  ```bash
  python3 main.py --sesi siang --ignore-time-filter
  ```

---

## 🔄 Cara Memperbarui Daftar Emiten IDX

Jika di kemudian hari Bursa Efek Indonesia kedatangan emiten baru (IPO) atau terjadi perubahan nama perusahaan:
```bash
python3 scripts/update_emiten.py
```
Script ini akan otomatis mengunduh daftar 11 sektor resmi BEI dan menyimpannya ke `data/emiten.csv`.

---

## 📰 Cara Menambah / Mengurangi Sumber Berita RSS

Semua sumber berita disimpan di file `config.py` dalam variabel `RSS_SOURCES`. 

Untuk menambah sumber baru, cukup tambahkan objek baru ke dalam daftar:
```python
{
    "name": "Nama Portal Berita",
    "url": "https://url-rss-portal.com/feed",
    "enabled": True,
}
```
Jika ada sumber yang ingin dinonaktifkan sementara tanpa menghapusnya, cukup ubah `"enabled": False`.
