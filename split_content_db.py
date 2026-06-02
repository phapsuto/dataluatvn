"""
split_content_db.py — Tách content_html ra database riêng
═══════════════════════════════════════════════════════════
Mục đích: Giảm RAM máy chủ bằng cách tách cột content_html (~3.3 GB)
ra file content_store.db riêng. DB chính chỉ giữ metadata (~300 MB).

Flow:
  1. Tạo content_store.db với bảng document_content
  2. Copy content_html từ documents sang content_store.db (batch)
  3. SET content_html = NULL trong DB chính
  4. VACUUM DB chính → co lại ~300 MB

An toàn:
  - Idempotent: chạy lại không mất dữ liệu
  - Kiểm tra integrity trước khi xóa content từ DB chính
  - Có progress bar cho quá trình dài

Usage:
  python split_content_db.py
"""
import os
import sys
import time
import sqlite3

MAIN_DB = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"
BATCH_SIZE = 500


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def create_content_db():
    """Tạo content_store.db với schema phù hợp"""
    conn = sqlite3.connect(CONTENT_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_content (
            doc_id       INTEGER PRIMARY KEY,
            content_html TEXT
        )
    """)
    conn.commit()
    conn.close()
    log(f"✅ Đã tạo/kiểm tra {CONTENT_DB}")


def copy_content(main_conn, content_conn):
    """Copy content_html từ DB chính sang content_store.db theo batch"""
    main_cursor = main_conn.cursor()
    content_cursor = content_conn.cursor()

    # Đếm tổng documents có content
    main_cursor.execute(
        "SELECT count(*) FROM documents WHERE content_html IS NOT NULL AND content_html != ''"
    )
    total = main_cursor.fetchone()[0]
    log(f"📊 Tổng documents có content_html: {total:,}")

    # Đếm đã copy (nếu chạy lại)
    content_cursor.execute("SELECT count(*) FROM document_content")
    already_copied = content_cursor.fetchone()[0]
    if already_copied > 0:
        log(f"📌 Đã có {already_copied:,} rows trong content_store.db (tiếp tục copy phần còn lại)")

    # Copy theo batch, skip những cái đã có
    offset = 0
    copied = 0
    start = time.time()

    while True:
        main_cursor.execute(
            """
            SELECT id, content_html FROM documents
            WHERE content_html IS NOT NULL AND content_html != ''
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            (BATCH_SIZE, offset),
        )
        rows = main_cursor.fetchall()
        if not rows:
            break

        for doc_id, content_html in rows:
            content_cursor.execute(
                "INSERT OR IGNORE INTO document_content (doc_id, content_html) VALUES (?, ?)",
                (doc_id, content_html),
            )
            copied += 1

        content_conn.commit()
        offset += BATCH_SIZE

        # Progress
        elapsed = time.time() - start
        pct = min(100, (offset / total) * 100) if total > 0 else 100
        rate = copied / elapsed if elapsed > 0 else 0
        eta = (total - offset) / rate if rate > 0 else 0
        log(f"   📦 {offset:,}/{total:,} ({pct:.1f}%) — {rate:.0f} rows/s — ETA: {eta:.0f}s")

    return copied


def verify_integrity(main_conn, content_conn):
    """Kiểm tra content_store.db có đầy đủ trước khi xóa từ DB chính"""
    main_cursor = main_conn.cursor()
    content_cursor = content_conn.cursor()

    main_cursor.execute(
        "SELECT count(*) FROM documents WHERE content_html IS NOT NULL AND content_html != ''"
    )
    main_count = main_cursor.fetchone()[0]

    content_cursor.execute("SELECT count(*) FROM document_content")
    content_count = content_cursor.fetchone()[0]

    log(f"🔍 Verification:")
    log(f"   DB chính (documents có content): {main_count:,}")
    log(f"   content_store.db:                {content_count:,}")

    if content_count < main_count:
        log(f"❌ THIẾU {main_count - content_count:,} documents! Không xóa content từ DB chính.")
        return False

    # Spot check: so sánh 10 documents ngẫu nhiên
    main_cursor.execute(
        "SELECT id, LENGTH(content_html) FROM documents WHERE content_html IS NOT NULL ORDER BY RANDOM() LIMIT 10"
    )
    samples = main_cursor.fetchall()

    for doc_id, main_len in samples:
        content_cursor.execute(
            "SELECT LENGTH(content_html) FROM document_content WHERE doc_id = ?",
            (doc_id,),
        )
        row = content_cursor.fetchone()
        if not row:
            log(f"❌ doc_id={doc_id} không có trong content_store.db!")
            return False
        if row[0] != main_len:
            log(f"❌ doc_id={doc_id} length mismatch: main={main_len}, content={row[0]}")
            return False

    log("✅ Integrity check PASSED — content_store.db đầy đủ và chính xác")
    return True


def nullify_main_content(main_conn):
    """SET content_html = NULL trong DB chính (theo batch để tránh lock quá lâu)"""
    cursor = main_conn.cursor()
    log("🗑️  Đang xóa content_html từ DB chính (thay bằng NULL)...")

    cursor.execute(
        "SELECT count(*) FROM documents WHERE content_html IS NOT NULL AND content_html != ''"
    )
    remaining = cursor.fetchone()[0]
    log(f"   Cần xóa content từ {remaining:,} rows")

    batch = 0
    while True:
        cursor.execute(
            """
            UPDATE documents SET content_html = NULL
            WHERE id IN (
                SELECT id FROM documents
                WHERE content_html IS NOT NULL AND content_html != ''
                LIMIT ?
            )
            """,
            (BATCH_SIZE,),
        )
        affected = cursor.rowcount
        main_conn.commit()
        batch += 1

        if affected == 0:
            break
        log(f"   Batch {batch}: đã xóa {affected} rows")

    log("✅ Đã xóa toàn bộ content_html từ DB chính")


def vacuum_main_db(main_conn):
    """VACUUM DB chính để thu hồi dung lượng"""
    log("🔧 VACUUM DB chính (có thể mất vài phút với DB lớn)...")
    main_conn.execute("VACUUM")
    log("✅ VACUUM hoàn thành")


def main():
    if not os.path.exists(MAIN_DB):
        log(f"❌ Không tìm thấy {MAIN_DB}!")
        sys.exit(1)

    log("=" * 60)
    log("🚀 TÁCH CONTENT_HTML RA DATABASE RIÊNG")
    log("=" * 60)

    # Kích thước trước
    main_size_before = os.path.getsize(MAIN_DB)
    log(f"📦 DB chính trước tách: {main_size_before / 1024 / 1024:.0f} MB")

    start = time.time()

    # Step 1: Tạo content_store.db
    create_content_db()

    # Step 2: Copy content
    main_conn = sqlite3.connect(MAIN_DB)
    content_conn = sqlite3.connect(CONTENT_DB)

    copied = copy_content(main_conn, content_conn)
    log(f"📋 Đã copy {copied:,} documents sang {CONTENT_DB}")

    # Step 3: Verify
    if not verify_integrity(main_conn, content_conn):
        log("❌ Integrity check FAILED! Dừng lại, KHÔNG xóa content từ DB chính.")
        main_conn.close()
        content_conn.close()
        sys.exit(1)

    content_conn.close()

    # Step 4: Xóa content_html từ DB chính
    nullify_main_content(main_conn)

    # Step 5: VACUUM
    vacuum_main_db(main_conn)
    main_conn.close()

    # Kích thước sau
    main_size_after = os.path.getsize(MAIN_DB)
    content_size = os.path.getsize(CONTENT_DB)

    log("=" * 60)
    log("🎉 HOÀN THÀNH!")
    log(f"   📦 DB chính:        {main_size_before / 1024 / 1024:.0f} MB → {main_size_after / 1024 / 1024:.0f} MB")
    log(f"   📦 content_store:   {content_size / 1024 / 1024:.0f} MB")
    log(f"   📉 Giảm RAM dự kiến: ~{(main_size_before - main_size_after) / 1024 / 1024:.0f} MB")
    log(f"   ⏱️  Thời gian: {time.time() - start:.1f}s")
    log("=" * 60)


if __name__ == "__main__":
    main()
