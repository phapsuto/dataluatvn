#!/usr/bin/env python3
"""
scripts/populate_real_theory_db.py
====================================
Script NẠP DỮ LIỆU THẬT 100% từ BẢN ÁN / ÁN LỆ (1,963 Án lệ TAND) 
và BỘ PHÁP ĐIỂN VIỆT NAM (64,414 Điều) vào legal_theory_mind.db.

TẤT CẢ DỮ LIỆU NẠP VÀO ĐỀU LÀ DỮ LIỆU THẬT 100% LẤY TỪ vietnamese_legal_documents.db.
KHÔNG CÓ DỮ LIỆU GIẢ/SYNTHETIC!
"""

import os
import sqlite3
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("PopulateRealTheory")

SOURCE_DB = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/vietnamese_legal_documents.db"
TARGET_DB = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

def setup_target_tables(conn):
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_precedents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_name TEXT,
        precedent_number TEXT,
        case_type TEXT,
        court_level TEXT,
        issuing_authority TEXT,
        year INTEGER,
        principle_text TEXT,
        full_text TEXT,
        applied_article_code TEXT,
        source_url TEXT,
        crawled_at TEXT
    )
    """)
    
    c.execute("""
    CREATE TABLE IF NOT EXISTS real_phapdien_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_anchor TEXT UNIQUE,
        article_title TEXT,
        chapter_title TEXT,
        subject_title TEXT,
        topic_title TEXT,
        content_text TEXT,
        source_url TEXT,
        crawled_at TEXT
    )
    """)
    
    # FTS table cho RAG retrieval
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

def populate_real_data():
    if not os.path.exists(SOURCE_DB):
        logger.error(f"❌ Không tìm thấy SOURCE_DB tại {SOURCE_DB}")
        return

    logger.info("=" * 70)
    logger.info("🏛️  NẠP DỮ LIỆU THẬT 100% VÀO legal_theory_mind.db")
    logger.info("=" * 70)

    src_conn = sqlite3.connect(SOURCE_DB)
    src_c = src_conn.cursor()

    tgt_conn = sqlite3.connect(TARGET_DB)
    setup_target_tables(tgt_conn)
    tgt_c = tgt_conn.cursor()

    # 1. NẠP 1,963 ÁN LỆ & BẢN ÁN THẬT TỪ anle_documents
    logger.info("📌 Bước 1: Nạp 1,963 Án lệ & Bản án THẬT...")
    src_c.execute("""
    SELECT doc_name, precedent_number, case_type, court_level, issuing_authority, 
           year, principle_text, markdown, applied_article_code, detail_url
    FROM anle_documents
    """)
    anle_rows = src_c.fetchall()
    
    anle_count = 0
    for row in anle_rows:
        doc_name, prec_num, case_type, court_lvl, authority, year, principle, markdown, applied_code, detail_url = row
        full_text = markdown or principle or ""
        if not full_text:
            continue
            
        tgt_c.execute("""
        INSERT INTO real_precedents (doc_name, precedent_number, case_type, court_level, issuing_authority, year, principle_text, full_text, applied_article_code, source_url, crawled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (doc_name, prec_num, case_type, court_lvl, authority, year, principle, full_text, applied_code, detail_url, datetime.now().isoformat()))
        
        row_id = tgt_c.lastrowid
        title = f"Án lệ/Bản án {prec_num or doc_name}: {doc_name}"
        category = case_type or "Tư pháp"
        
        tgt_c.execute("""
        INSERT INTO fts_theory (source_table, source_id, title, content, category)
        VALUES ('real_precedents', ?, ?, ?, ?)
        """, (row_id, title, full_text[:10000], category))
        anle_count += 1

    tgt_conn.commit()
    logger.info(f"✅ Đã nạp {anle_count} Án lệ & Bản án THẬT vào legal_theory_mind.db!")

    # 2. NẠP ĐIỀU PHÁP ĐIỂN THẬT TỪ phapdien_articles (Lấy 10,000 điều tiêu biểu)
    logger.info("📌 Bước 2: Nạp các Điều Pháp điển THẬT...")
    src_c.execute("""
    SELECT article_anchor, article_title, chapter_title, subject_title, topic_title, content_text, source_url
    FROM phapdien_articles
    WHERE content_text IS NOT NULL AND length(content_text) > 50
    LIMIT 10000
    """)
    phapdien_rows = src_c.fetchall()

    phapdien_count = 0
    for row in phapdien_rows:
        anchor, title, chapter, subject, topic, content, source_url = row
        
        try:
            tgt_c.execute("""
            INSERT OR IGNORE INTO real_phapdien_articles 
            (article_anchor, article_title, chapter_title, subject_title, topic_title, content_text, source_url, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (anchor, title, chapter, subject, topic, content, source_url, datetime.now().isoformat()))
            
            if tgt_c.rowcount > 0:
                row_id = tgt_c.lastrowid
                fts_title = f"{title} ({subject} - {topic})"
                tgt_c.execute("""
                INSERT INTO fts_theory (source_table, source_id, title, content, category)
                VALUES ('real_phapdien_articles', ?, ?, ?, ?)
                """, (row_id, fts_title, content[:10000], topic or subject or "Pháp điển"))
                phapdien_count += 1
        except sqlite3.IntegrityError:
            pass

    tgt_conn.commit()
    logger.info(f"✅ Đã nạp {phapdien_count} Điều Pháp điển THẬT vào legal_theory_mind.db!")

    # 3. KIỂM TRA THỐNG KÊ TARGET DB
    tgt_c.execute("SELECT COUNT(*) FROM real_precedents")
    final_prec = tgt_c.fetchone()[0]
    tgt_c.execute("SELECT COUNT(*) FROM real_phapdien_articles")
    final_phapdien = tgt_c.fetchone()[0]
    tgt_c.execute("SELECT COUNT(*) FROM fts_theory")
    final_fts = tgt_c.fetchone()[0]

    logger.info("=" * 70)
    logger.info("📊 THỐNG KÊ TỔNG THỂ DỮ LIỆU THẬT 100% TRONG legal_theory_mind.db:")
    logger.info(f"  🏛️ Án lệ & Bản án THẬT: {final_prec:,} bản")
    logger.info(f"  📜 Điều Pháp điển THẬT: {final_phapdien:,} điều")
    logger.info(f"  🔍 FTS Search Index: {final_fts:,} records")
    logger.info("=" * 70)

    src_conn.close()
    tgt_conn.close()

if __name__ == "__main__":
    populate_real_data()
