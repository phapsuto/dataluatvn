"""
import_huggingface.py — Tải content từ HuggingFace dataset th1nhng0/vietnamese-legal-documents
và merge vào DB hiện có. Nhanh hơn 1000x so với crawl Playwright!

Dataset có 3 subsets:
  - metadata: id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, ...
  - content: id, content_html
  - relationships: doc_id, other_doc_id, relationship
"""
import sqlite3
import time
import sys

try:
    from datasets import load_dataset
except ImportError:
    print("❌ Cần cài datasets: pip install datasets")
    print("   ./venv/bin/pip install datasets")
    sys.exit(1)

DB_NAME = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"

def main():
    print("=" * 60)
    print("📥 Tải content từ HuggingFace: th1nhng0/vietnamese-legal-documents")
    print("=" * 60)
    
    # Check hiện tại thiếu bao nhiêu
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    missing = conn.execute("SELECT COUNT(*) FROM documents WHERE has_content = 0").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    print(f"\n📊 DB hiện tại: {total:,} docs, thiếu content: {missing:,}")
    
    # Get all IDs that need content
    missing_ids = set(r[0] for r in conn.execute("SELECT id FROM documents WHERE has_content = 0").fetchall())
    print(f"   IDs cần tải: {len(missing_ids):,}")
    conn.close()
    
    if not missing_ids:
        print("✅ Tất cả đã có content!")
        return
    
    # Load content subset from HuggingFace
    print("\n⬇️  Đang tải dataset content từ HuggingFace (có thể mất 1-5 phút lần đầu)...")
    start = time.time()
    
    ds = load_dataset("th1nhng0/vietnamese-legal-documents", "content", split="data")
    
    elapsed = time.time() - start
    print(f"   ✅ Tải xong: {len(ds):,} documents trong {elapsed:.0f}s")
    
    # Build lookup: HF id -> content_html
    print("\n🔄 Đang merge vào DB...")
    
    conn_main = sqlite3.connect(DB_NAME, timeout=30)
    conn_main.execute("PRAGMA journal_mode=WAL")
    conn_content = sqlite3.connect(CONTENT_DB, timeout=30)
    conn_content.execute("PRAGMA journal_mode=WAL")
    
    filled = 0
    skipped = 0
    batch_size = 500
    
    for i, row in enumerate(ds):
        doc_id = row.get("id")
        content_html = row.get("content_html")
        
        # HuggingFace IDs might be strings
        try:
            doc_id_int = int(doc_id) if doc_id else None
        except (ValueError, TypeError):
            continue
        
        if doc_id_int is None or doc_id_int not in missing_ids:
            skipped += 1
            continue
        
        if not content_html or len(content_html) < 50:
            skipped += 1
            continue
        
        # Save to content_store.db
        conn_content.execute(
            "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
            (doc_id_int, content_html)
        )
        
        # Update has_content in main DB
        conn_main.execute("UPDATE documents SET has_content = 1 WHERE id = ?", (doc_id_int,))
        
        # Update FTS
        try:
            r = conn_main.execute("SELECT title, so_ky_hieu FROM documents WHERE id = ?", (doc_id_int,)).fetchone()
            if r:
                conn_main.execute(
                    "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
                    (doc_id_int, r[0], r[1])
                )
        except:
            pass
        
        filled += 1
        missing_ids.discard(doc_id_int)
        
        # Commit every batch
        if filled % batch_size == 0:
            conn_main.commit()
            conn_content.commit()
            elapsed = time.time() - start
            speed = filled / elapsed if elapsed > 0 else 0
            print(f"   ⏳ [{filled:,}] filled | {skipped:,} skipped | "
                  f"Speed: {speed:.0f}/s | Còn thiếu: {len(missing_ids):,}")
    
    # Final commit
    conn_main.commit()
    conn_content.commit()
    conn_main.close()
    conn_content.close()
    
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH!")
    print(f"   ✅ Đã fill: {filled:,} documents")
    print(f"   ⏭️  Skipped: {skipped:,}")
    print(f"   ⏳ Còn thiếu: {len(missing_ids):,}")
    print(f"   ⏱️  Thời gian: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print("=" * 60)
    
    if missing_ids:
        print(f"\n📋 Sample IDs vẫn thiếu (đầu tiên 20): {sorted(list(missing_ids))[:20]}")


if __name__ == "__main__":
    main()
