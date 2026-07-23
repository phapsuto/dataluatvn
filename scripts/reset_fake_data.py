#!/usr/bin/env python3
"""
scripts/reset_fake_data.py
===========================
Xóa sạch toàn bộ dữ liệu giả (synthetic) trong legal_theory_mind.db
và chuẩn bị DB sạch cho dữ liệu thật.
"""

import sqlite3
import os
import shutil
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ResetFakeData")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"
SFT_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_mind/legal_mind_sft_dataset.jsonl"
MODEL_DIR = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/models/mac_legal_mind_model"

def reset():
    # 1. Backup DB cũ
    backup_path = DB_PATH + ".fake_backup"
    if os.path.exists(DB_PATH):
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"📦 Backup DB giả sang: {backup_path}")

    # 2. Xóa sạch tất cả bảng dữ liệu giả
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Đếm trước khi xóa
    tables_to_clean = ["academic_publications", "curriculum_topics", "legal_doctrines", 
                       "legal_practice_skills", "crawler_logs"]
    
    for table in tables_to_clean:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            c.execute(f"DELETE FROM {table}")
            logger.info(f"🗑️  Xóa {count} records giả từ bảng '{table}'")
        except Exception as e:
            logger.warning(f"⚠️  Bảng '{table}' lỗi: {e}")

    # Reset FTS index
    try:
        c.execute("DELETE FROM fts_theory")
        logger.info("🗑️  Xóa FTS index giả")
    except Exception as e:
        logger.warning(f"⚠️  FTS reset lỗi: {e}")

    # Reset autoincrement
    try:
        c.execute("DELETE FROM sqlite_sequence")
        logger.info("🔄 Reset autoincrement counters")
    except:
        pass

    conn.commit()

    # Verify
    for table in tables_to_clean:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            logger.info(f"✅ Verify '{table}': {count} records (phải = 0)")
        except:
            pass

    conn.close()

    # 3. Xóa SFT dataset giả
    if os.path.exists(SFT_PATH):
        os.remove(SFT_PATH)
        logger.info(f"🗑️  Xóa SFT dataset giả: {SFT_PATH}")

    # 4. Xóa model training giả
    if os.path.exists(MODEL_DIR):
        shutil.rmtree(MODEL_DIR)
        logger.info(f"🗑️  Xóa model training giả: {MODEL_DIR}")

    logger.info("=" * 60)
    logger.info("✅ HOÀN THÀNH: Đã xóa sạch toàn bộ dữ liệu giả!")
    logger.info("   Database sẵn sàng nhận dữ liệu THẬT.")
    logger.info("=" * 60)

if __name__ == "__main__":
    reset()
