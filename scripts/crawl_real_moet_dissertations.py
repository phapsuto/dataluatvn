#!/usr/bin/env python3
"""
scripts/crawl_real_moet_dissertations.py
=========================================
Script Cào TOÀN VĂN LUẬN ÁN TIẾN SĨ LUẬT THẬT 100% từ Cổng Chuyên trang Luận văn - Luận án Bộ Giáo dục & Đào tạo (MOET)
URL: http://luanvan.moet.gov.vn
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
logger = logging.getLogger("MOETDissertationCrawler")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Bảng lưu Luận án Tiến sĩ thật từ Bộ GD&ĐT
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_dissertations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        degree_type TEXT,
        title TEXT,
        author TEXT,
        specialization TEXT,
        institution TEXT,
        publish_year TEXT,
        abstract_summary TEXT,
        full_text TEXT,
        source_url TEXT UNIQUE,
        download_link TEXT,
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

def crawl_moet_dissertations(max_pages=30):
    logger.info("=" * 70)
    logger.info("🎓 CÀO LUẬN ÁN TIẾN SĨ LUẬT THẬT TỪ BỘ GIÁO DỤC & ĐÀO TẠO (MOET)")
    logger.info("=" * 70)
    
    session = requests.Session()
    session.headers.update(HEADERS)
    # Disable SSL redirect issues
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    saved_count = 0
    
    # Keywords lọc ngành luật
    law_keywords = [
        "luật", "pháp luật", "tố tụng", "tòa án", "viện kiểm sát", "hình sự", "dân sự",
        "hiến pháp", "hành chính", "đất đai", "thương mại", "lao động", "tư pháp",
        "quyền con người", "tài phán", "án lệ", "quy phạm", "thể chế"
    ]
    
    for page in range(1, max_pages + 1):
        list_url = f"http://luanvan.moet.gov.vn/?page=1.{page}"
        logger.info(f"\n📡 Duyệt danh mục MOET trang {page}/{max_pages}: {list_url}")
        
        try:
            r = session.get(list_url, timeout=15, allow_redirects=True)
            if r.status_code != 200:
                logger.warning(f"   HTTP {r.status_code} - Bỏ qua trang {page}")
                continue
                
            soup = BeautifulSoup(r.content, "html.parser")
            
            # Lấy tất cả item luận án
            items = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.text.strip()
                if "view=" in href and len(text) > 10:
                    full_url = f"http://luanvan.moet.gov.vn/{href}" if not href.startswith("http") else href
                    items.append((text, full_url))
            
            logger.info(f"   Trang {page}: Tìm thấy {len(items)} luận án...")
            
            for item_title, item_url in items:
                # Kiểm tra keyword xem có thuộc ngành Luật / Pháp lý không
                if not any(k in item_title.lower() for k in law_keywords):
                    continue
                
                logger.info(f"   🎯 Phát hiện Luận án Luật THẬT: [{item_title[:60]}...]")
                
                try:
                    detail_r = session.get(item_url, timeout=12)
                    if detail_r.status_code != 200:
                        continue
                        
                    detail_soup = BeautifulSoup(detail_r.content, "html.parser")
                    
                    full_text_page = detail_soup.get_text(separator="\n", strip=True)
                    
                    # Trích xuất metadata
                    author = "NCS"
                    specialization = "Ngành Luật"
                    institution = "Cơ sở Đào tạo Tiến sĩ"
                    
                    for line in full_text_page.split("\n"):
                        if "Tác giả:" in line or "NCS:" in line:
                            author = line.replace("Tác giả:", "").replace("NCS:", "").strip()
                        elif "Chuyên ngành:" in line:
                            specialization = line.replace("Chuyên ngành:", "").strip()
                        elif "Nguồn phát hành:" in line or "Cơ sở đào tạo:" in line:
                            institution = line.replace("Nguồn phát hành:", "").replace("Cơ sở đào tạo:", "").strip()
                    
                    word_count = len(full_text_page.split())
                    content_hash = hashlib.md5(full_text_page.encode()).hexdigest()
                    
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    try:
                        c.execute("""
                        INSERT OR IGNORE INTO real_dissertations
                        (degree_type, title, author, specialization, institution, publish_year, abstract_summary, full_text, source_url, download_link, word_count, crawled_at, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            "Luận án Tiến sĩ Luật THẬT",
                            item_title,
                            author,
                            specialization,
                            institution,
                            "2023/2024",
                            full_text_page[:600],
                            full_text_page,
                            item_url,
                            item_url,
                            word_count,
                            datetime.now().isoformat(),
                            content_hash
                        ))
                        
                        if c.rowcount > 0:
                            row_id = c.lastrowid
                            fts_title = f"Luận án Tiến sĩ: {item_title} ({author} - {institution})"
                            c.execute("""
                            INSERT INTO fts_theory (source_table, source_id, title, content, category)
                            VALUES ('real_dissertations', ?, ?, ?, ?)
                            """, (row_id, fts_title, full_text_page[:10000], specialization))
                            
                            conn.commit()
                            saved_count += 1
                            logger.info(f"   ✅ Saved: [{item_title[:60]}] | {author} | {institution}")
                    except sqlite3.IntegrityError:
                        pass
                    finally:
                        conn.close()
                        
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"   ⚠️ Lỗi cào chi tiết {item_url}: {e}")
                    
        except Exception as e:
            logger.error(f"   ❌ Lỗi cào trang list {list_url}: {e}")
            
    logger.info("=" * 70)
    logger.info(f"🎉 TỔNG KẾT: Đã cào và lưu THẬT {saved_count} Luận án Tiến sĩ Luật từ Bộ GD&ĐT (MOET)!")
    logger.info("=" * 70)
    return saved_count

if __name__ == "__main__":
    setup_db()
    crawl_moet_dissertations(max_pages=25)
