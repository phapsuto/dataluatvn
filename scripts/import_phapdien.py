"""
import_phapdien.py — Import Bộ Pháp Điển từ HuggingFace
Dataset: tmquan/phapdien-moj-gov-vn
Subsets: articles (chính) + ontology_glossary (thuật ngữ VI-EN)
"""
import os
import sys
import json
import time
import sqlite3
import requests

DB_NAME = "vietnamese_legal_documents.db"
DATASET_ID = "tmquan/phapdien-moj-gov-vn"
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


def import_articles(conn):
    """Import subset 'articles' vào bảng phapdien_articles"""
    from datasets import load_dataset

    log("📥 Đang tải subset 'articles' từ HuggingFace...")
    ds = load_dataset(DATASET_ID, "articles", split="train")
    total = len(ds)
    log(f"   Tổng cộng: {total:,} Điều")

    cursor = conn.cursor()
    batch = []
    batch_size = 1000
    inserted = 0
    skipped = 0
    start = time.time()

    for i, row in enumerate(ds):
        # Serialize source_links thành JSON
        source_links = row.get("source_links")
        if source_links is not None:
            try:
                source_links_json = json.dumps(source_links, ensure_ascii=False)
            except (TypeError, ValueError):
                source_links_json = str(source_links)
        else:
            source_links_json = None

        batch.append((
            row.get("article_anchor"),
            row.get("article_title"),
            row.get("chapter_title"),
            row.get("subject_id"),
            row.get("subject_title"),
            row.get("topic_id"),
            row.get("topic_number"),
            row.get("topic_title"),
            row.get("content_text"),
            row.get("content_char_len"),
            row.get("content_word_count"),
            row.get("source_url"),
            row.get("source_note_text"),
            source_links_json,
            row.get("related_note_text"),
            row.get("scraped_at"),
            "huggingface",
        ))

        if len(batch) >= batch_size:
            result = cursor.executemany("""
                INSERT OR IGNORE INTO phapdien_articles (
                    article_anchor, article_title, chapter_title,
                    subject_id, subject_title, topic_id, topic_number, topic_title,
                    content_text, content_char_len, content_word_count,
                    source_url, source_note_text, source_links_json,
                    related_note_text, scraped_at, source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            conn.commit()
            inserted += cursor.rowcount if hasattr(cursor, 'rowcount') else len(batch)
            elapsed = time.time() - start
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            log(f"   Đã xử lý {i+1:>8,}/{total:,} ({speed:.0f} rows/s)")
            batch = []

    # Batch cuối
    if batch:
        cursor.executemany("""
            INSERT OR IGNORE INTO phapdien_articles (
                article_anchor, article_title, chapter_title,
                subject_id, subject_title, topic_id, topic_number, topic_title,
                content_text, content_char_len, content_word_count,
                source_url, source_note_text, source_links_json,
                related_note_text, scraped_at, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        conn.commit()

    # Đếm kết quả thực tế
    cursor.execute("SELECT count(*) FROM phapdien_articles")
    actual = cursor.fetchone()[0]
    log(f"✅ Import articles hoàn thành: {actual:,} Điều trong DB")
    return actual


def import_glossary(conn):
    """Import subset 'ontology_glossary' vào bảng phapdien_glossary"""
    from datasets import load_dataset

    log("📥 Đang tải subset 'ontology_glossary' từ HuggingFace...")
    ds = load_dataset(DATASET_ID, "ontology_glossary", split="train")
    total = len(ds)
    log(f"   Tổng cộng: {total:,} thuật ngữ")

    cursor = conn.cursor()

    # Xoá dữ liệu cũ (glossary không có primary key ổn định)
    cursor.execute("DELETE FROM phapdien_glossary")

    batch = []
    for row in ds:
        batch.append((
            row.get("category"),
            row.get("vi"),
            row.get("en"),
            row.get("note"),
        ))

    cursor.executemany("""
        INSERT INTO phapdien_glossary (category, vi, en, note)
        VALUES (?, ?, ?, ?)
    """, batch)
    conn.commit()

    cursor.execute("SELECT count(*) FROM phapdien_glossary")
    actual = cursor.fetchone()[0]
    log(f"✅ Import glossary hoàn thành: {actual:,} thuật ngữ VI-EN")
    return actual


def update_sync_log(conn, sha, last_modified, articles_count, glossary_count):
    """Ghi log sync vào hf_sync_log"""
    cursor = conn.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT OR REPLACE INTO hf_sync_log
        (dataset_id, last_sha, last_modified, last_checked_at, last_synced_at,
         records_added, records_total)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (DATASET_ID, sha, last_modified, now, now,
          articles_count + glossary_count, articles_count + glossary_count))
    conn.commit()


def print_stats(conn):
    """In thống kê sau import"""
    cursor = conn.cursor()

    print()
    print("=" * 60)
    print("📊 THỐNG KÊ PHÁP ĐIỂN SAU IMPORT")
    print("=" * 60)

    # Tổng Điều
    cursor.execute("SELECT count(*) FROM phapdien_articles")
    print(f"  📖 Tổng số Điều: {cursor.fetchone()[0]:,}")

    # Phân bố theo Chủ đề
    cursor.execute("""
        SELECT topic_title, count(*) as cnt
        FROM phapdien_articles
        GROUP BY topic_title
        ORDER BY cnt DESC
        LIMIT 10
    """)
    print("\n  📂 Top 10 Chủ đề (topic):")
    for row in cursor.fetchall():
        print(f"     {row[1]:>6,} Điều — {row[0]}")

    # Sample dữ liệu
    cursor.execute("""
        SELECT article_title, subject_title, substr(content_text, 1, 80)
        FROM phapdien_articles
        LIMIT 3
    """)
    print("\n  📝 Mẫu dữ liệu:")
    for row in cursor.fetchall():
        print(f"     [{row[0]}] {row[1]}")
        print(f"       {row[2]}...")

    # Glossary
    cursor.execute("SELECT count(*) FROM phapdien_glossary")
    gl_count = cursor.fetchone()[0]
    if gl_count > 0:
        print(f"\n  🔤 Thuật ngữ VI-EN: {gl_count:,}")
        cursor.execute("SELECT vi, en FROM phapdien_glossary LIMIT 5")
        for row in cursor.fetchall():
            print(f"     {row[0]} → {row[1]}")

    print("=" * 60)


def main():
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy {DB_NAME}! Chạy db_schema.py trước.")
        sys.exit(1)

    log("=" * 60)
    log("🚀 IMPORT PHÁP ĐIỂN TỪ HUGGINGFACE")
    log(f"   Dataset: {DATASET_ID}")
    log("=" * 60)

    # Lấy SHA
    sha, last_modified = get_dataset_info()
    log(f"   SHA: {sha[:12]}... | Last modified: {last_modified}")

    start = time.time()
    conn = sqlite3.connect(DB_NAME)

    articles_count = import_articles(conn)
    glossary_count = import_glossary(conn)
    update_sync_log(conn, sha, last_modified, articles_count, glossary_count)
    print_stats(conn)

    conn.close()
    log(f"\n⏱️  Tổng thời gian: {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
