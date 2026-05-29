import os
import sqlite3
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# --- Configuration ---
DB_NAME = os.environ.get("DB_PATH", "vietnamese_legal_documents.db")
API_PORT = int(os.environ.get("API_PORT", 2004))

# --- Lifespan (startup / shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate database exists on startup."""
    if not os.path.exists(DB_NAME):
        print(f"⚠️  Database file '{DB_NAME}' not found.")
        print("   Please run: python download_all_to_sqlite.py")
    else:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM documents")
        total = cursor.fetchone()[0]
        conn.close()
        print(f"✅ Database loaded: {total:,} documents")
    print(f"🚀 API server starting on port {API_PORT}")
    yield


# --- FastAPI App ---
DESCRIPTION = """
## 🇻🇳 API Dữ Liệu Pháp Luật Việt Nam

REST API hiệu năng cao cho kho dữ liệu **153.420+ văn bản pháp luật** và **897.890+ mối liên kết pháp lý** của Việt Nam.

### ✨ Tính năng chính

| Tính năng | Mô tả |
|---|---|
| 🔍 **Tìm kiếm nhanh** | Tìm theo từ khóa, loại văn bản, lĩnh vực, tình trạng hiệu lực |
| 📄 **Chi tiết toàn văn** | Lấy toàn bộ nội dung HTML và metadata của bất kỳ văn bản nào |
| 🔗 **Quan hệ pháp lý** | Xem sửa đổi, bổ sung, thay thế giữa các văn bản |
| 📊 **Thống kê** | Phân tích tổng quan theo loại, trạng thái, cơ quan ban hành |
| 🏷️ **Danh mục** | Liệt kê tất cả loại văn bản và lĩnh vực có trong CSDL |

### 🚀 Bắt đầu nhanh

```bash
# Tìm kiếm từ khóa
GET /laws/search?q=đất đai&limit=5

# Lấy chi tiết văn bản
GET /laws/123

# Xem quan hệ pháp lý
GET /laws/123/relationships

# Thống kê tổng quan
GET /laws/stats
```

### 📝 Lưu ý
- API hỗ trợ **CORS mở** (`*`) — kết nối trực tiếp từ mọi frontend.
- Dữ liệu ngày tháng theo định dạng **dd/MM/yyyy** (ví dụ: `15/06/2023`).
- Nội dung HTML (`content_html`) có thể lớn — chỉ gọi endpoint chi tiết khi cần.
"""

TAGS_METADATA = [
    {
        "name": "🏠 General",
        "description": "Kiểm tra trạng thái hệ thống và thông tin chung về API.",
    },
    {
        "name": "🔍 Tìm kiếm & Tra cứu",
        "description": "Tìm kiếm, lọc và lấy chi tiết văn bản pháp luật.",
    },
    {
        "name": "🔗 Quan hệ pháp lý",
        "description": "Tra cứu các mối liên kết giữa các văn bản (sửa đổi, bổ sung, thay thế, hướng dẫn...).",
    },
    {
        "name": "📊 Thống kê",
        "description": "Thống kê, phân tích tổng quan dữ liệu trong cơ sở dữ liệu.",
    },
    {
        "name": "🏷️ Danh mục",
        "description": "Liệt kê danh mục loại văn bản, lĩnh vực, cơ quan ban hành có trong CSDL.",
    },
]

app = FastAPI(
    title="Vietnamese Legal Documents API",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "Pháp sư Tô — dataluatvn",
        "url": "https://github.com/phapsuto/dataluatvn",
    },
    license_info={
        "name": "MIT",
    },
    responses={
        500: {"description": "Lỗi máy chủ nội bộ — thường do chưa khởi tạo database."},
    },
)

# Enable CORS (Allows connection from any frontend or external app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Helpers ---
def get_db_connection():
    if not os.path.exists(DB_NAME):
        raise HTTPException(
            status_code=500,
            detail="Database file not found. Please run download_all_to_sqlite.py first.",
        )
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Returns results as dict-like objects
    return conn


# --- Pydantic Models ---

class HealthResponse(BaseModel):
    """Thông tin trạng thái hệ thống."""
    status: str = Field(..., example="online", description="Trạng thái API")
    message: str = Field(..., example="Chào mừng đến với API Dữ Liệu Pháp Luật Việt Nam!")
    database_file: str = Field(..., example="/app/vietnamese_legal_documents.db")
    total_documents_loaded: int = Field(..., example=153420, description="Tổng số văn bản trong CSDL")
    docs_url: str = Field("/docs", description="Đường dẫn tài liệu Swagger UI")
    redoc_url: str = Field("/redoc", description="Đường dẫn tài liệu ReDoc")

class LawBrief(BaseModel):
    """Thông tin tóm tắt của một văn bản pháp luật (không bao gồm nội dung HTML)."""
    id: int = Field(..., example=38920, description="ID duy nhất của văn bản")
    title: str = Field(..., example="Luật Đất đai 2024", description="Tiêu đề văn bản")
    so_ky_hieu: Optional[str] = Field(None, example="31/2024/QH15", description="Số ký hiệu")
    ngay_ban_hanh: Optional[str] = Field(None, example="18/01/2024", description="Ngày ban hành (dd/MM/yyyy)")
    loai_van_ban: Optional[str] = Field(None, example="Luật", description="Loại văn bản")
    co_quan_ban_hanh: Optional[str] = Field(None, example="Quốc hội", description="Cơ quan ban hành")
    tinh_trang_hieu_luc: Optional[str] = Field(None, example="Còn hiệu lực", description="Tình trạng hiệu lực")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 38920,
                    "title": "Luật Đất đai 2024",
                    "so_ky_hieu": "31/2024/QH15",
                    "ngay_ban_hanh": "18/01/2024",
                    "loai_van_ban": "Luật",
                    "co_quan_ban_hanh": "Quốc hội",
                    "tinh_trang_hieu_luc": "Còn hiệu lực",
                }
            ]
        }
    }


class LawDetail(LawBrief):
    """Thông tin chi tiết đầy đủ của một văn bản, bao gồm toàn văn HTML."""
    ngay_co_hieu_luc: Optional[str] = Field(None, example="01/01/2025", description="Ngày có hiệu lực")
    ngay_het_hieu_luc: Optional[str] = Field(None, description="Ngày hết hiệu lực (nếu có)")
    nguon_thu_thap: Optional[str] = Field(None, description="Nguồn thu thập")
    ngay_dang_cong_bao: Optional[str] = Field(None, description="Ngày đăng công báo")
    nganh: Optional[str] = Field(None, example="Tài nguyên - Môi trường", description="Ngành")
    linh_vuc: Optional[str] = Field(None, example="Đất đai", description="Lĩnh vực")
    chuc_danh: Optional[str] = Field(None, description="Chức danh người ký")
    nguoi_ky: Optional[str] = Field(None, example="Vương Đình Huệ", description="Người ký")
    pham_vi: Optional[str] = Field(None, description="Phạm vi áp dụng")
    thong_tin_ap_dung: Optional[str] = Field(None, description="Thông tin áp dụng bổ sung")
    content_html: Optional[str] = Field(None, description="Toàn văn HTML của văn bản (có thể rất lớn)")


class RelationshipInfo(BaseModel):
    """Thông tin mối liên kết pháp lý giữa hai văn bản."""
    doc_id: int = Field(..., example=38920, description="ID văn bản gốc")
    other_doc_id: int = Field(..., example=12345, description="ID văn bản liên quan")
    relationship: str = Field(..., example="Được sửa đổi bởi", description="Loại quan hệ")
    other_doc_title: str = Field(..., example="Nghị định 43/2014/NĐ-CP", description="Tiêu đề văn bản liên quan")
    other_doc_so_ky_hieu: Optional[str] = Field(None, example="43/2014/NĐ-CP", description="Số ký hiệu văn bản liên quan")


class StatsResponse(BaseModel):
    """Thống kê tổng quan cơ sở dữ liệu."""
    total_documents: int = Field(..., example=153420, description="Tổng số văn bản")
    total_relationships: int = Field(..., example=897890, description="Tổng số mối liên kết pháp lý")
    by_document_type: Dict[str, int] = Field(..., description="Phân bổ theo loại văn bản")
    by_effectiveness_status: Dict[str, int] = Field(..., description="Phân bổ theo tình trạng hiệu lực")


class PaginatedSearchResponse(BaseModel):
    """Kết quả tìm kiếm có phân trang."""
    total: int = Field(..., example=2450, description="Tổng số kết quả khớp")
    limit: int = Field(..., example=20, description="Số lượng tối đa trả về")
    offset: int = Field(..., example=0, description="Vị trí bắt đầu")
    results: List[LawBrief] = Field(..., description="Danh sách văn bản")


class CategoryItem(BaseModel):
    """Một mục trong danh mục."""
    name: str = Field(..., example="Luật", description="Tên danh mục")
    count: int = Field(..., example=850, description="Số lượng văn bản")


class ErrorResponse(BaseModel):
    """Thông tin lỗi trả về."""
    detail: str = Field(..., example="Không tìm thấy văn bản có ID 999999")


# ╔══════════════════════════════════════════════════════════════╗
# ║                      API ENDPOINTS                          ║
# ╚══════════════════════════════════════════════════════════════╝


# ─────────────────── GENERAL ───────────────────

@app.get(
    "/",
    response_model=HealthResponse,
    tags=["🏠 General"],
    summary="Kiểm tra trạng thái hệ thống",
    description="Trả về trạng thái hoạt động của API, đường dẫn database, tổng số văn bản đã tải và link tới tài liệu.",
)
def welcome():
    """
    **Health-check & Welcome endpoint.**

    Sử dụng endpoint này để:
    - Kiểm tra API đang hoạt động.
    - Xem tổng số văn bản đã tải vào CSDL.
    - Truy cập nhanh tới trang tài liệu.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM documents")
    total_docs = cursor.fetchone()[0]
    conn.close()

    return {
        "status": "online",
        "message": "Chào mừng đến với API Dữ Liệu Pháp Luật Việt Nam!",
        "database_file": os.path.abspath(DB_NAME),
        "total_documents_loaded": total_docs,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }


# ─────────────────── STATISTICS ───────────────────

@app.get(
    "/laws/stats",
    response_model=StatsResponse,
    tags=["📊 Thống kê"],
    summary="Thống kê tổng quan cơ sở dữ liệu",
    description="Trả về tổng số văn bản, tổng mối liên kết, phân bổ theo loại văn bản và theo tình trạng hiệu lực.",
)
def get_stats():
    """
    **Phân tích tổng quan kho dữ liệu.**

    Kết quả bao gồm:
    - `total_documents`: Tổng số văn bản pháp luật.
    - `total_relationships`: Tổng số mối liên kết pháp lý.
    - `by_document_type`: Số lượng theo từng loại (Luật, Nghị định, Thông tư…).
    - `by_effectiveness_status`: Số lượng theo tình trạng (Còn hiệu lực, Hết hiệu lực…).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total documents
    cursor.execute("SELECT count(*) FROM documents")
    total_docs = cursor.fetchone()[0]

    # Total relationships
    cursor.execute("SELECT count(*) FROM relationships")
    total_rels = cursor.fetchone()[0]

    # Count by type
    cursor.execute(
        "SELECT loai_van_ban, count(*) FROM documents GROUP BY loai_van_ban ORDER BY count(*) DESC"
    )
    types_count = {row[0] or "Khác": row[1] for row in cursor.fetchall()}

    # Count by status
    cursor.execute(
        "SELECT tinh_trang_hieu_luc, count(*) FROM documents GROUP BY tinh_trang_hieu_luc ORDER BY count(*) DESC"
    )
    status_count = {row[0] or "Không xác định": row[1] for row in cursor.fetchall()}

    conn.close()

    return {
        "total_documents": total_docs,
        "total_relationships": total_rels,
        "by_document_type": types_count,
        "by_effectiveness_status": status_count,
    }


# ─────────────────── SEARCH & RETRIEVAL ───────────────────

@app.get(
    "/laws/search",
    response_model=PaginatedSearchResponse,
    tags=["🔍 Tìm kiếm & Tra cứu"],
    summary="Tìm kiếm văn bản pháp luật",
    description=(
        "Tìm kiếm nhanh trong toàn bộ kho dữ liệu. Hỗ trợ:\n"
        "- Từ khóa tự do (tìm trong tiêu đề + số ký hiệu).\n"
        "- Lọc theo loại văn bản, tình trạng hiệu lực, lĩnh vực.\n"
        "- Phân trang bằng `limit` + `offset`."
    ),
    responses={
        200: {
            "description": "Danh sách văn bản khớp điều kiện",
            "content": {
                "application/json": {
                    "example": {
                        "total": 2450,
                        "limit": 20,
                        "offset": 0,
                        "results": [
                            {
                                "id": 38920,
                                "title": "Luật Đất đai 2024",
                                "so_ky_hieu": "31/2024/QH15",
                                "ngay_ban_hanh": "18/01/2024",
                                "loai_van_ban": "Luật",
                                "co_quan_ban_hanh": "Quốc hội",
                                "tinh_trang_hieu_luc": "Còn hiệu lực",
                            }
                        ],
                    }
                }
            },
        }
    },
)
def search_laws(
    q: Optional[str] = Query(
        None,
        description="Từ khóa tìm kiếm (trong tiêu đề hoặc số ký hiệu)",
        examples=["đất đai", "thuế GTGT", "45/2019/QH14"],
    ),
    loai_van_ban: Optional[str] = Query(
        None,
        description="Lọc theo loại văn bản",
        examples=["Luật", "Nghị định", "Thông tư"],
    ),
    co_quan_ban_hanh: Optional[str] = Query(
        None,
        description="Lọc theo cơ quan ban hành",
        examples=["Quốc hội", "Chính phủ", "Bộ Tài chính"],
    ),
    status: Optional[str] = Query(
        None,
        alias="tinh_trang",
        description="Lọc theo tình trạng hiệu lực",
        examples=["Còn hiệu lực", "Hết hiệu lực"],
    ),
    linh_vuc: Optional[str] = Query(
        None,
        description="Lọc theo lĩnh vực hoặc ngành",
        examples=["Hình sự", "Đất đai", "Thuế - Phí - Lệ phí"],
    ),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả tối đa trả về (1–100)"),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu (dùng cho phân trang)"),
):
    """
    **Tìm kiếm và lọc văn bản pháp luật.**

    ### Ví dụ sử dụng

    | Mục đích | URL |
    |---|---|
    | Tìm "đất đai" | `/laws/search?q=đất đai` |
    | Chỉ lấy Luật | `/laws/search?loai_van_ban=Luật` |
    | Còn hiệu lực | `/laws/search?tinh_trang=Còn hiệu lực` |
    | Trang 2 | `/laws/search?q=thuế&limit=20&offset=20` |
    | Kết hợp | `/laws/search?q=lao động&loai_van_ban=Nghị định&tinh_trang=Còn hiệu lực` |
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clauses = ["1=1"]
    params: list = []

    if q:
        where_clauses.append("(title LIKE ? OR so_ky_hieu LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    if loai_van_ban:
        where_clauses.append("loai_van_ban = ?")
        params.append(loai_van_ban)

    if co_quan_ban_hanh:
        where_clauses.append("co_quan_ban_hanh LIKE ?")
        params.append(f"%{co_quan_ban_hanh}%")

    if status:
        where_clauses.append("tinh_trang_hieu_luc = ?")
        params.append(status)

    if linh_vuc:
        where_clauses.append("(linh_vuc LIKE ? OR nganh LIKE ?)")
        params.extend([f"%{linh_vuc}%", f"%{linh_vuc}%"])

    where_sql = " AND ".join(where_clauses)

    # Count total matching results
    count_query = f"SELECT count(*) FROM documents WHERE {where_sql}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    # Fetch paginated results
    data_query = f"""
        SELECT id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, co_quan_ban_hanh, tinh_trang_hieu_luc
        FROM documents
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(data_query, params + [limit, offset])
    rows = cursor.fetchall()
    conn.close()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [dict(row) for row in rows],
    }


@app.get(
    "/laws/{law_id}",
    response_model=LawDetail,
    tags=["🔍 Tìm kiếm & Tra cứu"],
    summary="Lấy chi tiết một văn bản",
    description="Trả về toàn bộ metadata và nội dung HTML (toàn văn) của một văn bản pháp luật theo ID.",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Không tìm thấy văn bản với ID đã cho.",
        }
    },
)
def get_law_detail(
    law_id: int = Path(..., description="ID duy nhất của văn bản pháp luật", example=38920),
):
    """
    **Lấy chi tiết toàn văn HTML và siêu dữ liệu đầy đủ.**

    ⚠️ **Lưu ý:** Trường `content_html` có thể chứa nội dung HTML rất lớn (hàng trăm KB).
    Chỉ gọi endpoint này khi thực sự cần toàn văn.

    ### Ví dụ
    ```
    GET /laws/38920
    ```
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM documents WHERE id = ?", (law_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy văn bản có ID {law_id}",
        )

    return dict(row)


# ─────────────────── RELATIONSHIPS ───────────────────

@app.get(
    "/laws/{law_id}/relationships",
    response_model=List[RelationshipInfo],
    tags=["🔗 Quan hệ pháp lý"],
    summary="Xem quan hệ pháp lý của văn bản",
    description=(
        "Trả về danh sách tất cả các mối liên kết pháp lý liên quan đến văn bản, bao gồm: "
        "sửa đổi, bổ sung, thay thế, hướng dẫn thi hành, bãi bỏ..."
    ),
    responses={
        200: {
            "description": "Danh sách quan hệ pháp lý",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "doc_id": 38920,
                            "other_doc_id": 12345,
                            "relationship": "Được sửa đổi bởi",
                            "other_doc_title": "Nghị định 43/2014/NĐ-CP hướng dẫn thi hành Luật Đất đai",
                            "other_doc_so_ky_hieu": "43/2014/NĐ-CP",
                        }
                    ]
                }
            },
        }
    },
)
def get_law_relationships(
    law_id: int = Path(..., description="ID văn bản cần xem quan hệ", example=38920),
):
    """
    **Tra cứu mạng lưới liên kết pháp lý.**

    Endpoint này trả về tất cả các mối quan hệ mà văn bản tham gia
    (cả chiều đi lẫn chiều đến). Ví dụ:
    - Văn bản A **sửa đổi** văn bản B
    - Văn bản A **được hướng dẫn bởi** văn bản C

    ### Ví dụ
    ```
    GET /laws/38920/relationships
    ```
    """
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


# ─────────────────── CATEGORIES ───────────────────

@app.get(
    "/laws/categories/types",
    response_model=List[CategoryItem],
    tags=["🏷️ Danh mục"],
    summary="Danh sách loại văn bản",
    description="Liệt kê tất cả loại văn bản có trong CSDL (Luật, Nghị định, Thông tư…) cùng số lượng.",
)
def get_document_types():
    """
    **Lấy danh sách tất cả loại văn bản.**

    Hữu ích để xây dựng bộ lọc dropdown trên giao diện frontend.

    ### Ví dụ kết quả
    ```json
    [
      {"name": "Nghị định", "count": 15420},
      {"name": "Thông tư", "count": 12830},
      {"name": "Luật", "count": 850}
    ]
    ```
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT loai_van_ban, count(*) as cnt FROM documents GROUP BY loai_van_ban ORDER BY cnt DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    return [{"name": row[0] or "Khác", "count": row[1]} for row in rows]


@app.get(
    "/laws/categories/fields",
    response_model=List[CategoryItem],
    tags=["🏷️ Danh mục"],
    summary="Danh sách lĩnh vực",
    description="Liệt kê tất cả lĩnh vực pháp luật có trong CSDL (Đất đai, Hình sự, Thuế…) cùng số lượng.",
)
def get_fields():
    """
    **Lấy danh sách tất cả lĩnh vực pháp luật.**

    ### Ví dụ kết quả
    ```json
    [
      {"name": "Thuế - Phí - Lệ phí", "count": 8520},
      {"name": "Đất đai - Nhà ở", "count": 5430}
    ]
    ```
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT linh_vuc, count(*) as cnt FROM documents WHERE linh_vuc IS NOT NULL AND linh_vuc != '' GROUP BY linh_vuc ORDER BY cnt DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    return [{"name": row[0], "count": row[1]} for row in rows]


@app.get(
    "/laws/categories/agencies",
    response_model=List[CategoryItem],
    tags=["🏷️ Danh mục"],
    summary="Danh sách cơ quan ban hành",
    description="Liệt kê tất cả cơ quan ban hành có trong CSDL (Quốc hội, Chính phủ, Bộ Tài chính…) cùng số lượng.",
)
def get_agencies():
    """
    **Lấy danh sách tất cả cơ quan ban hành.**

    ### Ví dụ kết quả
    ```json
    [
      {"name": "Chính phủ", "count": 18520},
      {"name": "Quốc hội", "count": 1230}
    ]
    ```
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT co_quan_ban_hanh, count(*) as cnt FROM documents WHERE co_quan_ban_hanh IS NOT NULL AND co_quan_ban_hanh != '' GROUP BY co_quan_ban_hanh ORDER BY cnt DESC"
    )
    rows = cursor.fetchall()
    conn.close()

    return [{"name": row[0], "count": row[1]} for row in rows]


# --- Startup / Run Config ---
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=API_PORT,
        reload=True,
    )
