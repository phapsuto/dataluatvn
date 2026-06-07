"""
import_huggingface.py — Tải content từ HuggingFace dataset th1nhng0/vietnamese-legal-documents
sử dụng pyarrow trực tiếp (tránh lỗi ArrowInvalid casting của datasets library) 
và merge vào DB hiện có. Nhanh hơn 1000x so với crawl Playwright!
"""
import sqlite3
import time
import os
import sys
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

DB_NAME = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"
DATASET_REPO = "th1nhng0/vietnamese-legal-documents"

def main():
    print("=" * 60)
    print("📥 Tải content từ HuggingFace: th1nhng0/vietnamese-legal-documents (pyarrow mode)")
    print("=" * 60)
    
    if not os.path.exists(DB_NAME):
        print(f"❌ DB chính {DB_NAME} không tồn tại!")
        return
        
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
        print("✅ Tất cả đã có đầy đủ content!")
        return
    
    # Download content parquet file via huggingface_hub
    print("\n⬇️  Đang tải file content.parquet từ HuggingFace (khoảng 3.5GB)...")
    start = time.time()
    try:
        content_parquet_path = hf_hub_download(DATASET_REPO, "data/content.parquet", repo_type="dataset")
        elapsed = time.time() - start
        print(f"   ✅ Tải thành công file parquet về cache: {content_parquet_path} trong {elapsed:.0f}s")
    except Exception as e:
        print(f"❌ Lỗi tải dữ liệu từ HuggingFace: {e}")
        sys.exit(1)
    
    # Merge into DB
    print("\n🔄 Đang merge dữ liệu content vào content_store.db...")
    start_merge = time.time()
    
    conn_main = sqlite3.connect(DB_NAME, timeout=60.0)
    conn_main.execute("PRAGMA journal_mode=WAL")
    conn_main.execute("PRAGMA synchronous=NORMAL")
    
    # Kết nối content_store.db
    conn_content = sqlite3.connect(CONTENT_DB, timeout=60.0)
    conn_content.execute("PRAGMA journal_mode=WAL")
    conn_content.execute("PRAGMA synchronous=NORMAL")
    
    # Tạo bảng nếu chưa có
    conn_content.execute("""
        CREATE TABLE IF NOT EXISTS document_content (
            doc_id INTEGER PRIMARY KEY,
            content_html TEXT
        )
    """)
    conn_content.commit()
    
    pf = pq.ParquetFile(content_parquet_path)
    total_rows = pf.metadata.num_rows
    print(f"   Tổng số văn bản trong file Parquet: {total_rows:,}")
    
    filled = 0
    skipped = 0
    batch_size = 1000
    
    # Đọc theo từng batch từ file parquet
    for batch in pf.iter_batches(batch_size=1000, columns=["id", "content_html"]):
        updates_content = []
        updates_main = []
        updates_fts = []
        
        for i in range(len(batch)):
            doc_id = batch.column("id")[i].as_py()
            content_html = batch.column("content_html")[i].as_py()
            
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
                
            # Đưa vào danh sách cập nhật
            updates_content.append((doc_id_int, content_html))
            updates_main.append((doc_id_int,))
            
            # Đọc metadata để đưa vào FTS
            try:
                r = conn_main.execute("SELECT title, so_ky_hieu FROM documents WHERE id = ?", (doc_id_int,)).fetchone()
                if r:
                    updates_fts.append((doc_id_int, r[0], r[1]))
            except:
                pass
                
            filled += 1
            missing_ids.discard(doc_id_int)
            
        # Thực thi ghi DB theo batch
        if updates_content:
            conn_content.executemany(
                "INSERT OR REPLACE INTO document_content (doc_id, content_html) VALUES (?, ?)",
                updates_content
            )
            
            for (did,) in updates_main:
                conn_main.execute("UPDATE documents SET has_content = 1 WHERE id = ?", (did,))
                
            if updates_fts:
                conn_main.executemany(
                    "INSERT OR REPLACE INTO documents_fts (rowid, title, so_ky_hieu) VALUES (?, ?, ?)",
                    updates_fts
                )
                
            conn_content.commit()
            conn_main.commit()
            
            elapsed = time.time() - start_merge
            speed = filled / elapsed if elapsed > 0 else 0
            print(f"   ⏳ [{filled:,}] filled | {skipped:,} checked | "
                  f"Speed: {speed:.0f} docs/s | Còn thiếu: {len(missing_ids):,}")
                  
    # Commit cuối cùng
    conn_content.commit()
    conn_main.commit()
    
    # Run optimize on main DB
    print("\n🔧 Đang tối ưu hóa FTS index và dọn dẹp database...")
    conn_main.execute("ANALYZE")
    conn_content.execute("ANALYZE")
    conn_main.close()
    conn_content.close()
    
    elapsed_total = time.time() - start
    print("\n" + "=" * 60)
    print("🎉 HOÀN THÀNH ĐỒNG BỘ DỮ LIỆU!")
    print(f"   ✅ Đã tải thành công: {filled:,} văn bản")
    print(f"   ⏭️  Skipped: {skipped:,}")
    print(f"   ⏳ Còn thiếu: {len(missing_ids):,}")
    print(f"   ⏱️  Tổng thời gian: {elapsed_total:.0f}s ({elapsed_total/60:.1f}m)")
    print("=" * 60)
    
    if missing_ids:
        print(f"\n📋 Danh sách 10 ID đầu tiên vẫn thiếu (cần cào trực tiếp bằng Playwright): {sorted(list(missing_ids))[:10]}")

if __name__ == "__main__":
    main()
