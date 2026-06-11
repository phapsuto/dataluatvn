#!/usr/bin/env python3
"""
Tiện ích xây dựng lại chỉ mục FAISS từ cache SQLite.
Hỗ trợ tạo các định dạng:
1. Chỉ mục Flat (Chính xác 100%, tốn nhiều RAM: ~6.3 GB)
2. Chỉ mục SQ8 (Lượng tử hóa 8-bit, tiết kiệm RAM: ~1.6 GB)
3. Chỉ mục IVF-SQ8 (Lượng tử hóa IVF 8-bit, siêu nhanh <20ms & tiết kiệm RAM: ~1.6 GB)
"""

import os
import sys
import sqlite3
import time
import argparse
import numpy as np
import faiss

# Thêm thư mục gốc vào path để import config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import VECTOR_DB_SOTA, FAISS_INDEX_SOTA

def rebuild_indexes(index_type="all"):
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
    
    # Định nghĩa các đường dẫn file index
    flat_file = FAISS_INDEX_SOTA
    if flat_file.endswith("_sq8.index"):
        flat_file = flat_file.replace("_sq8.index", ".index")
    elif flat_file.endswith("_ivf_sq8.index"):
        flat_file = flat_file.replace("_ivf_sq8.index", ".index")
        
    sq8_file = flat_file.replace(".index", "_sq8.index")
    ivf_sq8_file = flat_file.replace(".index", "_ivf_sq8.index")
    
    # --- PHẦN A: XÂY DỰNG CHỈ MỤC FLAT ---
    if index_type in ["flat", "all"]:
        print(f"\n🚀 Xây dựng Chỉ mục Flat (Chính xác tuyệt đối, lưu tại: {flat_file})...")
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
            
        print(f"💾 Đang lưu chỉ mục Flat vào: {flat_file}")
        faiss.write_index(index_flat, flat_file)
        print(f"✅ Hoàn thành xây dựng chỉ mục Flat trong {time.time() - start_time:.1f} giây!")
        
    # --- PHẦN B: XÂY DỰNG CHỈ MỤC SQ8 ---
    if index_type in ["sq8", "all"]:
        print(f"\n🚀 Xây dựng Chỉ mục SQ8 (Lượng tử hóa 8-bit Flat, lưu tại: {sq8_file})...")
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
            
        print(f"💾 Đang lưu chỉ mục SQ8 vào: {sq8_file}")
        faiss.write_index(index_sq8, sq8_file)
        print(f"✅ Hoàn thành xây dựng chỉ mục SQ8 trong {time.time() - start_time:.1f} giây!")
        
    # --- PHẦN C: XÂY DỰNG CHỈ MỤC IVF-SQ8 ---
    if index_type in ["ivf_sq8", "all"]:
        print(f"\n🚀 Xây dựng Chỉ mục IVF-SQ8 (Lượng tử hóa IVF 8-bit siêu tốc, lưu tại: {ivf_sq8_file})...")
        start_time = time.time()
        
        nlist = 2048  # Số phân vùng Voronoi (tối ưu cho 1.55 triệu vectors)
        train_samples = 120000 # Số lượng training points khuyến nghị cho nlist=2048 (~60x nlist)
        
        print(f"  🏋️ Đang lấy mẫu {train_samples:,} vectors để huấn luyện bộ phân vùng IVF-SQ8...")
        cursor.execute("SELECT vector FROM chunk_vectors LIMIT ?", (train_samples,))
        sample_rows = cursor.fetchall()
        sample_list = [np.frombuffer(r[0], dtype=np.float32) for r in sample_rows]
        sample_xb = np.vstack(sample_list).astype(np.float32)
        faiss.normalize_L2(sample_xb)
        
        print(f"  🧠 Đang huấn luyện chỉ mục IVF-SQ8 (nlist={nlist})...")
        coarse_quantizer = faiss.IndexFlatIP(dimension)
        index_ivf_sq8 = faiss.IndexIVFScalarQuantizer(
            coarse_quantizer, dimension, nlist, faiss.ScalarQuantizer.QT_8bit, faiss.METRIC_INNER_PRODUCT
        )
        index_ivf_sq8.train(sample_xb)
        
        # Nạp lại toàn bộ vector vào chỉ mục IVF-SQ8
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
            index_ivf_sq8.add_with_ids(xb, ids)
            count += len(rows)
            print(f"  📥 Đã nạp {count:,} / {total_vectors:,} vectors vào chỉ mục IVF-SQ8...")
            
        print(f"💾 Đang lưu chỉ mục IVF-SQ8 vào: {ivf_sq8_file}")
        faiss.write_index(index_ivf_sq8, ivf_sq8_file)
        print(f"✅ Hoàn thành xây dựng chỉ mục IVF-SQ8 trong {time.time() - start_time:.1f} giây!")
        
    conn.close()
    print("\n🎉 HỆ THỐNG ĐÃ HOÀN THÀNH XÂY DỰNG CHỈ MỤC THEO YÊU CẦU!")
    print(f"1. Chỉ mục Flat (RAM >= 12GB): {flat_file} (~6.3 GB)")
    print(f"2. Chỉ mục SQ8  (RAM >= 4GB) : {sq8_file} (~1.6 GB)")
    print(f"3. Chỉ mục IVF-SQ8 (RAM >= 4GB, Siêu nhanh): {ivf_sq8_file} (~1.6 GB)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild FAISS indexes from cache SQLite.")
    parser.add_argument(
        "--type", 
        type=str, 
        default="all", 
        choices=["flat", "sq8", "ivf_sq8", "all"], 
        help="Loại index muốn build (mặc định: all)"
    )
    args = parser.parse_args()
    rebuild_indexes(args.type)
