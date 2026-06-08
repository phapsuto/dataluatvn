import sqlite3
import io
import re
from datetime import datetime
from typing import Optional, List
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from bs4 import BeautifulSoup
from fastapi.responses import StreamingResponse

from fastapi import APIRouter, Depends, Query, Path, HTTPException

from app.dependencies import require_api_key
from app.database import get_db_connection, get_content_connection, simple_ttl_cache
from app.schemas.laws import (
    StatsResponse, PaginatedSearchResponse, CategoryItem,
    LawDetail, RelationshipInfo, ArticleModification,
    ProvinceItem, WardItem, PaginatedChunkSearchResponse,
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

# Stopwords tiếng Việt — loại bỏ khi xây dựng FTS query
VIETNAMESE_STOPWORDS = {
    # Đại từ & chỉ định
    "tôi", "tui", "mình", "ta", "chúng", "các", "những", "một", "này", "đó", "kia",
    "nào", "gì", "nào", "ai", "đâu", "sao", "bao", "mấy",
    # Giới từ & liên từ
    "của", "và", "với", "trong", "trên", "dưới", "ngoài", "giữa", "bên", "về",
    "cho", "đến", "từ", "tại", "theo", "bằng", "qua", "vào", "hay", "hoặc",
    "nhưng", "mà", "rằng", "nếu", "khi", "vì", "do", "bởi", "để",
    # Phó từ & trạng từ
    "đã", "đang", "sẽ", "sắp", "vẫn", "còn", "rất", "lắm", "quá", "hơn",
    "nhất", "không", "chưa", "chẳng", "nên", "cần", "phải", "được", "bị",
    "có", "là", "thì", "cũng", "lại", "rồi", "mới", "cứ", "đều",
    # Từ nghi vấn phổ biến
    "thế", "như", "thế nào", "như thế nào", "bao nhiêu", "vậy",
    # Từ chức năng khác
    "việc", "cái", "con", "người", "điều", "khoản",
}

def parse_fts_query(q: str) -> str:
    """
    Phân tích query FTS5 thông minh cho cả keyword search lẫn câu hỏi tự nhiên.
    
    Chiến lược 3 tầng:
    1. Nếu query ngắn (1-3 từ sau lọc): exact match + prefix
    2. Nếu query vừa (4-6 từ): exact phrase OR (AND tất cả từ khóa)
    3. Nếu query dài (>6 từ, ngôn ngữ tự nhiên): OR từ khóa chính + NEAR
    """
    # Bước 1: Loại bỏ ký tự đặc biệt FTS
    q_clean = re.sub(r'[^\w\s]', ' ', q).strip()
    all_words = [w for w in q_clean.split() if w]
    if not all_words:
        return ""
    
    # Bước 2: Loại bỏ stopwords và từ quá ngắn (≤1 ký tự)
    keywords = [w for w in all_words if w.lower() not in VIETNAMESE_STOPWORDS and len(w) > 1]
    
    # Nếu sau khi lọc không còn từ nào, dùng lại all_words
    if not keywords:
        keywords = [w for w in all_words if len(w) > 1]
    if not keywords:
        keywords = all_words
    
    # Bước 3: Áp dụng chiến lược theo độ dài
    if len(keywords) == 1:
        return f"{keywords[0]}*"
    
    if len(keywords) <= 3:
        # Query ngắn → exact phrase OR (AND prefix)
        exact_phrase = " ".join(keywords)
        and_query = " AND ".join([f"{w}*" for w in keywords])
        return f'"{exact_phrase}" OR ({and_query})'
    
    if len(keywords) <= 6:
        # Query vừa → AND tất cả (precision cao)
        and_query = " AND ".join(keywords)
        # Fallback: AND chỉ top 3 từ dài nhất
        top_words = sorted(keywords, key=len, reverse=True)[:3]
        and_fallback = " AND ".join(top_words)
        return f"({and_query}) OR ({and_fallback})"
    
    # Query dài (câu hỏi tự nhiên) → ưu tiên AND precision
    # Lấy top 7 từ khóa dài nhất (quan trọng nhất)
    top_keywords = sorted(keywords, key=len, reverse=True)[:7]
    
    # Chiến lược multi-tier:
    # Tier 1: AND top 5 (precision cao nhất)
    # Tier 2: AND top 3 (fallback rộng hơn)  
    and_top5 = " AND ".join(top_keywords[:5])
    and_top3 = " AND ".join(top_keywords[:3])
    return f"({and_top5}) OR ({and_top3})"

def get_province_search_terms(province_code: str, conn) -> list:
    cursor = conn.cursor()
    cursor.execute("SELECT name, full_name FROM provinces WHERE code = ?", (province_code,))
    row = cursor.fetchone()
    if not row:
        return []
    p_name = row['name']
    p_fullname = row['full_name']
    terms = {p_name, p_fullname}
    for term in list(terms):
        term_alt = term.replace("oà", "òa").replace("oá", "óa").replace("oả", "ỏa")
        term_alt2 = term.replace("òa", "oà").replace("óa", "oá").replace("ỏa", "oả")
        terms.add(term_alt)
        terms.add(term_alt2)
    return list(terms)

def get_ward_search_terms(ward_code: str, conn) -> list:
    cursor = conn.cursor()
    cursor.execute("SELECT name, full_name FROM wards WHERE code = ?", (ward_code,))
    row = cursor.fetchone()
    if not row:
        return []
    w_name = row['name']
    w_fullname = row['full_name']
    terms = {w_name, w_fullname}
    for term in list(terms):
        term_alt = term.replace("oà", "òa").replace("oá", "óa").replace("oả", "ỏa")
        term_alt2 = term.replace("òa", "oà").replace("óa", "oá").replace("ỏa", "oả")
        terms.add(term_alt)
        terms.add(term_alt2)
    return list(terms)


@router.get("/search", response_model=PaginatedSearchResponse, summary="Tìm kiếm văn bản")
def search_laws(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm"),
    loai_van_ban: Optional[str] = Query(None, description="Lọc theo loại văn bản"),
    co_quan_ban_hanh: Optional[str] = Query(None, description="Lọc theo cơ quan ban hành"),
    status: Optional[str] = Query(None, alias="tinh_trang", description="Lọc theo tình trạng hiệu lực"),
    linh_vuc: Optional[str] = Query(None, description="Lọc theo lĩnh vực"),
    province_code: Optional[str] = Query(None, description="Mã tỉnh/thành phố để lọc địa phương"),
    ward_code: Optional[str] = Query(None, description="Mã quận huyện/phường xã để lọc địa phương"),
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

    # Filter out future dates (e.g., typos like 3024 or 2055) relative to today's date
    today_str = datetime.now().strftime("%Y-%m-%d")
    where_clauses.append(
        "(d.ngay_ban_hanh IS NULL OR d.ngay_ban_hanh = '' OR "
        "(length(d.ngay_ban_hanh) = 10 AND "
        "substr(d.ngay_ban_hanh, 7, 4) || '-' || substr(d.ngay_ban_hanh, 4, 2) || '-' || substr(d.ngay_ban_hanh, 1, 2) <= ?))"
    )
    params.append(today_str)


    if require_content:
        where_clauses.append("d.has_content = 1")

    if q:
        fts_query = parse_fts_query(q)
        if fts_query:
            # Ưu tiên content_fts (index title + nội dung toàn văn) nếu có
            # Fallback về documents_fts (chỉ title) nếu chưa build content_fts
            try:
                cursor.execute("SELECT 1 FROM content_fts LIMIT 1")
                where_clauses.append("content_fts MATCH ?")
                params.append(fts_query)
                from_clause = "documents d JOIN content_fts ON d.id = content_fts.rowid"
            except Exception:
                where_clauses.append("documents_fts MATCH ?")
                params.append(fts_query)
                from_clause = "documents d JOIN documents_fts ON d.id = documents_fts.rowid"

    if province_code:
        terms = get_province_search_terms(province_code, conn)
        if terms:
            province_clauses = []
            for t in terms:
                province_clauses.append("d.pham_vi LIKE ? OR d.co_quan_ban_hanh LIKE ?")
                params.extend([f"%{t}%", f"%{t}%"])
            where_clauses.append(f"({' OR '.join(province_clauses)})")

    if ward_code:
        terms = get_ward_search_terms(ward_code, conn)
        if terms:
            ward_clauses = []
            for t in terms:
                ward_clauses.append("d.pham_vi LIKE ? OR d.co_quan_ban_hanh LIKE ?")
                params.extend([f"%{t}%", f"%{t}%"])
            where_clauses.append(f"({' OR '.join(ward_clauses)})")

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

    order_params = []
    if q:
        # ORDERING cho search: Relevance trước, status/type sau
        # 1. Exact match so_ky_hieu (người dùng tìm đúng số hiệu)
        # 2. FTS rank (BM25 relevance — quan trọng nhất cho tìm kiếm nội dung)
        # 3. Status hiệu lực (Còn > Hết một phần > NULL > Hết)
        # 4. Loại văn bản (Luật > Nghị định > Thông tư)
        # 5. Ngày ban hành mới nhất
        order_clause = (
            "CASE WHEN d.so_ky_hieu = ? THEN 2 WHEN d.so_ky_hieu LIKE ? THEN 1 ELSE 0 END DESC, "
            "content_fts.rank, "
            "CASE "
            "  WHEN d.tinh_trang_hieu_luc LIKE '%Còn hiệu lực%' THEN 3 "
            "  WHEN d.tinh_trang_hieu_luc LIKE '%Hết hiệu lực một phần%' THEN 2 "
            "  WHEN d.tinh_trang_hieu_luc IS NULL OR d.tinh_trang_hieu_luc = '' THEN 1 "
            "  WHEN d.tinh_trang_hieu_luc LIKE '%Hết hiệu lực%' THEN 0 "
            "  ELSE 1 "
            "END DESC, "
            "CASE LOWER(d.loai_van_ban) "
            "  WHEN 'hiến pháp' THEN 10 "
            "  WHEN 'bộ luật' THEN 9 "
            "  WHEN 'luật' THEN 9 "
            "  WHEN 'pháp lệnh' THEN 8 "
            "  WHEN 'nghị định' THEN 7 "
            "  WHEN 'nghị quyết' THEN 6 "
            "  WHEN 'quyết định' THEN 5 "
            "  WHEN 'thông tư' THEN 4 "
            "  ELSE 1 "
            "END DESC, "
            "substr(d.ngay_ban_hanh, 7, 4) DESC, substr(d.ngay_ban_hanh, 4, 2) DESC, substr(d.ngay_ban_hanh, 1, 2) DESC, d.id DESC"
        )
        q_strip = q.strip()
        order_params = [q_strip, f"%{q_strip}%"]
    else:
        order_clause = (
            "CASE WHEN d.tinh_trang_hieu_luc IN ('Hết hiệu lực toàn bộ', 'Hết hiệu lực') THEN 0 ELSE 1 END DESC, "
            "CASE LOWER(d.loai_van_ban) "
            "  WHEN 'hiến pháp' THEN 10 "
            "  WHEN 'bộ luật' THEN 9 "
            "  WHEN 'luật' THEN 9 "
            "  WHEN 'pháp lệnh' THEN 8 "
            "  WHEN 'nghị định' THEN 7 "
            "  WHEN 'nghị quyết' THEN 6 "
            "  WHEN 'quyết định' THEN 5 "
            "  WHEN 'thông tư' THEN 4 "
            "  ELSE 1 "
            "END DESC, "
            "substr(d.ngay_ban_hanh, 7, 4) DESC, substr(d.ngay_ban_hanh, 4, 2) DESC, substr(d.ngay_ban_hanh, 1, 2) DESC, d.id DESC"
        )

    cursor.execute(
        f"SELECT d.id, d.title, d.so_ky_hieu, d.ngay_ban_hanh, d.loai_van_ban, d.co_quan_ban_hanh, d.tinh_trang_hieu_luc "
        f"FROM {from_clause} WHERE {where_sql} ORDER BY {order_clause} LIMIT ? OFFSET ?",
        params + order_params + [limit, offset],
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



@router.get("/chunk-search", response_model=PaginatedChunkSearchResponse, summary="Tìm kiếm theo điều khoản (FTS5 trên Chunks)")
def chunk_search_laws(
    q: str = Query(..., description="Từ khóa tìm kiếm"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _key=Depends(require_api_key),
):
    """
    Tìm kiếm chi tiết đến cấp độ Điều (Article) của văn bản sử dụng FTS5 trên bảng chunks.
    Trả về danh sách các chunks (điều khoản) khớp kèm theo thông tin văn bản gốc.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    fts_query = parse_fts_query(q)
    if not fts_query:
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "total_pages": 0,
            "current_page": 1,
            "has_next": False,
            "has_previous": False,
            "results": [],
        }

    # Count total matching chunks
    try:
        cursor.execute("""
            SELECT count(*) 
            FROM chunks_fts 
            WHERE chunks_fts MATCH ?
        """, (fts_query,))
        total = cursor.fetchone()[0]
    except Exception:
        total = 0

    if total == 0:
        conn.close()
        return {
            "total": 0,
            "limit": limit,
            "offset": offset,
            "total_pages": 0,
            "current_page": 1,
            "has_next": False,
            "has_previous": False,
            "results": [],
        }

    # Fetch matching chunks with metadata
    query = """
        SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.token_estimate,
               d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
               d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
               d.ngay_ban_hanh as document_ngay_ban_hanh
        FROM chunks_fts f
        JOIN document_chunks c ON f.rowid = c.id
        JOIN documents d ON c.doc_id = d.id
        WHERE f.chunks_fts MATCH ?
        ORDER BY f.rank
        LIMIT ? OFFSET ?
    """
    
    try:
        cursor.execute(query, (fts_query, limit, offset))
        rows = cursor.fetchall()
    except Exception as e:
        rows = []
        
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


# ─────────────────── HYBRID SEARCH ───────────────────

@router.get("/hybrid-search", tags=["🔍 Tìm kiếm & Tra cứu (Luật)"], summary="Tìm kiếm Hybrid (BM25 + FTS5 + RRF)")
async def hybrid_search(
    q: str = Query(..., description="Từ khoá tìm kiếm"),
    limit: int = Query(10, ge=1, le=50),
    _api_key: str = Depends(require_api_key),
):
    """
    Tìm kiếm Hybrid: BM25Okapi + FTS5 + Reciprocal Rank Fusion.
    
    Cho kết quả chính xác hơn nhiều so với FTS5 thuần, đặc biệt với
    câu hỏi ngôn ngữ tự nhiên về pháp luật.
    """
    from app.hybrid_search import get_hybrid_engine
    
    engine = get_hybrid_engine()
    if not engine or not engine.is_ready:
        # Fallback về FTS5 nếu hybrid chưa sẵn sàng
        return await search_laws(q=q, limit=limit, _api_key=_api_key)
    
    results = engine.search(q, top_k=limit)
    
    return {
        "total": len(results),
        "limit": limit,
        "offset": 0,
        "engine": "hybrid_bm25_fts5_rrf",
        "results": results,
    }


# ─────────────────── SMART HYBRID SEARCH (PHASE 3) ───────────────────

def normalize_spelling(text: str) -> str:
    if not text:
        return ""
    text = text.replace('òa', 'o\u00e0').replace('óa', 'o\u00e1').replace('ỏa', 'o\u1ea3').replace('õa', 'o\u00e3').replace('ọa', 'o\u1ea1')
    text = text.replace('òe', 'o\u00e8').replace('óe', 'o\u00e9').replace('ỏe', 'o\u1ebd').replace('õe', 'o\u1ebd').replace('ọe', 'o\u1eb9')
    text = text.replace('ủy', 'u\u1ef7').replace('úy', 'u\u00fd').replace('ùy', 'u\u1ef3').replace('ũy', 'u\u1ef5').replace('ụy', 'u\u1ef9')
    text = text.replace('Òa', 'O\u00e0').replace('Óa', 'O\u00e1').replace('Ỏa', 'O\u1ea3').replace('Õa', 'O\u00e3').replace('Ọa', 'O\u1ea1')
    text = text.replace('Òe', 'O\u00e8').replace('Óe', 'O\u00e9').replace('Ỏe', 'O\u1ebd').replace('Õe', 'O\u1ebd').replace('Ọe', 'O\u1eb9')
    text = text.replace('Ủy', 'U\u1ef7').replace('Úy', 'U\u00fd').replace('Ùy', 'U\u1ef3').replace('Ũy', 'U\u1ef5').replace('Ụy', 'U\u1ef9')
    return text

_SMART_SEARCH_MODEL = None
_SMART_SEARCH_INDEX = None

def get_smart_search_resources():
    global _SMART_SEARCH_MODEL, _SMART_SEARCH_INDEX
    import os
    
    # Lazy load sentence-transformers & PyTorch
    if _SMART_SEARCH_MODEL is None:
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
            _SMART_SEARCH_MODEL = SentenceTransformer("bkai-foundation-models/vietnamese-bi-encoder", device=device)
        except Exception as e:
            print(f"⚠️ Không thể load embedding model: {e}")
            
    # Lazy load FAISS index
    if _SMART_SEARCH_INDEX is None:
        index_path = "chunks_faiss.index"
        if os.path.exists(index_path):
            try:
                import faiss
                _SMART_SEARCH_INDEX = faiss.read_index(index_path)
            except Exception as e:
                print(f"⚠️ Không thể load FAISS index từ {index_path}: {e}")
        else:
            print(f"⚠️ Không tìm thấy file index: {index_path}")
            
    return _SMART_SEARCH_MODEL, _SMART_SEARCH_INDEX


@router.get("/smart-search", response_model=PaginatedChunkSearchResponse, summary="Tìm kiếm Hybrid thông minh (FTS5 Chunks + FAISS Vector Chunks + RRF + Metadata Boost)")
def smart_search_laws(
    q: str = Query(..., description="Từ khóa tìm kiếm tự nhiên"),
    loai_van_ban: Optional[str] = Query(None, description="Lọc theo loại văn bản"),
    co_quan_ban_hanh: Optional[str] = Query(None, description="Lọc theo cơ quan ban hành"),
    status: Optional[str] = Query(None, alias="tinh_trang", description="Lọc theo tình trạng hiệu lực"),
    linh_vuc: Optional[str] = Query(None, description="Lọc theo lĩnh vực"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    _key=Depends(require_api_key),
):
    """
    Tìm kiếm ngữ nghĩa kết hợp FTS5, FAISS Vector và thuật toán RRF Boosting (khớp số ký hiệu, độ hiệu lực pháp lý, tình trạng văn bản).
    **Yêu cầu API Key.**
    """
    if not q.strip():
        return {
            "total": 0, "limit": limit, "offset": offset,
            "total_pages": 0, "current_page": 1,
            "has_next": False, "has_previous": False, "results": []
        }

    conn = get_db_connection()
    cursor = conn.cursor()

    # Xây dựng các điều kiện lọc (SQL Filter Clauses)
    where_clauses = []
    sql_params = []
    
    if loai_van_ban:
        where_clauses.append("d.loai_van_ban = ?")
        sql_params.append(loai_van_ban)
    if co_quan_ban_hanh:
        where_clauses.append("d.co_quan_ban_hanh LIKE ?")
        sql_params.append(f"%{co_quan_ban_hanh}%")
    if status:
        where_clauses.append("d.tinh_trang_hieu_luc = ?")
        sql_params.append(status)
    if linh_vuc:
        where_clauses.append("(d.linh_vuc LIKE ? OR d.nganh LIKE ?)")
        sql_params.extend([f"%{linh_vuc}%", f"%{linh_vuc}%"])

    # 1. Trích xuất số ký hiệu từ câu hỏi người dùng bằng Regex
    # Khớp định dạng số ký hiệu VN như 15/2020/NĐ-CP, 24/LĐ-NĐ, 12/QĐ-TTg, 25/2018/QH14
    symbol_patterns = re.findall(r'\b\d+/(?:[A-Za-z0-9À-ỹ-]+/)*[A-Za-z0-9À-ỹ-]+\b', q)
    extracted_symbols = [s.strip().lower() for s in symbol_patterns]

    # Gọi Query Expansion của Phase 4
    from app.query_expansion import expand_query
    expanded_terms = expand_query(q)

    # 2. Chạy FTS5 Search trên Chunks (Top 100)
    fts_query = parse_fts_query(q)
    if fts_query:
        if expanded_terms:
            expanded_clauses = [parse_fts_query(term) for term in expanded_terms if parse_fts_query(term)]
            if expanded_clauses:
                fts_query = f"({fts_query}) OR (" + " OR ".join(expanded_clauses) + ")"
                
        if extracted_symbols:
            # Bổ sung số ký hiệu vào FTS query với mức ưu tiên OR để kéo văn bản đích vào Top 100 thô
            fts_symbols = [re.sub(r'[^\w\s]', ' ', sym).strip() for sym in extracted_symbols]
            symbol_or_clause = " OR ".join([f'"{s}"' for s in fts_symbols if s])
            if symbol_or_clause:
                fts_query = f"({symbol_or_clause}) OR ({fts_query})"

    fts_results = []
    if fts_query:
        try:
            fts_where = " AND ".join(["f.chunks_fts MATCH ?"] + where_clauses)
            fts_sql_params = [fts_query] + sql_params
            cursor.execute(f"""
                SELECT c.id, c.doc_id
                FROM chunks_fts f
                CROSS JOIN document_chunks c ON f.rowid = c.id
                JOIN documents d ON c.doc_id = d.id
                WHERE {fts_where}
                ORDER BY f.rank
                LIMIT 100
            """, fts_sql_params)
            fts_results = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"⚠️ Lỗi truy vấn FTS5 Chunks: {e}")

    query_vector = None
    # 3. Chạy Vector Search trên FAISS (Top 150 để đề phòng lọc bỏ)
    vector_results = []
    model, faiss_index = get_smart_search_resources()
    
    if model and faiss_index:
        try:
            import numpy as np
            import faiss
            q_norm = normalize_spelling(q)
            if expanded_terms:
                q_norm = q_norm + " " + " ".join([normalize_spelling(term) for term in expanded_terms])
                
            query_vector = model.encode([q_norm], show_progress_bar=False, convert_to_numpy=True)
            faiss.normalize_L2(query_vector)
            # Lấy 150 lân cận nhất
            distances, indices = faiss_index.search(query_vector.astype(np.float32), 150)
            
            for cid in indices[0]:
                if cid != -1:
                    vector_results.append(int(cid))
        except Exception as e:
            print(f"⚠️ Lỗi truy vấn Vector Search: {e}")

    # 3. Lọc Post-filtering trong SQL cho kết quả FAISS (đảm bảo đồng nhất bộ lọc)
    vector_matched = []
    cid_to_doc = {}
    if vector_results:
        placeholders = ",".join(["?"] * len(vector_results))
        vec_where = " AND ".join([f"c.id IN ({placeholders})"] + where_clauses)
        vec_sql_params = list(vector_results) + sql_params
        try:
            cursor.execute(f"""
                SELECT c.id, c.doc_id 
                FROM document_chunks c
                JOIN documents d ON c.doc_id = d.id
                WHERE {vec_where}
            """, vec_sql_params)
            for row in cursor.fetchall():
                cid_to_doc[row["id"]] = row["doc_id"]
            
            # Giữ đúng thứ tự sắp xếp theo khoảng cách của FAISS
            vector_matched = [cid for cid in vector_results if cid in cid_to_doc]
        except Exception as e:
            print(f"⚠️ Lỗi lọc FAISS results: {e}")

    # 4. Trích xuất số ký hiệu đã được xử lý trước ở đầu hàm

    # 5. Phối hợp kết quả và tính điểm RRF Boosting
    RRF_K = 60
    rrf_scores = {} # chunk_id -> {"id": cid, "doc_id": doc_id, "score": float}

    # Add FTS5 ranks
    for rank, item in enumerate(fts_results):
        cid = item["id"]
        if cid not in rrf_scores:
            rrf_scores[cid] = {"id": cid, "doc_id": item["doc_id"], "score": 0.0}
        rrf_scores[cid]["score"] += 1.0 / (RRF_K + rank)

    # Add Vector ranks
    for rank, cid in enumerate(vector_matched):
        doc_id = cid_to_doc[cid]
        if cid not in rrf_scores:
            rrf_scores[cid] = {"id": cid, "doc_id": doc_id, "score": 0.0}
        rrf_scores[cid]["score"] += 1.0 / (RRF_K + rank)

    # Lấy thông tin metadata cần thiết của các tài liệu liên quan để tiến hành Boost
    doc_ids = list({item["doc_id"] for item in rrf_scores.values()})
    doc_meta = {}
    if doc_ids:
        placeholders = ",".join(["?"] * len(doc_ids))
        try:
            cursor.execute(f"""
                SELECT id, so_ky_hieu, loai_van_ban, tinh_trang_hieu_luc 
                FROM documents 
                WHERE id IN ({placeholders})
            """, doc_ids)
            for row in cursor.fetchall():
                doc_meta[row["id"]] = dict(row)
        except Exception as e:
            print(f"⚠️ Lỗi lấy metadata để boost: {e}")

    # Áp dụng công thức Boosting
    for cid, item in rrf_scores.items():
        doc_id = item["doc_id"]
        meta = doc_meta.get(doc_id)
        if not meta:
            continue
            
        so_ky_hieu = (meta.get("so_ky_hieu") or "").lower()
        loai_van_ban = (meta.get("loai_van_ban") or "").lower()
        status_str = (meta.get("tinh_trang_hieu_luc") or "").lower()

        # A. Symbol Match Boost (Boost cực lớn nếu tài liệu khớp số ký hiệu từ câu hỏi: +1.5 điểm)
        symbol_boost = 0.0
        for sym in extracted_symbols:
            if sym in so_ky_hieu:
                symbol_boost = 1.5
                break

        # B. Document Type Boost (Ưu tiên mức độ hiệu lực pháp lý cao hơn)
        type_boost = 0.0
        if "hiến pháp" in loai_van_ban:
            type_boost = 0.1
        elif "bộ luật" in loai_van_ban or "luật" in loai_van_ban:
            type_boost = 0.08
        elif "pháp lệnh" in loai_van_ban:
            type_boost = 0.06
        elif "nghị định" in loai_van_ban:
            type_boost = 0.05
        elif "nghị quyết" in loai_van_ban:
            type_boost = 0.04
        elif "quyết định" in loai_van_ban:
            type_boost = 0.02

        # C. Status Multiplier (Ưu tiên các văn bản đang còn hiệu lực: x1.2)
        status_multiplier = 1.0
        if "còn hiệu lực" in status_str or "hết hiệu lực một phần" in status_str:
            status_multiplier = 1.2

        # Thực thi công thức
        item["score"] = (item["score"] + symbol_boost + type_boost) * status_multiplier

    # Sắp xếp theo điểm Boosted RRF Score giảm dần
    sorted_items = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
    
    # Phase 5: Semantic Similarity Reranking (Chỉ chạy khi có query_vector và model hợp lệ)
    if model and query_vector is not None and sorted_items:
        candidates = sorted_items[:25]
        remaining_items = sorted_items[25:]
        
        candidate_cids = [item["id"] for item in candidates]
        candidate_details = {}
        if candidate_cids:
            placeholders = ",".join(["?"] * len(candidate_cids))
            try:
                cursor.execute(f"SELECT id, chunk_text FROM document_chunks WHERE id IN ({placeholders})", candidate_cids)
                for row in cursor.fetchall():
                    candidate_details[row["id"]] = row["chunk_text"]
            except Exception as e:
                print(f"⚠️ Lỗi lấy văn bản để rerank: {e}")
                
        # Tính Cosine Similarity
        try:
            import numpy as np
            import faiss
            candidate_texts = [candidate_details.get(cid, "") for cid in candidate_cids]
            if candidate_texts:
                # Sinh vector embedding cho Top-25 candidates
                candidate_embeddings = model.encode(candidate_texts, show_progress_bar=False, convert_to_numpy=True)
                faiss.normalize_L2(candidate_embeddings)
                
                # Tính toán tích vô hướng (Inner Product) chính là Cosine Similarity
                similarities = np.dot(candidate_embeddings, query_vector[0])
                
                # Cộng thêm điểm tương đồng (Similarity Rerank với trọng số w = 2.0)
                for idx, cid in enumerate(candidate_cids):
                    similarity = float(similarities[idx])
                    for item in candidates:
                        if item["id"] == cid:
                            item["score"] += 2.0 * similarity
                            break
                            
                # Sắp xếp lại toàn bộ sau khi rerank
                sorted_items = sorted(candidates + remaining_items, key=lambda x: x["score"], reverse=True)
        except Exception as e:
            print(f"⚠️ Lỗi trong quá trình chạy Reranker: {e}")
            
    total = len(sorted_items)

    # Phân trang
    paginated_items = sorted_items[offset:offset + limit]

    results = []
    if paginated_items:
        paginated_cids = [item["id"] for item in paginated_items]
        placeholders = ",".join(["?"] * len(paginated_cids))
        
        query_details = f"""
            SELECT c.id, c.doc_id, c.chunk_index, c.chunk_type, c.chunk_header, c.chunk_text, c.token_estimate,
                   d.title as document_title, d.so_ky_hieu as document_so_ky_hieu, d.loai_van_ban as document_loai_van_ban,
                   d.co_quan_ban_hanh as document_co_quan_ban_hanh, d.tinh_trang_hieu_luc as document_tinh_trang_hieu_luc,
                   d.ngay_ban_hanh as document_ngay_ban_hanh
            FROM document_chunks c
            JOIN documents d ON c.doc_id = d.id
            WHERE c.id IN ({placeholders})
        """
        try:
            cursor.execute(query_details, paginated_cids)
            details_map = {row["id"]: dict(row) for row in cursor.fetchall()}
            
            # Đảm bảo giữ đúng thứ tự đã boost
            for item in paginated_items:
                cid = item["id"]
                if cid in details_map:
                    res = details_map[cid]
                    res["score"] = item["score"] # Trả về score để kiểm tra tính đúng đắn
                    results.append(res)
        except Exception as e:
            print(f"⚠️ Lỗi lấy chi tiết chunks: {e}")

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
        "results": results,
    }


@router.post("/reload-index", tags=["🔍 Tìm kiếm & Tra cứu (Luật)"], summary="Hot-reload BM25 index")
async def reload_index(_api_key: str = Depends(require_api_key)):
    """
    Hot-reload BM25 index từ cache mới nhất (sau khi auto_rebuild_index.py chạy).
    Không cần restart server.
    """
    import threading
    from app.hybrid_search import init_hybrid_engine
    from app.config import CONTENT_DB, DB_NAME
    
    def _reload():
        try:
            init_hybrid_engine(DB_NAME, CONTENT_DB)
        except Exception as e:
            print(f"⚠️ Reload failed: {e}")
    
    threading.Thread(target=_reload, daemon=True).start()
    
    return {"status": "reloading", "message": "BM25 index đang được reload trong background. Sẽ sẵn sàng trong ~10s."}


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


# ─────────────────── ADMINISTRATIVE DIVISIONS ───────────────────

@router.get("/provinces", response_model=List[ProvinceItem], tags=["🏷️ Danh mục (Luật)"], summary="Danh sách tỉnh/thành phố")
def get_provinces(_key=Depends(require_api_key)):
    """Lấy danh sách các tỉnh thành phố trực thuộc trung ương."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT code, name, full_name, code_name, administrative_unit_id FROM provinces ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.get("/provinces/{province_code}/wards", response_model=List[WardItem], tags=["🏷️ Danh mục (Luật)"], summary="Danh sách quận huyện/phường xã theo tỉnh")
def get_wards(
    province_code: str = Path(..., description="Mã tỉnh thành"),
    _key=Depends(require_api_key),
):
    """Lấy danh sách các đơn vị cấp dưới (quận/huyện/thị xã/phường/xã) của một tỉnh thành."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT code, name, full_name, code_name, province_code, administrative_unit_id "
        "FROM wards WHERE province_code = ? ORDER BY name ASC",
        (province_code,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


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


@router.get("/{law_id}/download", summary="Tải file DOCX của văn bản")
def download_law_docx(
    law_id: int = Path(..., description="ID văn bản"),
    _key=Depends(require_api_key),
):
    """
    Tải văn bản pháp luật dưới dạng file Microsoft Word (.docx).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (law_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản có ID {law_id}")

    metadata = dict(row)
    title = metadata.get("title") or "Van ban phap luat"

    # Lấy content_html
    content_html = ""
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
            content_html = content_row["content_html"]

    # Parse and build docx
    doc = Document()
    
    # Page margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Base styling
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(12)

    # 1. Quốc hiệu / Tiêu ngữ
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_header1 = p_header.add_run("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n")
    r_header1.bold = True
    r_header1.font.size = Pt(12)
    r_header2 = p_header.add_run("Độc lập - Tự do - Hạnh phúc\n")
    r_header2.bold = True
    r_header2.font.size = Pt(11)
    r_header3 = p_header.add_run("---------------")
    r_header3.font.size = Pt(11)

    # 2. Metadata (Cơ quan & Số hiệu)
    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.LEFT
    organ = metadata.get("co_quan_ban_hanh") or "CƠ QUAN BAN HÀNH"
    so_ky_hieu = metadata.get("so_ky_hieu") or "N/A"
    ngay_ban_hanh = metadata.get("ngay_ban_hanh") or "N/A"
    
    p_meta.add_run(f"{organ.upper()}\nSố: {so_ky_hieu}\n").bold = True
    
    # 3. Ngày ban hành (Căn phải)
    p_date = doc.add_paragraph()
    p_date.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_date.add_run(f"Hà Nội, ngày {ngay_ban_hanh}").italic = True

    doc.add_paragraph()  # Spacing

    # 4. Tiêu đề chính
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run(title.upper())
    r_title.bold = True
    r_title.font.size = Pt(13)

    doc.add_paragraph()  # Spacing

    # 5. Nội dung văn bản
    if content_html:
        soup = BeautifulSoup(content_html, "html.parser")
        content_container = soup.find(id="content") or soup.find(class_="noi-dung") or soup
        
        # Traverse elements
        for block in content_container.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "li"]):
            if block.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(10)
                p.paragraph_format.space_after = Pt(4)
                r = p.add_run(block.get_text().strip())
                r.bold = True
                if block.name == "h1":
                    r.font.size = Pt(13)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    r.font.size = Pt(12)
            elif block.name == "p":
                if not block.find("table"):
                    text = block.get_text().strip()
                    if text:
                        p = doc.add_paragraph()
                        p.paragraph_format.space_after = Pt(6)
                        p.paragraph_format.line_spacing = 1.15
                        p.add_run(text)
            elif block.name == "li":
                text = block.get_text().strip()
                if text:
                    p = doc.add_paragraph(style='List Bullet')
                    p.paragraph_format.space_after = Pt(3)
                    p.add_run(text)
            elif block.name == "table":
                rows = block.find_all("tr")
                if rows:
                    max_cols = max(len(r.find_all(["td", "th"])) for r in rows)
                    if max_cols > 0:
                        tbl = doc.add_table(rows=0, cols=max_cols)
                        tbl.style = 'Table Grid'
                        for r_el in rows:
                            cells = r_el.find_all(["td", "th"])
                            row_cells = tbl.add_row().cells
                            for c_idx, cell in enumerate(cells):
                                if c_idx < len(row_cells):
                                    row_cells[c_idx].text = cell.get_text().strip()
    else:
        p = doc.add_paragraph()
        p.add_run("Văn bản chưa cập nhật nội dung toàn văn.")

    # Save to Stream
    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    
    # Safe file name
    safe_title = "".join([c if c.isalnum() or c in "._-" else "_" for c in so_ky_hieu])
    if not safe_title:
        safe_title = f"document_{law_id}"
    
    import urllib.parse
    encoded_filename = urllib.parse.quote(f"{safe_title}.docx")
    
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    )







