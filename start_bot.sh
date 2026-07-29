#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Script khởi động DataLuatVN Backend Server & Telegram Bot Lan Anh
# ══════════════════════════════════════════════════════════════

echo "🛑 Đang dừng các tiến trình cũ (nếu có)..."
pkill -f "telegram_bot.py" 2>/dev/null
pkill -f "server.py" 2>/dev/null
sleep 2

mkdir -p logs

echo "🚀 Đang khởi động Backend Server (server.py) trên cổng 2004..."
nohup python3 server.py > logs/server.log 2>&1 &
sleep 3

echo "🚀 Đang khởi động Telegram Bot (telegram_bot.py)..."
nohup python3 telegram_bot.py > logs/telegram_bot.log 2>&1 &
sleep 2

echo "✅ Hoàn tất! Hệ thống DataLuatVN & Bot Lan Anh (@LanAnh_lawbot) đang hoạt động ngầm."
