import math
import sqlite3
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, Path, HTTPException

from app.dependencies import require_api_key
from app.database import get_db_connection
from app.schemas.laws import CategoryItem
from app.schemas.phapdien import (
    PhapdienArticleBrief, PhapdienArticleDetail,
    PaginatedPhapdienResponse, GlossaryItem,
)

router = APIRouter(prefix="/phapdien", tags=["📖 Pháp Điển"])


@router.get("/stats", response_model=Dict[str, Any], summary="Thống kê Pháp Điển")
def get_phapdien_stats(_key=Depends(require_api_key)):
    """Thống kê tổng quan dữ liệu Bộ Pháp Điển. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM phapdien_articles")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT subject_title) FROM phapdien_articles")
    subjects = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT topic_title) FROM phapdien_articles")
    topics = c.fetchone()[0]
    c.execute("SELECT topic_title, COUNT(*) as cnt FROM phapdien_articles GROUP BY topic_title ORDER BY cnt DESC LIMIT 10")
    top_topics = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    return {
        "total_articles": total,
        "total_subjects": subjects,
        "total_topics": topics,
        "top_topics": top_topics,
    }


@router.get("/subjects", response_model=List[CategoryItem], summary="Danh sách Đề mục")
def get_phapdien_subjects(_key=Depends(require_api_key)):
    """Danh sách các Đề mục trong Bộ Pháp Điển. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT subject_title, COUNT(*) as cnt FROM phapdien_articles GROUP BY subject_title ORDER BY cnt DESC")
    rows = c.fetchall()
    conn.close()
    return [{"name": r[0] or "Khác", "count": r[1]} for r in rows]


@router.get("/topics", response_model=List[CategoryItem], summary="Danh sách Chủ đề")
def get_phapdien_topics(_key=Depends(require_api_key)):
    """Danh sách các Chủ đề trong Bộ Pháp Điển. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT topic_title, COUNT(*) as cnt FROM phapdien_articles GROUP BY topic_title ORDER BY cnt DESC")
    rows = c.fetchall()
    conn.close()
    return [{"name": r[0] or "Khác", "count": r[1]} for r in rows]


@router.get("/glossary", response_model=List[GlossaryItem], summary="Thuật ngữ VI-EN")
def get_phapdien_glossary(_key=Depends(require_api_key)):
    """Lấy danh sách thuật ngữ VI-EN từ ontology glossary. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, category, vi, en, note FROM phapdien_glossary ORDER BY vi ASC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


@router.get("/search", response_model=PaginatedPhapdienResponse, summary="Tìm kiếm Điều khoản")
def search_phapdien(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm FTS"),
    topic: Optional[str] = Query(None, description="Lọc theo Chủ đề"),
    subject: Optional[str] = Query(None, description="Lọc theo Đề mục"),
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số kết quả mỗi trang"),
    _key=Depends(require_api_key),
):
    """Tìm kiếm các Điều khoản trong Bộ Pháp Điển. Hỗ trợ FTS5. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clauses = []
    params = []

    if q:
        query_cleaned = q.replace("'", "''").replace('"', '""')
        where_clauses.append("rowid IN (SELECT rowid FROM phapdien_fts WHERE phapdien_fts MATCH ?)")
        params.append(f'"{query_cleaned}"')

    if topic:
        where_clauses.append("topic_title = ?")
        params.append(topic)

    if subject:
        where_clauses.append("subject_title = ?")
        params.append(subject)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    count_query = f"SELECT count(*) FROM phapdien_articles {where_sql}"
    try:
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
    except sqlite3.OperationalError:
        total = 0

    offset = (page - 1) * limit

    data_query = f"""
        SELECT article_anchor, article_title, subject_title, topic_title
        FROM phapdien_articles {where_sql}
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


@router.get("/{article_anchor}", response_model=PhapdienArticleDetail, summary="Chi tiết Điều khoản")
def get_phapdien_detail(article_anchor: str = Path(..., description="Mã định danh (anchor) của Điều khoản"), _key=Depends(require_api_key)):
    """Lấy chi tiết toàn bộ thông tin của 1 Điều khoản Pháp Điển. **Yêu cầu API Key.**"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM phapdien_articles WHERE article_anchor = ?", (article_anchor,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy Điều khoản")
    return dict(row)
