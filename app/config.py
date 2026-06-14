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
FPT_CLOUD_API_KEY = os.environ.get("FPT_CLOUD_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
API_PORT = int(os.environ.get("API_PORT", 2004))
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7 days

# Runtime safety check for public deployment
if not JWT_SECRET:
    import warnings
    warnings.warn("⚠️  JWT_SECRET not set in .env — using insecure default. Set JWT_SECRET for production!", stacklevel=2)
    JWT_SECRET = "dlvn-dev-only-insecure-default"
if not FPT_CLOUD_API_KEY and not GEMINI_API_KEY:
    import warnings
    warnings.warn("⚠️  Cả FPT_CLOUD_API_KEY và GEMINI_API_KEY đều chưa được thiết lập trong .env — các tính năng LLM sẽ bị tắt.", stacklevel=2)

# --- SOTA RAG Config ---
VECTOR_DB_SOTA = os.environ.get("VECTOR_DB_SOTA_PATH", "vector_store.db")
FAISS_INDEX_SOTA = os.environ.get("FAISS_INDEX_SOTA_PATH", "chunks_faiss.index")
EMBEDDING_MODEL_SOTA = os.environ.get("EMBEDDING_MODEL_SOTA", "BAAI/bge-m3")
RERANKER_MODEL_SOTA = os.environ.get("RERANKER_MODEL_SOTA", "AITeamVN/Vietnamese_Reranker")


# --- Fixed Accounts (Internal Use Only) ---
# Passwords loaded from environment variables. Set ADMIN_PASSWORD in .env.
_admin_password = os.environ.get("ADMIN_PASSWORD", "")
if not _admin_password:
    import warnings
    warnings.warn("⚠️  ADMIN_PASSWORD not set in .env — using insecure default. Set ADMIN_PASSWORD for production!", stacklevel=2)
    _admin_password = "changeme-insecure-default"

ACCOUNTS = {
    "phamkhoa3092003@gmail.com": hashlib.sha256(_admin_password.encode()).hexdigest(),
    "phapsuto@gmail.com": hashlib.sha256(_admin_password.encode()).hexdigest(),
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
