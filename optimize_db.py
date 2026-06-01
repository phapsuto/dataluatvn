"""
optimize_db.py — Tối ưu hóa Database cho Production
1. Tạo FTS5 Full-Text Search indexes (tăng tốc 10-50x)
2. Thêm missing indexes cho search columns
3. Tạo unified search endpoint data
4. VACUUM + ANALYZE
"""
import os
import sys
import time
import sqlite3

DB_NAME = "vietnamese_legal_documents.db"


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def create_fts_indexes(conn):
    """Tạo FTS5 virtual tables cho full-text search"""
    cursor = conn.cursor()

    # ── FTS cho documents (153K) ──
    log("📇 Tạo FTS5 cho documents...")
    cursor.execute("DROP TABLE IF EXISTS documents_fts")
    cursor.execute("""
        CREATE VIRTUAL TABLE documents_fts USING fts5(
            title,
            so_ky_hieu,
            content='documents',
            content_rowid='id',
            tokenize='unicode61'
        )
    """)
    cursor.execute("""
        INSERT INTO documents_fts(rowid, title, so_ky_hieu)
        SELECT id, title, so_ky_hieu FROM documents
    """)
    conn.commit()

    cursor.execute("SELECT count(*) FROM documents_fts")
    log(f"   ✅ documents_fts: {cursor.fetchone()[0]:,} rows indexed")

    # ── FTS cho phapdien_articles (64K) ──
    log("📇 Tạo FTS5 cho phapdien_articles...")
    cursor.execute("DROP TABLE IF EXISTS phapdien_fts")
    cursor.execute("""
        CREATE VIRTUAL TABLE phapdien_fts USING fts5(
            article_title,
            content_text,
            content='phapdien_articles',
            content_rowid='rowid',
            tokenize='unicode61'
        )
    """)
    cursor.execute("""
        INSERT INTO phapdien_fts(rowid, article_title, content_text)
        SELECT rowid, article_title, content_text FROM phapdien_articles
    """)
    conn.commit()

    cursor.execute("SELECT count(*) FROM phapdien_fts")
    log(f"   ✅ phapdien_fts: {cursor.fetchone()[0]:,} rows indexed")

    # ── FTS cho anle_documents (2K) ──
    log("📇 Tạo FTS5 cho anle_documents...")
    cursor.execute("DROP TABLE IF EXISTS anle_fts")
    cursor.execute("""
        CREATE VIRTUAL TABLE anle_fts USING fts5(
            title,
            markdown,
            principle_text,
            content='anle_documents',
            content_rowid='rowid',
            tokenize='unicode61'
        )
    """)
    cursor.execute("""
        INSERT INTO anle_fts(rowid, title, markdown, principle_text)
        SELECT rowid, title, markdown, principle_text FROM anle_documents
    """)
    conn.commit()

    cursor.execute("SELECT count(*) FROM anle_fts")
    log(f"   ✅ anle_fts: {cursor.fetchone()[0]:,} rows indexed")


def add_missing_indexes(conn):
    """Thêm indexes còn thiếu"""
    cursor = conn.cursor()
    log("📇 Thêm missing indexes...")

    indexes = [
        # Cho search trên content_text trong phapdien (FTS sẽ thay thế LIKE)
        "CREATE INDEX IF NOT EXISTS idx_pd_chapter ON phapdien_articles(chapter_title)",
        "CREATE INDEX IF NOT EXISTS idx_al_subtype ON anle_documents(doc_subtype)",
        "CREATE INDEX IF NOT EXISTS idx_al_jurisdiction ON anle_documents(jurisdiction)",
        # Composite index cho common search patterns
        "CREATE INDEX IF NOT EXISTS idx_al_case_year ON anle_documents(case_type, year)",
    ]

    for sql in indexes:
        cursor.execute(sql)
        name = sql.split("idx_")[1].split(" ")[0]
        log(f"   ✅ idx_{name}")

    conn.commit()


def optimize_db(conn):
    """VACUUM + ANALYZE cho performance"""
    cursor = conn.cursor()
    log("🔧 Running ANALYZE...")
    cursor.execute("ANALYZE")
    conn.commit()

    log("🔧 Running VACUUM (có thể mất vài giây)...")
    cursor.execute("VACUUM")
    conn.commit()


def benchmark(conn):
    """So sánh performance trước/sau FTS"""
    cursor = conn.cursor()

    print()
    print("=" * 60)
    print("⚡ BENCHMARK: LIKE vs FTS5")
    print("=" * 60)

    # ── Pháp điển ──
    start = time.time()
    cursor.execute("SELECT count(*) FROM phapdien_articles WHERE content_text LIKE '%hợp đồng%'")
    count_like = cursor.fetchone()[0]
    t_like = time.time() - start

    start = time.time()
    cursor.execute("""
        SELECT count(*) FROM phapdien_fts WHERE phapdien_fts MATCH 'hợp đồng'
    """)
    count_fts = cursor.fetchone()[0]
    t_fts = time.time() - start

    speedup = t_like / t_fts if t_fts > 0 else 999
    print(f"  Pháp điển 'hợp đồng':")
    print(f"    LIKE:  {t_like*1000:.0f}ms ({count_like} results)")
    print(f"    FTS5:  {t_fts*1000:.0f}ms ({count_fts} results)")
    print(f"    ⚡ Speedup: {speedup:.0f}x")

    # ── Documents ──
    start = time.time()
    cursor.execute("SELECT count(*) FROM documents WHERE title LIKE '%đất đai%' OR so_ky_hieu LIKE '%đất đai%'")
    count_like2 = cursor.fetchone()[0]
    t_like2 = time.time() - start

    start = time.time()
    cursor.execute("SELECT count(*) FROM documents_fts WHERE documents_fts MATCH 'đất đai'")
    count_fts2 = cursor.fetchone()[0]
    t_fts2 = time.time() - start

    speedup2 = t_like2 / t_fts2 if t_fts2 > 0 else 999
    print(f"\n  Documents 'đất đai':")
    print(f"    LIKE:  {t_like2*1000:.0f}ms ({count_like2} results)")
    print(f"    FTS5:  {t_fts2*1000:.0f}ms ({count_fts2} results)")
    print(f"    ⚡ Speedup: {speedup2:.0f}x")

    # ── Án lệ ──
    start = time.time()
    cursor.execute("SELECT count(*) FROM anle_documents WHERE markdown LIKE '%bồi thường%'")
    count_like3 = cursor.fetchone()[0]
    t_like3 = time.time() - start

    start = time.time()
    cursor.execute("SELECT count(*) FROM anle_fts WHERE anle_fts MATCH 'bồi thường'")
    count_fts3 = cursor.fetchone()[0]
    t_fts3 = time.time() - start

    speedup3 = t_like3 / t_fts3 if t_fts3 > 0 else 999
    print(f"\n  Án lệ 'bồi thường':")
    print(f"    LIKE:  {t_like3*1000:.0f}ms ({count_like3} results)")
    print(f"    FTS5:  {t_fts3*1000:.0f}ms ({count_fts3} results)")
    print(f"    ⚡ Speedup: {speedup3:.0f}x")

    print("=" * 60)


def main():
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy {DB_NAME}!")
        sys.exit(1)

    log("=" * 60)
    log("🚀 TỐI ƯU HÓA DATABASE")
    log("=" * 60)

    start = time.time()
    conn = sqlite3.connect(DB_NAME)

    create_fts_indexes(conn)
    add_missing_indexes(conn)
    optimize_db(conn)
    benchmark(conn)

    # Show final DB size
    cursor = conn.cursor()
    cursor.execute("SELECT page_count * page_size FROM pragma_page_count, pragma_page_size")
    size_bytes = cursor.fetchone()[0]
    log(f"\n📦 DB size sau tối ưu: {size_bytes / 1024 / 1024:.0f} MB")

    conn.close()
    log(f"⏱️  Hoàn thành trong {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
