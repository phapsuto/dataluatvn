#!/usr/bin/env python3
"""
GĐ1-HĐ1: Benchmark Phase 1 — Chunk-level FTS5 search vs Document-level FTS5 baseline.
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

from app.routers.laws import parse_fts_query

SAMPLE_SIZE = 500
TOP_K = 10
MAIN_DB = "vietnamese_legal_documents.db"

def normalize_spelling(text: str) -> str:
    if not text:
        return ""
    text = text.replace('òa', 'o\u00e0').replace('óa', 'o\u00e1').replace('ỏa', 'o\u1ea3').replace('õa', 'o\u00e3').replace('ọa', 'o\u1ea1')
    text = text.replace('òe', 'o\u00e8').replace('óe', 'o\u00e9').replace('ỏe', 'o\u1ebd').replace('õe', 'o\u1ebd').replace('ọe', 'o\u1eb9')
    text = text.replace('ủy', 'u\u1ef7').replace('úy', 'u\u00fd').replace('ùy', 'u\u1ef3').replace('ũy', 'u\u1ef5').replace('ụy', 'u\u1ef9')
    text = text.replace('Òa', 'O\u00e0').replace('Óa', 'O\u00e1').replace('Ỏa', 'O\u1ea3').replace('Õa', 'O\u00e3').replace('Ọa', 'O\u1ea1')
    text = text.replace('Òe', 'O\u00e8').replace('Óe', 'O\u00e9').replace('Ỏe', 'O\u1ebd').replace('Õe', 'O\u1ebd').replace('Ọe', 'O\u1eb9')
    text = text.replace('Ủy', 'U\u1ef7').replace('Úy', 'U\u00fd').replace('Ùy', 'U\u1ef3').replace('Ũy', 'U\u1ef5').replace('Ụy', 'U\u1ef9')
    return text

STOPWORDS = {
    "của", "và", "với", "trong", "trên", "về", "cho", "đến", "từ", "tại",
    "theo", "bằng", "qua", "vào", "hay", "hoặc", "nhưng", "mà", "rằng",
    "nếu", "khi", "vì", "do", "bởi", "để", "đã", "đang", "sẽ", "được",
    "bị", "có", "là", "thì", "cũng", "không", "các", "những", "một",
    "này", "đó", "người", "việc", "sau", "trước", "còn", "nên", "phải",
    "cần", "nào", "như", "thế", "gì", "đây", "đều", "lại", "mới", "rồi",
    "điều", "khoản", "mục", "chương", "điểm", "tổ", "chức",
}

def parse_fts_query_chunk(q: str) -> str:
    q_clean = re.sub(r'[^\w\s]', ' ', q).strip()
    all_words = [w for w in q_clean.split() if w]
    if not all_words:
        return ""
    all_words = [normalize_spelling(w) for w in all_words]
    keywords = [w for w in all_words if w.lower() not in STOPWORDS and len(w) > 1]
    if not keywords:
        keywords = [w for w in all_words if len(w) > 1]
    if not keywords:
        keywords = all_words
        
    if len(keywords) == 1:
        return f"{keywords[0]}*"
        
    phrase = " ".join(keywords)
    and_q = " AND ".join(keywords)
    or_q = " OR ".join(keywords)
    return f'"{phrase}" OR ({and_q}) OR ({or_q})'

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
            # Normalize snippet spelling to match FTS
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

def run_document_fts_benchmark(test_df, mapping, sample_indices, db_conn):
    """FTS5 baseline on whole documents."""
    mapped = [idx for idx in sample_indices if idx in mapping]
    total = len(mapped)
    cursor = db_conn.cursor()
    
    print(f"\n🔍 [Document-level FTS5 Baseline] Benchmark trên {total} câu hỏi (Top-{TOP_K})...")
    
    hits = 0
    rrs = []
    
    for i, idx in enumerate(mapped):
        row = test_df.iloc[idx]
        question = row["question"]
        gt_ids = mapping[idx]
        
        fts_query = parse_fts_query(question)
        results = []
        if fts_query:
            try:
                cursor.execute(
                    "SELECT rowid FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT ?",
                    (fts_query, TOP_K)
                )
                results = [r[0] for r in cursor.fetchall()]
            except:
                pass
                
        hit = False
        for rank, doc_id in enumerate(results):
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
            sys.stdout.write(f"\r   [{i+1}/{total}] Hit@{TOP_K}: {hr:.1f}% | MRR: {mrr:.3f}")
            sys.stdout.flush()
            
    print()
    return hits / total * 100, sum(rrs) / len(rrs) if rrs else 0

def run_chunk_fts_benchmark(test_df, mapping, sample_indices, db_conn):
    """FTS5 on document chunks."""
    mapped = [idx for idx in sample_indices if idx in mapping]
    total = len(mapped)
    cursor = db_conn.cursor()
    
    print(f"\n🔍 [Chunk-level FTS5] Benchmark trên {total} câu hỏi (Top-{TOP_K})...")
    
    hits = 0
    rrs = []
    
    for i, idx in enumerate(mapped):
        row = test_df.iloc[idx]
        question = row["question"]
        gt_ids = mapping[idx]
        
        # Use the optimized chunk query parser
        fts_query = parse_fts_query_chunk(question)
        results = []
        if fts_query:
            try:
                # Retrieve top chunks, order by relevance rank
                cursor.execute("""
                    SELECT doc_id FROM chunks_fts
                    JOIN document_chunks ON chunks_fts.rowid = document_chunks.id
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT 30
                """, (fts_query,))
                
                # Deduplicate retrieved doc_ids while preserving order
                seen = set()
                results = []
                for (doc_id,) in cursor.fetchall():
                    if doc_id not in seen:
                        seen.add(doc_id)
                        results.append(doc_id)
                        if len(results) >= TOP_K:
                            break
            except Exception as e:
                pass
                
        hit = False
        for rank, doc_id in enumerate(results):
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
            sys.stdout.write(f"\r   [{i+1}/{total}] Hit@{TOP_K}: {hr:.1f}% | MRR: {mrr:.3f}")
            sys.stdout.flush()
            
    print()
    return hits / total * 100, sum(rrs) / len(rrs) if rrs else 0

def main():
    print("=" * 60)
    print("PHASE 1 BENCHMARK: CHUNK-LEVEL FTS5 VS DOCUMENT-LEVEL FTS5")
    print("=" * 60)
    
    # Load dataset
    print("\n📥 Đọc dataset...")
    test_df = pq.read_table("data/yuITC/test.parquet").to_pandas()
    print(f"   Test dataset contains {len(test_df)} questions.")
    
    random.seed(42)
    sample_indices = random.sample(range(len(test_df)), min(SAMPLE_SIZE, len(test_df)))
    
    db_conn = sqlite3.connect(MAIN_DB)
    
    # First verify chunks table has data
    cursor = db_conn.cursor()
    cursor.execute("SELECT count(*) FROM document_chunks")
    chunk_count = cursor.fetchone()[0]
    print(f"Total chunks in database: {chunk_count}")
    if chunk_count == 0:
        print("❌ Error: document_chunks table is empty. Please run build_chunks_v2.py first.")
        db_conn.close()
        sys.exit(1)
        
    mapping = build_ground_truth(test_df, sample_indices, db_conn)
    
    doc_hr, doc_mrr = run_document_fts_benchmark(test_df, mapping, sample_indices, db_conn)
    chunk_hr, chunk_mrr = run_chunk_fts_benchmark(test_df, mapping, sample_indices, db_conn)
    
    print("\n" + "=" * 60)
    print("📊 KẾT QUẢ SO SÁNH")
    print("=" * 60)
    print(f"{'Method':<30} {'Hit@10':>12} {'MRR@10':>12}")
    print("-" * 60)
    print(f"{'Document-level FTS5 (Baseline)':<30} {doc_hr:>11.1f}% {doc_mrr:>12.3f}")
    print(f"{'Chunk-level FTS5 (Phase 1)':<30} {chunk_hr:>11.1f}% {chunk_mrr:>12.3f}")
    print("-" * 60)
    delta_hr = chunk_hr - doc_hr
    print(f"Change in Hit@10: {delta_hr:>+10.1f}%")
    print("=" * 60)
    
    db_conn.close()

if __name__ == "__main__":
    main()
