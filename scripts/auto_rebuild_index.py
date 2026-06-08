#!/usr/bin/env python3
"""
Auto-rebuild BM25 index khi có văn bản mới.

Chạy định kỳ (cron/launchd):
  - Kiểm tra: có VB mới chưa?
  - Nếu có: rebuild BM25 index + FTS5 content_fts
  - Hot-reload: server tự load cache mới khi restart hoặc qua API

Crontab (chạy mỗi đêm 2h sáng):
  0 2 * * * cd /path/to/luatvietnam && python3 scripts/auto_rebuild_index.py >> logs/rebuild.log 2>&1
"""

import sqlite3
import os
import sys
import time
import json
from datetime import datetime

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

MAIN_DB = os.path.join(BASE_DIR, "vietnamese_legal_documents.db")
CONTENT_DB = os.path.join(BASE_DIR, "content_store.db")
BM25_CACHE = os.path.join(BASE_DIR, "bm25_index.pkl")
STATE_FILE = os.path.join(BASE_DIR, "index_state.json")


def get_doc_count(db_path):
    """Đếm số VB trong database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM documents")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_content_fts_count(db_path):
    """Đếm số records trong content_fts."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT count(*) FROM content_fts")
        count = cursor.fetchone()[0]
    except:
        count = 0
    conn.close()
    return count


def load_state():
    """Load trạng thái build trước đó."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_doc_count": 0, "last_build": None, "last_fts_count": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def rebuild_content_fts():
    """Cập nhật FTS5 index cho văn bản mới (incremental)."""
    from html.parser import HTMLParser
    import re
    
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._text = []
            self._skip = False
        def handle_starttag(self, tag, attrs):
            if tag in ('script', 'style', 'svg'):
                self._skip = True
        def handle_endtag(self, tag):
            if tag in ('script', 'style', 'svg'):
                self._skip = False
        def handle_data(self, data):
            if not self._skip:
                self._text.append(data)
        def get_text(self):
            return ' '.join(self._text)
    
    def html_to_text(html):
        if not html:
            return ""
        try:
            e = TextExtractor()
            e.feed(html)
            return re.sub(r'\s+', ' ', e.get_text()).strip()
        except:
            return re.sub(r'<[^>]+>', ' ', html)
    
    main_conn = sqlite3.connect(MAIN_DB)
    content_conn = sqlite3.connect(CONTENT_DB)
    main_cursor = main_conn.cursor()
    content_cursor = content_conn.cursor()
    
    # Tìm doc_ids đã có trong content_fts
    try:
        main_cursor.execute("SELECT rowid FROM content_fts")
        existing_ids = {row[0] for row in main_cursor.fetchall()}
    except:
        existing_ids = set()
    
    # Tìm doc_ids mới (có trong documents nhưng chưa trong content_fts)
    main_cursor.execute("SELECT id, title FROM documents")
    all_docs = {row[0]: row[1] for row in main_cursor.fetchall()}
    
    new_ids = set(all_docs.keys()) - existing_ids
    if not new_ids:
        print(f"   ✅ FTS5 đã up-to-date ({len(existing_ids)} records)")
        main_conn.close()
        content_conn.close()
        return 0
    
    print(f"   📝 Thêm {len(new_ids)} VB mới vào content_fts...")
    added = 0
    
    for doc_id in new_ids:
        title = all_docs.get(doc_id, "")
        
        # Lấy content từ content_store
        content_cursor.execute(
            "SELECT content_html FROM document_content WHERE doc_id = ?", (doc_id,)
        )
        row = content_cursor.fetchone()
        content_text = html_to_text(row[0])[:15000] if row else ""
        
        full_text = f"{title} {content_text}" if content_text else title
        
        if full_text.strip():
            try:
                main_cursor.execute(
                    "INSERT INTO content_fts(rowid, title, content_text) VALUES (?, ?, ?)",
                    (doc_id, title, full_text)
                )
                added += 1
            except:
                pass
    
    main_conn.commit()
    main_conn.close()
    content_conn.close()
    
    print(f"   ✅ Đã thêm {added} VB mới vào FTS5")
    return added


def rebuild_bm25():
    """Rebuild toàn bộ BM25 index."""
    from app.hybrid_search import HybridSearchEngine
    
    print("   🏗️ Rebuilding BM25 index...")
    
    # Xóa cache cũ
    if os.path.exists(BM25_CACHE):
        os.remove(BM25_CACHE)
    
    engine = HybridSearchEngine(MAIN_DB, CONTENT_DB, BM25_CACHE)
    engine.build_index()
    
    return True


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"🔄 Auto-rebuild Index — {now}")
    print(f"{'='*60}")
    
    state = load_state()
    current_doc_count = get_doc_count(MAIN_DB)
    current_fts_count = get_content_fts_count(MAIN_DB)
    
    print(f"   📊 Documents: {current_doc_count:,} (trước: {state['last_doc_count']:,})")
    print(f"   📊 FTS5 records: {current_fts_count:,} (trước: {state['last_fts_count']:,})")
    
    new_docs = current_doc_count - state['last_doc_count']
    need_fts = current_doc_count > current_fts_count
    need_bm25 = new_docs > 0 or not os.path.exists(BM25_CACHE)
    
    if not need_fts and not need_bm25:
        print("   ✅ Tất cả index đều up-to-date. Không cần rebuild.")
        return
    
    start = time.time()
    
    # 1. Cập nhật FTS5 (incremental — chỉ thêm VB mới)
    if need_fts:
        print("\n📋 Bước 1: Cập nhật FTS5 (incremental)...")
        fts_added = rebuild_content_fts()
    else:
        print("\n📋 Bước 1: FTS5 đã up-to-date")
        fts_added = 0
    
    # 2. Rebuild BM25 (full rebuild — nhanh với cache)
    if need_bm25:
        print("\n📋 Bước 2: Rebuild BM25 index...")
        rebuild_bm25()
    else:
        print("\n📋 Bước 2: BM25 đã up-to-date")
    
    elapsed = time.time() - start
    
    # Save state
    new_state = {
        "last_doc_count": current_doc_count,
        "last_fts_count": get_content_fts_count(MAIN_DB),
        "last_build": now,
        "build_time_seconds": round(elapsed, 1),
        "new_docs_added": new_docs,
        "fts_records_added": fts_added,
    }
    save_state(new_state)
    
    print(f"\n{'='*60}")
    print(f"✅ Hoàn thành rebuild trong {elapsed:.1f}s")
    print(f"   Thêm: {new_docs} VB mới")
    print(f"   FTS5: +{fts_added} records")
    print(f"   BM25: rebuilt")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    main()
