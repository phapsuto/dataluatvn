#!/usr/bin/env python3
"""
Xây dựng FTS5 index trên NỘI DUNG văn bản pháp luật.
Content nằm ở content_store.db, metadata ở vietnamese_legal_documents.db.
"""
import sqlite3
import re
import sys
import time
from html.parser import HTMLParser

MAIN_DB = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"

class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'svg', 'iframe', 'img', 'video'):
            self._skip = True
    
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg', 'iframe', 'img', 'video'):
            self._skip = False
        if tag in ('p', 'br', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td'):
            self._text.append(' ')
    
    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)
    
    def get_text(self):
        return ' '.join(self._text)

def html_to_text(html: str) -> str:
    if not html:
        return ""
    try:
        extractor = HTMLTextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
    except:
        text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    # Giới hạn 15,000 chars cho FTS (đủ để cover toàn bộ nội dung quan trọng)
    return text[:15000]

def build_content_fts():
    print("=" * 70)
    print("🏗️  XÂY DỰNG FTS5 INDEX TRÊN NỘI DUNG VĂN BẢN PHÁP LUẬT")
    print("   Main DB: vietnamese_legal_documents.db")
    print("   Content DB: content_store.db")
    print("=" * 70)
    
    main_conn = sqlite3.connect(MAIN_DB, timeout=60)
    main_conn.execute("PRAGMA journal_mode = WAL")
    main_conn.execute("PRAGMA cache_size = -64000")
    
    content_conn = sqlite3.connect(CONTENT_DB, timeout=60)
    content_conn.execute("PRAGMA cache_size = -64000")
    
    main_cursor = main_conn.cursor()
    content_cursor = content_conn.cursor()
    
    # Bước 1: Xóa FTS cũ, tạo mới
    print("\n📦 Bước 1: Chuẩn bị bảng content_fts...")
    try:
        main_cursor.execute("DROP TABLE IF EXISTS content_fts")
        main_conn.commit()
    except:
        pass
    
    main_cursor.execute("""
        CREATE VIRTUAL TABLE content_fts USING fts5(
            title,
            so_ky_hieu,
            linh_vuc,
            content_text,
            tokenize='unicode61'
        )
    """)
    main_conn.commit()
    print("   ✅ Tạo bảng content_fts thành công")
    
    # Bước 2: Load metadata từ main DB
    print("\n📊 Bước 2: Load metadata...")
    main_cursor.execute("SELECT id, title, so_ky_hieu, linh_vuc FROM documents ORDER BY id")
    docs = {}
    for row in main_cursor.fetchall():
        docs[row[0]] = {"title": row[1] or "", "so_ky_hieu": row[2] or "", "linh_vuc": row[3] or ""}
    print(f"   Loaded {len(docs)} documents metadata")
    
    # Bước 3: Load content và build FTS
    content_cursor.execute("SELECT COUNT(*) FROM document_content")
    total_content = content_cursor.fetchone()[0]
    print(f"\n🔨 Bước 3: Xử lý {total_content} nội dung văn bản...")
    
    content_cursor.execute("SELECT doc_id, content_html FROM document_content ORDER BY doc_id")
    
    batch = []
    processed = 0
    start_time = time.time()
    
    while True:
        row = content_cursor.fetchone()
        if row is None:
            break
        
        doc_id, content_html = row
        meta = docs.get(doc_id, {"title": "", "so_ky_hieu": "", "linh_vuc": ""})
        
        content_text = html_to_text(content_html)
        
        batch.append((doc_id, meta["title"], meta["so_ky_hieu"], meta["linh_vuc"], content_text))
        
        if len(batch) >= 500:
            main_cursor.executemany(
                "INSERT INTO content_fts(rowid, title, so_ky_hieu, linh_vuc, content_text) VALUES (?, ?, ?, ?, ?)",
                batch
            )
            main_conn.commit()
            
            processed += len(batch)
            batch = []
            
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total_content - processed) / rate if rate > 0 else 0
            sys.stdout.write(
                f"\r   Đã xử lý: {processed}/{total_content} ({processed/total_content*100:.1f}%) "
                f"| {rate:.0f} doc/s | ETA: {eta:.0f}s"
            )
            sys.stdout.flush()
    
    if batch:
        main_cursor.executemany(
            "INSERT INTO content_fts(rowid, title, so_ky_hieu, linh_vuc, content_text) VALUES (?, ?, ?, ?, ?)",
            batch
        )
        processed += len(batch)
    
    # Insert documents KHÔNG có content (chỉ title/metadata)
    print(f"\n\n📄 Bước 3b: Thêm {len(docs) - processed} documents chỉ có metadata...")
    content_doc_ids = set()
    main_cursor.execute("SELECT rowid FROM content_fts")
    for row in main_cursor.fetchall():
        content_doc_ids.add(row[0])
    
    no_content_batch = []
    for doc_id, meta in docs.items():
        if doc_id not in content_doc_ids:
            no_content_batch.append((doc_id, meta["title"], meta["so_ky_hieu"], meta["linh_vuc"], ""))
            if len(no_content_batch) >= 1000:
                main_cursor.executemany(
                    "INSERT INTO content_fts(rowid, title, so_ky_hieu, linh_vuc, content_text) VALUES (?, ?, ?, ?, ?)",
                    no_content_batch
                )
                no_content_batch = []
    
    if no_content_batch:
        main_cursor.executemany(
            "INSERT INTO content_fts(rowid, title, so_ky_hieu, linh_vuc, content_text) VALUES (?, ?, ?, ?, ?)",
            no_content_batch
        )
    
    main_conn.commit()
    elapsed = time.time() - start_time
    
    main_cursor.execute("SELECT COUNT(*) FROM content_fts")
    fts_total = main_cursor.fetchone()[0]
    
    print(f"   ✅ Tổng records trong content_fts: {fts_total}")
    print(f"   ⏱️  Thời gian tổng: {elapsed:.1f}s")
    
    # Bước 4: Test search
    print(f"\n🔍 Bước 4: Kiểm chứng search trên content...")
    test_queries = [
        "luật đất đai",
        "bảo hiểm xã hội", 
        "xử phạt vi phạm hành chính",
        "Ngân hàng Chính sách xã hội xếp lương",
        "Chứng chỉ hành nghề dược",
    ]
    for tq in test_queries:
        main_cursor.execute(
            "SELECT rowid, title, rank FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT 3",
            (tq,)
        )
        results = main_cursor.fetchall()
        print(f"   '{tq}': {len(results)} kết quả", end="")
        if results:
            print(f" → [{results[0][1][:60]}]")
        else:
            print()
    
    content_conn.close()
    main_conn.close()
    
    print(f"\n{'=' * 70}")
    print(f"✅ HOÀN THÀNH! content_fts ({fts_total} records) đã sẵn sàng.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    build_content_fts()
