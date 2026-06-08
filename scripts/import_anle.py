"""
import_anle.py — Import Án Lệ & Bản Án từ HuggingFace
Dataset: tmquan/anle-toaan-gov-vn
Subset: documents (mặc định)
"""
import os
import sys
import time
import sqlite3
import requests

DB_NAME = "vietnamese_legal_documents.db"
DATASET_ID = "tmquan/anle-toaan-gov-vn"
HF_API_URL = f"https://huggingface.co/api/datasets/{DATASET_ID}"


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def get_dataset_info():
    """Lấy SHA và lastModified từ HuggingFace API"""
    try:
        r = requests.get(HF_API_URL, timeout=15)
        info = r.json()
        return info.get("sha", ""), info.get("lastModified", "")
    except Exception as e:
        log(f"⚠️  Không lấy được info từ HF API: {e}")
        return "", ""


def import_documents(conn):
    """Import subset 'documents' vào bảng anle_documents"""
    from datasets import load_dataset

    log("📥 Đang tải subset 'documents' từ HuggingFace...")
    ds = load_dataset(DATASET_ID, "documents", split="train")
    total = len(ds)
    log(f"   Tổng cộng: {total:,} văn bản")

    cursor = conn.cursor()
    batch = []
    batch_size = 500  # Nhỏ hơn vì markdown lớn
    start = time.time()

    # Các cột cần lấy
    columns = [
        "doc_name", "title", "doc_code", "doc_type", "case_type",
        "doc_subtype", "year", "issue_date", "issuing_authority",
        "court_level", "jurisdiction", "subject", "markdown",
        "num_pages", "num_sections", "num_paragraphs", "num_sentences",
        "char_len", "text_hash", "precedent_number", "adopted_date",
        "applied_article_code", "applied_article_number",
        "applied_article_clause", "principle_text",
        "detail_url", "pdf_url", "confidence", "parsed_at",
    ]

    for i, row in enumerate(ds):
        values = []
        for col in columns:
            val = row.get(col)
            # Chuyển NaN/None thành None cho SQLite
            if val is not None:
                try:
                    import math
                    if isinstance(val, float) and math.isnan(val):
                        val = None
                except (TypeError, ValueError):
                    pass
            values.append(val)

        # Thêm source
        values.append("huggingface")

        batch.append(tuple(values))

        if len(batch) >= batch_size:
            cursor.executemany(f"""
                INSERT OR IGNORE INTO anle_documents (
                    {', '.join(columns)}, source
                ) VALUES ({','.join(['?'] * (len(columns) + 1))})
            """, batch)
            conn.commit()
            elapsed = time.time() - start
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            log(f"   Đã xử lý {i+1:>8,}/{total:,} ({speed:.0f} rows/s)")
            batch = []

    # Batch cuối
    if batch:
        cursor.executemany(f"""
            INSERT OR IGNORE INTO anle_documents (
                {', '.join(columns)}, source
            ) VALUES ({','.join(['?'] * (len(columns) + 1))})
        """, batch)
        conn.commit()

    # Đếm kết quả
    cursor.execute("SELECT count(*) FROM anle_documents")
    actual = cursor.fetchone()[0]
    log(f"✅ Import documents hoàn thành: {actual:,} văn bản trong DB")
    return actual


def update_sync_log(conn, sha, last_modified, count):
    """Ghi log sync"""
    cursor = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT OR REPLACE INTO hf_sync_log
        (dataset_id, last_sha, last_modified, last_checked_at, last_synced_at,
         records_added, records_total)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (DATASET_ID, sha, last_modified, now, now, count, count))
    conn.commit()


def print_stats(conn):
    """In thống kê sau import"""
    cursor = conn.cursor()

    print()
    print("=" * 60)
    print("📊 THỐNG KÊ ÁN LỆ SAU IMPORT")
    print("=" * 60)

    # Tổng
    cursor.execute("SELECT count(*) FROM anle_documents")
    total = cursor.fetchone()[0]
    print(f"  📋 Tổng số văn bản: {total:,}")

    # Án lệ vs Bản án thường
    cursor.execute("""
        SELECT count(*) FROM anle_documents
        WHERE precedent_number IS NOT NULL AND precedent_number != ''
    """)
    precedents = cursor.fetchone()[0]
    print(f"  ⚖️  Án lệ chính thức: {precedents:,}")
    print(f"  📄 Bản án thường: {total - precedents:,}")

    # Phân bố theo loại vụ án
    cursor.execute("""
        SELECT case_type, count(*) as cnt
        FROM anle_documents
        WHERE case_type IS NOT NULL
        GROUP BY case_type
        ORDER BY cnt DESC
    """)
    rows = cursor.fetchall()
    if rows:
        print("\n  📂 Phân bố theo loại vụ án:")
        for row in rows:
            print(f"     {row[1]:>6,} — {row[0]}")

    # Phân bố theo cấp tòa
    cursor.execute("""
        SELECT court_level, count(*) as cnt
        FROM anle_documents
        WHERE court_level IS NOT NULL
        GROUP BY court_level
        ORDER BY cnt DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        print("\n  🏛️  Phân bố theo cấp tòa (Top 10):")
        for row in rows:
            print(f"     {row[1]:>6,} — {row[0]}")

    # Phân bố theo năm
    cursor.execute("""
        SELECT year, count(*) as cnt
        FROM anle_documents
        WHERE year IS NOT NULL
        GROUP BY year
        ORDER BY year DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    if rows:
        print("\n  📅 Phân bố theo năm (gần nhất):")
        for row in rows:
            print(f"     {row[1]:>6,} — Năm {row[0]}")

    # Sample án lệ
    cursor.execute("""
        SELECT precedent_number, title, case_type
        FROM anle_documents
        WHERE precedent_number IS NOT NULL AND precedent_number != ''
        LIMIT 5
    """)
    rows = cursor.fetchall()
    if rows:
        print("\n  📝 Mẫu án lệ:")
        for row in rows:
            title = (row[1] or "")[:70]
            print(f"     AL {row[0]} [{row[2]}] {title}...")

    print("=" * 60)


def main():
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy {DB_NAME}! Chạy db_schema.py trước.")
        sys.exit(1)

    log("=" * 60)
    log("🚀 IMPORT ÁN LỆ & BẢN ÁN TỪ HUGGINGFACE")
    log(f"   Dataset: {DATASET_ID}")
    log("=" * 60)

    sha, last_modified = get_dataset_info()
    log(f"   SHA: {sha[:12]}... | Last modified: {last_modified}")

    start = time.time()
    conn = sqlite3.connect(DB_NAME)

    count = import_documents(conn)
    update_sync_log(conn, sha, last_modified, count)
    print_stats(conn)

    conn.close()
    log(f"\n⏱️  Tổng thời gian: {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
