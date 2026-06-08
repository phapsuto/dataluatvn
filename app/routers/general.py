import os
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.database import get_db_connection
from app.schemas.laws import HealthResponse

router = APIRouter(tags=["🏠 General"])


@router.get("/", response_model=HealthResponse, summary="Health Check")
def welcome():
    """Kiểm tra trạng thái hệ thống (không yêu cầu API Key)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM documents")
    total = cursor.fetchone()[0]
    conn.close()
    return {
        "status": "online",
        "message": "Chào mừng đến với API Dữ Liệu Pháp Luật Việt Nam!",
        "total_documents_loaded": total,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "admin_url": "/admin",
    }


@router.get("/llms.txt", response_class=PlainTextResponse, summary="llms.txt for AI Search Engines")
def get_llms_txt():
    """Tệp tin đặc tả dữ liệu phục vụ các AI Search crawler (Perplexity, ChatGPT).
    
    Nội dung gồm 2 phần:
    - Phần tĩnh: Mô tả API endpoints và cấu trúc dữ liệu (từ static/llms.txt).
    - Phần động: 5 văn bản pháp luật mới nhất được tự động truy vấn từ database.
    """
    # Đọc nội dung tĩnh làm nền
    static_content = ""
    file_path = os.path.join("static", "llms.txt")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            static_content = f.read()
    else:
        static_content = "Vietnamese Legal Documents API system. Visit /docs for OpenAPI specifications.\n"

    # Truy vấn 5 văn bản mới nhất từ database
    dynamic_section = ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh, tinh_trang_hieu_luc
            FROM documents
            WHERE title IS NOT NULL AND title != ''
            ORDER BY
                CASE WHEN tinh_trang_hieu_luc LIKE '%Còn hiệu lực%' THEN 0 ELSE 1 END,
                ngay_ban_hanh DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()
        conn.close()

        if rows:
            dynamic_section = "\n\n## Recently Updated Documents\n\n"
            dynamic_section += "The following are the 5 most recent active legal documents in the database:\n\n"
            for row in rows:
                doc_id = row[0]
                title = row[1] or "N/A"
                symbol = row[2] or "N/A"
                doc_type = row[3] or "N/A"
                issued_date = row[4] or "N/A"
                status = row[5] or "N/A"
                dynamic_section += f"- **[{symbol}]** {title}\n"
                dynamic_section += f"  - Type: {doc_type} | Issued: {issued_date} | Status: {status}\n"
                dynamic_section += f"  - Retrieve via: `GET /laws/{doc_id}`\n"
    except Exception:
        # Nếu database không khả dụng, trả về nội dung tĩnh thuần túy
        pass

    return static_content + dynamic_section
