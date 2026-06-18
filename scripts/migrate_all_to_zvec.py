import os
import sys
import time
import sqlite3
import numpy as np
import zvec

# Set single-thread CPU execution for PyTorch, FAISS, and OpenBLAS to prevent deadlocks and segfaults
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import DB_NAME, VECTOR_DB_SOTA, ZVEC_DB_PATH

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def main():
    log("==========================================================")
    log("🚀 ALIBABA ZVEC FULL DATABASE MIGRATION (1.55M VECTORS)")
    log("==========================================================")
    
    # Check databases exist
    if not os.path.exists(DB_NAME):
        log(f"❌ Error: SQLite metadata database not found at {DB_NAME}")
        sys.exit(1)
    if not os.path.exists(VECTOR_DB_SOTA):
        log(f"❌ Error: SQLite vector database not found at {VECTOR_DB_SOTA}")
        sys.exit(1)
        
    # Create or open Zvec collection
    schema = zvec.CollectionSchema(
        name="zvec_laws",
        vectors=[
            zvec.VectorSchema("dense_vector", zvec.DataType.VECTOR_FP32, 1024)
        ],
        fields=[
            zvec.FieldSchema("doc_id", zvec.DataType.INT64),
            zvec.FieldSchema("so_ky_hieu", zvec.DataType.STRING),
            zvec.FieldSchema("loai_van_ban", zvec.DataType.STRING),
            zvec.FieldSchema("tinh_trang_hieu_luc", zvec.DataType.STRING),
            zvec.FieldSchema("chunk_text", zvec.DataType.STRING)
        ]
    )
    
    # Clean up the Zvec database to start a fresh 100% migration
    import shutil
    if os.path.exists(ZVEC_DB_PATH):
        log(f"🧹 Removing old Zvec database at {ZVEC_DB_PATH} to start a fresh migration...")
        try:
            shutil.rmtree(ZVEC_DB_PATH)
        except Exception as e:
            log(f"⚠️ Could not delete directory: {e}")
            
    log(f"Creating new Zvec database at {ZVEC_DB_PATH}...")
    collection = zvec.create_and_open(path=ZVEC_DB_PATH, schema=schema)
        
    # Connect to SQLite
    log("Connecting to SQLite databases...")
    conn = sqlite3.connect(DB_NAME)
    conn.execute(f"ATTACH DATABASE '{VECTOR_DB_SOTA}' AS vector_db")
    cursor = conn.cursor()
    
    # Count total chunks with vectors to migrate
    log("Counting records to migrate...")
    cursor.execute("SELECT COUNT(*) FROM vector_db.chunk_vectors")
    total_count = cursor.fetchone()[0]
    log(f"Total records to migrate: {total_count:,}")
    
    # Execute query to retrieve chunks + metadata + vectors
    cursor.execute("""
        SELECT c.id, c.doc_id, c.chunk_text,
               d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc,
               v.vector
        FROM document_chunks c
        JOIN documents d ON c.doc_id = d.id
        JOIN vector_db.chunk_vectors v ON c.id = v.chunk_id
        WHERE v.vector IS NOT NULL
    """)
    
    batch_size = 20000
    count = 0
    t_start = time.time()
    t_batch = time.time()
    
    log(f"Starting batch migration (Batch Size: {batch_size:,})...")
    
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
            
        zvec_docs = []
        for r in rows:
            chunk_id, doc_id, text, so_ky, loai_vb, status, vec_bytes = r
            
            # Convert float32 binary BLOB back to Python list
            vector = np.frombuffer(vec_bytes, dtype=np.float32).tolist()
            
            zvec_docs.append(zvec.Doc(
                id=str(chunk_id),
                vectors={"dense_vector": vector},
                fields={
                    "doc_id": doc_id,
                    "so_ky_hieu": so_ky or "",
                    "loai_van_ban": loai_vb or "",
                    "tinh_trang_hieu_luc": status or "Còn hiệu lực",
                    "chunk_text": text or ""
                }
            ))
            
        # Insert in sub-batches of 1000 to comply with Zvec's limit
        sub_batch_size = 1000
        for i in range(0, len(zvec_docs), sub_batch_size):
            collection.insert(zvec_docs[i:i + sub_batch_size])
        count += len(rows)
        
        # Free memory
        del zvec_docs
        del rows
        
        elapsed = time.time() - t_batch
        total_elapsed = time.time() - t_start
        rate = batch_size / elapsed if elapsed > 0 else 0
        log(f"   Ingested {count:,}/{total_count:,} chunks ({count/total_count*100:.2f}%) | Speed: {rate:.1f} docs/sec | Total Time: {total_elapsed:.1f}s")
        t_batch = time.time()
        
    log("Flushing Zvec collection writes to disk...")
    collection.flush()
    log("✅ Ingestion complete. Running garbage collection...")
    conn.close()
    import gc
    gc.collect()
    
    # 5. Build HNSW index on the dense vector field
    log("🏗️ Building HNSW vector search index (this can take a few minutes)...")
    hnsw_param = zvec.HnswIndexParam(
        metric_type=zvec.MetricType.IP,
        m=16,
        ef_construction=200
    )
    t_index = time.time()
    collection.create_index("dense_vector", hnsw_param)
    index_time = time.time() - t_index
    log(f"✅ Zvec HNSW index created successfully in {index_time:.1f} seconds ({index_time/60:.2f} minutes)!")
    
    log("==========================================================")
    log("🎉 MIGRATION SUCCESSFUL! 100% DATA LAW SYNCED WITH ALIBABA ZVEC")
    log("==========================================================")

if __name__ == "__main__":
    main()
