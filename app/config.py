import os
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ╔══════════════════════════════════════════════════════════════╗
# ║                     CONFIGURATION                           ║
# ╚══════════════════════════════════════════════════════════════╝

DB_NAME = os.environ.get("DB_PATH", "vietnamese_legal_documents.db")
CONTENT_DB = os.environ.get("CONTENT_DB_PATH", "content_store.db")
ADMIN_DB = os.environ.get("ADMIN_DB_PATH", "admin.db")
MEMORY_DB = os.environ.get("MEMORY_DB_PATH", "user_session_memory.db")
ZVEC_DB_PATH = os.environ.get("ZVEC_DB_PATH", "zvec_laws_db")
FPT_CLOUD_API_KEY = os.environ.get("FPT_CLOUD_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
API_PORT = int(os.environ.get("API_PORT", 2004))
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7 days

# Runtime safety checks
import warnings
if not JWT_SECRET:
    raise RuntimeError(
        "❌ JWT_SECRET chưa được thiết lập trong .env. "
        "Hãy tạo secret ngẫu nhiên: python3 -c \"import secrets; print(secrets.token_hex(32))\" "
        "rồi thêm JWT_SECRET=<giá_trị> vào .env"
    )
if not FPT_CLOUD_API_KEY and not GEMINI_API_KEY:
    warnings.warn("⚠️  Cả FPT_CLOUD_API_KEY và GEMINI_API_KEY đều chưa được thiết lập trong .env — các tính năng LLM sẽ bị tắt.", stacklevel=2)

# --- SOTA RAG Config ---
VECTOR_DB_SOTA = os.environ.get("VECTOR_DB_SOTA_PATH", "vector_store.db")
FAISS_INDEX_SOTA = os.environ.get("FAISS_INDEX_SOTA_PATH", "chunks_faiss_sq8.index")  # SQ8 quantized: 1.5 GB thay vì FP32 5.9 GB → tiết kiệm ~4.5 GB RAM
EMBEDDING_MODEL_SOTA = os.environ.get("EMBEDDING_MODEL_SOTA", "BAAI/bge-m3")
RERANKER_MODEL_SOTA = os.environ.get("RERANKER_MODEL_SOTA", "BAAI/bge-reranker-v2-m3")
USE_ZVEC_BACKEND = os.environ.get("USE_ZVEC_BACKEND", "true").lower() == "true"


# --- Fixed Accounts (Internal Use Only) ---
# Passwords and admin emails loaded from environment variables.
_admin_password = os.environ.get("ADMIN_PASSWORD", "")
if not _admin_password:
    raise RuntimeError(
        "❌ ADMIN_PASSWORD chưa được thiết lập trong .env. "
        "Hãy thêm ADMIN_PASSWORD=<mật_khẩu_mạnh> vào file .env"
    )

# Admin emails: cấu hình trong .env, cách nhau bằng dấu phẩy
# Ví dụ: ADMIN_EMAILS=email1@gmail.com,email2@gmail.com
_admin_emails_raw = os.environ.get("ADMIN_EMAILS", "phamkhoa3092003@gmail.com,phapsuto@gmail.com")
_admin_emails = [e.strip() for e in _admin_emails_raw.split(",") if e.strip()]

ACCOUNTS = {
    email: hashlib.sha256(_admin_password.encode()).hexdigest()
    for email in _admin_emails
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
