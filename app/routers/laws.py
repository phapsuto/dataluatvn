import sqlite3
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, Path, HTTPException

from app.dependencies import require_api_key
from app.database import get_db_connection, get_content_connection, simple_ttl_cache
from app.schemas.laws import (
    StatsResponse, PaginatedSearchResponse, CategoryItem,
    LawDetail, RelationshipInfo, ArticleModification,
)

router = APIRouter(prefix="/laws", tags=["🔍 Tìm kiếm & Tra cứu (Luật)"])


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


@router.get("/stats", response_model=StatsResponse, tags=["📊 Thống kê (Luật)"], summary="Thống kê tổng quan")
def get_stats(_key=Depends(require_api_key)):
    """Thống kê tổng quan cơ sở dữ liệu. **Yêu cầu API Key.**"""
    return _get_cached_stats()


# ─────────────────── SEARCH & RETRIEVAL ───────────────────

@router.get("/search", response_model=PaginatedSearchResponse, summary="Tìm kiếm văn bản")
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
        "results": [dict(r) for r in rows],
    }


# ─────────────────── CATEGORIES ───────────────────

@simple_ttl_cache(ttl_seconds=3600)
def _get_cached_document_types():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT loai_van_ban, count(*) as cnt FROM documents GROUP BY loai_van_ban ORDER BY cnt DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"name": row[0] or "Khác", "count": row[1]} for row in rows]


@router.get("/categories/types", response_model=List[CategoryItem], tags=["🏷️ Danh mục (Luật)"], summary="Loại văn bản")
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


@router.get("/categories/fields", response_model=List[CategoryItem], tags=["🏷️ Danh mục (Luật)"], summary="Lĩnh vực")
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


@router.get("/categories/agencies", response_model=List[CategoryItem], tags=["🏷️ Danh mục (Luật)"], summary="Cơ quan ban hành")
def get_agencies(_key=Depends(require_api_key)):
    """Danh sách cơ quan ban hành. **Yêu cầu API Key.**"""
    return _get_cached_agencies()


# ─────────────────── DETAIL ───────────────────

@router.get("/{law_id}", response_model=LawDetail, summary="Chi tiết văn bản")
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

@router.get("/{law_id}/relationships", response_model=List[RelationshipInfo], tags=["🔗 Quan hệ pháp lý (Luật)"], summary="Quan hệ pháp lý")
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


@router.get("/{law_id}/article-modifications", response_model=List[ArticleModification], tags=["🔗 Quan hệ pháp lý (Luật)"], summary="Các điều khoản bị sửa đổi")
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
