import os
import sys
import time
import sqlite3
import numpy as np
import zvec
import faiss
import json

# Set single-thread CPU execution for PyTorch, FAISS, and OpenBLAS to prevent deadlocks and segfaults
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["DISABLE_LLM_EXPANSION"] = "1"

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.routers.laws import get_smart_search_resources
from app.config import DB_NAME, ZVEC_DB_PATH

GOLD_INPUT = "scratch/benchmark_gold_500.json"

def main():
    print("=" * 60)
    print("🧪 RUNNING 500 RANDOM TEST QUESTIONS BENCHMARK ON ALIBABA ZVEC")
    print("=" * 60)
    
    if not os.path.exists(GOLD_INPUT):
        print(f"❌ Error: Gold questions file {GOLD_INPUT} not found!")
        sys.exit(1)
        
    with open(GOLD_INPUT, "r", encoding="utf-8") as f:
        gold_data = json.load(f)
        
    print(f"📥 Loaded {len(gold_data)} gold questions with ground truth.")
    
    print("📦 Loading embedding model and legacy FAISS index...")
    model, faiss_index = get_smart_search_resources()
    
    print(f"Opening Zvec collection at {ZVEC_DB_PATH}...")
    col = zvec.open(path=ZVEC_DB_PATH)
    
    # Connect to SQLite for legacy mapping
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Metric accumulators
    legacy_latencies = []
    zvec_latencies = []
    
    legacy_hits = {1: 0, 3: 0, 5: 0, 10: 0}
    zvec_hits = {1: 0, 3: 0, 5: 0, 10: 0}
    
    legacy_rrs = []
    zvec_rrs = []
    
    total = len(gold_data)
    
    print(f"\n📊 Starting benchmark execution on {total} queries...")
    
    for idx, item in enumerate(gold_data):
        query = item["question"]
        gt_ids = [int(x) for x in item["gt_doc_ids"]]
        
        # Encode query
        q_vec = model.encode([query], show_progress_bar=False, convert_to_numpy=True).astype(np.float32)
        faiss.normalize_L2(q_vec)
        q_vec_list = q_vec[0].tolist()
        
        # 1. Evaluate Legacy Pipeline (FAISS Search + SQLite Map)
        t0 = time.time()
        distances, indices = faiss_index.search(q_vec, 20)
        faiss_ids = [int(cid) for cid in indices[0] if cid != -1]
        
        legacy_doc_ids = []
        if faiss_ids:
            placeholders = ",".join(["?"] * len(faiss_ids))
            # Keep ordering of FAISS IDs using ORDER BY CASE
            order_cases = " ".join([f"WHEN c.id = {cid} THEN {rank}" for rank, cid in enumerate(faiss_ids)])
            cursor.execute(f"""
                SELECT c.doc_id
                FROM document_chunks c
                WHERE c.id IN ({placeholders})
                ORDER BY CASE {order_cases} END
            """, tuple(faiss_ids))
            
            seen = set()
            for row in cursor.fetchall():
                doc_id = int(row[0])
                if doc_id not in seen:
                    seen.add(doc_id)
                    legacy_doc_ids.append(doc_id)
                    
        legacy_latency = (time.time() - t0) * 1000  # ms
        legacy_latencies.append(legacy_latency)
        
        # 2. Evaluate Zvec Pipeline (HNSW search + Inline metadata)
        t0 = time.time()
        zvec_results = col.query(
            queries=zvec.Query(field_name="dense_vector", vector=q_vec_list),
            topk=20
        )
        
        zvec_doc_ids = []
        seen_z = set()
        for res in zvec_results:
            doc_id = int(res.fields.get("doc_id"))
            if doc_id not in seen_z:
                seen_z.add(doc_id)
                zvec_doc_ids.append(doc_id)
                
        zvec_latency = (time.time() - t0) * 1000  # ms
        zvec_latencies.append(zvec_latency)
        
        # Calculate Hits and MRR for Legacy
        for k in [1, 3, 5, 10]:
            if any(gt in legacy_doc_ids[:k] for gt in gt_ids):
                legacy_hits[k] += 1
                
        legacy_rr = 0.0
        for rank, doc_id in enumerate(legacy_doc_ids[:10]):
            if doc_id in gt_ids:
                legacy_rr = 1.0 / (rank + 1)
                break
        legacy_rrs.append(legacy_rr)
        
        # Calculate Hits and MRR for Zvec
        for k in [1, 3, 5, 10]:
            if any(gt in zvec_doc_ids[:k] for gt in gt_ids):
                zvec_hits[k] += 1
                
        zvec_rr = 0.0
        for rank, doc_id in enumerate(zvec_doc_ids[:10]):
            if doc_id in gt_ids:
                zvec_rr = 1.0 / (rank + 1)
                break
        zvec_rrs.append(zvec_rr)
        
        if (idx + 1) % 50 == 0 or idx == total - 1:
            avg_legacy_l = sum(legacy_latencies) / len(legacy_latencies)
            avg_zvec_l = sum(zvec_latencies) / len(zvec_latencies)
            legacy_hr10 = (legacy_hits[10] / (idx + 1)) * 100
            zvec_hr10 = (zvec_hits[10] / (idx + 1)) * 100
            sys.stdout.write(f"\r   [{idx+1}/{total}] | Legacy (Hit@10: {legacy_hr10:.1f}%, Lat: {avg_legacy_l:.1f}ms) | Zvec (Hit@10: {zvec_hr10:.1f}%, Lat: {avg_zvec_l:.1f}ms)")
            sys.stdout.flush()
            
    print("\n")
    conn.close()
    
    # Calculate final results
    legacy_mrr = sum(legacy_rrs) / len(legacy_rrs)
    zvec_mrr = sum(zvec_rrs) / len(zvec_rrs)
    
    avg_legacy_lat = sum(legacy_latencies) / len(legacy_latencies)
    avg_zvec_lat = sum(zvec_latencies) / len(zvec_latencies)
    
    # Print comparison table
    print("=" * 85)
    print("📊 ALIBABA ZVEC VS. LEGACY PIPELINE ACCURACY & LATENCY BENCHMARK (500 GOLD QUERIES)")
    print("=" * 85)
    print(f"{'Metric':<25} {'Legacy Pipeline (FAISS+SQL)':<30} {'Alibaba Zvec Pipeline':<30}")
    print("-" * 85)
    print(f"{'Hit@1':<25} {(legacy_hits[1]/total)*100:>21.2f}% {(zvec_hits[1]/total)*100:>23.2f}%")
    print(f"{'Hit@3':<25} {(legacy_hits[3]/total)*100:>21.2f}% {(zvec_hits[3]/total)*100:>23.2f}%")
    print(f"{'Hit@5':<25} {(legacy_hits[5]/total)*100:>21.2f}% {(zvec_hits[5]/total)*100:>23.2f}%")
    print(f"{'Hit@10':<25} {(legacy_hits[10]/total)*100:>21.2f}% {(zvec_hits[10]/total)*100:>23.2f}%")
    print(f"{'MRR@10':<25} {legacy_mrr:>22.4f} {zvec_mrr:>24.4f}")
    print(f"{'Average Latency':<25} {avg_legacy_lat:>20.2f} ms {avg_zvec_lat:>22.2f} ms")
    print("-" * 85)
    print(f"🚀 Speedup Ratio: {avg_legacy_lat / avg_zvec_lat:.2f}x Faster")
    print("=" * 85)

if __name__ == "__main__":
    main()
