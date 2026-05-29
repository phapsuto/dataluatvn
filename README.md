# 🚀 dataluatvn — API Dữ Liệu Pháp Luật Việt Nam

> REST API hiệu năng cao cho hơn **153.420 văn bản pháp luật Việt Nam** cùng **897.890 mối liên kết pháp lý**.
> Giải pháp tối ưu nhất để xây dựng Chatbot RAG (AI) và Website tra cứu luật chuyên nghiệp.

---

## 🌟 Tính Năng Nổi Bật

| Tính năng | Mô tả |
|---|---|
| 🔍 **Tìm kiếm nhanh** | Tìm theo từ khóa, loại văn bản, lĩnh vực, tình trạng hiệu lực, cơ quan ban hành |
| 📄 **Chi tiết toàn văn** | Lấy toàn bộ nội dung HTML và metadata đầy đủ |
| 🔗 **Quan hệ pháp lý** | Tra cứu sửa đổi, bổ sung, thay thế giữa các văn bản |
| 📊 **Thống kê** | Phân tích tổng quan theo loại, trạng thái, cơ quan ban hành |
| 🏷️ **Danh mục** | Liệt kê loại văn bản, lĩnh vực, cơ quan ban hành |
| 📚 **Tài liệu tự động** | Swagger UI tại `/docs` và ReDoc tại `/redoc` |
| 🐳 **Docker Ready** | Triển khai 1 lệnh với Docker Compose |

---

## 📂 Cấu Trúc Dự Án

```
dataluatvn/
├── server.py                 # REST API server (FastAPI) — Port 2004
├── download_all_to_sqlite.py # Tải bộ dữ liệu gốc từ HuggingFace
├── sync_new_laws.py          # Đồng bộ văn bản mới hàng đêm
├── requirements.txt          # Python dependencies (pinned versions)
├── Dockerfile                # Docker image build
├── docker-compose.yml        # Docker Compose deployment
├── huongdan.md               # Hướng dẫn kết nối API & Database
└── KE_HOACH_XAY_DUNG_DATA_PHAP_LUAT.md  # Kiến trúc & lộ trình
```

---

## 📡 API Endpoints

API chạy trên **port 2004**. Tài liệu tương tác đầy đủ tại `/docs` (Swagger) và `/redoc`.

### 🏠 General

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/` | Health-check, thông tin hệ thống |

### 🔍 Tìm kiếm & Tra cứu

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/laws/search` | Tìm kiếm + lọc văn bản (hỗ trợ phân trang) |
| `GET`  | `/laws/{law_id}` | Lấy chi tiết toàn văn HTML + metadata |

**Tham số tìm kiếm `/laws/search`:**

| Tham số | Kiểu | Mô tả | Ví dụ |
|---------|------|-------|-------|
| `q` | string | Từ khóa tìm kiếm | `đất đai` |
| `loai_van_ban` | string | Lọc theo loại | `Luật`, `Nghị định` |
| `co_quan_ban_hanh` | string | Lọc theo cơ quan | `Quốc hội` |
| `tinh_trang` | string | Lọc theo hiệu lực | `Còn hiệu lực` |
| `linh_vuc` | string | Lọc theo lĩnh vực | `Đất đai` |
| `limit` | int | Số lượng tối đa (1–100) | `20` |
| `offset` | int | Vị trí bắt đầu | `0` |

### 🔗 Quan hệ pháp lý

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/laws/{law_id}/relationships` | Xem tất cả liên kết pháp lý |

### 📊 Thống kê

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/laws/stats` | Thống kê tổng quan CSDL |

### 🏷️ Danh mục

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/laws/categories/types` | Danh sách loại văn bản |
| `GET`  | `/laws/categories/fields` | Danh sách lĩnh vực |
| `GET`  | `/laws/categories/agencies` | Danh sách cơ quan ban hành |

---

## 🛠️ Cài Đặt & Chạy

### Yêu cầu
- **Python 3.9+**
- **Docker** (nếu dùng Docker)

### Cách 1: Chạy trực tiếp

```bash
# 1. Cài đặt dependencies
pip install -r requirements.txt

# 2. Tải database gốc (~153.420 văn bản, ~3.2 GB)
python download_all_to_sqlite.py

# 3. Khởi chạy API server (port 2004)
python server.py
```

**Truy cập:**
- API: `http://localhost:2004`
- Swagger Docs: `http://localhost:2004/docs`
- ReDoc: `http://localhost:2004/redoc`

### Cách 2: Chạy bằng Docker 🐳 (Khuyên dùng)

```bash
# 1. Tải database trước (chạy 1 lần)
pip install pyarrow huggingface_hub
python download_all_to_sqlite.py

# 2. Build & Run bằng Docker Compose
docker compose up -d --build

# Hoặc dùng Docker trực tiếp
docker build -t dataluat-api .
docker run -d \
  -p 2004:2004 \
  -v $(pwd)/vietnamese_legal_documents.db:/app/vietnamese_legal_documents.db \
  --name dataluat-api \
  dataluat-api
```

**Kiểm tra container:**
```bash
# Xem log
docker logs dataluat-api

# Kiểm tra health
curl http://localhost:2004/

# Dừng container
docker compose down
```

---

## ⏰ Cập Nhật Tự Động (Cron Job)

Để hệ thống tự cập nhật luật mới mỗi đêm lúc **00:00**:

```bash
# Mở bảng cron
crontab -e

# Thêm dòng sau:
0 0 * * * cd /path/to/dataluatvn && /usr/bin/python3 sync_new_laws.py >> sync.log 2>&1
```

Hoặc sử dụng PM2:
```bash
pm2 start "python3 server.py" --name "dataluat-api"
```

---

## 📝 Ví Dụ Sử Dụng (cURL)

```bash
# 1. Kiểm tra hệ thống
curl http://localhost:2004/

# 2. Tìm kiếm "đất đai"
curl "http://localhost:2004/laws/search?q=đất đai&limit=5"

# 3. Lọc Nghị định còn hiệu lực
curl "http://localhost:2004/laws/search?loai_van_ban=Nghị định&tinh_trang=Còn hiệu lực"

# 4. Lấy chi tiết văn bản ID 38920
curl http://localhost:2004/laws/38920

# 5. Xem quan hệ pháp lý
curl http://localhost:2004/laws/38920/relationships

# 6. Thống kê tổng quan
curl http://localhost:2004/laws/stats

# 7. Danh sách loại văn bản
curl http://localhost:2004/laws/categories/types

# 8. Danh sách lĩnh vực
curl http://localhost:2004/laws/categories/fields

# 9. Danh sách cơ quan ban hành
curl http://localhost:2004/laws/categories/agencies
```

---

## 📞 Liên Hệ & Hỗ Trợ
Dự án được duy trì và phát triển bởi **Pháp sư Tô** và đội ngũ phát triển. Vui lòng gửi Pull Request hoặc tạo Issue nếu bạn muốn đóng góp cho kho dữ liệu pháp luật Việt Nam ngày càng hoàn thiện!
