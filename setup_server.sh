#!/bin/bash
# ══════════════════════════════════════════════════════════════
# 🚀 DataLuatVN — Setup Script cho Vultr Ubuntu 22.04
# Chạy: bash setup_server.sh
# ══════════════════════════════════════════════════════════════

set -e  # Dừng ngay nếu có lỗi

echo "═══════════════════════════════════════════════"
echo "🚀 SETUP DATALUATVN SERVER"
echo "═══════════════════════════════════════════════"

# ─── 1. Update Ubuntu ───
echo ""
echo "📦 [1/8] Update hệ thống..."
sudo apt update && sudo apt upgrade -y

# ─── 2. Cài Python 3.11 + tools ───
echo ""
echo "🐍 [2/8] Cài Python 3.11 + Nginx + tools..."
sudo apt install -y python3.11 python3.11-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    xvfb curl git htop ufw rsync

# Cài thêm deps cho Playwright/Chromium
sudo apt install -y --no-install-recommends \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    fonts-liberation fonts-noto-cjk

# ─── 3. Tạo user riêng ───
echo ""
echo "👤 [3/8] Tạo user dataluat..."
if ! id "dataluat" &>/dev/null; then
    sudo useradd -m -s /bin/bash dataluat
    echo "   ✅ User dataluat đã tạo"
else
    echo "   ⏭️ User dataluat đã tồn tại"
fi

# ─── 4. Clone project ───
echo ""
echo "📂 [4/8] Clone project..."
sudo -u dataluat bash -c '
cd /home/dataluat
if [ ! -d "dataluatvn" ]; then
    echo "   Nhập Git repo URL:"
    read -r REPO_URL
    git clone "$REPO_URL" dataluatvn
else
    echo "   ⏭️ Thư mục dataluatvn đã tồn tại, git pull..."
    cd dataluatvn && git pull
fi
'

# ─── 5. Python venv + dependencies ───
echo ""
echo "📦 [5/8] Cài Python dependencies..."
sudo -u dataluat bash -c '
cd /home/dataluat/dataluatvn
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install playwright
playwright install chromium
playwright install-deps chromium
'

# ─── 6. Tạo .env ───
echo ""
echo "⚙️ [6/8] Tạo file .env..."
if [ ! -f /home/dataluat/dataluatvn/.env ]; then
    JWT_SECRET=$(openssl rand -hex 32)
    sudo -u dataluat bash -c "cat > /home/dataluat/dataluatvn/.env << EOF
API_PORT=2004
DB_PATH=vietnamese_legal_documents.db
CONTENT_DB_PATH=content_store.db
ADMIN_DB_PATH=admin.db
JWT_SECRET=${JWT_SECRET}
EOF"
    echo "   ✅ .env đã tạo (JWT_SECRET random)"
else
    echo "   ⏭️ .env đã tồn tại"
fi

# ─── 7. Tạo thư mục logs ───
sudo -u dataluat mkdir -p /home/dataluat/dataluatvn/logs

# ─── 8. Tạo systemd service ───
echo ""
echo "🔧 [7/8] Tạo systemd service..."
sudo tee /etc/systemd/system/dataluat-api.service > /dev/null << 'EOF'
[Unit]
Description=DataLuatVN API Server
After=network.target

[Service]
Type=exec
User=dataluat
WorkingDirectory=/home/dataluat/dataluatvn
EnvironmentFile=/home/dataluat/dataluatvn/.env
ExecStart=/home/dataluat/dataluatvn/venv/bin/uvicorn server:app \
    --host 127.0.0.1 \
    --port 2004 \
    --workers 4 \
    --limit-concurrency 100 \
    --timeout-keep-alive 30
Restart=always
RestartSec=5
MemoryMax=4G
CPUQuota=300%

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable dataluat-api
echo "   ✅ Service dataluat-api đã tạo"

# ─── 9. Tạo Nginx config ───
echo ""
echo "🌐 [8/8] Tạo Nginx config..."
sudo tee /etc/nginx/sites-available/dataluat > /dev/null << 'NGINX'
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;

server {
    listen 80;
    server_name _;

    limit_req zone=api burst=50 nodelay;

    gzip on;
    gzip_types application/json text/html text/plain text/css;
    gzip_min_length 500;
    gzip_comp_level 6;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:2004;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_read_timeout 30s;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/dataluat /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
echo "   ✅ Nginx đã config"

# ─── 10. Firewall ───
echo ""
echo "🔒 Cấu hình firewall..."
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
echo "   ✅ Firewall đã bật"

# ─── 11. Tạo crawler script ───
sudo -u dataluat tee /home/dataluat/dataluatvn/run_crawler.sh > /dev/null << 'SCRIPT'
#!/bin/bash
cd /home/dataluat/dataluatvn
source venv/bin/activate

MODE="${1:-sync}"
LIMIT="${2:-}"

export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 -ac &
XVFB_PID=$!
sleep 1

echo "🖥️ Xvfb started (PID: $XVFB_PID)"
unset CRAWLER_HEADLESS

if [ "$MODE" = "sync" ]; then
    SYNC_PAGES=${LIMIT:-5} python3 sync_new_laws.py
elif [ "$MODE" = "fill" ]; then
    if [ -n "$LIMIT" ]; then
        CRAWLER_TABS=5 python3 fill_missing_content.py $LIMIT
    else
        CRAWLER_TABS=5 python3 fill_missing_content.py
    fi
fi

kill $XVFB_PID 2>/dev/null
echo "✅ Done"
SCRIPT
sudo -u dataluat chmod +x /home/dataluat/dataluatvn/run_crawler.sh

echo ""
echo "═══════════════════════════════════════════════"
echo "✅ SETUP HOÀN TẤT!"
echo "═══════════════════════════════════════════════"
echo ""
echo "📋 BƯỚC TIẾP THEO (phải làm thủ công):"
echo ""
echo "1️⃣  Upload DB files từ Mac:"
echo "   rsync -avz --progress vietnamese_legal_documents.db root@YOUR_SERVER_IP:/home/dataluat/dataluatvn/"
echo "   rsync -avz --progress content_store.db root@YOUR_SERVER_IP:/home/dataluat/dataluatvn/"
echo "   rsync -avz --progress admin.db root@YOUR_SERVER_IP:/home/dataluat/dataluatvn/"
echo ""
echo "2️⃣  Sau khi upload xong, fix ownership:"
echo "   sudo chown dataluat:dataluat /home/dataluat/dataluatvn/*.db"
echo ""
echo "3️⃣  Start API server:"
echo "   sudo systemctl start dataluat-api"
echo "   sudo systemctl status dataluat-api"
echo ""
echo "4️⃣  Test:"
echo "   curl http://localhost:2004/"
echo ""
echo "5️⃣  (Tùy chọn) SSL nếu có domain:"
echo "   sudo certbot --nginx -d YOUR_DOMAIN"
echo ""
