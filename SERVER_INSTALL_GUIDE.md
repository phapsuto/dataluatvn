# ⚙️ HƯỚNG DẪN CẤU HÌNH VÀ CÀI ĐẶT MÁY CHỦ DATALUATVN API
*(Tài liệu chi tiết dành cho Kỹ sư Vận hành / Đồng nghiệp phụ trách hạ tầng)*

Tài liệu này hướng dẫn từng bước thiết lập hệ thống REST API dữ liệu luật Việt Nam (`dataluatvn`), cấu hình crawler tự động cập nhật, cấu hình Nginx Reverse Proxy bảo mật và tối ưu hóa hệ thống trên máy chủ Linux Ubuntu.

---

## 📂 Sơ Đồ Tổng Quan Hệ Thống

```
                           ┌──────────────────────────┐
                           │   Người Dùng / Chatbot   │
                           └─────────────┬────────────┘
                                         │ HTTPS (Cổng 443/80)
                                         ▼
                           ┌──────────────────────────┐
                           │   Nginx Reverse Proxy    │
                           └─────────────┬────────────┘
                                         │ HTTP Proxy (Cổng 2004)
                                         ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │                           Server FastAPI                             │
  │  - Quản trị viên điều khiển qua Dashboard: http://localhost:2004/admin│
  │  - API tài liệu phục vụ kết nối: http://localhost:2004/docs          │
  └──────────────┬────────────────────────────────────────┬──────────────┘
                 │ Đọc/Ghi dữ liệu                        │ Đọc/Ghi nội dung HTML
                 ▼                                        ▼
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│  vietnamese_legal_documents.db   │    │         content_store.db         │
│  (Database chính: FTS5, Meta)    │    │   (Database chứa HTML toàn văn)  │
└──────────────────────────────────┘    └──────────────────────────────────┘
```

---

## 🛠️ PHẦN I: YÊU CẦU HỆ THỐNG
*   **Hệ điều hành:** Ubuntu 20.04 LTS hoặc Ubuntu 22.04 LTS (Khuyên dùng).
*   **Cấu hình tối thiểu:** 1 vCPU, 2 GB RAM (nếu chạy thông thường). 
*   **Cấu hình khuyên dùng:** 2 vCPU, 4 GB RAM (để chạy crawler Playwright đa luồng mượt mà).
*   **Dung lượng đĩa:** Tối thiểu 10 GB trống (Database chính và DB nội dung chiếm khoảng 4 GB).

---

## 📥 PHẦN II: CÀI ĐẶT HỆ THỐNG TRÊN SERVER BẰNG COMMAND LINE

### 1. Cài đặt các gói phụ thuộc hệ thống
Chạy cập nhật Ubuntu và cài đặt Python 3.11, Nginx cùng các thư viện đồ họa để chạy trình duyệt ảo Playwright ngầm:
```bash
sudo apt update && sudo apt upgrade -y

# Cài đặt Python, Nginx, Certbot và các công cụ bổ trợ
sudo apt install -y python3.11 python3.11-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    xvfb curl git htop ufw rsync

# Cài đặt các thư viện cần thiết cho nhân Chromium của Playwright
sudo apt install -y --no-install-recommends \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    fonts-liberation fonts-noto-cjk
```

### 2. Tạo User vận hành riêng (Khuyên dùng)
Để bảo mật hệ thống, tránh chạy API server và crawler bằng tài khoản root:
```bash
sudo useradd -m -s /bin/bash dataluat
```

### 3. Tải mã nguồn dự án và cài đặt Virtual Environment
```bash
# Đăng nhập vào user dataluat
sudo -i -u dataluat

# Clone repo code từ GitHub (Nhập URL repository của anh)
git clone https://github.com/phapsuto/dataluatvn.git dataluatvn
cd dataluatvn

# Khởi tạo môi trường ảo Python
python3.11 -m venv venv
source venv/bin/activate

# Nâng cấp pip và cài đặt thư viện dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Cài đặt Playwright Browser và các thư viện hệ thống đi kèm
pip install playwright
playwright install chromium
playwright install-deps chromium
```

### 4. Cấu hình file Môi trường `.env`
Tạo file `.env` tại thư mục gốc `/home/dataluat/dataluatvn/.env` với cấu hình sau:
```ini
API_PORT=2004
DB_PATH=vietnamese_legal_documents.db
CONTENT_DB_PATH=content_store.db
ADMIN_DB_PATH=admin.db
# Khóa JWT bí mật để xác thực tài khoản Admin (tự sinh ngẫu nhiên)
JWT_SECRET=Thay_The_Bang_Chuoi_Random_32_Ky_Tu
```

---

## 🗄️ PHẦN III: KHỞI TẠO VÀ NÂNG CẤP DATABASE

### 1. Đồng bộ các file cơ sở dữ liệu có sẵn từ máy Local
Anh cần tải các tệp database (`.db`) hiện tại lên thư mục `/home/dataluat/dataluatvn/` trên server (sử dụng lệnh `rsync` hoặc `scp` từ máy local của anh):
```bash
# Thực hiện lệnh này trên máy Local của anh:
rsync -avz --progress vietnamese_legal_documents.db dataluat@YOUR_SERVER_IP:/home/dataluat/dataluatvn/
rsync -avz --progress content_store.db dataluat@YOUR_SERVER_IP:/home/dataluat/dataluatvn/
rsync -avz --progress admin.db dataluat@YOUR_SERVER_IP:/home/dataluat/dataluatvn/
```

### 2. Phân quyền tệp cơ sở dữ liệu trên Server
Đảm bảo quyền đọc/ghi database cho user `dataluat`:
```bash
sudo chown -R dataluat:dataluat /home/dataluat/dataluatvn/*.db
sudo chmod 664 /home/dataluat/dataluatvn/*.db
```

### 3. Chạy script nâng cấp cấu trúc Database
Chạy script để đảm bảo bảng dữ liệu chính được thêm cột `has_content` và đồng bộ chính xác với file lưu trữ nội dung `content_store.db`:
```bash
source venv/bin/activate
python3 upgrade_db.py
```

---

## ⚙️ PHẦN IV: CẤU HÌNH SYSTEMD VÀ NGINX REVERSE PROXY

### 1. Tạo Service tự khởi chạy FastAPI (`systemd`)
Tạo tệp service hệ thống tại `/etc/systemd/system/dataluat-api.service`:
```ini
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
    --limit-concurrency 200 \
    --timeout-keep-alive 30
Restart=always
RestartSec=5
MemoryMax=3G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```
Kích hoạt và khởi chạy API Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable dataluat-api
sudo systemctl start dataluat-api

# Kiểm tra trạng thái service hoạt động
sudo systemctl status dataluat-api
```

### 2. Cấu hình Nginx với giới hạn Rate-limiting chống DDoS
Tạo tệp cấu hình Nginx tại `/etc/nginx/sites-available/dataluat`:
```nginx
# Giới hạn yêu cầu tối đa 30 request/giây từ mỗi IP để bảo vệ API
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/s;

server {
    listen 80;
    server_name yourdomain.com; # Thay thế bằng domain thực tế của anh

    # Áp dụng giới hạn rate-limiting, hỗ trợ burst tối đa 50 requests
    limit_req zone=api burst=50 nodelay;

    # Cấu hình Gzip để nén JSON/HTML giảm dung lượng truyền tải mạng
    gzip on;
    gzip_types application/json text/html text/plain text/css text/javascript;
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
        
        # Tăng timeout để phục vụ các truy vấn search nặng
        proxy_connect_timeout 15s;
        proxy_read_timeout 60s;
    }
}
```
Kích hoạt cấu hình và restart Nginx:
```bash
sudo ln -sf /etc/nginx/sites-available/dataluat /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 3. Cài đặt SSL HTTPS miễn phí bằng Let's Encrypt
```bash
sudo certbot --nginx -d yourdomain.com
```

---

## ⏰ PHẦN V: CẤU HÌNH CRAWLER TỰ ĐỘNG CẬP NHẬT (CRONJOB)

### 1. Đồng bộ văn bản mới hàng đêm (Daily Sync)
Thiết lập cron job để hệ thống tự động quét 10 trang văn bản mới nhất trên vbpl.vn vào lúc **00:00 hàng đêm**:
1. Chuyển sang user `dataluat`: `sudo -i -u dataluat`
2. Mở trình quản lý cronjob: `crontab -e`
3. Thêm dòng lệnh sau vào cuối file:
   ```bash
   0 0 * * * cd /home/dataluat/dataluatvn && SYNC_PAGES=10 CRAWLER_HEADLESS=1 ./venv/bin/python3 sync_new_laws.py >> logs/sync.log 2>&1
   ```

### 2. Xử lý cào 6.558 văn bản thiếu nội dung
Đối với lần cấu hình đầu tiên, cần cào nội dung chi tiết cho nhóm văn bản cũ bị thiếu.
Chạy ngầm crawler qua `nohup` (để tiến trình tiếp tục chạy khi anh đóng terminal):
```bash
# Chạy ngầm cào dữ liệu với 5 luồng song song
nohup ./venv/bin/python3 fill_missing_content.py > logs/fill_missing.log 2>&1 &
```
Anh có thể giám sát tiến độ thông qua logs:
```bash
tail -f logs/fill_missing.log
```

---

## 🛡️ PHẦN VI: TÍCH HỢP CHATBOT CHỐNG ẢO GIÁC (RAG GUARDRAILS)

Trong dự án đã tích hợp sẵn thư viện **`rag_guardrails.py`** phục vụ việc xây dựng Chatbot. Lập trình viên Backend của chatbot có thể tích hợp trực tiếp như sau:

```python
from rag_guardrails import RAGGuardrails

# Khởi tạo bộ lọc bảo vệ với đường dẫn DB
guard = RAGGuardrails(
    db_path="/home/dataluat/dataluatvn/vietnamese_legal_documents.db",
    content_db_path="/home/dataluat/dataluatvn/content_store.db"
)

# 1. Tìm tài liệu liên quan sạch
context_docs = guard.retrieve_context("quy định về thuế đất đai", limit=4)

# 2. Xây dựng prompt ràng buộc thép
strict_prompt = guard.build_strict_prompt("quy định về thuế đất đai", context_docs)

# 3. Gửi prompt lên LLM (BẮT BUỘC đặt temperature = 0.0)
# response = call_llm(strict_prompt, temperature=0.0)

# 4. Kiểm soát trích dẫn đầu ra chống tự bịa luật
is_safe, message, hallucinated_sources = guard.validate_citations(response, context_docs)

if not is_safe:
    # Nếu chatbot tự bịa nguồn không có trong context, chặn câu trả lời và dùng fallback
    print("Cảnh báo: Phát hiện ảo giác nguồn luật!")
    final_output = "Tôi xin lỗi, thông tin pháp luật hiện tại trong cơ sở dữ liệu của tôi không đủ để trả lời chính xác câu hỏi này."
```
