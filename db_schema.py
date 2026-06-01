"""
db_schema.py — Quản lý Schema Migration cho dataluatvn
Thêm bảng mới mà KHÔNG ảnh hưởng dữ liệu documents/relationships cũ.
Idempotent: chạy bao nhiêu lần cũng an toàn.
"""
import os
import sys
import sqlite3
import time

DB_NAME = "vietnamese_legal_documents.db"


def upgrade_schema(conn):
    """Thêm các bảng mới + indexes"""
    cursor = conn.cursor()

    # ── 1. Bảng phapdien_articles ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS phapdien_articles (
        article_anchor    TEXT PRIMARY KEY,
        article_title     TEXT,
        chapter_title     TEXT,
        subject_id        TEXT,
        subject_title     TEXT,
        topic_id          TEXT,
        topic_number      INTEGER,
        topic_title       TEXT,
        content_text      TEXT,
        content_char_len  INTEGER,
        content_word_count INTEGER,
        source_url        TEXT,
        source_note_text  TEXT,
        source_links_json TEXT,
        related_note_text TEXT,
        scraped_at        TEXT,
        source            TEXT DEFAULT 'huggingface'
    )
    """)

    # ── 2. Bảng phapdien_glossary (thuật ngữ VI-EN) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS phapdien_glossary (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        category    TEXT,
        vi          TEXT,
        en          TEXT,
        note        TEXT
    )
    """)

    # ── 3. Bảng anle_documents ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS anle_documents (
        doc_name              TEXT PRIMARY KEY,
        title                 TEXT,
        doc_code              TEXT,
        doc_type              TEXT,
        case_type             TEXT,
        doc_subtype           TEXT,
        year                  INTEGER,
        issue_date            TEXT,
        issuing_authority     TEXT,
        court_level           TEXT,
        jurisdiction          TEXT,
        subject               TEXT,
        markdown              TEXT,
        num_pages             INTEGER,
        num_sections          INTEGER,
        num_paragraphs        INTEGER,
        num_sentences         INTEGER,
        char_len              INTEGER,
        text_hash             TEXT,
        precedent_number      TEXT,
        adopted_date          TEXT,
        applied_article_code  TEXT,
        applied_article_number INTEGER,
        applied_article_clause INTEGER,
        principle_text        TEXT,
        detail_url            TEXT,
        pdf_url               TEXT,
        source                TEXT DEFAULT 'huggingface',
        confidence            REAL,
        parsed_at             TEXT
    )
    """)

    # ── 4. Bảng hf_sync_log ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hf_sync_log (
        dataset_id      TEXT PRIMARY KEY,
        last_sha        TEXT,
        last_modified   TEXT,
        last_checked_at TEXT,
        last_synced_at  TEXT,
        records_added   INTEGER DEFAULT 0,
        records_total   INTEGER DEFAULT 0
    )
    """)

    # ── 5. Bảng crosslinks (Phase 5, tạo trước cho gọn) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS crosslinks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        anle_doc_name   TEXT,
        phapdien_anchor TEXT,
        match_type      TEXT,
        confidence      REAL,
        FOREIGN KEY (anle_doc_name) REFERENCES anle_documents(doc_name),
        FOREIGN KEY (phapdien_anchor) REFERENCES phapdien_articles(article_anchor)
    )
    """)

    # ── Indexes ──
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_pd_subject    ON phapdien_articles(subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_pd_topic      ON phapdien_articles(topic_id)",
        "CREATE INDEX IF NOT EXISTS idx_pd_title      ON phapdien_articles(article_title)",
        "CREATE INDEX IF NOT EXISTS idx_gl_vi         ON phapdien_glossary(vi)",
        "CREATE INDEX IF NOT EXISTS idx_al_case       ON anle_documents(case_type)",
        "CREATE INDEX IF NOT EXISTS idx_al_court      ON anle_documents(court_level)",
        "CREATE INDEX IF NOT EXISTS idx_al_year       ON anle_documents(year)",
        "CREATE INDEX IF NOT EXISTS idx_al_prec       ON anle_documents(precedent_number)",
        "CREATE INDEX IF NOT EXISTS idx_al_article    ON anle_documents(applied_article_code)",
        "CREATE INDEX IF NOT EXISTS idx_al_hash       ON anle_documents(text_hash)",
        "CREATE INDEX IF NOT EXISTS idx_cl_anle       ON crosslinks(anle_doc_name)",
        "CREATE INDEX IF NOT EXISTS idx_cl_phapdien   ON crosslinks(phapdien_anchor)",
    ]
    for stmt in index_statements:
        cursor.execute(stmt)

    conn.commit()


def verify_schema(conn):
    """Kiểm tra schema đã đúng chưa"""
    cursor = conn.cursor()

    # Lấy danh sách bảng
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    required = [
        "documents", "relationships",  # Cũ
        "phapdien_articles", "phapdien_glossary",  # Mới
        "anle_documents", "hf_sync_log", "crosslinks",  # Mới
    ]

    print("=" * 60)
    print("📋 SCHEMA VERIFICATION")
    print("=" * 60)

    all_ok = True
    for tbl in required:
        exists = tbl in tables
        status = "✅" if exists else "❌"
        print(f"  {status} {tbl}")
        if not exists:
            all_ok = False

    # Kiểm tra dữ liệu cũ không bị ảnh hưởng
    cursor.execute("SELECT count(*) FROM documents")
    doc_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM relationships")
    rel_count = cursor.fetchone()[0]

    print()
    print(f"  📊 documents:     {doc_count:>10,} rows (dữ liệu cũ)")
    print(f"  📊 relationships: {rel_count:>10,} rows (dữ liệu cũ)")

    # Kiểm tra bảng mới (phải rỗng)
    for tbl in ["phapdien_articles", "phapdien_glossary", "anle_documents", "hf_sync_log", "crosslinks"]:
        if tbl in tables:
            cursor.execute(f"SELECT count(*) FROM {tbl}")
            cnt = cursor.fetchone()[0]
            print(f"  📊 {tbl}: {cnt:>10,} rows (mới)")

    print()
    if all_ok and doc_count > 0:
        print("🎉 Schema migration thành công! Dữ liệu cũ nguyên vẹn.")
    else:
        print("⚠️  Có vấn đề — kiểm tra lại.")

    return all_ok


def main():
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy {DB_NAME}!")
        print("   Hãy chạy download_all_to_sqlite.py trước.")
        sys.exit(1)

    print(f"⚙️  Đang upgrade schema cho: {os.path.abspath(DB_NAME)}")
    start = time.time()

    conn = sqlite3.connect(DB_NAME)
    upgrade_schema(conn)
    verify_schema(conn)
    conn.close()

    print(f"\n⏱️  Hoàn thành trong {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
