import os
import json
import sqlite3
import secrets
import hashlib
import time
import subprocess
import signal
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt as pyjwt
from fastapi import FastAPI, HTTPException, Query, Path, Depends, Header, Request

def simple_ttl_cache(ttl_seconds: int):
    def decorator(func):
        cached_value = None
        last_update = 0
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal cached_value, last_update
            if time.time() - last_update > ttl_seconds:
                cached_value = func(*args, **kwargs)
                last_update = time.time()
            return cached_value
        return wrapper
    return decorator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from pydantic import BaseModel, Field

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

# --- Security Schemes ---
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   DATABASE HELPERS                          ║
# ╚══════════════════════════════════════════════════════════════╝

def get_db_connection():
    """Connect to the main legal documents database (metadata only, ~300 MB)."""
    if not os.path.exists(DB_NAME):
        raise HTTPException(
            status_code=500,
            detail="Database file not found. Please run download_all_to_sqlite.py first.",
        )
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # ── PRAGMA tối ưu RAM ──
    conn.execute("PRAGMA cache_size = -32000")   # 32 MB cache (thay vì mặc định hàng GB)
    conn.execute("PRAGMA mmap_size = 0")          # Tắt memory-mapped I/O
    conn.execute("PRAGMA journal_mode = WAL")     # Write-Ahead Logging cho concurrent reads
    conn.execute("PRAGMA synchronous = NORMAL")   # Cân bằng safety/performance
    conn.execute("PRAGMA temp_store = FILE")      # Temp tables lưu disk, không RAM
    return conn


def get_content_connection():
    """Connect to content_store.db (chỉ chứa content_html, ~3.3 GB).
    Chỉ mở khi cần lấy toàn văn 1 document cụ thể."""
    if not os.path.exists(CONTENT_DB):
        return None  # Fallback: content vẫn nằm trong DB chính
    conn = sqlite3.connect(CONTENT_DB, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = -8000")    # 8 MB cache (chỉ đọc 1 row)
    conn.execute("PRAGMA mmap_size = 0")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA temp_store = FILE")
    return conn


def get_admin_db():
    """Connect to the admin database (API keys)."""
    conn = sqlite3.connect(ADMIN_DB, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_admin_db():
    """Initialize admin database with api_keys table."""
    conn = sqlite3.connect(ADMIN_DB, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_value TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            is_active INTEGER DEFAULT 1,
            request_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_key_value ON api_keys(key_value)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_active ON api_keys(is_active)")
    conn.commit()
    conn.close()
    print("✅ Admin database initialized")


# ╔══════════════════════════════════════════════════════════════╗
# ║                     JWT HELPERS                             ║
# ╚══════════════════════════════════════════════════════════════╝

def create_jwt_token(email: str) -> str:
    """Create a JWT token for admin access."""
    payload = {
        "sub": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token đã hết hạn. Vui lòng đăng nhập lại.")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ.")


# ╔══════════════════════════════════════════════════════════════╗
# ║                 SECURITY DEPENDENCIES                       ║
# ╚══════════════════════════════════════════════════════════════╝

async def require_jwt(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Dependency: require valid JWT token (for admin endpoints)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập. Vui lòng đăng nhập tại /admin")
    return decode_jwt_token(credentials.credentials)

async def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Depends(api_key_header_scheme),
    api_key_query: Optional[str] = Query(None, alias="api_key", include_in_schema=False),
):
    """Dependency: require valid API key OR admin JWT (for law data endpoints)."""
    key = x_api_key or api_key_query

    # 1. Try API key
    if key:
        conn = get_admin_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_keys WHERE key_value = ? AND is_active = 1", (key,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=403, detail="API Key không hợp lệ hoặc đã bị vô hiệu hóa.")

        cursor.execute(
            "UPDATE api_keys SET last_used_at = ?, request_count = request_count + 1 WHERE key_value = ?",
            (datetime.now(timezone.utc).isoformat(), key),
        )
        conn.commit()
        conn.close()
        return dict(row)

    # 2. Try JWT (admin dashboard access)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("sub") in ACCOUNTS:
                return {"type": "admin", "email": payload["sub"]}
        except Exception:
            pass

    raise HTTPException(
        status_code=401,
        detail="Yêu cầu API Key. Vui lòng đăng nhập tại /admin để tạo API key.",
    )



# ╔══════════════════════════════════════════════════════════════╗
# ║                    PYDANTIC MODELS                          ║
# ╚══════════════════════════════════════════════════════════════╝

# --- Auth Models ---
class LoginRequest(BaseModel):
    email: str = Field(..., example="phapsuto@gmail.com")
    password: str = Field(..., example="••••••••")

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    expires_in_hours: int

class UserInfo(BaseModel):
    email: str

# --- API Key Models ---
class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, example="My App Key")

class ApiKeyResponse(BaseModel):
    id: int
    key_value: str
    name: str
    created_by: str
    created_at: str
    last_used_at: Optional[str] = None
    is_active: bool
    request_count: int

class ApiKeyCreated(BaseModel):
    id: int
    key_value: str
    name: str
    created_by: str
    created_at: str
    message: str = "API Key đã tạo thành công. Hãy lưu lại key này — bạn sẽ không thể xem lại toàn bộ key sau này."

# --- Law Models ---
class HealthResponse(BaseModel):
    status: str
    message: str
    total_documents_loaded: int
    docs_url: str
    redoc_url: str
    admin_url: str

class LawBrief(BaseModel):
    id: int
    title: str
    so_ky_hieu: Optional[str] = None
    ngay_ban_hanh: Optional[str] = None
    loai_van_ban: Optional[str] = None
    co_quan_ban_hanh: Optional[str] = None
    tinh_trang_hieu_luc: Optional[str] = None

class LawDetail(LawBrief):
    ngay_co_hieu_luc: Optional[str] = None
    ngay_het_hieu_luc: Optional[str] = None
    nguon_thu_thap: Optional[str] = None
    ngay_dang_cong_bao: Optional[str] = None
    nganh: Optional[str] = None
    linh_vuc: Optional[str] = None
    chuc_danh: Optional[str] = None
    nguoi_ky: Optional[str] = None
    pham_vi: Optional[str] = None
    thong_tin_ap_dung: Optional[str] = None
    content_html: Optional[str] = None

class RelationshipInfo(BaseModel):
    doc_id: int
    other_doc_id: int
    relationship: str
    other_doc_title: str
    other_doc_so_ky_hieu: Optional[str] = None

class ArticleModification(BaseModel):
    article_name: str
    modified_text: str
    modified_by_doc_id: int

class StatsResponse(BaseModel):
    total_documents: int
    total_relationships: int
    by_document_type: Dict[str, int]
    by_effectiveness_status: Dict[str, int]

class PaginatedSearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    total_pages: int
    current_page: int
    has_next: bool
    has_previous: bool
    results: List[LawBrief]

class CategoryItem(BaseModel):
    name: str
    count: int

class ErrorResponse(BaseModel):
    detail: str


# ╔══════════════════════════════════════════════════════════════╗
# ║                      APP SETUP                              ║
# ╚══════════════════════════════════════════════════════════════╝

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init admin DB, validate main DB."""
    init_admin_db()
    if os.path.exists(DB_NAME):
        try:
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM documents")
            total = cursor.fetchone()[0]
            conn.close()
            print(f"✅ Legal database loaded: {total:,} documents")
        except sqlite3.OperationalError as e:
            print(f"⚠️  Could not count documents on startup (database might be busy): {e}")
    else:
        print(f"⚠️  Legal database '{DB_NAME}' not found. Run download_all_to_sqlite.py first.")
    print(f"🚀 API server starting on port {API_PORT}")
    yield


DESCRIPTION = """
## 🇻🇳 API Dữ Liệu Pháp Luật Việt Nam

REST API hiệu năng cao cho kho dữ liệu **153.420+ văn bản pháp luật** và **897.890+ mối liên kết pháp lý**.

### 🔐 Xác thực API
Tất cả endpoints `/laws/*` yêu cầu **API Key** trong header:
```
X-API-Key: dlvn_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Hoặc qua query parameter: `?api_key=dlvn_xxx...`

👉 **Đăng nhập tại [/admin](/admin)** để tạo API Key.

### ✨ Tính năng chính
| Tính năng | Mô tả |
|---|---|
| 🔍 **Tìm kiếm nhanh** | Tìm kiếm **Full-Text Search (FTS5)** siêu tốc, tự động sắp xếp kết quả liên quan lên top, kèm theo tính năng **Phân trang (Pagination)** tiêu chuẩn. |
| 📄 **Chi tiết toàn văn** | Lấy toàn bộ nội dung HTML và metadata |
| 🔗 **Quan hệ pháp lý** | Sửa đổi, bổ sung, thay thế giữa các văn bản |
| 📊 **Thống kê** | Phân tích tổng quan theo loại, trạng thái |
| 🏷️ **Danh mục** | Liệt kê loại văn bản, lĩnh vực, cơ quan ban hành |
"""

TAGS_METADATA = [
    {"name": "🏠 General", "description": "Kiểm tra trạng thái hệ thống."},
    {"name": "🔐 Authentication", "description": "Đăng nhập và quản lý phiên làm việc."},
    {"name": "🔑 API Keys", "description": "Tạo, xem và quản lý API Keys (yêu cầu đăng nhập)."},
    {"name": "🔍 Tìm kiếm & Tra cứu", "description": "Tìm kiếm và lấy chi tiết văn bản (yêu cầu API Key)."},
    {"name": "🔗 Quan hệ pháp lý", "description": "Tra cứu liên kết giữa các văn bản (yêu cầu API Key)."},
    {"name": "📊 Thống kê", "description": "Thống kê tổng quan dữ liệu (yêu cầu API Key)."},
    {"name": "🏷️ Danh mục", "description": "Danh mục loại văn bản, lĩnh vực, cơ quan (yêu cầu API Key)."},
]

app = FastAPI(
    title="Vietnamese Legal Documents API",
    description=DESCRIPTION,
    version="1.1.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={"name": "Pháp sư Tô — dataluatvn"},
    license_info={"name": "MIT"},
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   GENERAL ENDPOINTS                         ║
# ╚══════════════════════════════════════════════════════════════╝

@app.get("/", response_model=HealthResponse, tags=["🏠 General"], summary="Health Check")
def welcome():
    """Kiểm tra trạng thái hệ thống (không yêu cầu API Key)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM documents")
    total_docs = cursor.fetchone()[0]
    conn.close()

    return {
        "status": "online",
        "message": "Chào mừng đến với API Dữ Liệu Pháp Luật Việt Nam!",
        "total_documents_loaded": total_docs,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "admin_url": "/admin",
    }


# ╔══════════════════════════════════════════════════════════════╗
# ║                  AUTH ENDPOINTS                             ║
# ╚══════════════════════════════════════════════════════════════╝

@app.post("/auth/login", response_model=LoginResponse, tags=["🔐 Authentication"], summary="Đăng nhập")
def login(body: LoginRequest):
    """
    Đăng nhập bằng email và mật khẩu.
    Chỉ các tài khoản nội bộ được phép đăng nhập.
    Trả về JWT token dùng để quản lý API Keys.
    """
    email = body.email.strip().lower()
    password_hash = hashlib.sha256(body.password.encode()).hexdigest()

    expected_hash = ACCOUNTS.get(email)
    if not expected_hash or password_hash != expected_hash:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng.")

    token = create_jwt_token(email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "email": email,
        "expires_in_hours": JWT_EXPIRE_HOURS,
    }


@app.get("/auth/me", response_model=UserInfo, tags=["🔐 Authentication"], summary="Thông tin người dùng")
def get_current_user(user=Depends(require_jwt)):
    """Lấy thông tin tài khoản đang đăng nhập (yêu cầu JWT token)."""
    return {"email": user["sub"]}


# ╔══════════════════════════════════════════════════════════════╗
# ║                API KEY MANAGEMENT                           ║
# ╚══════════════════════════════════════════════════════════════╝

@app.get("/admin/api-keys", response_model=List[ApiKeyResponse], tags=["🔑 API Keys"], summary="Danh sách API Keys")
def list_api_keys(user=Depends(require_jwt)):
    """Lấy danh sách tất cả API Keys (yêu cầu đăng nhập)."""
    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        d = dict(row)
        d["is_active"] = bool(d["is_active"])
        results.append(d)
    return results


@app.post("/admin/api-keys", response_model=ApiKeyCreated, tags=["🔑 API Keys"], summary="Tạo API Key mới")
def create_api_key(body: ApiKeyCreate, user=Depends(require_jwt)):
    """
    Tạo một API Key mới. Key có dạng `dlvn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
    **Lưu ý:** Hãy lưu key ngay sau khi tạo.
    """
    key_value = f"dlvn_{secrets.token_hex(24)}"
    now = datetime.now(timezone.utc).isoformat()

    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO api_keys (key_value, name, created_by, created_at) VALUES (?, ?, ?, ?)",
        (key_value, body.name.strip(), user["sub"], now),
    )
    conn.commit()
    key_id = cursor.lastrowid
    conn.close()

    return {
        "id": key_id,
        "key_value": key_value,
        "name": body.name.strip(),
        "created_by": user["sub"],
        "created_at": now,
    }


@app.put("/admin/api-keys/{key_id}/toggle", tags=["🔑 API Keys"], summary="Bật/tắt API Key")
def toggle_api_key(key_id: int, user=Depends(require_jwt)):
    """Bật hoặc tắt trạng thái hoạt động của một API Key."""
    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy API Key.")

    new_status = 0 if row["is_active"] else 1
    cursor.execute("UPDATE api_keys SET is_active = ? WHERE id = ?", (new_status, key_id))
    conn.commit()
    conn.close()

    return {"message": "Đã cập nhật trạng thái", "is_active": bool(new_status)}


@app.delete("/admin/api-keys/{key_id}", tags=["🔑 API Keys"], summary="Xóa API Key")
def delete_api_key(key_id: int, user=Depends(require_jwt)):
    """Xóa vĩnh viễn một API Key."""
    conn = get_admin_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy API Key.")

    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()

    return {"message": "Đã xóa API Key thành công."}


# ╔══════════════════════════════════════════════════════════════╗
# ║              ADMIN PORTAL (HTML PAGE)                       ║
# ╚══════════════════════════════════════════════════════════════╝

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page():
    """Serve the admin portal HTML page."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "admin.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=500, detail="Admin page not found.")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ╔══════════════════════════════════════════════════════════════╗
# ║          LAW DATA ENDPOINTS (API KEY REQUIRED)              ║
# ╚══════════════════════════════════════════════════════════════╝

# ─────────────────── STATISTICS ───────────────────

@simple_ttl_cache(ttl_seconds=3600)
def _get_cached_stats():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT count(*) FROM documents")
    total_docs = cursor.fetchone()[0]

    cursor.execute("SELECT count(*) FROM relationships")
    total_rels = cursor.fetchone()[0]

    cursor.execute("SELECT loai_van_ban, count(*) FROM documents GROUP BY loai_van_ban ORDER BY count(*) DESC")
    types_count = {row[0] or "Khác": row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT tinh_trang_hieu_luc, count(*) FROM documents GROUP BY tinh_trang_hieu_luc ORDER BY count(*) DESC")
    status_count = {row[0] or "Không xác định": row[1] for row in cursor.fetchall()}

    conn.close()
    return {
        "total_documents": total_docs,
        "total_relationships": total_rels,
        "by_document_type": types_count,
        "by_effectiveness_status": status_count,
    }

@app.get("/laws/stats", response_model=StatsResponse, tags=["📊 Thống kê"], summary="Thống kê tổng quan")
def get_stats(_key=Depends(require_api_key)):
    """Thống kê tổng quan cơ sở dữ liệu. **Yêu cầu API Key.**"""
    return _get_cached_stats()


# ─────────────────── SEARCH & RETRIEVAL ───────────────────

@app.get("/laws/search", response_model=PaginatedSearchResponse, tags=["🔍 Tìm kiếm & Tra cứu"], summary="Tìm kiếm văn bản")
def search_laws(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm"),
    loai_van_ban: Optional[str] = Query(None, description="Lọc theo loại văn bản"),
    co_quan_ban_hanh: Optional[str] = Query(None, description="Lọc theo cơ quan ban hành"),
    status: Optional[str] = Query(None, alias="tinh_trang", description="Lọc theo tình trạng hiệu lực"),
    linh_vuc: Optional[str] = Query(None, description="Lọc theo lĩnh vực"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng tối đa (1–100)"),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu"),
    require_content: bool = Query(False, description="Chỉ trả về văn bản có nội dung HTML"),
    _key=Depends(require_api_key),
):
    """
    Tìm kiếm và lọc văn bản pháp luật bằng **Full-Text Search (FTS5)**.
    
    **Tính năng nổi bật:**
    - Kết quả tự động sắp xếp theo độ liên quan (relevance) nếu có từ khóa `q`.
    - Phân trang đầy đủ với `total_pages`, `current_page`, `has_next`, `has_previous`.
    
    **Yêu cầu API Key.**
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clauses = []
    params: list = []
    from_clause = "documents d"

    if require_content:
        where_clauses.append("d.has_content = 1")

    if q:
        escaped_q = q.replace('"', '""')
        where_clauses.append("documents_fts MATCH ?")
        params.append(f'"{escaped_q}"')
        from_clause = "documents d JOIN documents_fts ON d.id = documents_fts.rowid"

    if loai_van_ban:
        where_clauses.append("d.loai_van_ban = ?")
        params.append(loai_van_ban)
    if co_quan_ban_hanh:
        where_clauses.append("d.co_quan_ban_hanh LIKE ?")
        params.append(f"%{co_quan_ban_hanh}%")
    if status:
        where_clauses.append("d.tinh_trang_hieu_luc = ?")
        params.append(status)
    if linh_vuc:
        where_clauses.append("(d.linh_vuc LIKE ? OR d.nganh LIKE ?)")
        params.extend([f"%{linh_vuc}%", f"%{linh_vuc}%"])

    if not where_clauses:
        where_clauses.append("1=1")

    where_sql = " AND ".join(where_clauses)

    cursor.execute(f"SELECT count(*) FROM {from_clause} WHERE {where_sql}", params)
    total = cursor.fetchone()[0]

    order_clause = "documents_fts.rank, d.id DESC" if q else "d.id DESC"

    cursor.execute(
        f"SELECT d.id, d.title, d.so_ky_hieu, d.ngay_ban_hanh, d.loai_van_ban, d.co_quan_ban_hanh, d.tinh_trang_hieu_luc "
        f"FROM {from_clause} WHERE {where_sql} ORDER BY {order_clause} LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = cursor.fetchall()
    conn.close()

    total_pages = (total + limit - 1) // limit if limit > 0 else 0
    current_page = (offset // limit) + 1 if limit > 0 else 1
    has_next = current_page < total_pages
    has_previous = current_page > 1

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "total_pages": total_pages,
        "current_page": current_page,
        "has_next": has_next,
        "has_previous": has_previous,
        "results": [dict(r) for r in rows]
    }


@simple_ttl_cache(ttl_seconds=3600)
def _get_cached_document_types():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT loai_van_ban, count(*) as cnt FROM documents GROUP BY loai_van_ban ORDER BY cnt DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0] or "Khác", "count": row[1]} for row in rows]

@app.get("/laws/categories/types", response_model=List[CategoryItem], tags=["🏷️ Danh mục"], summary="Loại văn bản")
def get_document_types(_key=Depends(require_api_key)):
    """Danh sách loại văn bản. **Yêu cầu API Key.**"""
    return _get_cached_document_types()


@simple_ttl_cache(ttl_seconds=3600)
def _get_cached_fields():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT linh_vuc, count(*) as cnt FROM documents WHERE linh_vuc IS NOT NULL AND linh_vuc != '' GROUP BY linh_vuc ORDER BY cnt DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0], "count": row[1]} for row in rows]

@app.get("/laws/categories/fields", response_model=List[CategoryItem], tags=["🏷️ Danh mục"], summary="Lĩnh vực")
def get_fields(_key=Depends(require_api_key)):
    """Danh sách lĩnh vực pháp luật. **Yêu cầu API Key.**"""
    return _get_cached_fields()


@simple_ttl_cache(ttl_seconds=3600)
def _get_cached_agencies():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT co_quan_ban_hanh, count(*) as cnt FROM documents WHERE co_quan_ban_hanh IS NOT NULL AND co_quan_ban_hanh != '' GROUP BY co_quan_ban_hanh ORDER BY cnt DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0], "count": row[1]} for row in rows]

@app.get("/laws/categories/agencies", response_model=List[CategoryItem], tags=["🏷️ Danh mục"], summary="Cơ quan ban hành")
def get_agencies(_key=Depends(require_api_key)):
    """Danh sách cơ quan ban hành. **Yêu cầu API Key.**"""
    return _get_cached_agencies()


@app.get("/laws/{law_id}", response_model=LawDetail, tags=["🔍 Tìm kiếm & Tra cứu"], summary="Chi tiết văn bản")
def get_law_detail(
    law_id: int = Path(..., description="ID văn bản"),
    _key=Depends(require_api_key),
):
    """Lấy toàn văn HTML và metadata đầy đủ. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (law_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản có ID {law_id}")

    result = dict(row)

    # Nếu content_html đã được tách sang content_store.db
    if not result.get("content_html"):
        content_conn = get_content_connection()
        if content_conn:
            content_cursor = content_conn.cursor()
            content_cursor.execute(
                "SELECT content_html FROM document_content WHERE doc_id = ?",
                (law_id,),
            )
            content_row = content_cursor.fetchone()
            content_conn.close()
            if content_row:
                result["content_html"] = content_row["content_html"]

    return result


# ─────────────────── RELATIONSHIPS ───────────────────

@app.get("/laws/{law_id}/relationships", response_model=List[RelationshipInfo], tags=["🔗 Quan hệ pháp lý"], summary="Quan hệ pháp lý")
def get_law_relationships(
    law_id: int = Path(..., description="ID văn bản"),
    _key=Depends(require_api_key),
):
    """Tra cứu mạng lưới liên kết pháp lý. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT r.doc_id, r.other_doc_id, r.relationship,
               d.title as other_doc_title, d.so_ky_hieu as other_doc_so_ky_hieu
        FROM relationships r
        JOIN documents d ON r.other_doc_id = d.id
        WHERE r.doc_id = ?
        UNION
        SELECT r.doc_id, r.other_doc_id, r.relationship,
               d.title as other_doc_title, d.so_ky_hieu as other_doc_so_ky_hieu
        FROM relationships r
        JOIN documents d ON r.doc_id = d.id
        WHERE r.other_doc_id = ?
    """

    cursor.execute(query, (law_id, law_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/laws/{law_id}/article-modifications", response_model=List[ArticleModification], tags=["🔗 Quan hệ pháp lý"], summary="Các điều khoản bị sửa đổi")
def get_article_modifications(
    law_id: int = Path(..., description="ID văn bản"),
    _key=Depends(require_api_key),
):
    """Tra cứu các điều khoản bị sửa đổi của văn bản. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT article_name, modified_text, modified_by_doc_id
        FROM article_modifications
        WHERE doc_id = ?
    """

    try:
        cursor.execute(query, (law_id,))
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        # Table might not exist yet if script hasn't run fully
        rows = []
    
    conn.close()
    return [dict(row) for row in rows]


# ╔══════════════════════════════════════════════════════════════╗
# ║                    DASHBOARD                                ║
# ╚══════════════════════════════════════════════════════════════╝

# Global crawler process reference
_crawler_process = None

@app.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page():
    html_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=500, detail="Dashboard page not found.")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/dashboard/stats", include_in_schema=False)
def dashboard_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM documents")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE has_content = 1")
    with_content = c.fetchone()[0]
    without_content = total - with_content

    c.execute("SELECT loai_van_ban, COUNT(*) FROM documents GROUP BY loai_van_ban ORDER BY COUNT(*) DESC LIMIT 10")
    by_type = [{"name": r[0] or "Không xác định", "count": r[1]} for r in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM relationships")
    total_rels = c.fetchone()[0]

    try:
        c.execute("SELECT COUNT(*) FROM article_modifications")
        total_mods = c.fetchone()[0]
    except:
        total_mods = 0

    try:
        c.execute("SELECT COUNT(*) FROM documents_fts")
        fts_count = c.fetchone()[0]
    except:
        fts_count = 0

    conn.close()

    content_size = os.path.getsize(CONTENT_DB) if os.path.exists(CONTENT_DB) else 0

    return {
        "total_documents": total,
        "with_content": with_content,
        "without_content": without_content,
        "progress_pct": round(with_content / total * 100, 2) if total > 0 else 0,
        "by_type": by_type,
        "total_relationships": total_rels,
        "total_modifications": total_mods,
        "fts_indexed": fts_count,
        "content_db_size_mb": round(content_size / 1024 / 1024, 1),
        "main_db_size_mb": round(os.path.getsize(DB_NAME) / 1024 / 1024, 1),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/dashboard/logs", include_in_schema=False)
def dashboard_logs():
    all_lines = []
    for log_file in ["fill_missing.log", "sync.log"]:
        log_path = os.path.join(os.path.dirname(__file__), log_file)
        if os.path.isfile(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    all_lines.extend(lines)
            except Exception:
                pass
    return {"lines": all_lines[-100:], "total_lines": len(all_lines)}


@app.get("/api/dashboard/sample", include_in_schema=False)
def dashboard_sample(limit: int = 20):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh, tinh_trang_hieu_luc
        FROM documents WHERE has_content = 1
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    docs = []
    for row in c.fetchall():
        doc = dict(row)
        # Check content length
        try:
            conn_c = get_content_connection()
            cc = conn_c.cursor()
            cc.execute("SELECT LENGTH(content_html) FROM document_content WHERE doc_id = ?", (row["id"],))
            cr = cc.fetchone()
            doc["content_length"] = cr[0] if cr else 0
            conn_c.close()
        except:
            doc["content_length"] = 0
        docs.append(doc)
    conn.close()
    return {"documents": docs}


@app.get("/api/dashboard/check", include_in_schema=False)
def dashboard_check(id: int = Query(...)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM documents WHERE id = ?", (id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": f"Document {id} not found"}

    doc = dict(row)

    # Content preview
    try:
        conn_c = get_content_connection()
        cc = conn_c.cursor()
        cc.execute("SELECT content_html FROM document_content WHERE doc_id = ?", (id,))
        cr = cc.fetchone()
        if cr and cr[0]:
            doc["content_preview"] = cr[0][:2000]
            doc["content_length"] = len(cr[0])
        else:
            doc["content_preview"] = None
            doc["content_length"] = 0
        conn_c.close()
    except:
        doc["content_preview"] = None
        doc["content_length"] = 0

    # Relationships
    c.execute("""
        SELECT r.other_doc_id, r.relationship, d.title
        FROM relationships r
        LEFT JOIN documents d ON d.id = r.other_doc_id
        WHERE r.doc_id = ? LIMIT 20
    """, (id,))
    doc["relationships"] = [
        {"other_id": r[0], "type": r[1], "other_title": r[2]}
        for r in c.fetchall()
    ]

    # Modifications
    try:
        c.execute("""
            SELECT am.article_name, am.modified_by_doc_id, am.modified_text, d.title
            FROM article_modifications am
            LEFT JOIN documents d ON d.id = am.modified_by_doc_id
            WHERE am.doc_id = ? LIMIT 20
        """, (id,))
        doc["modifications"] = [
            {"article": r[0], "by_doc_id": r[1], "text": (r[2] or "")[:200], "by_title": r[3]}
            for r in c.fetchall()
        ]
    except:
        doc["modifications"] = []

    conn.close()
    return doc


@app.get("/api/dashboard/crawler/progress", include_in_schema=False)
def dashboard_crawler_progress():
    """Đọc progress từ crawler_progress.json — Dashboard poll mỗi 2s."""
    progress_file = os.path.join(os.path.dirname(__file__), "crawler_progress.json")
    pid_file = os.path.join(os.path.dirname(__file__), "crawler.pid")

    # Check if crawler process is alive
    is_running = False
    pid = None
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # Check if alive
            is_running = True
        except (ProcessLookupError, ValueError, PermissionError):
            is_running = False
            try:
                os.remove(pid_file)
            except:
                pass

    if os.path.exists(progress_file):
        try:
            with open(progress_file, encoding="utf-8") as f:
                data = json.load(f)
            data["is_running"] = is_running
            data["pid"] = pid
            return data
        except:
            pass

    return {"status": "idle", "is_running": False, "total": 0, "success": 0, "fail": 0}


@app.post("/api/dashboard/crawler/start", include_in_schema=False)
async def dashboard_crawler_start(request: Request):
    """Start crawler as subprocess. Headless trên Linux server, headed trên macOS."""
    pid_file = os.path.join(os.path.dirname(__file__), "crawler.pid")

    # Check if already running
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return {"ok": False, "error": "Crawler đang chạy rồi!", "pid": pid}
        except (ProcessLookupError, ValueError):
            try:
                os.remove(pid_file)
            except:
                pass

    body = await request.json()
    tabs = body.get("tabs", 5)
    limit = body.get("limit", 0)

    script = os.path.join(os.path.dirname(__file__), "fill_missing_content.py")
    cmd = ["python", script]
    if limit and limit > 0:
        cmd.append(str(limit))

    env = os.environ.copy()
    env["CRAWLER_TABS"] = str(tabs)
    # Auto-detect: headless on Linux, headed on macOS
    import platform
    if platform.system() == "Linux":
        env["CRAWLER_HEADLESS"] = "1"

    _crawler_process = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(__file__))
    return {"ok": True, "pid": _crawler_process.pid, "tabs": tabs, "limit": limit,
            "headless": env.get("CRAWLER_HEADLESS", "0") == "1"}


@app.post("/api/dashboard/crawler/stop", include_in_schema=False)
def dashboard_crawler_stop():
    """Gửi SIGTERM để crawler dừng an toàn."""
    pid_file = os.path.join(os.path.dirname(__file__), "crawler.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            return {"ok": True, "message": f"Đã gửi tín hiệu dừng (PID {pid}). Crawler sẽ kết thúc an toàn."}
        except ProcessLookupError:
            try:
                os.remove(pid_file)
            except:
                pass
            return {"ok": True, "message": "Crawler đã dừng trước đó."}
        except Exception as e:
            return {"ok": False, "message": str(e)}
    return {"ok": False, "message": "Không có crawler nào đang chạy."}


@app.post("/api/dashboard/sync/start", include_in_schema=False)
async def dashboard_sync_start(request: Request):
    body = await request.json()
    pages = body.get("pages", 5)
    script = os.path.join(os.path.dirname(__file__), "sync_new_laws.py")
    if os.path.exists(script):
        env = os.environ.copy()
        env["MAX_PAGES"] = str(pages)
        subprocess.Popen(["python", script], env=env, cwd=os.path.dirname(__file__))
        return {"ok": True, "message": f"Sync đã bắt đầu (quét {pages} trang)"}
    return {"ok": False, "message": "Script không tồn tại"}


@app.post("/api/dashboard/tools/rebuild-fts", include_in_schema=False)
def dashboard_rebuild_fts():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    try:
        conn.execute("DROP TABLE IF EXISTS documents_fts")
        conn.execute("""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                title, so_ky_hieu, content='documents', content_rowid='id', tokenize='unicode61'
            )
        """)
        conn.execute("""
            INSERT INTO documents_fts(rowid, title, so_ky_hieu)
            SELECT id, title, so_ky_hieu FROM documents
        """)
        conn.commit()
        conn.close()
        return {"ok": True, "message": "FTS index đã được rebuild thành công!"}
    except Exception as e:
        conn.close()
        return {"ok": False, "message": str(e)}


@app.post("/api/dashboard/tools/extract-mods", include_in_schema=False)
def dashboard_extract_mods():
    script = os.path.join(os.path.dirname(__file__), "extract_modifications.py")
    if os.path.exists(script):
        subprocess.Popen(["python", script], cwd=os.path.dirname(__file__))
        return {"ok": True, "message": "Extract modifications đã bắt đầu"}
    return {"ok": False, "message": "Script không tồn tại"}


@app.post("/api/dashboard/tools/build-crosslinks", include_in_schema=False)
def dashboard_build_crosslinks():
    script = os.path.join(os.path.dirname(__file__), "build_crosslinks.py")
    if os.path.exists(script):
        subprocess.Popen(["python", script], cwd=os.path.dirname(__file__))
        return {"ok": True, "message": "Build crosslinks đã bắt đầu"}
    return {"ok": False, "message": "Script không tồn tại"}


# ╔══════════════════════════════════════════════════════════════╗
# ║                       MAIN                                 ║
# ╚══════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=API_PORT, reload=True)
