import os
import hashlib


# ╔══════════════════════════════════════════════════════════════╗
# ║                     CONFIGURATION                           ║
# ╚══════════════════════════════════════════════════════════════╝

DB_NAME = os.environ.get("DB_PATH", "vietnamese_legal_documents.db")
CONTENT_DB = os.environ.get("CONTENT_DB_PATH", "content_store.db")
ADMIN_DB = os.environ.get("ADMIN_DB_PATH", "admin.db")
API_PORT = int(os.environ.get("API_PORT", 2004))
JWT_SECRET = os.environ.get("JWT_SECRET", "dlvn-jwt-secret-2024-phapsuto-internal")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7 days

# --- Fixed Accounts (Internal Use Only) ---
ACCOUNTS = {
    "phamkhoa3092003@gmail.com": hashlib.sha256("Apple0202".encode()).hexdigest(),
    "phapsuto@gmail.com": hashlib.sha256("Apple0202".encode()).hexdigest(),
}


# ╔══════════════════════════════════════════════════════════════╗
# ║                  SWAGGER / OPENAPI METADATA                 ║
# ╚══════════════════════════════════════════════════════════════╝

DESCRIPTION = """
## 🇻🇳 API Dữ Liệu Pháp Luật Việt Nam

REST API hiệu năng cao cho kho dữ liệu **153.420+ văn bản pháp luật**, **64.400+ Điều Pháp Điển**, **gần 2.000 Án Lệ/Bản Án** và **897.890+ mối liên kết pháp lý**.

### 🔐 Xác thực API
Tất cả endpoints `/laws/*`, `/anle/*`, `/phapdien/*` yêu cầu **API Key** trong header:
```
X-API-Key: dlvn_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Hoặc qua query parameter: `?api_key=dlvn_xxx...`

👉 **Đăng nhập tại [/admin](/admin)** để tạo API Key.

### ✨ Tính năng chính
| Tính năng | Mô tả |
|---|---|
| 🔍 **Tìm kiếm nhanh** | Tìm kiếm **Full-Text Search (FTS5)** siêu tốc, tự động sắp xếp kết quả liên quan lên top, kèm theo tính năng **Phân trang (Pagination)** tiêu chuẩn. Dành cho Luật, Án Lệ và Pháp Điển. |
| 📄 **Chi tiết toàn văn** | Lấy toàn bộ nội dung HTML và metadata |
| 🔗 **Quan hệ pháp lý** | Sửa đổi, bổ sung, thay thế giữa các văn bản |
| 📊 **Thống kê** | Phân tích tổng quan theo loại, trạng thái |
| 🏷️ **Danh mục** | Liệt kê loại văn bản, lĩnh vực, cơ quan ban hành, Đề mục Pháp Điển, cấp Tòa Án Lệ |
"""

TAGS_METADATA = [
    {"name": "🏠 General", "description": "Kiểm tra trạng thái hệ thống."},
    {"name": "🔐 Authentication", "description": "Đăng nhập và quản lý phiên làm việc."},
    {"name": "🔑 API Keys", "description": "Tạo, xem và quản lý API Keys (yêu cầu đăng nhập)."},
    {"name": "⚖️ Án Lệ", "description": "Tìm kiếm và tra cứu Bản Án & Án Lệ Việt Nam (yêu cầu API Key)."},
    {"name": "📖 Pháp Điển", "description": "Tra cứu Bộ Pháp Điển điện tử (yêu cầu API Key)."},
    {"name": "🔍 Tìm kiếm & Tra cứu (Luật)", "description": "Tìm kiếm và lấy chi tiết văn bản (yêu cầu API Key)."},
    {"name": "🔗 Quan hệ pháp lý (Luật)", "description": "Tra cứu liên kết giữa các văn bản (yêu cầu API Key)."},
    {"name": "📊 Thống kê (Luật)", "description": "Thống kê tổng quan dữ liệu (yêu cầu API Key)."},
    {"name": "🏷️ Danh mục (Luật)", "description": "Danh mục loại văn bản, lĩnh vực, cơ quan (yêu cầu API Key)."},
]
