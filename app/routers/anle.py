import math
import sqlite3
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, Path, HTTPException

from app.dependencies import require_api_key
from app.database import get_db_connection
from app.schemas.laws import CategoryItem
from app.schemas.anle import AnleBrief, AnleDetail, PaginatedAnleResponse

router = APIRouter(prefix="/anle", tags=["⚖️ Án Lệ"])


@router.get("/stats", response_model=Dict[str, Any], summary="Thống kê Án Lệ")
def get_anle_stats(_key=Depends(require_api_key)):
    """Thống kê tổng quan dữ liệu Bản Án & Án Lệ. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM anle_documents")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM anle_documents WHERE precedent_number IS NOT NULL AND precedent_number != ''")
    precedents = c.fetchone()[0]

    c.execute("SELECT case_type, COUNT(*) FROM anle_documents WHERE case_type IS NOT NULL GROUP BY case_type")
    by_case = {r[0]: r[1] for r in c.fetchall()}

    c.execute("SELECT court_level, COUNT(*) FROM anle_documents WHERE court_level IS NOT NULL GROUP BY court_level")
    by_court = {r[0]: r[1] for r in c.fetchall()}
    conn.close()

    return {
        "total_documents": total,
        "official_precedents": precedents,
        "normal_cases": total - precedents,
        "by_case_type": by_case,
        "by_court_level": by_court,
    }


@router.get("/categories/case-types", response_model=List[CategoryItem], summary="Loại vụ án")
def get_anle_case_types(_key=Depends(require_api_key)):
    """Danh sách các loại vụ án. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT case_type, COUNT(*) as cnt FROM anle_documents WHERE case_type IS NOT NULL GROUP BY case_type ORDER BY cnt DESC")
    rows = c.fetchall()
    conn.close()
    return [{"name": r[0], "count": r[1]} for r in rows]


@router.get("/categories/court-levels", response_model=List[CategoryItem], summary="Cấp tòa")
def get_anle_court_levels(_key=Depends(require_api_key)):
    """Danh sách các cấp tòa án. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT court_level, COUNT(*) as cnt FROM anle_documents WHERE court_level IS NOT NULL GROUP BY court_level ORDER BY cnt DESC")
    rows = c.fetchall()
    conn.close()
    return [{"name": r[0], "count": r[1]} for r in rows]


@router.get("/search", response_model=PaginatedAnleResponse, summary="Tìm kiếm Án Lệ")
def search_anle(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm Full-text search"),
    case_type: Optional[str] = Query(None, description="Lọc theo loại vụ án"),
    court_level: Optional[str] = Query(None, description="Lọc theo cấp tòa"),
    only_precedents: bool = Query(False, description="Chỉ tìm Án Lệ chính thức"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số kết quả mỗi trang"),
    _key=Depends(require_api_key),
):
    """Tìm kiếm siêu tốc trên dữ liệu Án Lệ & Bản Án bằng FTS5. Hỗ trợ bộ lọc. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if q:
        query_cleaned = q.replace("'", "''").replace('"', '""')
        where_clauses.append("rowid IN (SELECT rowid FROM anle_fts WHERE anle_fts MATCH ?)")
        params.append(f'"{query_cleaned}"')

    if case_type:
        where_clauses.append("case_type = ?")
        params.append(case_type)

    if court_level:
        where_clauses.append("court_level = ?")
        params.append(court_level)

    if only_precedents:
        where_clauses.append("precedent_number IS NOT NULL AND precedent_number != ''")

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    count_query = f"SELECT count(*) FROM anle_documents {where_sql}"
    try:
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
    except sqlite3.OperationalError:
        total = 0

    offset = (page - 1) * limit
    order_sql = "ORDER BY year DESC, rowid DESC"
    if q:
        order_sql = ""  # fts5 naturally ranks results

    data_query = f"""
        SELECT doc_name, title, doc_code, doc_type, case_type, year, court_level, precedent_number
        FROM anle_documents {where_sql}
        {order_sql}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    try:
        cursor.execute(data_query, params)
        results = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        results = []
    conn.close()

    total_pages = math.ceil(total / limit) if limit > 0 else 1
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "total_pages": total_pages,
        "current_page": page,
        "has_next": page < total_pages,
        "has_previous": page > 1,
        "results": results,
    }


@router.get("/{doc_name}", response_model=AnleDetail, summary="Chi tiết Án Lệ")
def get_anle_detail(doc_name: str = Path(..., description="Mã doc_name của bản án"), _key=Depends(require_api_key)):
    """Lấy chi tiết và toàn văn markdown của Bản Án/Án Lệ. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM anle_documents WHERE doc_name = ?", (doc_name,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản án")
    return dict(row)
