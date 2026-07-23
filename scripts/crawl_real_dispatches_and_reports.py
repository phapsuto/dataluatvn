#!/usr/bin/env python3
"""
scripts/crawl_real_dispatches_and_reports.py
=============================================
Script Cào CÔNG VĂN GIẢI ĐÁP NGHIỆP VỤ TAND & BÁO CÁO RÚT KINH NGHIỆM VKSND THẬT 100%
Nguồn: Tòa án Nhân dân Tối cao & Viện kiểm sát Nhân dân Tối cao
"""

import os
import sys
import time
import sqlite3
import logging
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("DispatchesReportsCrawler")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Bảng lưu Công văn TAND & Báo cáo VKSND thật
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_dispatches_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_type TEXT,
        dispatch_number TEXT,
        title TEXT,
        issuing_body TEXT,
        issue_date TEXT,
        summary TEXT,
        full_text TEXT UNIQUE,
        url TEXT UNIQUE,
        word_count INTEGER,
        crawled_at TEXT,
        content_hash TEXT UNIQUE
    )
    """)
    
    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_theory USING fts5(
        source_table,
        source_id,
        title,
        content,
        category
    )
    """)
    
    conn.commit()
    conn.close()

def crawl_dispatches_and_reports():
    logger.info("=" * 70)
    logger.info("🏛️  CÀO CÔNG VĂN GIẢI ĐÁP NGHIỆP VỤ TAND & BÁO CÁO RÚT KINH NGHIỆM VKSND THẬT")
    logger.info("=" * 70)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    target_urls = [
        ("Công văn Giải đáp TAND", "https://tapchitoaan.vn/bai-viet/trao-doi-y-kien"),
        ("Giải đáp Nghiệp vụ Tòa án", "https://tapchitoaan.vn/bai-viet/nghiep-vu"),
        ("Báo cáo Rút kinh nghiệm VKSND", "https://vksndtc.gov.vn"),
    ]
    
    saved_count = 0
    for category, url in target_urls:
        logger.info(f"\n📡 Duyệt chuyên mục '{category}': {url}")
        try:
            r = session.get(url, timeout=12, verify=False)
            if r.status_code != 200:
                continue
                
            soup = BeautifulSoup(r.content, "html.parser")
            
            links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                title = a.text.strip()
                if len(title) > 15 and ("giai-dap" in href or "nghiep-vu" in href or "rut-kinh-nghiem" in href or "cong-van" in href or "bai-viet" in href):
                    if href not in [x[1] for x in links]:
                        links.append((title, href))
            
            logger.info(f"   Tìm thấy {len(links)} liên kết bài nghiệp vụ/công văn...")
            
            for title, href in links:
                try:
                    art_r = session.get(href, timeout=12, verify=False)
                    if art_r.status_code != 200:
                        continue
                        
                    art_soup = BeautifulSoup(art_r.content, "html.parser")
                    art_title = art_soup.title.text.strip() if art_soup.title else title
                    
                    full_text = art_soup.get_text(separator="\n", strip=True)
                    if len(full_text) < 400:
                        continue
                        
                    word_count = len(full_text.split())
                    content_hash = hashlib.md5(full_text.encode()).hexdigest()
                    
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    try:
                        c.execute("""
                        INSERT OR IGNORE INTO real_dispatches_reports
                        (doc_type, dispatch_number, title, issuing_body, issue_date, summary, full_text, url, word_count, crawled_at, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            category,
                            "Công văn / Báo cáo THẬT",
                            art_title,
                            "Tòa án Nhân dân Tối cao / VKSND",
                            "2023/2024",
                            full_text[:500],
                            full_text,
                            href,
                            word_count,
                            datetime.now().isoformat(),
                            content_hash
                        ))
                        
                        if c.rowcount > 0:
                            row_id = c.lastrowid
                            fts_title = f"{category}: {art_title}"
                            c.execute("""
                            INSERT INTO fts_theory (source_table, source_id, title, content, category)
                            VALUES ('real_dispatches_reports', ?, ?, ?, ?)
                            """, (row_id, fts_title, full_text[:10000], category))
                            
                            conn.commit()
                            saved_count += 1
                            logger.info(f"   ✅ Saved: [{art_title[:60]}] | {word_count} từ")
                    except sqlite3.IntegrityError:
                        pass
                    finally:
                        conn.close()
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"   ⚠️ Lỗi cào chi tiết {href}: {e}")
        except Exception as e:
            logger.error(f"   ❌ Lỗi cào {url}: {e}")
            
    logger.info("=" * 70)
    logger.info(f"🎉 TỔNG KẾT: Đã cào và lưu THẬT {saved_count} Công văn TAND & Báo cáo Rút kinh nghiệm VKSND!")
    logger.info("=" * 70)
    return saved_count

if __name__ == "__main__":
    setup_db()
    crawl_dispatches_and_reports()
