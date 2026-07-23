#!/usr/bin/env python3
"""
scripts/crawl_real_moj_danchu.py
=================================
Script Cào BÀI BÁO KHOA HỌC & GIẢI ĐÁP NGHIỆP VỤ THẬT 100%
từ Tạp chí Dân chủ và Pháp luật & Cổng thông tin Bộ Tư pháp (MOJ)
URLs: https://danchuphapluat.vn & https://moj.gov.vn
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
import urllib3
urllib3.disable_warnings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("MOJDanchuCrawler")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_academic_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        category TEXT,
        author TEXT,
        institution TEXT,
        publish_date TEXT,
        summary TEXT,
        full_text TEXT UNIQUE,
        url TEXT UNIQUE,
        word_count INTEGER,
        crawled_at TEXT,
        content_hash TEXT UNIQUE
    )
    """)
    conn.commit()
    conn.close()

def crawl_danchu_phapluat():
    logger.info("=" * 70)
    logger.info("📰 CÀO TẠP CHÍ DÂN CHỦ VÀ PHÁP LUẬT THẬT (danchuphapluat.vn)")
    logger.info("=" * 70)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    categories = [
        ("Nghiên cứu - Trao đổi", "https://danchuphapluat.vn/xay-dung-va-hoan-thien-phap-luat/nghien-cuu-trao-doi"),
        ("Phản biện - Đề xuất chính sách", "https://danchuphapluat.vn/xay-dung-va-hoan-thien-phap-luat/phan-bien-de-xuat-chinh-sach"),
        ("Thực thi Pháp luật", "https://danchuphapluat.vn/to-chuc-thi-hanh-phap-luat"),
    ]
    
    saved_count = 0
    for cat_name, cat_url in categories:
        logger.info(f"\n📡 Duyệt danh mục '{cat_name}': {cat_url}")
        try:
            r = session.get(cat_url, timeout=12, verify=False)
            if r.status_code != 200:
                continue
                
            soup = BeautifulSoup(r.content, "html.parser")
            
            article_links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(cat_url, a["href"])
                title = a.text.strip()
                if len(title) > 20 and "danchuphapluat.vn" in href and href != cat_url:
                    if href not in [x[1] for x in article_links]:
                        article_links.append((title, href))
            
            logger.info(f"   Tìm thấy {len(article_links)} liên kết bài báo...")
            
            for title, href in article_links[:15]:
                try:
                    art_r = session.get(href, timeout=12, verify=False)
                    if art_r.status_code != 200:
                        continue
                        
                    art_soup = BeautifulSoup(art_r.content, "html.parser")
                    art_title = art_soup.title.text.strip() if art_soup.title else title
                    
                    content_div = art_soup.find("div", class_="detail-content") or art_soup.find("article") or art_soup.find("div", class_="content")
                    if content_div:
                        full_text = content_div.get_text(separator="\n", strip=True)
                    else:
                        full_text = art_soup.get_text(separator="\n", strip=True)
                        
                    if len(full_text) < 400:
                        continue
                        
                    word_count = len(full_text.split())
                    content_hash = hashlib.md5(full_text.encode()).hexdigest()
                    
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    try:
                        c.execute("""
                        INSERT OR IGNORE INTO real_academic_articles
                        (title, category, author, institution, publish_date, summary, full_text, url, word_count, crawled_at, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            art_title,
                            cat_name,
                            "Tạp chí Dân chủ và Pháp luật",
                            "Bộ Tư pháp",
                            "2024",
                            full_text[:500],
                            full_text,
                            href,
                            word_count,
                            datetime.now().isoformat(),
                            content_hash
                        ))
                        
                        if c.rowcount > 0:
                            row_id = c.lastrowid
                            fts_title = f"Tạp chí DCPL: {art_title}"
                            c.execute("""
                            INSERT INTO fts_theory (source_table, source_id, title, content, category)
                            VALUES ('real_academic_articles', ?, ?, ?, ?)
                            """, (row_id, fts_title, full_text[:10000], cat_name))
                            
                            conn.commit()
                            saved_count += 1
                            logger.info(f"   ✅ Saved: [{art_title[:60]}] | {word_count} từ")
                    except sqlite3.IntegrityError:
                        pass
                    finally:
                        conn.close()
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"   ⚠️ Lỗi cào {href}: {e}")
        except Exception as e:
            logger.error(f"   ❌ Lỗi cào {cat_url}: {e}")
            
    logger.info("=" * 70)
    logger.info(f"🎉 TỔNG KẾT: Đã cào và lưu THẬT {saved_count} bài báo Tạp chí Dân chủ & Pháp luật!")
    logger.info("=" * 70)
    return saved_count

if __name__ == "__main__":
    setup_db()
    crawl_danchu_phapluat()
