#!/usr/bin/env python3
"""
Lập chỉ mục Vector SOTA: Tạo vector embeddings bằng model BAAI/bge-m3 (1024 chiều)
và xây dựng FAISS index chunks_faiss_bgem3.index.
Hỗ trợ checkpoint an toàn thông qua SQLite vector_store_bgem3.db.
Tối ưu hóa tốc độ xử lý bằng cách tải toàn bộ chunks chưa xử lý, sắp xếp theo độ dài,
và mã hóa theo batch lớn trên MPS.
"""

import os
# Đặt biến môi trường đơn luồng để tránh lỗi crash bộ nhớ OpenMP trên macOS
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import sys
import sqlite3
import numpy as np
import torch
import faiss
import argparse
import time
from sentence_transformers import SentenceTransformer

# Thêm thư mục gốc vào path để import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import DB_NAME, VECTOR_DB_SOTA, FAISS_INDEX_SOTA, EMBEDDING_MODEL_SOTA

BATCH_SIZE = 128
COMMIT_INTERVAL = 10000

def init_vector_db():
    conn = sqlite3.connect(VECTOR_DB_SOTA)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunk_vectors (
            chunk_id INTEGER PRIMARY KEY,
            vector BLOB NOT NULL
        )
    """)
    conn.commit()
    return conn

def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

def main():
    parser = argparse.ArgumentParser(description="Build Optimized SOTA Vector Index")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng chunks để chạy thử")
    parser.add_argument("--reset", action="store_true", help="Xóa cache vectors cũ và build lại từ đầu")
    args = parser.parse_args()

    if args.reset:
        if os.path.exists(VECTOR_DB_SOTA):
            os.remove(VECTOR_DB_SOTA)
            print(f"🗑️ Đã xóa cache vectors cũ ({VECTOR_DB_SOTA})")
        if os.path.exists(FAISS_INDEX_SOTA):
            os.remove(FAISS_INDEX_SOTA)
            print(f"🗑️ Đã xóa FAISS index cũ ({FAISS_INDEX_SOTA})")

    # Khởi tạo DB cache vector
    init_vector_db().close()

    # 1. Kết nối và đếm số lượng chunks còn lại bằng LEFT JOIN để hỗ trợ thứ tự xáo trộn
    if not os.path.exists(DB_NAME):
        print(f"❌ Không tìm thấy database chính: {DB_NAME}")
        sys.exit(1)

    print("🔍 Đang truy vấn danh sách chunks cần xử lý...")
    m_conn = sqlite3.connect(DB_NAME)
    m_cursor = m_conn.cursor()
    
    # Gắn cơ sở dữ liệu cache vector để thực hiện JOIN xuyên suốt
    m_cursor.execute("ATTACH DATABASE ? AS cache", (VECTOR_DB_SOTA,))
    
    # Đếm số lượng chunks chưa có vector
    m_cursor.execute("""
        SELECT COUNT(*) 
        FROM document_chunks c 
        LEFT JOIN cache.chunk_vectors v ON c.id = v.chunk_id 
        WHERE v.chunk_id IS NULL
    """)
    total_pending = m_cursor.fetchone()[0]
    
    if args.limit and total_pending > args.limit:
        total_pending = args.limit

    print(f"⚡ Số lượng chunks cần sinh vector mới: {total_pending}")

    if total_pending > 0:
        device = get_device()
        print(f"🤖 Khởi tạo mô hình {EMBEDDING_MODEL_SOTA} trên thiết bị: {device.upper()}")
        
        # Load model BGE-M3 với float16 trên MPS
        model_kwargs = {"torch_dtype": torch.float16} if device == "mps" else {}
        model = SentenceTransformer(EMBEDDING_MODEL_SOTA, device=device, model_kwargs=model_kwargs)
        model.max_seq_length = 512
        print("✅ Load model thành công. max_seq_length = 512")

        # Tải tất cả dữ liệu chunks chưa xử lý lên bộ nhớ để sắp xếp tối ưu hóa
        print("📥 Đang tải văn bản chunks lên RAM...")
        select_query = """
            SELECT c.id, c.chunk_with_meta 
            FROM document_chunks c 
            LEFT JOIN cache.chunk_vectors v ON c.id = v.chunk_id 
            WHERE v.chunk_id IS NULL
        """
        if args.limit:
            select_query += f" LIMIT {args.limit}"
            
        m_cursor.execute(select_query)
        pending_chunks = m_cursor.fetchall()
        
        # Sắp xếp theo độ dài văn bản để tránh padding lãng phí bộ nhớ GPU
        print("⚖️ Đang sắp xếp chunks theo độ dài để tối ưu hóa hiệu năng batching...")
        pending_chunks.sort(key=lambda x: len(x[1] or ""))
        
        # Giải phóng kết nối m_conn trước để tránh lock DB
        m_conn.close()

        start_time = time.time()
        processed = 0
        
        # Kết nối ghi vector vào DB cache
        w_conn = sqlite3.connect(VECTOR_DB_SOTA)
        w_cursor = w_conn.cursor()
        w_cursor.execute("PRAGMA journal_mode=WAL")
        w_cursor.execute("PRAGMA synchronous=NORMAL")

        print(f"🚀 Bắt đầu sinh vector cho {len(pending_chunks)} chunks...")
        
        temp_batch_ids = []
        temp_batch_texts = []
        
        for idx, (cid, text) in enumerate(pending_chunks):
            # Trực quan hóa tiến độ bằng cách truncate outlier cực dài
            temp_batch_ids.append(cid)
            temp_batch_texts.append((text or "")[:4096])
            
            if len(temp_batch_ids) == BATCH_SIZE or idx == len(pending_chunks) - 1:
                # Sinh vector
                embeddings = model.encode(
                    temp_batch_texts, 
                    batch_size=len(temp_batch_texts), 
                    show_progress_bar=False, 
                    convert_to_numpy=True
                )
                embeddings = embeddings.astype(np.float32)
                
                # Insert vào DB cache
                insert_data = [(chunk_id, emb.tobytes()) for chunk_id, emb in zip(temp_batch_ids, embeddings)]
                w_cursor.executemany(
                    "INSERT OR REPLACE INTO chunk_vectors (chunk_id, vector) VALUES (?, ?)",
                    insert_data
                )
                
                processed += len(temp_batch_ids)
                
                # Commit định kỳ
                if processed % COMMIT_INTERVAL == 0 or idx == len(pending_chunks) - 1:
                    w_conn.commit()
                
                # Reset batch tạm thời
                temp_batch_ids = []
                temp_batch_texts = []
                
                # Log tiến trình
                if processed % 512 == 0 or processed == total_pending:
                    elapsed = time.time() - start_time
                    speed = processed / elapsed if elapsed > 0 else 0
                    eta = (total_pending - processed) / speed if speed > 0 else 0
                    print(f"⚙️ Tiến độ: {processed}/{total_pending} ({processed/total_pending*100:.1f}%) | "
                          f"Tốc độ: {speed:.1f} chunks/s | ETA: {eta/60:.1f} phút")
                          
        w_conn.close()
    else:
        m_conn.close()
        print("✅ Tất cả chunks đã được sinh vector trước đó.")

    # Xây dựng FAISS Index từ toàn bộ vector đã cache
    print("\n📦 Đang khởi tạo và xây dựng FAISS Index từ cơ sở dữ liệu cache...")
    v_conn = sqlite3.connect(VECTOR_DB_SOTA)
    v_cursor = v_conn.cursor()

    index = None
    dimension = 1024  # BGE-M3
    count = 0

    v_cursor.execute("SELECT chunk_id, vector FROM chunk_vectors ORDER BY chunk_id ASC")
    
    while True:
        rows = v_cursor.fetchmany(50000)
        if not rows:
            break
            
        chunk_ids = []
        vectors_list = []
        
        for row in rows:
            cid, vec_bytes = row
            vec = np.frombuffer(vec_bytes, dtype=np.float32)
            chunk_ids.append(cid)
            vectors_list.append(vec)

        xb = np.vstack(vectors_list).astype(np.float32)
        ids = np.array(chunk_ids, dtype=np.int64)

        # L2 normalize
        faiss.normalize_L2(xb)

        if index is None:
            quantizer = faiss.IndexFlatIP(dimension)
            index = faiss.IndexIDMap(quantizer)
        
        index.add_with_ids(xb, ids)
        count += len(rows)
        print(f"📥 Đã nạp {count} vectors vào chỉ mục FAISS...")

    v_conn.close()

    if index is not None and index.ntotal > 0:
        print(f"💾 Đang lưu FAISS index vào file: {FAISS_INDEX_SOTA}")
        faiss.write_index(index, FAISS_INDEX_SOTA)
        print(f"🎉 Đã xây dựng xong chỉ mục FAISS với {index.ntotal} vectors!")
    else:
        print("❌ Không tìm thấy vector nào để xây dựng chỉ mục.")

if __name__ == "__main__":
    main()
