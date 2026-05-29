"""
Script chỉ import content_html vào database đã có sẵn metadata.
Dùng khi Step 5 của download_all_to_sqlite.py bị lỗi OOM.
"""
import os
import sys
import time
import sqlite3
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

DB_NAME = "vietnamese_legal_documents.db"
DATASET_REPO = "th1nhng0/vietnamese-legal-documents"

def main():
    print("=" * 60)
    print("🔧 IMPORT CONTENT HTML ONLY (Low Memory Mode)")
    print("=" * 60)
    
    if not os.path.exists(DB_NAME):
        print(f"❌ Database '{DB_NAME}' not found! Run download_all_to_sqlite.py first.")
        sys.exit(1)
    
    # Check current state
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM documents")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM documents WHERE content_html IS NOT NULL AND content_html != ''")
    with_content = cursor.fetchone()[0]
    print(f"📊 Database: {total:,} documents, {with_content:,} with content_html")
    
    if with_content == total:
        print("✅ All documents already have content_html. Nothing to do!")
        conn.close()
        return
    
    print(f"⚠️  {total - with_content:,} documents missing content_html")
    print()
    
    # Download content parquet (uses HuggingFace cache if already downloaded)
    print("📥 Downloading content.parquet (uses cache if available)...")
    content_path = hf_hub_download(DATASET_REPO, "data/content.parquet", repo_type="dataset")
    print(f"✅ Content file ready: {content_path}")
    print()
    
    # Import using small batches
    print("📥 Importing content_html (200 docs per batch, low memory)...")
    pf = pq.ParquetFile(content_path)
    total_rows = pf.metadata.num_rows
    print(f"   Total rows in parquet: {total_rows:,}")
    
    start_time = time.time()
    total_updated = 0
    
    for batch in pf.iter_batches(batch_size=200, columns=["id", "content_html"]):
        updates = []
        for i in range(len(batch)):
            doc_id = batch.column("id")[i].as_py()
            content_html = batch.column("content_html")[i].as_py()
            if content_html:
                updates.append((content_html, doc_id))
        
        if updates:
            cursor.executemany("UPDATE documents SET content_html = ? WHERE id = ?", updates)
            conn.commit()
        
        total_updated += len(batch)
        elapsed = time.time() - start_time
        speed = total_updated / elapsed if elapsed > 0 else 0
        
        if total_updated % 2000 == 0 or total_updated >= total_rows:
            pct = total_updated / total_rows * 100
            eta = (total_rows - total_updated) / speed if speed > 0 else 0
            print(f"   {total_updated:,}/{total_rows:,} ({pct:.1f}%) | {speed:.0f} docs/s | ETA: {eta/60:.1f} min")
        
        del batch, updates
    
    conn.close()
    
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"🎉 DONE! Content imported in {elapsed/60:.1f} minutes")
    print("=" * 60)

if __name__ == "__main__":
    main()
