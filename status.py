#!/usr/bin/env python3
"""
Hệ thống giám sát trạng thái (Status Dashboard) cho luatvietnam.
Giúp lập trình viên nhanh chóng khôi phục ngữ cảnh (state) mà không bị "tràn bộ nhớ".
"""

import os
import sys
import time
import json
import sqlite3
import socket
import subprocess
from datetime import datetime

# ANSI Color Codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"
GRAY = "\033[90m"

CHECKPOINT_FILE = ".status_checkpoint.json"
MAIN_DB = "vietnamese_legal_documents.db"
VECTOR_DB = "vector_store.db"
FAISS_INDEX = "chunks_faiss.index"
API_PORT = 2004

def get_db_count(db_path, query, params=()):
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0

def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except Exception:
            return False

def get_process_status(script_name):
    try:
        output = subprocess.check_output(["ps", "-ef"]).decode("utf-8")
        for line in output.splitlines():
            if script_name in line and "grep" not in line:
                parts = line.strip().split()
                # ps -ef thường in PID ở cột thứ 2 (chỉ số 1)
                pid = parts[1]
                return f"{GREEN}ĐANG CHẠY (PID: {pid}){RESET}"
        return f"{RED}ĐÃ DỪNG{RESET}"
    except Exception:
        return f"{GRAY}KHÔNG RÕ{RESET}"

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def get_file_info(filepath):
    if not os.path.exists(filepath):
        return f"{RED}Không tồn tại{RESET}"
    size = os.path.getsize(filepath)
    mtime = os.path.getmtime(filepath)
    mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    return f"{GREEN}OK{RESET} ({format_size(size)}, {mtime_str})"

def main():
    print(f"\n{BOLD}{CYAN}🔍 HỆ THỐNG GIÁM SÁT TRẠNG THÁI DỰ ÁN LUATVIETNAM{RESET}")
    print(f"{GRAY}Thời gian quét: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}\n")

    # 1. Đọc số liệu từ DB
    total_chunks = get_db_count(MAIN_DB, "SELECT count(*) FROM document_chunks")
    indexed_vectors = get_db_count(VECTOR_DB, "SELECT count(*) FROM chunk_vectors")
    
    pct = (indexed_vectors / total_chunks * 100) if total_chunks > 0 else 0
    
    now = time.time()
    speed_str = "Đang đo..."
    eta_str = "N/A"
    
    # Tính tốc độ tức thời qua checkpoint file
    checkpoint = {}
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                checkpoint = json.load(f)
        except Exception:
            pass
            
    if checkpoint and "time" in checkpoint and "vectors" in checkpoint:
        delta_t = now - checkpoint["time"]
        delta_v = indexed_vectors - checkpoint["vectors"]
        if delta_t > 1.0 and delta_v >= 0:
            speed = delta_v / delta_t
            if speed > 0:
                speed_str = f"{speed:.1f} chunks/s"
                remaining = total_chunks - indexed_vectors
                eta_sec = remaining / speed
                eta_hours = eta_sec / 3600
                eta_str = f"{eta_hours:.2f} giờ ({eta_sec/60:.1f} phút)"
            else:
                speed_str = "0.0 chunks/s (Tạm dừng)"
                eta_str = "Vô hạn"
        else:
            speed_str = checkpoint.get("last_speed", "Đang đo...")
            eta_str = checkpoint.get("last_eta", "N/A")
            
    # Ghi lại checkpoint
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({
            "time": now,
            "vectors": indexed_vectors,
            "last_speed": speed_str,
            "last_eta": eta_str
        }, f)

    # 2. Trạng thái dịch vụ & Tiến trình
    api_running = check_port(API_PORT)
    api_status = f"{GREEN}ĐANG LẮNG NGHE (Port {API_PORT}){RESET}" if api_running else f"{RED}OFFLINE (Port {API_PORT} không phản hồi){RESET}"
    
    build_process = get_process_status("build_vector_index.py")
    server_process = get_process_status("server.py")
    
    # 3. Thông tin files
    main_db_info = get_file_info(MAIN_DB)
    vector_db_info = get_file_info(VECTOR_DB)
    faiss_info = get_file_info(FAISS_INDEX)

    # Hiển thị giao diện Dashboard đẹp mắt
    print("┌────────────────────────────────────────────────────────────────────────┐")
    print(f"│  {BOLD}1. DỊCH VỤ & TIẾN TRÌNH NỀN (BACKGROUND TASKS){RESET}                         │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print(f"│  • FastAPI Server Status: {api_status.ljust(45)}│")
    print(f"│  • Process server.py:     {server_process.ljust(45)}│")
    print(f"│  • Process sinh Vector:   {build_process.ljust(45)}│")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print(f"│  {BOLD}2. TIẾN ĐỘ THỰC HIỆN VECTOR EMBEDDINGS (PHASE 2){RESET}                      │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    
    # Progress Bar
    bar_width = 30
    filled = int(pct / 100 * bar_width)
    bar = "█" * filled + "-" * (bar_width - filled)
    print(f"│  • Tiến độ: [{bar}] {pct:.2f}%".ljust(73) + "│")
    print(f"│  • Tổng document chunks:  {total_chunks:,}".ljust(73) + "│")
    print(f"│  • Vector đã sinh (cache): {indexed_vectors:,}".ljust(73) + "│")
    print(f"│  • Tốc độ tức thời:       {speed_str}".ljust(73) + "│")
    print(f"│  • Dự kiến hoàn thành:    {eta_str}".ljust(73) + "│")
    print("├────────────────────────────────────────────────────────────────────────┤")
    print(f"│  {BOLD}3. THÔNG TIN CƠ SỞ DỮ LIỆU & CHỈ MỤC{RESET}                                  │")
    print("├────────────────────────────────────────────────────────────────────────┤")
    
    def print_file_row(label, info_str):
        # Tính toán độ dài chuỗi sạch (không chứa mã màu ANSI) để căn lề chuẩn xác
        clean_info = info_str.replace(GREEN, "").replace(RED, "").replace(RESET, "")
        total_len = len(clean_info)
        spaces = 48 - total_len
        if spaces < 0:
            spaces = 0
        return f"│  • {label.ljust(15)}: {info_str}" + " " * spaces + "│"

    print(print_file_row("Database chính", main_db_info))
    print(print_file_row("Cache Vector", vector_db_info))
    print(print_file_row("Chỉ mục FAISS", faiss_info))
    print("└────────────────────────────────────────────────────────────────────────┘")

    # 4. Các lệnh hữu ích
    print(f"\n{BOLD}{YELLOW}🎯 ROADMAP TIẾP THEO & CÁC LỆNH NHANH{RESET}")
    print("──────────────────────────────────────────────────────────────────────────")
    print(f"{BLUE}1. Để theo dõi tiến độ sinh vector real-time:{RESET}")
    print(f"   python3 status.py  (chạy lại lệnh này sau vài giây)")
    print(f"{BLUE}2. Chạy test chức năng Boosting & Retrieval (Phase 3):{RESET}")
    print(f"   pytest scratch/test_smart_search_boosting.py -v")
    print(f"{BLUE}3. Chạy test chức năng Query Expansion (Phase 4):{RESET}")
    print(f"   python3 scratch/test_query_expansion.py")
    print(f"{BLUE}4. Chạy benchmark đo Recall@10 (Đảm bảo set các biến môi trường đơn luồng để tránh crash):{RESET}")
    print(f"   OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 python3 scratch/benchmark_phase2.py")
    print("──────────────────────────────────────────────────────────────────────────\n")

if __name__ == "__main__":
    main()
