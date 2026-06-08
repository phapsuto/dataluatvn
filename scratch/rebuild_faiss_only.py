#!/usr/bin/env python3
import sqlite3
import numpy as np
import faiss
import os
import sys
import time

VECTOR_DB = "vector_store.db"
FAISS_INDEX_FILE = "chunks_faiss.index"
LOAD_CHUNK_SIZE = 50000
DIMENSION = 768

def main():
    print("🚀 Bắt đầu tiến trình xây dựng lại FAISS Index từ vector_store.db...", flush=True)
    
    if not os.path.exists(VECTOR_DB):
        print(f"❌ Không tìm thấy database chứa vector cache: {VECTOR_DB}", flush=True)
        sys.exit(1)
        
    print(f"📂 Đang kết nối tới database vector: {VECTOR_DB}", flush=True)
    v_conn = sqlite3.connect(VECTOR_DB)
    v_cursor = v_conn.cursor()
    
    # Đếm tổng số vector trong DB
    v_cursor.execute("SELECT COUNT(*) FROM chunk_vectors")
    total_vectors = v_cursor.fetchone()[0]
    print(f"📊 Tổng số vectors tìm thấy trong database: {total_vectors:,}", flush=True)
    
    if total_vectors == 0:
        print("❌ Không có vector nào trong database để xây dựng index.", flush=True)
        v_conn.close()
        sys.exit(1)
        
    # Xóa file index cũ nếu có để tránh ghi đè lỗi hoặc tăng dung lượng không cần thiết
    if os.path.exists(FAISS_INDEX_FILE):
        print(f"🗑️ Đã phát hiện và xóa file index cũ: {FAISS_INDEX_FILE}", flush=True)
        try:
            os.remove(FAISS_INDEX_FILE)
        except Exception as e:
            print(f"⚠️ Không thể xóa file index cũ: {e}", flush=True)

    print("🏗️ Khởi tạo chỉ mục FAISS (IndexFlatIP + IndexIDMap)...", flush=True)
    quantizer = faiss.IndexFlatIP(DIMENSION)
    index = faiss.IndexIDMap(quantizer)
    
    # Query đọc tuần tự tất cả vector
    v_cursor.execute("SELECT chunk_id, vector FROM chunk_vectors ORDER BY chunk_id ASC")
    
    count = 0
    start_time = time.time()
    
    while True:
        rows = v_cursor.fetchmany(LOAD_CHUNK_SIZE)
        if not rows:
            break
            
        chunk_ids = []
        vectors_list = []
        
        for row in rows:
            cid, vec_bytes = row
            # Chuyển BLOB thành numpy array
            vec = np.frombuffer(vec_bytes, dtype=np.float32)
            chunk_ids.append(cid)
            vectors_list.append(vec)
            
        # Chuyển đổi thành các ma trận numpy
        xb = np.vstack(vectors_list).astype(np.float32)
        ids = np.array(chunk_ids, dtype=np.int64)
        
        # L2 normalize để tính cosine similarity bằng IndexFlatIP
        faiss.normalize_L2(xb)
        
        # Thêm vào index
        index.add_with_ids(xb, ids)
        count += len(rows)
        
        elapsed = time.time() - start_time
        speed = count / elapsed if elapsed > 0 else 0
        progress = (count / total_vectors) * 100 if total_vectors > 0 else 0
        print(f"📥 Đã nạp {count:,}/{total_vectors:,} vectors vào FAISS ({progress:.2f}%) | Tốc độ: {speed:.1f} vectors/s", flush=True)
        
    v_conn.close()
    
    if index.ntotal > 0:
        print(f"💾 Đang ghi FAISS index xuống file: {FAISS_INDEX_FILE} (với {index.ntotal:,} vectors)", flush=True)
        faiss.write_index(index, FAISS_INDEX_FILE)
        
        # Kiểm tra dung lượng file index sau khi ghi
        file_size_gb = os.path.getsize(FAISS_INDEX_FILE) / (1024 * 1024 * 1024)
        print(f"🎉 Xây dựng thành công FAISS Index!", flush=True)
        print(f"📁 Đường dẫn file: {os.path.abspath(FAISS_INDEX_FILE)}", flush=True)
        print(f"⚖️ Dung lượng file: {file_size_gb:.2f} GB", flush=True)
    else:
        print("❌ Lỗi: Chỉ mục FAISS rỗng sau khi quét DB.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
