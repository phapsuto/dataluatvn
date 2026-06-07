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
    """Tệp tin đặc tả dữ liệu phục vụ các AI Search crawler (Perplexity, ChatGPT)."""
    file_path = os.path.join("static", "llms.txt")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return "Vietnamese Legal Documents API system. Visit /docs for OpenAPI specifications."
