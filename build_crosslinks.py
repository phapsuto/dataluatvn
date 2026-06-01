"""
build_crosslinks.py — Xây dựng liên kết chéo Án Lệ ↔ Pháp Điển
Matching: applied_article_code trong anle → article_anchor trong phapdien
"""
import os
import re
import sys
import time
import sqlite3

DB_NAME = "vietnamese_legal_documents.db"


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def build_exact_crosslinks(conn):
    """
    Tìm liên kết chính xác:
    applied_article_code trong anle_documents khớp article_anchor trong phapdien_articles
    """
    cursor = conn.cursor()

    # Lấy tất cả bản án có applied_article_code
    cursor.execute("""
        SELECT doc_name, applied_article_code, applied_article_number,
               applied_article_clause, title
        FROM anle_documents
        WHERE applied_article_code IS NOT NULL
          AND applied_article_code != ''
    """)
    anle_with_codes = cursor.fetchall()
    log(f"📋 Tìm thấy {len(anle_with_codes)} bản án có applied_article_code")

    if not anle_with_codes:
        log("⚠️  Không có bản án nào có applied_article_code. Bỏ qua exact matching.")
        return 0

    # Lấy tất cả article_anchor từ pháp điển
    cursor.execute("SELECT article_anchor, article_title FROM phapdien_articles")
    phapdien_map = {}
    for row in cursor.fetchall():
        # Index by anchor
        phapdien_map[row[0]] = row[1]
        # Also index by cleaned anchor (strip leading #)
        cleaned = row[0].lstrip("#")
        phapdien_map[cleaned] = row[1]

    log(f"📖 Đã load {len(phapdien_map) // 2} Điều pháp điển vào bộ nhớ")

    # Xoá crosslinks cũ
    cursor.execute("DELETE FROM crosslinks")

    matched = 0
    for doc_name, code, art_num, art_clause, title in anle_with_codes:
        # Thử khớp chính xác
        if code in phapdien_map:
            cursor.execute("""
                INSERT INTO crosslinks (anle_doc_name, phapdien_anchor, match_type, confidence)
                VALUES (?, ?, 'exact', 1.0)
            """, (doc_name, code))
            matched += 1
        elif code.lstrip("#") in phapdien_map:
            anchor_clean = code.lstrip("#")
            cursor.execute("""
                INSERT INTO crosslinks (anle_doc_name, phapdien_anchor, match_type, confidence)
                VALUES (?, ?, 'exact', 1.0)
            """, (doc_name, "#" + anchor_clean))
            matched += 1

    conn.commit()
    log(f"✅ Exact matching: {matched} liên kết")
    return matched


def build_fuzzy_crosslinks(conn):
    """
    Tìm liên kết gần đúng:
    Dựa trên số Điều (applied_article_number) xuất hiện trong article_title
    """
    cursor = conn.cursor()

    # Lấy bản án có article_number nhưng CHƯA được match exact
    cursor.execute("""
        SELECT a.doc_name, a.applied_article_number, a.applied_article_clause, a.title
        FROM anle_documents a
        WHERE a.applied_article_number IS NOT NULL
          AND a.doc_name NOT IN (SELECT anle_doc_name FROM crosslinks)
    """)
    unmatched = cursor.fetchall()
    log(f"🔍 {len(unmatched)} bản án chưa được match exact, thử fuzzy...")

    if not unmatched:
        return 0

    # Lấy pháp điển và parse số Điều từ title
    cursor.execute("SELECT article_anchor, article_title, subject_title FROM phapdien_articles")
    phapdien_rows = cursor.fetchall()

    # Build index: article_number → [(anchor, title, subject)]
    article_num_index = {}
    for anchor, title, subject in phapdien_rows:
        if not title:
            continue
        # Parse "Điều X.Y.Z.W" hoặc "Điều N"
        m = re.search(r'Điều\s+(\d+)', title)
        if m:
            num = int(m.group(1))
            if num not in article_num_index:
                article_num_index[num] = []
            article_num_index[num].append((anchor, title, subject))

    matched = 0
    for doc_name, art_num, art_clause, anle_title in unmatched:
        if art_num not in article_num_index:
            continue

        candidates = article_num_index[art_num]

        # Nếu chỉ có 1 candidate → match luôn
        if len(candidates) == 1:
            cursor.execute("""
                INSERT INTO crosslinks (anle_doc_name, phapdien_anchor, match_type, confidence)
                VALUES (?, ?, 'fuzzy', 0.7)
            """, (doc_name, candidates[0][0]))
            matched += 1
        elif len(candidates) <= 10:
            # Nhiều candidates → thêm hết với confidence thấp hơn
            for anchor, pd_title, pd_subject in candidates:
                cursor.execute("""
                    INSERT INTO crosslinks (anle_doc_name, phapdien_anchor, match_type, confidence)
                    VALUES (?, ?, 'fuzzy', 0.4)
                """, (doc_name, anchor))
                matched += 1

    conn.commit()
    log(f"✅ Fuzzy matching: {matched} liên kết")
    return matched


def print_stats(conn):
    """In thống kê crosslinks"""
    cursor = conn.cursor()

    print()
    print("=" * 60)
    print("📊 THỐNG KÊ LIÊN KẾT CHÉO")
    print("=" * 60)

    cursor.execute("SELECT count(*) FROM crosslinks")
    total = cursor.fetchone()[0]
    print(f"  🔗 Tổng crosslinks: {total:,}")

    cursor.execute("SELECT match_type, count(*) FROM crosslinks GROUP BY match_type")
    for row in cursor.fetchall():
        print(f"     {row[0]}: {row[1]:,}")

    # Số bản án unique được link
    cursor.execute("SELECT count(DISTINCT anle_doc_name) FROM crosslinks")
    unique_anle = cursor.fetchone()[0]
    print(f"  ⚖️  Bản án được liên kết: {unique_anle}")

    # Số Điều unique được link
    cursor.execute("SELECT count(DISTINCT phapdien_anchor) FROM crosslinks")
    unique_pd = cursor.fetchone()[0]
    print(f"  📖 Điều pháp điển được liên kết: {unique_pd}")

    # Sample
    cursor.execute("""
        SELECT c.anle_doc_name, a.title, p.article_title, c.match_type, c.confidence
        FROM crosslinks c
        JOIN anle_documents a ON c.anle_doc_name = a.doc_name
        JOIN phapdien_articles p ON c.phapdien_anchor = p.article_anchor
        LIMIT 5
    """)
    rows = cursor.fetchall()
    if rows:
        print("\n  📝 Mẫu liên kết:")
        for r in rows:
            anle_title = (r[1] or "")[:50]
            print(f"     [{r[3]}|{r[4]:.1f}] {anle_title}... ↔ {r[2]}")

    print("=" * 60)


def main():
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy {DB_NAME}!")
        sys.exit(1)

    log("=" * 60)
    log("🔗 XÂY DỰNG LIÊN KẾT CHÉO ÁN LỆ ↔ PHÁP ĐIỂN")
    log("=" * 60)

    start = time.time()
    conn = sqlite3.connect(DB_NAME)

    exact = build_exact_crosslinks(conn)
    fuzzy = build_fuzzy_crosslinks(conn)

    print_stats(conn)
    conn.close()

    log(f"\n⏱️  Hoàn thành trong {time.time() - start:.1f}s")
    log(f"   Exact: {exact}, Fuzzy: {fuzzy}, Total: {exact + fuzzy}")


if __name__ == "__main__":
    main()
