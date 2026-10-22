"""
src/generator.py
Modul pembuatan halaman web dashboard statis (HTML/CSS/JS dalam satu file).
Mendukung:
- Sistem 2 sesi: Sesi Pagi (12.00–06.00 WIB) dan Sesi Siang (06.00–11.45 WIB).
- Tombol pemindah (switcher) antara Sesi Pagi dan Sesi Siang untuk tanggal yang sama (nonaktif jika belum rilis).
- Desain bersih & responsif (font IBM Plex Sans & Mono, warna aksen biru #1D4ED8, kartu border membulat).
- Toolbar pencarian instan dan filter sentimen berbasis JavaScript murni (tanpa reload).
- Sidebar: Top 5 saham terpopuler dengan diagram batang, rekap sentimen, dan riwayat arsip sesi.
- Menyimpan ke index.html (sesi terbaru), arsip/YYYY-MM-DD-{sesi}.html, dan data/YYYY-MM-DD-{sesi}.json.
"""

import os
import json
import glob
from datetime import datetime
from typing import Dict, List

from config import (
    BASE_DIR,
    DATA_DIR,
    ARCHIVE_DIR,
    INDEX_HTML_PATH,
    TIMEZONE,
)


def get_archive_list() -> List[dict]:
    """
    Memindai folder arsip/ untuk mendapatkan daftar seluruh sesi yang pernah dibuat.
    Mengembalikan daftar kamus terurut dari yang paling baru:
    [{ 'date': '2026-10-22', 'session': 'siang', 'filename': '2026-10-22-siang.html' }, ...]
    """
    if not os.path.exists(ARCHIVE_DIR):
        return []

    html_files = glob.glob(os.path.join(ARCHIVE_DIR, "*.html"))
    archives = []

    for filepath in html_files:
        filename = os.path.basename(filepath)
        # Pola: YYYY-MM-DD-sesi.html
        name_part = filename.replace(".html", "")
        parts = name_part.split("-")
        if len(parts) >= 4:
            date_str = f"{parts[0]}-{parts[1]}-{parts[2]}"
            session_str = parts[3].lower()
            archives.append({
                "date": date_str,
                "session": session_str,
                "session_label": "Sesi Pagi" if session_str == "pagi" else "Sesi Siang",
                "filename": filename,
            })

    # Urutkan berdasarkan tanggal & sesi (siang lebih baru dari pagi)
    archives.sort(
        key=lambda x: (x["date"], 1 if x["session"] == "siang" else 0),
        reverse=True
    )
    return archives


def render_dashboard_html(
    session: str,
    session_label: str,
    date_str: str,
    total_news: int,
    total_sources: int,
    sorted_stocks: Dict[str, dict],
    archives: List[dict],
    is_archive_page: bool = False,
) -> str:
    """
    Menghasilkan kode HTML lengkap (CSS + JS inline) untuk dashboard.
    """
    now_wib = datetime.now(TIMEZONE).strftime("%d %b %Y, %H:%M WIB")
    total_stocks = len(sorted_stocks)

    # Hitung rekap sentimen & aksi korporasi
    count_positif = sum(1 for s in sorted_stocks.values() if s.get("sentiment") == "Positif")
    count_netral = sum(1 for s in sorted_stocks.values() if s.get("sentiment") == "Netral")
    count_negatif = sum(1 for s in sorted_stocks.values() if s.get("sentiment") == "Negatif")
    count_buyback = sum(1 for s in sorted_stocks.values() if s.get("has_buyback"))
    count_pp = sum(1 for s in sorted_stocks.values() if s.get("has_pp"))

    # Ambil 5 saham teratas untuk visualisasi batang di sidebar
    top_5_stocks = list(sorted_stocks.values())[:5]
    max_news_count = top_5_stocks[0]["news_count"] if top_5_stocks else 1

    # Tentukan status switcher sesi untuk tanggal yang sama
    other_session = "siang" if session == "pagi" else "pagi"
    other_filename = f"{date_str}-{other_session}.html"
    other_file_exists = os.path.exists(os.path.join(ARCHIVE_DIR, other_filename))

    prefix = "../" if is_archive_page else ""
    home_link = "../index.html" if is_archive_page else "index.html"

    # URL tautan untuk sesi pagi dan siang pada tanggal ini
    pagi_link = f"{prefix}arsip/{date_str}-pagi.html" if session != "pagi" else "#"
    siang_link = f"{prefix}arsip/{date_str}-siang.html" if session != "siang" else "#"

    # Buat HTML kartu saham
    cards_html = []
    for code, stock in sorted_stocks.items():
        sentiment = stock.get("sentiment", "Netral")
        pill_class = f"pill-{sentiment.lower()}"
        company_name = stock.get("company_name", code)
        summary = stock.get("summary", "")
        news_items = stock.get("news", [])
        news_count = stock.get("news_count", len(news_items))

        # Komponen ringkasan AI
        summary_html = ""
        if summary:
            summary_html = f"""
            <div class="summary-box">
                <div class="summary-header">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
                    Ringkasan AI
                </div>
                <p class="summary-text">{summary}</p>
            </div>
            """

        # Daftar judul berita untuk saham ini
        headlines_html = []
        for n in news_items:
            headlines_html.append(f"""
            <li class="news-item">
                <a href="{n['link']}" target="_blank" rel="noopener noreferrer" class="news-link">
                    {n['title']}
                </a>
                <div class="news-meta">
                    <span class="news-source">{n['source']}</span>
                    <span class="news-dot">•</span>
                    <span class="news-time">{n['pub_date_str']}</span>
                </div>
            </li>
            """)

        # Buat badge aksi korporasi jika ada
        has_buyback = stock.get("has_buyback", False)
        has_pp = stock.get("has_pp", False)
        action_pills = []
        if has_buyback:
            action_pills.append('<span class="action-pill pill-buyback" title="Aksi Korporasi: Buyback Saham">🎯 Buyback</span>')
        if has_pp:
            action_pills.append('<span class="action-pill pill-pp" title="Aksi Korporasi: Private Placement / PMTHMETD">⚡ Private Placement</span>')
        action_pills_html = "".join(action_pills)

        cards_html.append(f"""
        <article class="stock-card" data-code="{code}" data-name="{company_name.lower()}" data-sentiment="{sentiment}" data-has-buyback="{'true' if has_buyback else 'false'}" data-has-pp="{'true' if has_pp else 'false'}">
            <div class="card-top">
                <div class="ticker-group">
                    <span class="ticker-code">{code}</span>
                    <span class="company-name" title="{company_name}">{company_name}</span>
                </div>
                <div class="badge-group">
                    {action_pills_html}
                    <span class="sentiment-pill {pill_class}">{sentiment}</span>
                    <span class="count-badge">{news_count} Berita</span>
                </div>
            </div>
            {summary_html}
            <div class="card-news-section">
                <div class="section-label">Berita Terkait:</div>
                <ul class="news-list">
                    {''.join(headlines_html)}
                </ul>
            </div>
        </article>
        """)

    # Render daftar 5 saham teratas di sidebar
    top_5_bars_html = []
    for item in top_5_stocks:
        pct = int((item["news_count"] / max_news_count) * 100)
        top_5_bars_html.append(f"""
        <div class="rank-item">
            <div class="rank-info">
                <span class="rank-ticker">{item['code']}</span>
                <span class="rank-count">{item['news_count']} berita</span>
            </div>
            <div class="progress-track">
                <div class="progress-bar" style="width: {pct}%"></div>
            </div>
        </div>
        """)

    # Render daftar arsip di sidebar (maks 10 arsip terakhir)
    archive_links_html = []
    for arc in archives[:10]:
        arc_href = f"{prefix}arsip/{arc['filename']}"
        active_class = "active" if arc["filename"] == f"{date_str}-{session}.html" else ""
        badge_class = "badge-pagi" if arc["session"] == "pagi" else "badge-siang"
        archive_links_html.append(f"""
        <a href="{arc_href}" class="archive-item {active_class}">
            <span class="archive-date">{arc['date']}</span>
            <span class="archive-badge {badge_class}">{arc['session_label']}</span>
        </a>
        """)

    if not archive_links_html:
        archive_links_html.append('<div class="empty-archive">Belum ada arsip hari lain.</div>')

    # Status tombol switch sesi
    pagi_btn_class = "session-btn active" if session == "pagi" else "session-btn"
    siang_btn_class = "session-btn active" if session == "siang" else "session-btn"

    if session == "pagi":
        pagi_attr = 'href="#"'
        if other_file_exists:
            siang_attr = f'href="{siang_link}"'
            siang_sub = ""
        else:
            siang_attr = 'href="javascript:void(0)" class="session-btn disabled" title="Sesi Siang belum tersedia"'
            siang_sub = '<span class="status-tag">belum tersedia</span>'
    else:  # Sesi siang
        siang_attr = 'href="#"'
        pagi_attr = f'href="{pagi_link}"'
        siang_sub = ""

    header_badge = "RANGKUMAN PAGI" if session == "pagi" else "RANGKUMAN SIANG"
    session_title = "Sesi Pagi · 13.20–07.00 WIB" if session == "pagi" else "Sesi Siang · 07.00–13.20 WIB"

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Berita Saham IDX - {session_title}</title>
    <!-- Google Fonts: IBM Plex Sans & IBM Plex Mono -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-page: #F4F6F9;
            --bg-card: #FFFFFF;
            --border-color: #E2E8F0;
            --border-hover: #CBD5E1;
            --text-main: #0F172A;
            --text-secondary: #475569;
            --text-muted: #94A3B8;
            --blue-accent: #1D4ED8;
            --blue-light: #EFF6FF;
            --blue-border: #BFDBFE;
            
            /* Sentimen */
            --pos-text: #1D4ED8;
            --pos-bg: #EFF6FF;
            --pos-border: #DBEAFE;
            --net-text: #334155;
            --net-bg: #F1F5F9;
            --net-border: #E2E8F0;
            --neg-text: #C2410C;
            --neg-bg: #FFF7ED;
            --neg-border: #FFEDD5;

            --font-sans: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --font-mono: 'IBM Plex Mono', SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            --radius-md: 12px;
            --radius-sm: 8px;
            --radius-pill: 9999px;
            --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(15, 23, 42, 0.08);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-page);
            font-family: var(--font-sans);
            color: var(--text-main);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            padding-bottom: 60px;
        }}

        /* Container utama */
        .container {{
            max-width: 1240px;
            margin: 0 auto;
            padding: 0 20px;
        }}

        /* Header */
        header.dashboard-header {{
            background-color: var(--bg-card);
            border-bottom: 1px solid var(--border-color);
            padding: 32px 0 24px;
            margin-bottom: 24px;
        }}

        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 24px;
        }}

        .header-tag {{
            display: inline-block;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.08em;
            color: var(--blue-accent);
            background-color: var(--blue-light);
            border: 1px solid var(--blue-border);
            padding: 4px 10px;
            border-radius: var(--radius-pill);
            margin-bottom: 8px;
        }}

        h1.dashboard-title {{
            font-size: 28px;
            font-weight: 700;
            color: var(--text-main);
            letter-spacing: -0.02em;
            line-height: 1.2;
            margin-bottom: 6px;
        }}

        .header-meta {{
            font-size: 14px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .meta-session {{
            font-weight: 600;
            color: var(--blue-accent);
        }}

        /* Switcher Sesi */
        .session-switcher {{
            display: inline-flex;
            background-color: var(--bg-page);
            border: 1px solid var(--border-color);
            padding: 4px;
            border-radius: var(--radius-md);
            gap: 4px;
        }}

        .session-btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            color: var(--text-secondary);
            border-radius: var(--radius-sm);
            transition: all 0.15s ease;
        }}

        .session-btn:hover:not(.disabled):not(.active) {{
            background-color: rgba(255, 255, 255, 0.8);
            color: var(--text-main);
        }}

        .session-btn.active {{
            background-color: var(--bg-card);
            color: var(--blue-accent);
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border-color);
        }}

        .session-btn.disabled {{
            opacity: 0.55;
            cursor: not-allowed;
            color: var(--text-muted);
        }}

        .status-tag {{
            font-size: 10px;
            background-color: #E2E8F0;
            color: #64748B;
            padding: 2px 6px;
            border-radius: var(--radius-pill);
            font-weight: 500;
        }}

        /* Kotak Statistik */
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
        }}

        .stat-box {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
        }}

        .stat-value {{
            font-size: 26px;
            font-weight: 700;
            font-family: var(--font-mono);
            color: var(--text-main);
            line-height: 1.1;
        }}

        .stat-label {{
            font-size: 12px;
            font-weight: 500;
            color: var(--text-secondary);
            margin-top: 4px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        /* Toolbar Kontrol (Pencarian & Filter) */
        .toolbar {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 14px 18px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 14px;
            box-shadow: var(--shadow-sm);
        }}

        .search-box {{
            position: relative;
            flex: 1;
            min-width: 260px;
        }}

        .search-input {{
            width: 100%;
            padding: 10px 14px 10px 38px;
            font-size: 14px;
            font-family: var(--font-sans);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            outline: none;
            background-color: var(--bg-page);
            color: var(--text-main);
            transition: border-color 0.15s ease;
        }}

        .search-input:focus {{
            border-color: var(--blue-accent);
            background-color: #FFFFFF;
        }}

        .search-icon {{
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            pointer-events: none;
        }}

        .filter-buttons {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
        }}

        .filter-btn {{
            background-color: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 500;
            padding: 7px 14px;
            border-radius: var(--radius-pill);
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .filter-btn:hover {{
            border-color: var(--border-hover);
            color: var(--text-main);
        }}

        .filter-btn.active {{
            background-color: var(--blue-accent);
            color: #FFFFFF;
            border-color: var(--blue-accent);
        }}

        /* Tata Letak Konten & Sidebar */
        .main-layout {{
            display: grid;
            grid-template-columns: 1fr 340px;
            gap: 24px;
            align-items: start;
        }}

        /* Daftar Kartu Saham */
        .stock-cards-list {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .stock-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 20px;
            box-shadow: var(--shadow-sm);
            transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
        }}

        .stock-card:hover {{
            border-color: var(--border-hover);
            box-shadow: var(--shadow-md);
        }}

        .stock-card.hidden {{
            display: none !important;
        }}

        .card-top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 14px;
            flex-wrap: wrap;
        }}

        .ticker-group {{
            display: flex;
            flex-direction: column;
        }}

        .ticker-code {{
            font-family: var(--font-mono);
            font-size: 22px;
            font-weight: 700;
            color: var(--blue-accent);
            letter-spacing: -0.01em;
            line-height: 1.1;
        }}

        .company-name {{
            font-size: 13px;
            color: var(--text-secondary);
            font-weight: 500;
            margin-top: 2px;
        }}

        .badge-group {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        .sentiment-pill {{
            font-size: 12px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: var(--radius-pill);
            display: inline-flex;
            align-items: center;
            letter-spacing: 0.02em;
        }}

        .pill-positif {{
            background-color: var(--pos-bg);
            color: var(--pos-text);
            border: 1px solid var(--pos-border);
        }}

        .pill-netral {{
            background-color: var(--net-bg);
            color: var(--net-text);
            border: 1px solid var(--net-border);
        }}

        .pill-negatif {{
            background-color: var(--neg-bg);
            color: var(--neg-text);
            border: 1px solid var(--neg-border);
        }}

        /* Aksi Korporasi: Buyback & Private Placement */
        .action-pill {{
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: var(--radius-pill);
            display: inline-flex;
            align-items: center;
            letter-spacing: 0.02em;
        }}

        .pill-buyback {{
            background-color: #ECFDF5;
            color: #047857;
            border: 1px solid #A7F3D0;
        }}

        .pill-pp {{
            background-color: #F5F3FF;
            color: #6D28D9;
            border: 1px solid #DDD6FE;
        }}

        .filter-action-btn.btn-buyback:hover, .filter-action-btn.btn-buyback.active {{
            background-color: #047857 !important;
            border-color: #047857 !important;
            color: #FFFFFF !important;
        }}

        .filter-action-btn.btn-pp:hover, .filter-action-btn.btn-pp.active {{
            background-color: #6D28D9 !important;
            border-color: #6D28D9 !important;
            color: #FFFFFF !important;
        }}

        .count-badge {{
            font-size: 12px;
            font-weight: 500;
            background-color: var(--bg-page);
            color: var(--text-secondary);
            padding: 4px 10px;
            border-radius: var(--radius-sm);
            border: 1px solid var(--border-color);
        }}

        /* Ringkasan AI Box */
        .summary-box {{
            background-color: #F8FAFC;
            border-left: 3px solid var(--blue-accent);
            border-radius: 4px var(--radius-sm) var(--radius-sm) 4px;
            padding: 12px 14px;
            margin-bottom: 16px;
        }}

        .summary-header {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--blue-accent);
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 4px;
        }}

        .summary-text {{
            font-size: 13.5px;
            color: var(--text-main);
            line-height: 1.5;
        }}

        /* Bagian Berita */
        .card-news-section {{
            border-top: 1px solid var(--border-color);
            padding-top: 12px;
        }}

        .section-label {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }}

        .news-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .news-item {{
            display: flex;
            flex-direction: column;
            gap: 2px;
        }}

        .news-link {{
            font-size: 14px;
            font-weight: 500;
            color: var(--text-main);
            text-decoration: none;
            line-height: 1.4;
            transition: color 0.15s ease;
        }}

        .news-link:hover {{
            color: var(--blue-accent);
            text-decoration: underline;
        }}

        .news-meta {{
            font-size: 11.5px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .news-source {{
            font-weight: 600;
            color: var(--text-secondary);
        }}

        .news-dot {{
            color: var(--text-muted);
        }}

        /* Sidebar */
        .sidebar {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}

        .side-widget {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 18px;
            box-shadow: var(--shadow-sm);
        }}

        .widget-title {{
            font-size: 14px;
            font-weight: 700;
            color: var(--text-main);
            letter-spacing: -0.01em;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        /* Widget Top 5 Progress Bar */
        .rank-item {{
            margin-bottom: 12px;
        }}

        .rank-item:last-child {{
            margin-bottom: 0;
        }}

        .rank-info {{
            display: flex;
            justify-content: space-between;
            font-size: 12.5px;
            margin-bottom: 4px;
        }}

        .rank-ticker {{
            font-family: var(--font-mono);
            font-weight: 700;
            color: var(--text-main);
        }}

        .rank-count {{
            color: var(--text-secondary);
            font-size: 11.5px;
        }}

        .progress-track {{
            height: 6px;
            background-color: var(--bg-page);
            border-radius: var(--radius-pill);
            overflow: hidden;
        }}

        .progress-bar {{
            height: 100%;
            background-color: var(--blue-accent);
            border-radius: var(--radius-pill);
        }}

        /* Widget Rekap Sentimen */
        .sentiment-recap-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            text-align: center;
        }}

        .recap-box {{
            padding: 10px 6px;
            border-radius: var(--radius-sm);
            display: flex;
            flex-direction: column;
        }}

        .recap-box.box-pos {{
            background-color: var(--pos-bg);
            border: 1px solid var(--pos-border);
        }}

        .recap-box.box-net {{
            background-color: var(--net-bg);
            border: 1px solid var(--net-border);
        }}

        .recap-box.box-neg {{
            background-color: var(--neg-bg);
            border: 1px solid var(--neg-border);
        }}

        .recap-num {{
            font-size: 20px;
            font-weight: 700;
            font-family: var(--font-mono);
            line-height: 1.1;
        }}

        .recap-box.box-pos .recap-num {{ color: var(--pos-text); }}
        .recap-box.box-net .recap-num {{ color: var(--net-text); }}
        .recap-box.box-neg .recap-num {{ color: var(--neg-text); }}

        .recap-label {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-top: 2px;
        }}

        /* Widget Arsip */
        .archive-list {{
            display: flex;
            flex-direction: column;
            gap: 6px;
            max-height: 280px;
            overflow-y: auto;
        }}

        .archive-item {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 10px;
            background-color: var(--bg-page);
            border: 1px solid transparent;
            border-radius: var(--radius-sm);
            text-decoration: none;
            color: var(--text-main);
            font-size: 12.5px;
            transition: all 0.15s ease;
        }}

        .archive-item:hover {{
            background-color: #FFFFFF;
            border-color: var(--border-color);
        }}

        .archive-item.active {{
            background-color: var(--blue-light);
            border-color: var(--blue-border);
            color: var(--blue-accent);
            font-weight: 600;
        }}

        .archive-badge {{
            font-size: 10px;
            padding: 2px 6px;
            border-radius: var(--radius-pill);
            font-weight: 600;
        }}

        .badge-pagi {{
            background-color: #E0E7FF;
            color: #3730A3;
        }}

        .badge-siang {{
            background-color: #FEF3C7;
            color: #92400E;
        }}

        .empty-archive {{
            font-size: 12px;
            color: var(--text-muted);
            text-align: center;
            padding: 12px 0;
        }}

        /* Footer & Catatan Kaki */
        footer.dashboard-footer {{
            margin-top: 48px;
            text-align: center;
            font-size: 12.5px;
            color: var(--text-secondary);
            border-top: 1px solid var(--border-color);
            padding-top: 24px;
        }}

        .disclaimer {{
            background-color: #FFFBEB;
            border: 1px solid #FEF3C7;
            color: #92400E;
            padding: 10px 16px;
            border-radius: var(--radius-sm);
            display: inline-block;
            margin-bottom: 12px;
            font-size: 12px;
            line-height: 1.5;
        }}

        /* Responsive Breakpoints (Mobile Friendly) */
        @media (max-width: 900px) {{
            .main-layout {{
                grid-template-columns: 1fr;
            }}
            .sidebar {{
                order: 2;
            }}
            .stock-cards-list {{
                order: 1;
            }}
        }}

        @media (max-width: 640px) {{
            .stat-grid {{
                grid-template-columns: 1fr;
            }}
            .header-top {{
                flex-direction: column;
            }}
            .session-switcher {{
                width: 100%;
                justify-content: stretch;
            }}
            .session-btn {{
                flex: 1;
                justify-content: center;
            }}
            h1.dashboard-title {{
                font-size: 24px;
            }}
            .toolbar {{
                flex-direction: column;
                align-items: stretch;
            }}
            .filter-buttons {{
                justify-content: center;
            }}
        }}
    </style>
</head>
<body>

    <!-- Header Halaman -->
    <header class="dashboard-header">
        <div class="container">
            <div class="header-top">
                <div>
                    <span class="header-tag">{header_badge}</span>
                    <h1 class="dashboard-title">Berita Saham Hari Ini</h1>
                    <div class="header-meta">
                        <span class="meta-session">{session_title}</span>
                        <span>•</span>
                        <span>Update: {now_wib}</span>
                    </div>
                </div>

                <!-- Pemindah Sesi (Pagi <-> Siang) -->
                <div class="session-switcher">
                    <a {pagi_attr} class="{pagi_btn_class}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>
                        Sesi Pagi
                    </a>
                    <a {siang_attr} class="{siang_btn_class}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>
                        Sesi Siang
                        {siang_sub}
                    </a>
                </div>
            </div>

            <!-- Tiga Kotak Angka Ringkasan -->
            <div class="stat-grid">
                <div class="stat-box">
                    <span class="stat-value">{total_news}</span>
                    <span class="stat-label">Total Berita Disaring</span>
                </div>
                <div class="stat-box">
                    <span class="stat-value">{total_stocks}</span>
                    <span class="stat-label">Saham IDX Dibahas</span>
                </div>
                <div class="stat-box">
                    <span class="stat-value">{total_sources}</span>
                    <span class="stat-label">Sumber Berita Aktif</span>
                </div>
            </div>
        </div>
    </header>

    <div class="container">
        <!-- Toolbar Pencarian & Filter Sentimen Interaktif -->
        <div class="toolbar">
            <div class="search-box">
                <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input type="text" id="searchInput" class="search-input" placeholder="Cari kode saham atau nama emiten (misal: BBCA, Bank Mandiri)...">
            </div>
            <div class="filter-buttons">
                <button class="filter-btn active" data-filter="all">Semua ({total_stocks})</button>
                <button class="filter-btn" data-filter="Positif">Positif ({count_positif})</button>
                <button class="filter-btn" data-filter="Netral">Netral ({count_netral})</button>
                <button class="filter-btn" data-filter="Negatif">Negatif ({count_negatif})</button>
                <button class="filter-btn filter-action-btn btn-buyback" data-filter="buyback">🎯 Buyback ({count_buyback})</button>
                <button class="filter-btn filter-action-btn btn-pp" data-filter="pp">⚡ Private Placement ({count_pp})</button>
            </div>
        </div>

        <!-- Tata Letak Utama -->
        <main class="main-layout">
            <!-- Kolom Kiri: Kartu Saham -->
            <section class="stock-cards-list" id="stockCardsContainer">
                {''.join(cards_html) if cards_html else '<div class="empty-state">Tidak ada saham yang memenuhi kriteria filter.</div>'}
            </section>

            <!-- Kolom Kanan / Bawah: Sidebar -->
            <aside class="sidebar">
                <!-- Widget Top 5 Saham -->
                <div class="side-widget">
                    <h2 class="widget-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
                        Paling Ramai Diberitakan
                    </h2>
                    <div class="top-ranks">
                        {''.join(top_5_bars_html)}
                    </div>
                </div>

                <!-- Widget Rekap Sentimen -->
                <div class="side-widget">
                    <h2 class="widget-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
                        Rekap Sentimen Saham
                    </h2>
                    <div class="sentiment-recap-grid">
                        <div class="recap-box box-pos">
                            <span class="recap-num">{count_positif}</span>
                            <span class="recap-label">Positif</span>
                        </div>
                        <div class="recap-box box-net">
                            <span class="recap-num">{count_netral}</span>
                            <span class="recap-label">Netral</span>
                        </div>
                        <div class="recap-box box-neg">
                            <span class="recap-num">{count_negatif}</span>
                            <span class="recap-label">Negatif</span>
                        </div>
                    </div>
                </div>

                <!-- Widget Riwayat Arsip -->
                <div class="side-widget">
                    <h2 class="widget-title">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg>
                        Arsip Sesi Sebelumnya
                    </h2>
                    <div class="archive-list">
                        {''.join(archive_links_html)}
                    </div>
                </div>
            </aside>
        </main>

        <!-- Footer & Disclaimer -->
        <footer class="dashboard-footer">
            <div class="disclaimer">
                ⚠️ <strong>Catatan:</strong> Ringkasan dan sentimen dibuat otomatis oleh AI dari judul berita, bisa keliru. Bukan rekomendasi jual/beli saham.
            </div>
            <p>Dashboard Berita Saham IDX • Diperbarui otomatis via GitHub Actions & Gemini API</p>
        </footer>
    </div>

    <!-- JavaScript Murni untuk Pencarian & Filter Instan -->
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            const searchInput = document.getElementById('searchInput');
            const filterButtons = document.querySelectorAll('.filter-btn');
            const cards = document.querySelectorAll('.stock-card');
            let currentFilter = 'all';

            function applyFilters() {{
                const query = searchInput.value.toLowerCase().trim();

                cards.forEach(card => {{
                    const code = card.getAttribute('data-code').toLowerCase();
                    const name = card.getAttribute('data-name').toLowerCase();
                    const sentiment = card.getAttribute('data-sentiment');
                    const hasBuyback = card.getAttribute('data-has-buyback') === 'true';
                    const hasPP = card.getAttribute('data-has-pp') === 'true';

                    const matchesSearch = !query || code.includes(query) || name.includes(query)
                        || (query === 'buyback' && hasBuyback)
                        || (query.includes('placement') && hasPP);

                    let matchesFilter = false;
                    if (currentFilter === 'all') {{
                        matchesFilter = true;
                    }} else if (currentFilter === 'buyback') {{
                        matchesFilter = hasBuyback;
                    }} else if (currentFilter === 'pp') {{
                        matchesFilter = hasPP;
                    }} else {{
                        matchesFilter = (sentiment === currentFilter);
                    }}

                    if (matchesSearch && matchesFilter) {{
                        card.classList.remove('hidden');
                    }} else {{
                        card.classList.add('hidden');
                    }}
                }});
            }}

            // Event listener pencarian
            searchInput.addEventListener('input', applyFilters);

            // Event listener tombol filter sentimen
            filterButtons.forEach(btn => {{
                btn.addEventListener('click', function() {{
                    filterButtons.forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    currentFilter = this.getAttribute('data-filter');
                    applyFilters();
                }});
            }});
        }});
    </script>
</body>
</html>
"""


def generate_dashboard(
    session: str,
    session_label: str,
    date_str: str,
    total_news: int,
    total_sources: int,
    sorted_stocks: Dict[str, dict],
    news_items: List[dict] = None,
) -> dict:
    """
    Fungsi utama pembuatan dan penyimpanan file dashboard:
    1. Menyimpan data mentah ke data/YYYY-MM-DD-{sesi}.json
    2. Merender HTML arsip ke arsip/YYYY-MM-DD-{sesi}.html
    3. Merender HTML utama ke index.html (selalu menampilkan sesi terbaru)
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 1. Simpan data mentah JSON
    json_filename = f"{date_str}-{session}.json"
    json_filepath = os.path.join(DATA_DIR, json_filename)
    payload_to_save = {
        "date": date_str,
        "session": session,
        "session_label": session_label,
        "total_news": total_news,
        "total_sources": total_sources,
        "total_stocks": len(sorted_stocks),
        "stocks": sorted_stocks,
        "news_items": news_items or [],
    }

    with open(json_filepath, "w", encoding="utf-8") as f:
        json.dump(payload_to_save, f, ensure_ascii=False, indent=2, default=str)

    # 2. Dapatkan daftar arsip terkini
    archives = get_archive_list()
    # Pastikan sesi saat ini terdaftar jika belum ada
    current_entry = {
        "date": date_str,
        "session": session,
        "session_label": "Sesi Pagi" if session == "pagi" else "Sesi Siang",
        "filename": f"{date_str}-{session}.html"
    }
    if not any(a["filename"] == current_entry["filename"] for a in archives):
        archives.insert(0, current_entry)

    # 3. Render file arsip (is_archive_page=True)
    archive_html = render_dashboard_html(
        session=session,
        session_label=session_label,
        date_str=date_str,
        total_news=total_news,
        total_sources=total_sources,
        sorted_stocks=sorted_stocks,
        archives=archives,
        is_archive_page=True,
    )
    archive_filepath = os.path.join(ARCHIVE_DIR, f"{date_str}-{session}.html")
    with open(archive_filepath, "w", encoding="utf-8") as f:
        f.write(archive_html)

    # 4. Render file index.html (is_archive_page=False)
    index_html = render_dashboard_html(
        session=session,
        session_label=session_label,
        date_str=date_str,
        total_news=total_news,
        total_sources=total_sources,
        sorted_stocks=sorted_stocks,
        archives=archives,
        is_archive_page=False,
    )
    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(index_html)

    return {
        "index_html": INDEX_HTML_PATH,
        "archive_html": archive_filepath,
        "json_path": json_filepath,
    }
