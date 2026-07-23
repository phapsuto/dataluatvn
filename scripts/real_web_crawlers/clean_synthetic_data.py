#!/usr/bin/env python3
"""
scripts/real_web_crawlers/clean_synthetic_data.py
===================================================
Script Làm sạch và Xóa bỏ toàn bộ Dữ liệu Mô phỏng (Synthetic Data).
Đảm bảo CSLD data/legal_theory_mind.db CHỈ LƯU TRỮ VÀ TÍCH LŨY DỮ LIỆU CÀO THẬT 100%
từ các Cổng thông tin Chính phủ, Tòa án, Viện kiểm sát và Thư viện Quốc gia.
"""

import os
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("CleanSyntheticData")

DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

def clean_synthetic_records():
    if not os.path.exists(DB_PATH):
        logger.error(f"Không tìm thấy DB tại {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    logger.info("🧹 Đang tiến hành dọn dẹp và xóa toàn bộ dữ liệu mô phỏng...")

    # Xóa toàn bộ dữ liệu mô phỏng trong các bảng
    cursor.execute("DELETE FROM academic_publications WHERE title LIKE 'Nghiên cứu Luận án Tiến sĩ #%' OR title LIKE 'Luận văn Thạc sĩ Luật #%' OR title LIKE 'Bài báo Khoa học #%' OR title LIKE 'Công văn số %/TANDT-PC%' OR title LIKE 'Báo cáo Rút kinh nghiệm Nghiệp vụ #%'")
    cursor.execute("DELETE FROM fts_theory WHERE title LIKE 'Nghiên cứu Luận án Tiến sĩ #%' OR title LIKE 'Luận văn Thạc sĩ Luật #%' OR title LIKE 'Bài báo Khoa học #%' OR title LIKE 'Công văn số %/TANDT-PC%' OR title LIKE 'Báo cáo Rút kinh nghiệm Nghiệp vụ #%'")

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM academic_publications")
    total_pubs = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM fts_theory")
    total_fts = cursor.fetchone()[0]

    logger.info(f"✨ Đã làm sạch xong! Tổng số bản ghi THẬT còn lại: Academic = {total_pubs} | FTS Index = {total_fts}")
    conn.close()

if __name__ == "__main__":
    clean_synthetic_records()
