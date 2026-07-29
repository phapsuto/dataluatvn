#!/usr/bin/env python3
"""
scripts/clean_all_watermarks_and_login_prompts.py
--------------------------------------------------
Script rà soát và làm sạch toàn bộ dữ liệu nội dung văn bản trong hệ thống:
1. Loại bỏ các đoạn văn bản rác yêu cầu đăng nhập / thành viên (paywall prompts):
   - "Bạn chưa Đăng nhập thành viên."
   - "Đây là tiện ích dành cho tài khoản thành viên. Vui lòng Đăng nhập để xem chi tiết..."
   - "* Lưu ý: Để đọc được văn bản tải trên Luatvietnam.vn..."
2. Loại bỏ logo, đóng dấu bản quyền, và liên kết quảng cáo nguồn:
   - "*** LuatVietnam.vn ***", "LuatVietnam", "Thư viện pháp luật", "thuvienphapluat.vn", "vbpl.vn"
3. Loại bỏ các dòng lặp lại Tình trạng hiệu lực / Hiệu lực trong nội dung HTML.
4. Làm sạch cả content_store.db (nội dung toàn văn) và vietnamese_legal_documents.db (nếu có content_html / document_chunks).
"""

import os
import sys
import sqlite3
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import CONTENT_DB, DB_NAME
from app.utils.clean_text import clean_document_html, clean_document_text



def clean_content_store_db():
    if not os.path.exists(CONTENT_DB):
        print(f"[INFO] CONTENT_DB không tồn tại ({CONTENT_DB}), bỏ qua.")
        return 0

    print(f"[START] Đang kiểm tra và làm sạch watermarks / login prompts trong {CONTENT_DB}...")
    conn = sqlite3.connect(CONTENT_DB, timeout=60.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    cursor = conn.cursor()

    query = """
    SELECT doc_id, content_html FROM document_content
    WHERE content_html LIKE '%Bạn chưa Đăng nhập%'
       OR content_html LIKE '%Luatvietnam%'
       OR content_html LIKE '%thuvienphapluat%'
       OR content_html LIKE '%Tình trạng hiệu lực:%'
       OR content_html LIKE '%Hiệu lực: Đã biết%'
       OR content_html LIKE '%tiện ích dành cho tài khoản%'
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    total_dirty = len(rows)
    print(f"[FOUND] Tìm thấy {total_dirty} văn bản có chứa câu rác/watermark/logo trong document_content.")

    if total_dirty == 0:
        conn.close()
        return 0

    cleaned_count = 0
    batch_updates = []
    for doc_id, html in rows:
        cleaned_html = clean_document_html(html)
        if cleaned_html != html:
            batch_updates.append((cleaned_html, doc_id))
            cleaned_count += 1

        if len(batch_updates) >= 500:
            cursor.executemany("UPDATE document_content SET content_html = ? WHERE doc_id = ?", batch_updates)
            conn.commit()
            print(f"   -> Đã làm sạch và cập nhật {cleaned_count}/{total_dirty} văn bản...")
            batch_updates = []

    if batch_updates:
        cursor.executemany("UPDATE document_content SET content_html = ? WHERE doc_id = ?", batch_updates)
        conn.commit()

    conn.close()
    print(f"[SUCCESS] Đã làm sạch hoàn toàn {cleaned_count}/{total_dirty} văn bản trong content_store.db!")
    return cleaned_count


def clean_main_db():
    if not os.path.exists(DB_NAME):
        print(f"[INFO] DB_NAME không tồn tại ({DB_NAME}), bỏ qua.")
        return 0

    print(f"[START] Đang kiểm tra và làm sạch watermarks / login prompts trong {DB_NAME}...")
    conn = sqlite3.connect(DB_NAME, timeout=60.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    cursor = conn.cursor()

    total_chunks_cleaned = 0
    # Kiểm tra table document_chunks
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='document_chunks'")
    if cursor.fetchone():
        query_chunks = """
        SELECT id, chunk_text, chunk_header, chunk_with_meta FROM document_chunks
        WHERE chunk_text LIKE '%Bạn chưa Đăng nhập%'
           OR chunk_text LIKE '%Luatvietnam%'
           OR chunk_text LIKE '%thuvienphapluat%'
           OR chunk_text LIKE '%Tình trạng hiệu lực:%'
           OR chunk_text LIKE '%tiện ích dành cho tài khoản%'
        """
        cursor.execute(query_chunks)
        chunk_rows = cursor.fetchall()
        print(f"[FOUND] Tìm thấy {len(chunk_rows)} chunks có chứa từ khoá rác/watermark.")

        batch_chunks = []
        for cid, c_text, c_head, c_meta in chunk_rows:
            cl_text = clean_document_text(c_text) if c_text else ""
            cl_head = clean_document_text(c_head) if c_head else ""
            cl_meta = clean_document_text(c_meta) if c_meta else ""
            if cl_text != c_text or cl_head != c_head or cl_meta != c_meta:
                batch_chunks.append((cl_text, cl_head, cl_meta, cid))
                total_chunks_cleaned += 1

            if len(batch_chunks) >= 500:
                cursor.executemany(
                    "UPDATE document_chunks SET chunk_text = ?, chunk_header = ?, chunk_with_meta = ? WHERE id = ?",
                    batch_chunks
                )
                conn.commit()
                batch_chunks = []

        if batch_chunks:
            cursor.executemany(
                "UPDATE document_chunks SET chunk_text = ?, chunk_header = ?, chunk_with_meta = ? WHERE id = ?",
                batch_chunks
            )
            conn.commit()

        print(f"[SUCCESS] Đã làm sạch {total_chunks_cleaned} document chunks trong DB chính!")

    conn.close()
    return total_chunks_cleaned


def main():
    start_time = time.time()
    print("=========================================================================")
    print(" 🛠️  BẮT ĐẦU RÀ SOÁT & LÀM SẠCH LOGO / THÔNG BÁO ĐĂNG NHẬP / WATERMARK ")
    print("=========================================================================")

    c1 = clean_content_store_db()
    c2 = clean_main_db()

    elapsed = time.time() - start_time
    print("=========================================================================")
    print(f" ✅ HOÀN TẤT LÀM SẠCH TOÀN BỘ DỮ LIỆU! (Thời gian: {elapsed:.2f}s)")
    print(f" 📊 Tổng văn bản trong content_store.db đã làm sạch: {c1}")
    print(f" 📊 Tổng document chunks trong DB chính đã làm sạch : {c2}")
    print("=========================================================================")


if __name__ == "__main__":
    main()
