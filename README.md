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
| ⚡ **Tối ưu RAM** | Kiến trúc tách DB — server chỉ dùng ~50-80 MB RAM |

---

## 📂 Cấu Trúc Dự Án

```
dataluatvn/
├── server.py                      # REST API server (FastAPI) — Slim entry point
├── app/                           # Modular API Architecture
│   ├── config.py                  # Configurations & Swagger Metadata
│   ├── database.py                # DB connections & Optimizations
│   ├── dependencies.py            # JWT & API Key authentication
│   ├── routers/                   # API Routes (laws, anle, phapdien, admin, dashboard)
│   └── schemas/                   # Pydantic models
├── download_all_to_sqlite.py      # Tải bộ dữ liệu gốc từ HuggingFace
├── split_content_db.py            # Tách content_html ra DB riêng (tối ưu RAM)
├── sync_new_laws.py               # Đồng bộ văn bản mới hàng đêm
├── optimize_db.py                 # Tạo FTS5 indexes + VACUUM
├── db_schema.py                   # Schema migration (pháp điển, án lệ)
├── build_crosslinks.py            # Xây dựng liên kết chéo
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker image build
├── docker-compose.yml             # Docker Compose deployment
├── static/admin.html              # Trang quản trị API Keys & Tìm kiếm
├── static/dashboard.html          # Trang Dashboard thống kê & Crawler
├── huongdan.md                    # Hướng dẫn kết nối API & Database
└── KE_HOACH_XAY_DUNG_DATA_PHAP_LUAT.md  # Kiến trúc & lộ trình
```

### 📦 Kiến Trúc Database (Tách DB — Tối ưu RAM)

```
vietnamese_legal_documents.db   (~585 MB)   ← metadata, FTS5, relationships, pháp điển, án lệ
content_store.db                (~3.1 GB)   ← chỉ chứa content_html (toàn văn)
admin.db                        (~4 KB)     ← API keys
```

> **Tại sao tách?**
> Trước đây toàn bộ nằm trong 1 file 3.7 GB — mỗi query SQLite cache pages chứa `content_html` vào RAM → chiếm hàng GB.
> Sau khi tách, DB chính chỉ 585 MB và search/list không đụng content → **RAM giảm từ ~1-3 GB xuống ~50-80 MB**.

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
| `require_content`| bool | Chỉ lấy văn bản có ruột HTML | `true` |

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

### ⚖️ Án Lệ

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/anle/search` | Tìm kiếm Án Lệ, Bản Án (FTS5) |
| `GET`  | `/anle/{doc_name}` | Xem chi tiết & toàn văn markdown |
| `GET`  | `/anle/stats` | Thống kê dữ liệu Án Lệ |
| `GET`  | `/anle/categories/case-types` | Danh sách loại vụ án |
| `GET`  | `/anle/categories/court-levels` | Danh sách cấp tòa |

### 📖 Pháp Điển

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET`  | `/phapdien/search` | Tìm kiếm Điều khoản Pháp Điển (FTS5) |
| `GET`  | `/phapdien/{article_anchor}` | Xem chi tiết Điều khoản |
| `GET`  | `/phapdien/stats` | Thống kê Pháp Điển |
| `GET`  | `/phapdien/subjects` | Danh sách Đề mục |
| `GET`  | `/phapdien/topics` | Danh sách Chủ đề |
| `GET`  | `/phapdien/glossary` | Danh sách thuật ngữ VI-EN |

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

# 3. Chạy cập nhật cờ dữ liệu (đánh dấu văn bản có nội dung)
python upgrade_db.py

# 4. (Tùy chọn) Tách content_html ra DB riêng để giảm RAM
python split_content_db.py

# 5. Khởi chạy API server (port 2004)
# (Trên server production, chạy bằng uvicorn với 4 workers
# để tận dụng RAM dư dả và tăng tốc độ xử lý đồng thời)
uvicorn server:app --host 0.0.0.0 --port 2004 --workers 4
```

**Truy cập:**
- API: `http://localhost:2004`
- Swagger Docs: `http://localhost:2004/docs`
- ReDoc: `http://localhost:2004/redoc`
- Admin: `http://localhost:2004/admin` (Đăng nhập và lấy API Key tại đây)

### Cách 2: Chạy bằng Docker 🐳 (Khuyên dùng)

```bash
# 1. Tải database trước (chạy 1 lần)
pip install pyarrow huggingface_hub
python download_all_to_sqlite.py

# 2. Tách content_html (chạy 1 lần, giảm RAM server ~85%)
python split_content_db.py

# 3. Build & Run bằng Docker Compose
docker compose up -d --build

# Hoặc dùng Docker trực tiếp
docker build -t dataluat-api .
docker run -d \
  -p 2004:2004 \
  -v $(pwd)/vietnamese_legal_documents.db:/app/vietnamese_legal_documents.db \
  -v $(pwd)/content_store.db:/app/content_store.db \
  --name dataluat-api \
  --memory=512m \
  dataluat-api
```

**Kiểm tra container:**
```bash
# Xem log
docker logs dataluat-api

# Kiểm tra health
curl http://localhost:2004/

# Kiểm tra RAM usage
docker stats dataluat-api --no-stream

# Dừng container
docker compose down
```

---

## ⚡ Tối Ưu RAM (Split DB Architecture)

| Metric | Trước | Sau |
|---|---|---|
| DB chính | 3,721 MB | **585 MB** |
| RAM usage (ước tính) | ~1-3 GB | **~50-80 MB** |
| content_store.db | — | 3,140 MB |
| Search/List performance | Chậm (phải scan qua content) | **Nhanh** (chỉ scan metadata) |

### Cách hoạt động

1. **Search, list, stats, categories** → chỉ query DB chính (585 MB, không chứa content)
2. **Chi tiết 1 văn bản** → lấy metadata từ DB chính + `content_html` từ `content_store.db` (chỉ 1 row ~18KB)
3. **PRAGMA tối ưu** — giới hạn SQLite cache 32 MB, tắt memory-mapped I/O, dùng WAL mode

```bash
# Chạy tách DB (an toàn, idempotent, có integrity check)
python split_content_db.py
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

> **Lưu ý:** Script sync tự động lưu content vào cả DB chính và `content_store.db` nếu đã tách.

---

## 📝 Ví Dụ Sử Dụng (cURL)

```bash
# LƯU Ý: Thay YOUR_API_KEY bằng key thật tạo từ trang /admin
export API_KEY="dlvn_xxxxxxxxxxxxxxxxxxxx"

# 1. Kiểm tra hệ thống (Không cần key)
curl http://localhost:2004/

# 2. Tìm kiếm "đất đai" (Chỉ lấy văn bản có HTML)
curl -H "X-API-Key: $API_KEY" "http://localhost:2004/laws/search?q=đất+đai&limit=5&require_content=true"

# 3. Lọc Nghị định còn hiệu lực
curl -H "X-API-Key: $API_KEY" "http://localhost:2004/laws/search?loai_van_ban=Nghị+định&tinh_trang=Còn+hiệu+lực"

# 4. Lấy chi tiết văn bản ID 38920
curl -H "X-API-Key: $API_KEY" http://localhost:2004/laws/38920

# 5. Xem quan hệ pháp lý
curl -H "X-API-Key: $API_KEY" http://localhost:2004/laws/38920/relationships

# 6. Thống kê tổng quan
curl -H "X-API-Key: $API_KEY" http://localhost:2004/laws/stats

# 7. Danh sách loại văn bản
curl -H "X-API-Key: $API_KEY" http://localhost:2004/laws/categories/types

# 8. Danh sách lĩnh vực
curl -H "X-API-Key: $API_KEY" http://localhost:2004/laws/categories/fields

# 9. Danh sách cơ quan ban hành
curl -H "X-API-Key: $API_KEY" http://localhost:2004/laws/categories/agencies

# 10. Tìm kiếm Án Lệ
curl -H "X-API-Key: $API_KEY" "http://localhost:2004/anle/search?q=dân+sự&limit=5"

# 11. Tìm kiếm Pháp Điển
curl -H "X-API-Key: $API_KEY" "http://localhost:2004/phapdien/search?q=lao+động&limit=5"
```

---

## 📞 Liên Hệ & Hỗ Trợ
Dự án được duy trì và phát triển bởi **Pháp sư Tô** và đội ngũ phát triển. Vui lòng gửi Pull Request hoặc tạo Issue nếu bạn muốn đóng góp cho kho dữ liệu pháp luật Việt Nam ngày càng hoàn thiện!
