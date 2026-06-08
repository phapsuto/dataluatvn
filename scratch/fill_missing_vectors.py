#!/usr/bin/env python3
import sqlite3
import numpy as np
import torch
import faiss
import os
import sys
import time
from sentence_transformers import SentenceTransformer

MAIN_DB = "vietnamese_legal_documents.db"
VECTOR_DB = "vector_store.db"
FAISS_INDEX_FILE = "chunks_faiss.index"
MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
BATCH_SIZE = 256
DIMENSION = 768

def main():
    print("🚀 Bắt đầu quét các chunks chưa có vector embeddings...", flush=True)
    
    if not os.path.exists(MAIN_DB):
        print(f"❌ Không tìm thấy database chính: {MAIN_DB}", flush=True)
        sys.exit(1)
        
    if not os.path.exists(VECTOR_DB):
        print(f"❌ Không tìm thấy database vector cache: {VECTOR_DB}", flush=True)
        sys.exit(1)

    # Kết nối các DB
    m_conn = sqlite3.connect(MAIN_DB)
    m_cursor = m_conn.cursor()
    
    # Đính kèm vector_db vào main_db để truy vấn liên kết chéo nhanh chóng
    m_cursor.execute(f"ATTACH DATABASE '{VECTOR_DB}' AS v_db")
    
    print("🔍 Tìm các chunk_id chưa có vector...", flush=True)
    # Lấy danh sách các chunk_id chưa có vector
    query = """
        SELECT dc.id, dc.chunk_with_meta 
        FROM document_chunks dc
        LEFT JOIN v_db.chunk_vectors cv ON dc.id = cv.chunk_id
        WHERE cv.chunk_id IS NULL
        ORDER BY dc.id ASC
    """
    
    m_cursor.execute(query)
    missing_chunks = m_cursor.fetchall()
    total_missing = len(missing_chunks)
    
    print(f"📊 Số lượng chunks thiếu vector: {total_missing:,}", flush=True)
    
    if total_missing == 0:
        print("✅ Tuyệt vời! Đã đầy đủ 100% vectors. Không cần sinh thêm.", flush=True)
        m_conn.close()
        rebuild_faiss()
        return

    # Khởi tạo mô hình trên CPU để đảm bảo an toàn tuyệt đối, tránh lỗi crash MPS trên Mac
    device = "cpu"
    print(f"🤖 Khởi tạo mô hình {MODEL_NAME} trên thiết bị: {device.upper()}...", flush=True)
    start_init = time.time()
    model = SentenceTransformer(MODEL_NAME, device=device)
    print(f"✅ Load model thành công trong {time.time() - start_init:.2f} giây.", flush=True)

    # Mở kết nối ghi vector
    w_conn = sqlite3.connect(VECTOR_DB)
    w_cursor = w_conn.cursor()
    w_cursor.execute("PRAGMA journal_mode=WAL")
    w_cursor.execute("PRAGMA synchronous=NORMAL")

    print(f"⚡ Đang bắt đầu sinh vector cho {total_missing:,} chunks...", flush=True)
    start_time = time.time()
    processed = 0
    
    for i in range(0, total_missing, BATCH_SIZE):
        batch = missing_chunks[i:i + BATCH_SIZE]
        batch_ids = [row[0] for row in batch]
        batch_texts = [row[1] for row in batch]
        
        # Sinh embeddings
        embeddings = model.encode(
            batch_texts, 
            batch_size=len(batch_texts), 
            show_progress_bar=False, 
            convert_to_numpy=True
        )
        
        # Lưu vào cache DB
        insert_data = [(cid, emb.tobytes()) for cid, emb in zip(batch_ids, embeddings)]
        w_cursor.executemany(
            "INSERT OR REPLACE INTO chunk_vectors (chunk_id, vector) VALUES (?, ?)",
            insert_data
        )
        w_conn.commit()
        
        processed += len(batch_ids)
        elapsed = time.time() - start_time
        speed = processed / elapsed if elapsed > 0 else 0
        eta = (total_missing - processed) / speed if speed > 0 else 0
        
        print(f"⚙️ Tiến độ: {processed}/{total_missing} ({processed/total_missing*100:.2f}%) | Tốc độ: {speed:.1f} chunks/s | ETA: {eta/60:.2f} phút", flush=True)

    w_conn.close()
    m_conn.close()
    print(f"🎉 Đã hoàn thành sinh vector cho {processed} chunks thiếu!", flush=True)
    
    # Tiến hành xây dựng lại FAISS
    rebuild_faiss()

def rebuild_faiss():
    print("\n🏗️ Bắt đầu xây dựng lại FAISS Index từ vector_store.db...", flush=True)
    v_conn = sqlite3.connect(VECTOR_DB)
    v_cursor = v_conn.cursor()
    
    v_cursor.execute("SELECT COUNT(*) FROM chunk_vectors")
    total_vectors = v_cursor.fetchone()[0]
    print(f"📊 Tổng số vectors trong cache: {total_vectors:,}", flush=True)
    
    if os.path.exists(FAISS_INDEX_FILE):
        try:
            os.remove(FAISS_INDEX_FILE)
            print(f"🗑️ Đã xóa file index cũ: {FAISS_INDEX_FILE}", flush=True)
        except Exception as e:
            print(f"⚠️ Cảnh báo: Không thể xóa file index cũ: {e}", flush=True)
            
    quantizer = faiss.IndexFlatIP(DIMENSION)
    index = faiss.IndexIDMap(quantizer)
    
    v_cursor.execute("SELECT chunk_id, vector FROM chunk_vectors ORDER BY chunk_id ASC")
    
    count = 0
    LOAD_CHUNK_SIZE = 50000
    start_time = time.time()
    
    while True:
        rows = v_cursor.fetchmany(LOAD_CHUNK_SIZE)
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
        
        faiss.normalize_L2(xb)
        index.add_with_ids(xb, ids)
        count += len(rows)
        
        elapsed = time.time() - start_time
        speed = count / elapsed if elapsed > 0 else 0
        print(f"📥 Đã nạp {count:,}/{total_vectors:,} vectors vào FAISS | Tốc độ: {speed:.1f} vectors/s", flush=True)
        
    v_conn.close()
    
    if index.ntotal > 0:
        print(f"💾 Đang ghi FAISS index xuống file: {FAISS_INDEX_FILE}", flush=True)
        faiss.write_index(index, FAISS_INDEX_FILE)
        file_size_gb = os.path.getsize(FAISS_INDEX_FILE) / (1024 * 1024 * 1024)
        print(f"🎉 Hoàn thành xuất sắc FAISS Index! Kích thước file: {file_size_gb:.2f} GB ({index.ntotal:,} vectors)", flush=True)
    else:
        print("❌ Lỗi: Chỉ mục FAISS rỗng sau khi build.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
