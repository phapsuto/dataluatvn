#!/usr/bin/env python3
"""
Tiện ích xây dựng lại chỉ mục FAISS từ cache SQLite.
Hỗ trợ tạo cả 2 định dạng:
1. Chỉ mục Flat (Chính xác 100%, tốn nhiều RAM: ~6.3 GB)
2. Chỉ mục SQ8 (Lượng tử hóa 8-bit, tiết kiệm RAM: ~1.6 GB, tốc độ nhanh hơn, Recall hầu như không đổi)
"""

import os
import sys
import sqlite3
import time
import numpy as np
import faiss

# Thêm thư mục gốc vào path để import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import VECTOR_DB_SOTA, FAISS_INDEX_SOTA

def rebuild_indexes():
    db_path = VECTOR_DB_SOTA
    
    if not os.path.exists(db_path):
        print(f"❌ Không tìm thấy cache vector database tại: {db_path}")
        print("Vui lòng đảm bảo tiến trình sinh vector đang chạy hoặc đã hoàn thành.")
        sys.exit(1)
        
    print(f"📦 Đang kết nối tới database cache: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Đếm số lượng vector hiện có trong DB
    cursor.execute("SELECT COUNT(*) FROM chunk_vectors")
    total_vectors = cursor.fetchone()[0]
    print(f"📊 Tổng số vector đã cache trong DB: {total_vectors:,}")
    
    if total_vectors == 0:
        print("❌ Không có vector nào trong database để lập chỉ mục.")
        conn.close()
        sys.exit(1)
        
    dimension = 1024 # BGE-M3
    
    # --- PHẦN A: XÂY DỰNG CHỈ MỤC FLAT (MẶC ĐỊNH) ---
    print("\n🚀 [1/2] Xây dựng Chỉ mục Flat (Chính xác tuyệt đối)...")
    start_time = time.time()
    
    quantizer_flat = faiss.IndexFlatIP(dimension)
    index_flat = faiss.IndexIDMap(quantizer_flat)
    
    cursor.execute("SELECT chunk_id, vector FROM chunk_vectors ORDER BY chunk_id ASC")
    
    count = 0
    while True:
        rows = cursor.fetchmany(50000)
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
        
        # Chuẩn hóa L2 trước khi đưa vào IndexFlatIP (để tính Cosine Similarity bằng Inner Product)
        faiss.normalize_L2(xb)
        index_flat.add_with_ids(xb, ids)
        count += len(rows)
        print(f"  📥 Đã nạp {count:,} / {total_vectors:,} vectors vào chỉ mục Flat...")
        
    flat_file = FAISS_INDEX_SOTA
    # Đảm bảo không ghi đè nhầm nếu cấu hình file index đang trỏ tới bản SQ8
    if flat_file.endswith("_sq8.index"):
        flat_file = flat_file.replace("_sq8.index", ".index")
        
    print(f"💾 Đang lưu chỉ mục Flat vào: {flat_file}")
    faiss.write_index(index_flat, flat_file)
    print(f"✅ Hoàn thành xây dựng chỉ mục Flat trong {time.time() - start_time:.1f} giây!")
    
    # --- PHẦN B: XÂY DỰNG CHỈ MỤC SQ8 (TIẾT KIỆM RAM) ---
    print("\n🚀 [2/2] Xây dựng Chỉ mục SQ8 (Lượng tử hóa 8-bit tiết kiệm RAM)...")
    start_time = time.time()
    
    # Lấy mẫu tối đa 50,000 vectors để huấn luyện bộ lượng tử hóa
    print("  🏋️ Đang lấy mẫu 50,000 vectors để huấn luyện bộ lượng tử hóa SQ8...")
    cursor.execute("SELECT vector FROM chunk_vectors LIMIT 50000")
    sample_rows = cursor.fetchall()
    sample_list = [np.frombuffer(r[0], dtype=np.float32) for r in sample_rows]
    sample_xb = np.vstack(sample_list).astype(np.float32)
    faiss.normalize_L2(sample_xb)
    
    print("  🧠 Đang huấn luyện bộ lượng tử hóa SQ8...")
    quantizer_sq8 = faiss.IndexScalarQuantizer(dimension, faiss.ScalarQuantizer.QT_8bit, faiss.METRIC_INNER_PRODUCT)
    quantizer_sq8.train(sample_xb)
    index_sq8 = faiss.IndexIDMap(quantizer_sq8)
    
    # Nạp lại toàn bộ vector vào chỉ mục SQ8
    cursor.execute("SELECT chunk_id, vector FROM chunk_vectors ORDER BY chunk_id ASC")
    
    count = 0
    while True:
        rows = cursor.fetchmany(50000)
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
        index_sq8.add_with_ids(xb, ids)
        count += len(rows)
        print(f"  📥 Đã nạp {count:,} / {total_vectors:,} vectors vào chỉ mục SQ8...")
        
    sq8_file = flat_file.replace(".index", "_sq8.index")
    print(f"💾 Đang lưu chỉ mục SQ8 vào: {sq8_file}")
    faiss.write_index(index_sq8, sq8_file)
    print(f"✅ Hoàn thành xây dựng chỉ mục SQ8 trong {time.time() - start_time:.1f} giây!")
    
    conn.close()
    print("\n🎉 HỆ THỐNG ĐÃ TẠO XONG CẢ 2 BẢN CHỈ MỤC THÀNH CÔNG!")
    print(f"1. Chỉ mục Flat (Yêu cầu RAM server >= 12GB): {flat_file} (~6.3 GB)")
    print(f"2. Chỉ mục SQ8  (Yêu cầu RAM server >= 4GB) : {sq8_file} (~1.6 GB)")
    print("Anh có thể tùy chọn trỏ file cấu hình dự án tới 1 trong 2 file trên.")

if __name__ == "__main__":
    rebuild_indexes()
