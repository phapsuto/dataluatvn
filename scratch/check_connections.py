#!/usr/bin/env python3
import os
import sys
import json
import socket
import requests
import subprocess
from datetime import datetime

# Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API_PORT = int(os.environ.get("API_PORT", 2004))
LUATBOT_API_URL = f"http://localhost:{API_PORT}"
LUATBOT_API_KEY = os.environ.get("LUATBOT_API_KEY", "dlvn_testkey")

print("==================================================")
print("🔍 KIỂM TRA HỆ THỐNG KẾT NỐI TELEGRAM & API SERVER")
print("==================================================")
print(f"Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# 1. Kiểm tra biến môi trường
print("1. Kiểm tra Cấu hình & Biến môi trường:")
if TELEGRAM_BOT_TOKEN:
    masked_token = TELEGRAM_BOT_TOKEN[:10] + "..." + TELEGRAM_BOT_TOKEN[-5:]
    print(f"  - TELEGRAM_BOT_TOKEN: {masked_token} (Đã cấu hình)")
else:
    print("  - TELEGRAM_BOT_TOKEN: CHƯA CẤU HÌNH (Lỗi)")
print(f"  - LUATBOT_API_URL: {LUATBOT_API_URL}")
print(f"  - LUATBOT_API_KEY: {LUATBOT_API_KEY[:5]}...")

# 2. Kiểm tra tiến trình hệ thống
print("\n2. Kiểm tra các Tiến trình đang chạy:")
def get_pids(script_name):
    try:
        output = subprocess.check_output(["pgrep", "-f", script_name]).decode().strip()
        return [int(pid) for pid in output.split()]
    except Exception:
        return []

bot_pids = get_pids("telegram_bot.py")
server_pids = get_pids("server.py")

if bot_pids:
    print(f"  - telegram_bot.py: ĐANG CHẠY (PIDs: {bot_pids})")
else:
    print("  - telegram_bot.py: ĐÃ DỪNG (Lỗi)")

if server_pids:
    print(f"  - server.py: ĐANG CHẠY (PIDs: {server_pids})")
else:
    print("  - server.py: ĐÃ DỪNG (Lỗi)")

# 3. Kiểm tra Port 2004 & 12005 (Socket lock)
print("\n3. Kiểm tra các cổng kết nối (Ports):")
def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except Exception:
            return False

print(f"  - Port {API_PORT} (FastAPI Server): {'MỞ (Đang lắng nghe)' if is_port_open(API_PORT) else 'ĐÓNG (Offline)'}")
print(f"  - Port 12005 (Telegram Socket Lock): {'MỞ (Bot đang chạy)' if is_port_open(12005) else 'ĐÓNG (Chưa khóa)'}")

# 4. Kiểm tra Kết nối API Telegram
print("\n4. Kiểm tra kết nối tới Telegram API:")
if TELEGRAM_BOT_TOKEN:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            res = resp.json()
            if res.get("ok"):
                bot_info = res["result"]
                print(f"  - Kết nối Telegram API: THÀNH CÔNG")
                print(f"  - Username Bot: @{bot_info.get('username')}")
                print(f"  - Tên Bot: {bot_info.get('first_name')}")
            else:
                print(f"  - Lỗi phản hồi từ Telegram: {res}")
        else:
            print(f"  - Lỗi kết nối HTTP {resp.status_code}")
    except Exception as e:
        print(f"  - Không thể kết nối tới Telegram API: {e}")
else:
    print("  - Bỏ qua kiểm tra Telegram (thiếu Token)")

# 5. Kiểm tra Kết nối LuatBot API Server
print("\n5. Kiểm tra kết nối tới LuatBot API Server:")
try:
    resp = requests.get(f"{LUATBOT_API_URL}/", timeout=5)
    if resp.status_code == 200:
        res = resp.json()
        print("  - Kết nối API Server: THÀNH CÔNG")
        print(f"  - Trạng thái Server: {res.get('status')}")
        print(f"  - Số tài liệu đã tải: {res.get('total_documents_loaded', 0):,}")
    else:
        print(f"  - Lỗi kết nối API Server HTTP {resp.status_code}")
except Exception as e:
    print(f"  - Không thể kết nối tới API Server: {e}")

# 6. Kiểm tra cấu hình đồng bộ (Sync config)
print("\n6. Kiểm tra trạng thái Đồng bộ (Sync):")
sync_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".telegram_sync.json")
if os.path.exists(sync_path):
    try:
        with open(sync_path, "r") as f:
            sync_data = json.load(f)
        print(f"  - Trạng thái đồng bộ: {'BẬT (Enabled)' if sync_data.get('sync_enabled') else 'TẮT (Disabled)'}")
        print(f"  - Chat ID đồng bộ: {sync_data.get('chat_id')}")
        print(f"  - Conversation ID: {sync_data.get('conversation_id')}")
    except Exception as e:
        print(f"  - Lỗi đọc file cấu hình đồng bộ: {e}")
else:
    print("  - File cấu hình đồng bộ .telegram_sync.json không tồn tại")

print("==================================================")
