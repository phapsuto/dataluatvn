import os
# Set environment variables before any other imports to prevent online checks
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import sys
import json
import sqlite3
import numpy as np
import torch
import faiss
import time
from sentence_transformers import SentenceTransformer

GOLD_INPUT = "scratch/benchmark_gold_500.json"
MAIN_DB = "vietnamese_legal_documents.db"
BENCHMARK_DB = "vector_store_bgem3_benchmark.db"
BENCHMARK_INDEX = "chunks_faiss_bgem3_benchmark.index"

def main():
    print("🎯 STARTING BENCHMARK INDEX BUILDER")
    
    # 1. Load unique ground truth document IDs
    with open(GOLD_INPUT, "r", encoding="utf-8") as f:
        gold_data = json.load(f)
    
    gt_docs = set()
    for item in gold_data:
        gt_docs.update(item["gt_doc_ids"])
    
    print(f"Loaded {len(gold_data)} queries with {len(gt_docs)} unique ground truth document IDs.")
    
    # 2. Query chunk IDs for GT documents
    conn = sqlite3.connect(MAIN_DB)
    cursor = conn.cursor()
    
    placeholders = ",".join(["?"] * len(gt_docs))
    cursor.execute(f"SELECT id, chunk_with_meta FROM document_chunks WHERE doc_id IN ({placeholders})", list(gt_docs))
    gt_chunks = cursor.fetchall()
    
    print(f"Found {len(gt_chunks)} chunks for ground truth documents.")
    
    # 3. Query 20,000 random noise chunks efficiently without ORDER BY RANDOM()
    gt_chunk_ids = {row[0] for row in gt_chunks}
    
    cursor.execute("SELECT MIN(id), MAX(id) FROM document_chunks")
    min_id, max_id = cursor.fetchone()
    if min_id is None or max_id is None:
        min_id, max_id = 1, 1550000
        
    import random
    noise_chunks = []
    random_ids = set()
    while len(random_ids) < 20000:
        needed = 25000 - len(random_ids)
        candidates = [random.randint(min_id, max_id) for _ in range(needed)]
        random_ids.update(candidates)
        random_ids.difference_update(gt_chunk_ids)
        
    random_ids = list(random_ids)[:20000]
    # Query in batches to respect SQLite limit
    for j in range(0, len(random_ids), 900):
        batch_ids = random_ids[j:j+900]
        placeholders = ",".join(["?"] * len(batch_ids))
        cursor.execute(f"SELECT id, chunk_with_meta FROM document_chunks WHERE id IN ({placeholders})", batch_ids)
        noise_chunks.extend(cursor.fetchall())
        
    conn.close()
    print(f"Selected {len(noise_chunks)} random noise chunks.")
    
    all_chunks = gt_chunks + noise_chunks
    print(f"Total chunks to index: {len(all_chunks)}")
    
    # Optimize encoding speed by sorting by length and truncating outliers to 4096 chars
    # Sorting guarantees similar length chunks are in the same batch, preventing heavy padding.
    all_chunks.sort(key=lambda x: len(x[1]))
    all_chunks = [(row[0], row[1][:4096]) for row in all_chunks]
    print("⚡ Sorted chunks by length and truncated to 4096 chars for optimal batching.")
    
    # 4. Initialize BGE-M3 model
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading BGE-M3 on {device.upper()} (float16)...")
    model = SentenceTransformer(
        "BAAI/bge-m3", 
        device=device, 
        model_kwargs={"torch_dtype": torch.float16} if device == "mps" else {}
    )
    model.max_seq_length = 512
    print("Model loaded successfully. Max sequence length set to 512.")
    
    # 5. Index chunks in batches
    BATCH_SIZE = 128
    vectors = []
    chunk_ids = []
    
    start_time = time.time()
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i+BATCH_SIZE]
        batch_ids = [row[0] for row in batch]
        batch_texts = [row[1] for row in batch]
        
        embeddings = model.encode(
            batch_texts, 
            batch_size=len(batch_texts), 
            show_progress_bar=False, 
            convert_to_numpy=True
        )
        
        vectors.append(embeddings)
        chunk_ids.extend(batch_ids)
        
        processed = i + len(batch)
        if processed % 1024 == 0 or processed == len(all_chunks):
            elapsed = time.time() - start_time
            speed = processed / elapsed if elapsed > 0 else 0
            print(f"Indexed {processed}/{len(all_chunks)} | Speed: {speed:.1f} chunks/s")
            
    xb = np.vstack(vectors).astype(np.float32)
    ids = np.array(chunk_ids, dtype=np.int64)
    
    # Normalize L2
    faiss.normalize_L2(xb)
    
    # Build FAISS Index
    dimension = 1024
    quantizer = faiss.IndexFlatIP(dimension)
    index = faiss.IndexIDMap(quantizer)
    index.add_with_ids(xb, ids)
    
    print(f"Saving FAISS index to {BENCHMARK_INDEX}...")
    faiss.write_index(index, BENCHMARK_INDEX)
    print("🎉 Benchmark index built successfully!")

if __name__ == "__main__":
    main()
