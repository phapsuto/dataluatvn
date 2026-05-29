import os
import sqlite3
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Configuration ---
DB_NAME = "vietnamese_legal_documents.db"

app = FastAPI(
    title="Vietnamese Legal Documents API",
    description="REST API cho kho dữ liệu 153.420 văn bản pháp luật Việt Nam. Hỗ trợ tìm kiếm nhanh, lấy chi tiết toàn văn, quan hệ văn bản và thống kê.",
    version="1.0.0"
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
        raise HTTPException(status_code=500, detail="Database file not found. Please run download_all_to_sqlite.py first.")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Returns results as dict-like objects
    return conn

# --- Pydantic Models for response types ---
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

# --- API Endpoints ---

@app.get("/", tags=["General"])
def welcome():
    """Welcome and health-check endpoint"""
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
        "interactive_documentation": "/docs"
    }

@app.get("/laws/stats", tags=["Statistics"])
def get_stats():
    """Retrieve statistics about the legal database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total count
    cursor.execute("SELECT count(*) FROM documents")
    total_docs = cursor.fetchone()[0]
    
    # Count by type
    cursor.execute("SELECT loai_van_ban, count(*) FROM documents GROUP BY loai_van_ban ORDER BY count(*) DESC")
    types_count = {row[0] or "Khác": row[1] for row in cursor.fetchall()}
    
    # Count by status
    cursor.execute("SELECT tinh_trang_hieu_luc, count(*) FROM documents GROUP BY tinh_trang_hieu_luc ORDER BY count(*) DESC")
    status_count = {row[0] or "Không xác định": row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {
        "total_documents": total_docs,
        "by_document_type": types_count,
        "by_effectiveness_status": status_count
    }

@app.get("/laws/search", response_model=List[LawBrief], tags=["Search & Retrieval"])
def search_laws(
    q: Optional[str] = Query(None, description="Từ khóa tìm kiếm (trong tiêu đề hoặc số ký hiệu)"),
    loai_van_ban: Optional[str] = Query(None, description="Lọc theo loại văn bản (Ví dụ: Luật, Nghị định, Thông tư)"),
    status: Optional[str] = Query(None, description="Lọc theo tình trạng hiệu lực (Ví dụ: Còn hiệu lực, Hết hiệu lực)"),
    linh_vuc: Optional[str] = Query(None, description="Lọc theo lĩnh vực (Ví dụ: Hình sự, Đất đai, Thuế)"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng kết quả tối đa trả về"),
    offset: int = Query(0, ge=0, description="Vị trí bắt đầu (dùng cho phân trang)")
):
    """
    Tìm kiếm nhanh văn bản pháp luật. 
    Hỗ trợ lọc nâng cao theo loại văn bản, tình trạng hiệu lực, lĩnh vực và phân trang.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, co_quan_ban_hanh, tinh_trang_hieu_luc 
        FROM documents 
        WHERE 1=1
    """
    params = []
    
    if q:
        query += " AND (title LIKE ? OR so_ky_hieu LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
        
    if loai_van_ban:
        query += " AND loai_van_ban = ?"
        params.append(loai_van_ban)
        
    if status:
        query += " AND tinh_trang_hieu_luc = ?"
        params.append(status)
        
    if linh_vuc:
        query += " AND (linh_vuc LIKE ? OR nganh LIKE ?)"
        params.extend([f"%{linh_vuc}%", f"%{linh_vuc}%"])
        
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/laws/{law_id}", response_model=LawDetail, tags=["Search & Retrieval"])
def get_law_detail(law_id: int):
    """Lấy chi tiết toàn văn HTML và siêu dữ liệu đầy đủ của một văn bản qua ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM documents WHERE id = ?", (law_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy văn bản có ID {law_id}")
        
    return dict(row)

@app.get("/laws/{law_id}/relationships", response_model=List[RelationshipInfo], tags=["Relationships"])
def get_law_relationships(law_id: int):
    """
    Lấy danh sách các liên kết pháp lý của văn bản (sửa đổi, bổ sung, bị thay thế...)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # We find relationships where the requested document is either the main doc or the related doc
    query = """
        SELECT r.doc_id, r.other_doc_id, r.relationship, d.title as other_doc_title, d.so_ky_hieu as other_doc_so_ky_hieu
        FROM relationships r
        JOIN documents d ON r.other_doc_id = d.id
        WHERE r.doc_id = ?
        UNION
        SELECT r.doc_id, r.other_doc_id, r.relationship, d.title as other_doc_title, d.so_ky_hieu as other_doc_so_ky_hieu
        FROM relationships r
        JOIN documents d ON r.doc_id = d.id
        WHERE r.other_doc_id = ?
    """
    
    cursor.execute(query, (law_id, law_id))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

# --- Startup / Run Config ---
if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8080
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=True)
