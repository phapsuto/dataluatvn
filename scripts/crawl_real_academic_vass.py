#!/usr/bin/env python3
"""
scripts/crawl_real_academic_vass.py
====================================
Script Cào BÀI BÁO KHOA HỌC PHÁP LÝ & ĐỀ TÀI NGHIÊN CỨU THẬT 100%
từ Viện Nhà nước và Pháp luật (Viện Hàn lâm KHXH Việt Nam - VASS)
URL: http://isl.vass.gov.vn
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
logger = logging.getLogger("VASSCrawler")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Bảng lưu bài báo khoa học & nghiên cứu thật
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

def crawl_vass_section(section_name, section_url, session, max_pages=3):
    logger.info(f"\n📡 Đang cào mục '{section_name}': {section_url}...")
    saved_count = 0
    
    for page in range(1, max_pages + 1):
        page_url = section_url if page == 1 else f"{section_url}?page={page}"
        try:
            r = session.get(page_url, timeout=12)
            if r.status_code != 200:
                break
                
            soup = BeautifulSoup(r.content, "html.parser")
            
            # Tìm tất cả bài viết trong mục
            article_links = []
            for a in soup.find_all("a", href=True):
                href = urljoin(section_url, a["href"])
                title = a.text.strip()
                if len(title) > 20 and ("de-tai" in href or "tin-tuc" in href or "hoat-dong" in href or "nghien-cuu" in href or "hoi-thao" in href):
                    if href not in [x[1] for x in article_links]:
                        article_links.append((title, href))
            
            logger.info(f"   Trang {page}: Tìm thấy {len(article_links)} bài viết...")
            
            for title, href in article_links:
                try:
                    art_r = session.get(href, timeout=12)
                    if art_r.status_code != 200:
                        continue
                        
                    art_soup = BeautifulSoup(art_r.content, "html.parser")
                    page_title = art_soup.title.text.strip() if art_soup.title else title
                    
                    # Trích xuất nội dung bài viết
                    content_el = (
                        art_soup.find("div", class_="content-detail") or
                        art_soup.find("div", class_="detail-content") or
                        art_soup.find("div", id="content") or
                        art_soup.find("article")
                    )
                    
                    if content_el:
                        full_text = content_el.get_text(separator="\n", strip=True)
                    else:
                        # Fallback
                        full_text = art_soup.get_text(separator="\n", strip=True)
                    
                    if not full_text or len(full_text) < 300:
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
                            page_title,
                            section_name,
                            "Viện Nhà nước và Pháp luật (VASS)",
                            "Viện Hàn lâm KHXH Việt Nam",
                            "",
                            full_text[:500],
                            full_text,
                            href,
                            word_count,
                            datetime.now().isoformat(),
                            content_hash
                        ))
                        
                        if c.rowcount > 0:
                            row_id = c.lastrowid
                            c.execute("""
                            INSERT INTO fts_theory (source_table, source_id, title, content, category)
                            VALUES ('real_academic_articles', ?, ?, ?, ?)
                            """, (row_id, page_title, full_text[:10000], section_name))
                            
                            conn.commit()
                            saved_count += 1
                            logger.info(f"   ✅ Saved: [{page_title[:60]}] | {word_count} từ")
                    except sqlite3.IntegrityError:
                        pass
                    finally:
                        conn.close()
                    
                    time.sleep(1) # Delay tôn trọng server
                except Exception as e:
                    logger.warning(f"   ⚠️ Lỗi cào {href[:50]}: {e}")
                    
        except Exception as e:
            logger.error(f"   ❌ Lỗi cào trang {page_url}: {e}")
            break
            
    return saved_count

def main():
    setup_db()
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    logger.info("=" * 70)
    logger.info("🏛️  CÀO BÀI BÁO KHOA HỌC PHÁP LÝ THẬT TỪ VIỆN NHÀ NƯỚC VÀ PHÁP LUẬT (VASS)")
    logger.info("=" * 70)
    
    sections = [
        ("Đề tài cấp Bộ", "http://isl.vass.gov.vn/de-tai-cap-bo"),
        ("Đề tài cấp Nhà nước", "http://isl.vass.gov.vn/de-tai-cap-nha-nuoc"),
        ("Đề tài cấp Viện", "http://isl.vass.gov.vn/de-tai-cap-vien"),
        ("Hoạt động khoa học", "http://isl.vass.gov.vn/hoat-dong-khoa-hoc"),
        ("Tin tức Sự kiện Pháp lý", "http://isl.vass.gov.vn/tin-tuc-su-kien"),
    ]
    
    total_saved = 0
    for name, url in sections:
        total_saved += crawl_vass_section(name, url, session, max_pages=2)
        
    logger.info("=" * 70)
    logger.info(f"🎉 TỔNG KẾT: Đã cào và lưu THẬT {total_saved} bài báo & công trình khoa học pháp lý VASS!")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
