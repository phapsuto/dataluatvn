#!/usr/bin/env python3
"""
GĐ2-HĐ2: Benchmark Phase 2 — Hybrid Search (FTS5 Chunks + FAISS Vector Chunks + RRF) vs Baselines.
Sửa lỗi Segmentation Fault (exit code 139) bằng cách dùng Lazy Import cho PyTorch/FAISS sau khi đóng SQLite.
"""

import pyarrow.parquet as pq
import sqlite3
import random
import time
import sys
import os
import re

# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routers.laws import parse_fts_query, normalize_spelling

SAMPLE_SIZE = 500
TOP_K = 10
MAIN_DB = "vietnamese_legal_documents.db"
FAISS_INDEX_FILE = "chunks_faiss.index"
MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"

STOPWORDS = {
    "của", "và", "với", "trong", "trên", "về", "cho", "đến", "từ", "tại",
    "theo", "bằng", "qua", "vào", "hay", "hoặc", "nhưng", "mà", "rằng",
    "nếu", "khi", "vì", "do", "bởi", "để", "đã", "đang", "sẽ", "được",
    "bị", "có", "là", "thì", "cũng", "không", "các", "những", "một",
    "này", "đó", "người", "việc", "sau", "trước", "còn", "nên", "phải",
    "cần", "nào", "như", "thế", "gì", "đây", "đều", "lại", "mới", "rồi",
    "điều", "khoản", "mục", "chương", "điểm", "tổ", "chức",
}

def extract_fts_snippet(context_text):
    if not context_text or len(context_text) < 20:
        return None
    clean = re.sub(r'[^\w\s]', ' ', context_text)
    words = [w for w in clean.split() if len(w) >= 3 and w.lower() not in STOPWORDS]
    if len(words) < 2:
        return None
    top = sorted(set(words), key=len, reverse=True)[:5]
    return " AND ".join(top)

def build_ground_truth(test_df, sample_indices, db_conn):
    print("\n🔗 Mapping ground truth (FTS-accelerated using document content)...")
    cursor = db_conn.cursor()
    mapping = {}
    found = 0
    total = len(sample_indices)
    
    for i, idx in enumerate(sample_indices):
        row = test_df.iloc[idx]
        contexts = list(row["context_list"])
        matched_ids = set()
        
        for ctx in contexts:
            snippet = extract_fts_snippet(str(ctx))
            if not snippet:
                continue
            snippet_norm = normalize_spelling(snippet)
            try:
                cursor.execute(
                    "SELECT rowid FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT 3",
                    (snippet_norm,)
                )
                for r in cursor.fetchall():
                    matched_ids.add(r[0])
            except:
                try:
                    words = snippet_norm.replace(" AND ", " ").split()[:3]
                    simple_q = " OR ".join(words)
                    cursor.execute(
                        "SELECT rowid FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT 3",
                        (simple_q,)
                    )
                    for r in cursor.fetchall():
                        matched_ids.add(r[0])
                except:
                    pass
        
        if matched_ids:
            mapping[idx] = matched_ids
            found += 1
        
        if (i + 1) % 100 == 0 or i == total - 1:
            sys.stdout.write(f"\r   [{i+1}/{total}] Mapped: {found} ({found/(i+1)*100:.0f}%)")
            sys.stdout.flush()
    
    print(f"\n   ✅ {found}/{total} ({found/total*100:.1f}%)")
    return mapping

def main():
    print("=" * 60)
    print("PHASE 2 BENCHMARK: HYBRID SEARCH VS BASELINES")
    print("=" * 60)
    
    if not os.path.exists(FAISS_INDEX_FILE):
        print(f"❌ Error: {FAISS_INDEX_FILE} not found. Please run build_vector_index.py first.")
        sys.exit(1)
        
    db_conn = sqlite3.connect(MAIN_DB)
    
    # Load test dataset
    print("\n📥 Đọc dataset...")
    test_df = pq.read_table("data/yuITC/test.parquet").to_pandas()
    print(f"   Test dataset contains {len(test_df)} questions.")
    
    random.seed(42)
    sample_indices = random.sample(range(len(test_df)), min(SAMPLE_SIZE, len(test_df)))
    
    # Chạy mapping ground truth
    mapping = build_ground_truth(test_df, sample_indices, db_conn)
    
    # ĐÓNG KẾT NỐI DATABASE trước khi import các thư viện nặng để tránh Segmentation Fault 139
    db_conn.close()
    
    mapped = [idx for idx in sample_indices if idx in mapping]
    total = len(mapped)
    
    # LAZY IMPORT để tránh xung đột thư viện OpenMP/Metal với SQLite3
    print("\n📦 Loading PyTorch, FAISS và SentenceTransformers...")
    import numpy as np
    import torch
    import faiss
    from sentence_transformers import SentenceTransformer
    
    device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🤖 Khởi tạo mô hình {MODEL_NAME} trên thiết bị: {device.upper()}")
    model = SentenceTransformer(MODEL_NAME, device=device)
    print(f"📥 Loading FAISS index từ file: {FAISS_INDEX_FILE}")
    faiss_index = faiss.read_index(FAISS_INDEX_FILE)
    print(f"✅ Đã tải xong chỉ mục FAISS chứa {faiss_index.ntotal} vectors.")
    
    print(f"\n🔍 [Hybrid Search (FTS5 + FAISS + RRF)] Benchmark trên {total} câu hỏi...")
    
    RRF_K = 60
    hits = 0
    rrs = []
    
    # Mở lại kết nối SQLite mới để truy vấn trong vòng lặp (mỗi lần dùng xong sẽ commit/đóng nếu cần, ở đây ta giữ kết nối readonly)
    db_conn = sqlite3.connect(MAIN_DB)
    cursor = db_conn.cursor()
    
    start_time = time.time()
    
    for i, idx in enumerate(mapped):
        row = test_df.iloc[idx]
        question = row["question"]
        gt_ids = mapping[idx]
        
        # 1. FTS5 Chunks (Top 100)
        fts_query = parse_fts_query(question)
        fts_results = []
        if fts_query:
            try:
                # Dùng CROSS JOIN để tối ưu hóa hiệu năng quét FTS
                cursor.execute("""
                    SELECT c.id, c.doc_id
                    FROM chunks_fts f
                    CROSS JOIN document_chunks c ON f.rowid = c.id
                    WHERE f.chunks_fts MATCH ?
                    ORDER BY f.rank
                    LIMIT 100
                """, (fts_query,))
                fts_results = cursor.fetchall()
            except Exception as e:
                pass

        # 2. Vector Search (Top 100)
        vector_results = []
        try:
            q_norm = normalize_spelling(question)
            query_vector = model.encode([q_norm], show_progress_bar=False, convert_to_numpy=True)
            faiss.normalize_L2(query_vector)
            distances, indices = faiss_index.search(query_vector.astype(np.float32), 100)
            
            for cid in indices[0]:
                if cid != -1:
                    vector_results.append(int(cid))
        except Exception as e:
            pass

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        
        # Add FTS5 ranks
        for rank, (cid, doc_id) in enumerate(fts_results):
            if cid not in rrf_scores:
                rrf_scores[cid] = {"doc_id": doc_id, "score": 0.0}
            rrf_scores[cid]["score"] += 1.0 / (RRF_K + rank)
            
        # Add Vector ranks
        needed_cids = [cid for cid in vector_results if cid not in rrf_scores]
        cid_to_doc = {}
        if needed_cids:
            placeholders = ",".join(["?"] * len(needed_cids))
            try:
                cursor.execute(f"SELECT id, doc_id FROM document_chunks WHERE id IN ({placeholders})", list(needed_cids))
                for row in cursor.fetchall():
                    cid_to_doc[row[0]] = row[1]
            except Exception as e:
                pass
                
        for rank, cid in enumerate(vector_results):
            doc_id = cid_to_doc.get(cid)
            if cid not in rrf_scores:
                if doc_id is None:
                    continue
                rrf_scores[cid] = {"doc_id": doc_id, "score": 0.0}
            rrf_scores[cid]["score"] += 1.0 / (RRF_K + rank)
            
        # Sort và lấy Top-K tài liệu
        sorted_items = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
        
        seen_docs = set()
        retrieved_docs = []
        for item in sorted_items:
            doc_id = item["doc_id"]
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                retrieved_docs.append(doc_id)
                if len(retrieved_docs) >= TOP_K:
                    break
                    
        # Đo Hit@10
        hit = False
        for rank, doc_id in enumerate(retrieved_docs):
            if doc_id in gt_ids:
                hits += 1
                rrs.append(1.0 / (rank + 1))
                hit = True
                break
        if not hit:
            rrs.append(0)
            
        if (i + 1) % 50 == 0 or i == total - 1:
            hr = hits / (i + 1) * 100
            mrr = sum(rrs) / len(rrs)
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed
            sys.stdout.write(f"\r   [{i+1}/{total}] Hit@{TOP_K}: {hr:.1f}% | MRR: {mrr:.3f} | Tốc độ: {speed:.1f} q/s")
            sys.stdout.flush()
            
    print()
    
    final_hr = hits / total * 100
    final_mrr = sum(rrs) / len(rrs) if rrs else 0
    
    print("\n" + "=" * 60)
    print("📊 KẾT QUẢ SO SÁNH")
    print("=" * 60)
    print(f"{'Method':<35} {'Hit@10':>12} {'MRR@10':>12}")
    print("-" * 60)
    print(f"{'Document-level FTS5 (Baseline)':<35} {'7.8%':>11} {'0.057':>12}")
    print(f"{'Chunk-level FTS5 (Phase 1)':<35} {'6.1%':>11} {'0.033':>12}")
    print(f"{'Hybrid FTS5 + Vector + RRF (Phase 2)':<35} {final_hr:>11.1f}% {final_mrr:>12.3f}")
    print("-" * 60)
    print("=" * 60)
    
    db_conn.close()

if __name__ == "__main__":
    main()
