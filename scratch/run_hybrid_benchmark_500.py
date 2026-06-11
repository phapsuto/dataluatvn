#!/usr/bin/env python3
import json
import sqlite3
import time
import os
import sys
import numpy as np

# Thêm thư mục dự án vào PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Đặt biến môi trường đơn luồng để tránh lỗi crash OpenMP trên macOS
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["DISABLE_LLM_EXPANSION"] = "1"

from app.routers.laws import smart_search_laws, get_smart_search_resources, parse_fts_query, chunk_search_laws

GOLD_INPUT = "scratch/benchmark_gold_500.json"
MAIN_DB = "vietnamese_legal_documents.db"

def run_document_fts(query: str, limit: int = 10) -> list:
    conn = sqlite3.connect(MAIN_DB)
    cursor = conn.cursor()
    fts_query = parse_fts_query(query)
    results = []
    if fts_query:
        try:
            cursor.execute("""
                SELECT rowid 
                FROM content_fts 
                WHERE content_fts MATCH ? 
                ORDER BY rank 
                LIMIT ?
            """, (fts_query, limit))
            results = [row[0] for row in cursor.fetchall()]
        except Exception:
            pass
    conn.close()
    return results

def run_chunk_fts(query: str, limit: int = 10) -> list:
    try:
        search_res = chunk_search_laws(q=query, limit=30, offset=0, _key=None)
        # Lọc trùng và lấy top document ids
        seen_docs = set()
        retrieved_docs = []
        for chunk in search_res.get("results", []):
            doc_id = chunk.get("doc_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs.add(doc_id)
                retrieved_docs.append(doc_id)
                if len(retrieved_docs) >= limit:
                    break
        return retrieved_docs
    except Exception as e:
        print(f"⚠️ Chunk FTS Error: {e}")
        return []

def run_hybrid_search(query: str, limit: int = 10) -> list:
    try:
        search_res = smart_search_laws(
            q=query,
            loai_van_ban=None,
            co_quan_ban_hanh=None,
            status=None,
            linh_vuc=None,
            limit=30, # Lấy nhiều hơn một chút để lọc trùng
            offset=0,
            _key=None
        )
        seen_docs = set()
        retrieved_docs = []
        for chunk in search_res.get("results", []):
            doc_id = chunk.get("doc_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs.add(doc_id)
                retrieved_docs.append(doc_id)
                if len(retrieved_docs) >= limit:
                    break
        return retrieved_docs
    except Exception as e:
        print(f"⚠️ Hybrid Search Error: {e}")
        return []

def evaluate(method_name: str, search_fn, gold_data: list) -> dict:
    print(f"\n🔍 Đang đánh giá phương pháp: {method_name}...")
    
    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    hits_at_10 = 0
    rrs = []
    latencies = []
    
    total = len(gold_data)
    
    for idx, item in enumerate(gold_data):
        query = item["question"]
        gt_ids = item["gt_doc_ids"]
        
        # Đo latency
        start_time = time.time()
        retrieved = search_fn(query, 10)
        latency = (time.time() - start_time) * 1000 # ms
        latencies.append(latency)
        
        # Tính toán các chỉ số
        hit_1 = any(gt in retrieved[:1] for gt in gt_ids)
        hit_3 = any(gt in retrieved[:3] for gt in gt_ids)
        hit_5 = any(gt in retrieved[:5] for gt in gt_ids)
        hit_10 = any(gt in retrieved[:10] for gt in gt_ids)
        
        if hit_1: hits_at_1 += 1
        if hit_3: hits_at_3 += 1
        if hit_5: hits_at_5 += 1
        if hit_10: hits_at_10 += 1
        
        rr = 0.0
        for rank, doc_id in enumerate(retrieved):
            if doc_id in gt_ids:
                rr = 1.0 / (rank + 1)
                break
        rrs.append(rr)
        
        if (idx + 1) % 50 == 0 or idx == total - 1:
            hr10 = (hits_at_10 / (idx + 1)) * 100
            avg_l = sum(latencies) / len(latencies)
            sys.stdout.write(f"\r   Progress: [{idx+1}/{total}] | Hit@10: {hr10:.1f}% | Avg Latency: {avg_l:.1f}ms")
            sys.stdout.flush()
            
    print()
    return {
        "hit@1": (hits_at_1 / total) * 100,
        "hit@3": (hits_at_3 / total) * 100,
        "hit@5": (hits_at_5 / total) * 100,
        "hit@10": (hits_at_10 / total) * 100,
        "mrr": sum(rrs) / len(rrs) if rrs else 0.0,
        "latency": sum(latencies) / len(latencies)
    }

def main():
    print("=" * 60)
    print("🧪 BENCHMARK SEARCH QUALITY ON 500 GOLD LEGAL QUESTIONS")
    print("=" * 60)
    
    if not os.path.exists(GOLD_INPUT):
        print(f"❌ Error: Không tìm thấy file {GOLD_INPUT}. Vui lòng tạo nó trước.")
        sys.exit(1)
        
    with open(GOLD_INPUT, "r", encoding="utf-8") as f:
        gold_data = json.load(f)
        
    print(f"📥 Loaded {len(gold_data)} gold questions with verified Ground Truth.")
    
    print("📦 Loading models, FAISS và Reranker...")
    get_smart_search_resources()
    print("✅ System Ready.\n")
    
    # Chạy lần lượt các phương pháp
    fts_doc_metrics = evaluate("1. Document-level FTS5 (Baseline)", run_document_fts, gold_data)
    fts_chunk_metrics = evaluate("2. Chunk-level FTS5 (Phase 1)", run_chunk_fts, gold_data)
    hybrid_metrics = evaluate("3. Hybrid Search (Vector 1.55M + FTS5 + RRF + Boosting + Rerank)", run_hybrid_search, gold_data)
    
    # In bảng kết quả so sánh chi tiết
    print("\n" + "=" * 85)
    print("📊 BẢNG KẾT QUẢ SO SÁNH BENCHMARK CHI TIẾT (500 CÂU HỎI VÀNG)")
    print("=" * 85)
    print(f"{'Phương Pháp Tìm Kiếm':<45} {'Hit@1':>8} {'Hit@3':>8} {'Hit@5':>8} {'Hit@10':>8} {'MRR@10':>8} {'Latency':>10}")
    print("-" * 97)
    
    print(f"{'Document-level FTS5 (Baseline)':<45} "
          f"{fts_doc_metrics['hit@1']:>7.1f}% "
          f"{fts_doc_metrics['hit@3']:>7.1f}% "
          f"{fts_doc_metrics['hit@5']:>7.1f}% "
          f"{fts_doc_metrics['hit@10']:>7.1f}% "
          f"{fts_doc_metrics['mrr']:>8.3f} "
          f"{fts_doc_metrics['latency']:>8.1f}ms")
          
    print(f"{'Chunk-level FTS5 (Phase 1)':<45} "
          f"{fts_chunk_metrics['hit@1']:>7.1f}% "
          f"{fts_chunk_metrics['hit@3']:>7.1f}% "
          f"{fts_chunk_metrics['hit@5']:>7.1f}% "
          f"{fts_chunk_metrics['hit@10']:>7.1f}% "
          f"{fts_chunk_metrics['mrr']:>8.3f} "
          f"{fts_chunk_metrics['latency']:>8.1f}ms")
          
    print(f"{'Hybrid Search (Vector 1.55M + RRF + Rerank)':<45} "
          f"{hybrid_metrics['hit@1']:>7.1f}% "
          f"{hybrid_metrics['hit@3']:>7.1f}% "
          f"{hybrid_metrics['hit@5']:>7.1f}% "
          f"{hybrid_metrics['hit@10']:>7.1f}% "
          f"{hybrid_metrics['mrr']:>8.3f} "
          f"{hybrid_metrics['latency']:>8.1f}ms")
          
    print("-" * 97)
    print("=" * 85)
    
    # Tính toán độ cải thiện
    improvement_hit10 = hybrid_metrics['hit@10'] - fts_doc_metrics['hit@10']
    improvement_mrr = hybrid_metrics['mrr'] - fts_doc_metrics['mrr']
    print(f"\n💡 Đánh giá hiệu quả cải tiến:")
    print(f"  • Độ phủ chính xác tìm kiếm tài liệu (Hit@10) tăng: {improvement_hit10:>+5.1f}% so với FTS5 thô.")
    print(f"  • Điểm thứ hạng liên quan (MRR@10) cải thiện: {improvement_mrr:>+5.3f} điểm.")
    print(f"  • Nhờ sự kết hợp của 1.55 triệu vector ngữ nghĩa, RRF Boosting và Reranker cục bộ,")
    print(f"    hệ thống có khả năng truy xuất chính xác vượt trội đối với các câu hỏi tự nhiên thực tế.")

if __name__ == "__main__":
    main()
