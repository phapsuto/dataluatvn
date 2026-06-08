#!/usr/bin/env python3
"""
GĐ2-HĐ1: Tạo vector embeddings cho các document chunks và xây dựng FAISS index.
Thiết kế tối ưu I/O tuần tự: Đọc tuần tự bằng Range Scan (id > last_id) giúp tận dụng cache đĩa,
giải quyết triệt để nghẽn cổ chai I/O SSD và khôi phục tốc độ sinh vector lên tối đa (~56 chunks/s).
"""

import sqlite3
import numpy as np
import torch
import faiss
import os
import sys
import argparse
import time
from sentence_transformers import SentenceTransformer

MAIN_DB = "vietnamese_legal_documents.db"
VECTOR_DB = "vector_store.db"
FAISS_INDEX_FILE = "chunks_faiss.index"
MODEL_NAME = "bkai-foundation-models/vietnamese-bi-encoder"
BATCH_SIZE = 256
LOAD_CHUNK_SIZE = 20000  # Đọc 20,000 dòng tuần tự mỗi lần để tối ưu bộ đệm SSD

def init_vector_db():
    conn = sqlite3.connect(VECTOR_DB)
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
    parser = argparse.ArgumentParser(description="Build Vector Index for Legal Document Chunks")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng chunks để chạy thử")
    parser.add_argument("--reset", action="store_true", help="Xóa cache vectors cũ và build lại từ đầu")
    args = parser.parse_args()

    if args.reset:
        if os.path.exists(VECTOR_DB):
            os.remove(VECTOR_DB)
            print(f"🗑️ Đã xóa cache vectors cũ ({VECTOR_DB})")
        if os.path.exists(FAISS_INDEX_FILE):
            os.remove(FAISS_INDEX_FILE)
            print(f"🗑️ Đã xóa FAISS index cũ ({FAISS_INDEX_FILE})")

    # Khởi tạo DB cache vector
    init_vector_db().close()

    # 1. Tìm ID lớn nhất đã được xử lý để checkpoint tuần tự
    v_conn = sqlite3.connect(VECTOR_DB)
    v_cursor = v_conn.cursor()
    v_cursor.execute("SELECT MAX(chunk_id) FROM chunk_vectors")
    last_id = v_cursor.fetchone()[0] or 0
    v_conn.close()

    # 2. Đếm số lượng chunks còn lại từ mốc last_id
    if not os.path.exists(MAIN_DB):
        print(f"❌ Không tìm thấy database chính: {MAIN_DB}")
        sys.exit(1)
        
    m_conn = sqlite3.connect(MAIN_DB)
    m_cursor = m_conn.cursor()
    
    count_query = "SELECT count(*) FROM document_chunks WHERE id > ?"
    m_cursor.execute(count_query, (last_id,))
    total_pending = m_cursor.fetchone()[0]
    
    if args.limit and total_pending > args.limit:
        total_pending = args.limit

    print(f"📊 Mốc ID lớn nhất đã xử lý trước đó: {last_id}")
    print(f"⚡ Số lượng chunks cần sinh vector mới tuần tự: {total_pending}")

    if total_pending > 0:
        device = get_device()
        print(f"🤖 Khởi tạo mô hình {MODEL_NAME} trên thiết bị: {device.upper()}")
        
        # Load model với sentence-transformers
        model = SentenceTransformer(MODEL_NAME, device=device)
        print("✅ Load model thành công.")

        # Query đọc tuần tự cực nhanh nhờ Index Range Scan trên SQLite chính
        select_query = "SELECT id, chunk_with_meta FROM document_chunks WHERE id > ? ORDER BY id ASC"
        if args.limit:
            select_query += f" LIMIT {args.limit}"
            
        m_cursor.execute(select_query, (last_id,))

        start_time = time.time()
        processed = 0
        
        # Kết nối ghi vector với cấu hình WAL tối ưu tốc độ ghi
        w_conn = sqlite3.connect(VECTOR_DB)
        w_cursor = w_conn.cursor()
        w_cursor.execute("PRAGMA journal_mode=WAL")
        w_cursor.execute("PRAGMA synchronous=NORMAL")

        # Đọc dữ liệu theo lô tuần tự bằng fetchmany
        while True:
            batch = m_cursor.fetchmany(LOAD_CHUNK_SIZE)
            if not batch:
                break
                
            # Chia nhỏ lô thành các batch để nạp PyTorch sinh embedding
            for i in range(0, len(batch), BATCH_SIZE):
                sub_batch = batch[i:i + BATCH_SIZE]
                batch_ids = [row[0] for row in sub_batch]
                batch_texts = [row[1] for row in sub_batch]

                # Sinh vector
                embeddings = model.encode(
                    batch_texts, 
                    batch_size=len(batch_texts), 
                    show_progress_bar=False, 
                    convert_to_numpy=True
                )

                # Insert vào DB cache
                insert_data = [(cid, emb.tobytes()) for cid, emb in zip(batch_ids, embeddings)]
                w_cursor.executemany(
                    "INSERT OR REPLACE INTO chunk_vectors (chunk_id, vector) VALUES (?, ?)",
                    insert_data
                )
                w_conn.commit()

                processed += len(batch_ids)
                elapsed = time.time() - start_time
                speed = processed / elapsed if elapsed > 0 else 0
                eta = (total_pending - processed) / speed if speed > 0 else 0
                
                if processed % (BATCH_SIZE * 4) == 0 or processed == total_pending:
                    print(f"⚙️ Tiến độ: {processed}/{total_pending} ({processed/total_pending*100:.1f}%) | "
                          f"Tốc độ: {speed:.1f} chunks/s | ETA: {eta/60:.1f} phút")

        w_conn.close()

    m_conn.close()

    # Xây dựng FAISS Index từ toàn bộ vector đã cache
    print("\n📦 Đang khởi tạo và xây dựng FAISS Index...")
    v_conn = sqlite3.connect(VECTOR_DB)
    v_cursor = v_conn.cursor()

    quantizer = None
    index = None
    dimension = 768
    count = 0

    # Đọc tuần tự toàn bộ vector từ cache ra theo lô 50,000 dòng
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

        # Trực quan hóa ma trận
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
        print(f"💾 Đang lưu FAISS index vào file: {FAISS_INDEX_FILE}")
        faiss.write_index(index, FAISS_INDEX_FILE)
        print(f"🎉 Đã xây dựng xong chỉ mục FAISS với {index.ntotal} vectors!")
        
        # Xây dựng đồ thị tri thức bổ trợ
        build_document_graph(limit=args.limit)
    else:
        print("❌ Không tìm thấy vector nào để xây dựng chỉ mục.")

def build_document_graph(limit=None):
    from app.utils.light_graph_manager import LightGraphManager
    from app.config import CONTENT_DB
    
    print("\n🕸️  Đang xây dựng Đồ thị tri thức pháp lý (Light Graph Store)...")
    LightGraphManager.init_db()
    
    conn = sqlite3.connect(MAIN_DB)
    conn.execute(f"ATTACH DATABASE '{CONTENT_DB}' AS content_db")
    cursor = conn.cursor()
    
    query = """
        SELECT d.id, d.title, d.so_ky_hieu, c.content_html 
        FROM documents d
        JOIN content_db.document_content c ON d.id = c.doc_id
    """
    if limit:
        query += f" LIMIT {limit}"
        
    try:
        cursor.execute(query)
        processed = 0
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for row in rows:
                doc_id, title, so_ky_hieu, content_html = row
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content_html or "", "html.parser")
                text = soup.get_text()
                
                LightGraphManager.index_document_graph(doc_id, title or "", so_ky_hieu or "", text)
                processed += 1
                if processed % 5000 == 0:
                    print(f"  - Đã nạp {processed} văn bản vào đồ thị tri thức...")
        print(f"🎉 Đã hoàn thành xây dựng đồ thị tri thức cho {processed} văn bản!")
    except Exception as e:
        print(f"⚠️  Lỗi khi xây dựng đồ thị tri thức: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
