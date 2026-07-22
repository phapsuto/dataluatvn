import sqlite3
import re
from typing import List, Dict, Any, Optional
from app.config import DB_NAME
from app.utils.ultimate_retrieval import ultimate_retrieve

# OpenAI-style Function Calling Schema for Legal Cross-Referencing
SEARCH_REFERENCED_DOC_TOOL = {
    "type": "function",
    "function": {
        "name": "search_referenced_document",
        "description": (
            "Tìm kiếm nội dung cụ thể trong một văn bản pháp luật được trích dẫn. "
            "Sử dụng KHI VÀ CHỈ KHI ngữ cảnh hiện tại nhắc đến một văn bản khác (vd: Luật X, Thông tư Y, Nghị định Z) "
            "và bạn BẮT BUỘC cần chi tiết từ văn bản đó để trả lời chính xác câu hỏi."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doc_ref": {
                    "type": "string",
                    "description": "Số hiệu hoặc tên đầy đủ của văn bản pháp luật (ví dụ: '100/2019/NĐ-CP', 'Bộ luật Lao động 2019').",
                },
                "dieu_filter": {
                    "type": "string",
                    "description": "(Tùy chọn) Chỉ ghi số điều, ví dụ 'Điều 5' hoặc '5'.",
                },
                "khoan_filter": {
                    "type": "string",
                    "description": "(Tùy chọn) Chỉ ghi số khoản, ví dụ 'Khoản 2' hoặc '2'.",
                },
                "content_query": {
                    "type": "string",
                    "description": "(Bắt buộc) Từ khóa hoặc chủ đề cần tra cứu trong văn bản đó.",
                },
            },
            "required": ["doc_ref", "content_query"],
        },
    }
}


async def execute_tool_search_referenced_doc(
    doc_ref: str,
    content_query: str,
    dieu_filter: Optional[str] = None,
    khoan_filter: Optional[str] = None,
    domain_filter: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Thực thi tra cứu chéo văn bản được dẫn chiếu trong CSDL.
    """
    search_term = f"{doc_ref} {dieu_filter or ''} {khoan_filter or ''} {content_query}".strip()
    
    # 1. Tra cứu trực tiếp từ số hiệu văn bản trong SQLite
    conn = sqlite3.connect(DB_NAME, timeout=10)
    cursor = conn.cursor()
    
    so_hieu_clean = re.sub(r'^(nghị định|thông tư|bộ luật|luật|quyết định)\s+', '', doc_ref, flags=re.IGNORECASE).strip()
    
    cursor.execute("""
        SELECT c.id, c.chunk_text, c.chunk_with_meta, d.title, d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc
        FROM document_chunks c
        JOIN documents d ON c.doc_id = d.id
        WHERE d.so_ky_hieu LIKE ? OR d.title LIKE ?
        LIMIT 5
    """, (f"%{so_hieu_clean}%", f"%{doc_ref}%"))
    
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    if rows:
        for r in rows:
            chunk_id, text, meta_text, title, so_ky_hieu, loai_vb, status = r
            results.append({
                "chunk_id": chunk_id,
                "content": meta_text or text,
                "title": title,
                "so_ky_hieu": so_ky_hieu,
                "loai_van_ban": loai_vb,
                "tinh_trang_hieu_luc": status
            })
    else:
        # Fallback to ultimate_retrieve
        formatted_chunks, citations = await ultimate_retrieve(search_term, domain_filter=domain_filter, top_k=3)
        if formatted_chunks:
            for k, v in citations.items():
                results.append({
                    "chunk_id": v.get("id"),
                    "content": v.get("title", ""),
                    "title": v.get("title"),
                    "so_ky_hieu": v.get("so_ky_hieu"),
                    "loai_van_ban": v.get("loai_van_ban"),
                    "tinh_trang_hieu_luc": v.get("tinh_trang_hieu_luc")
                })
                
    return {
        "doc_ref": doc_ref,
        "found_count": len(results),
        "results": results
    }

VERIFY_LEGAL_EFFECT_TOOL = {
    "type": "function",
    "function": {
        "name": "verify_legal_effect_status",
        "description": "Tra cứu trạng thái hiệu lực pháp lý và các văn bản sửa đổi, bổ sung, thay thế mới nhất của một số hiệu văn bản.",
        "parameters": {
            "type": "object",
            "properties": {
                "doc_symbol": {
                    "type": "string",
                    "description": "Số hiệu văn bản pháp luật (ví dụ: '100/2019/NĐ-CP', 'Luật Đất đai 2024')."
                }
            },
            "required": ["doc_symbol"]
        }
    }
}

async def execute_tool_verify_legal_effect(doc_symbol: str) -> Dict[str, Any]:
    """Tra cứu tình trạng hiệu lực thực tế trong SQLite."""
    conn = sqlite3.connect(DB_NAME, timeout=10)
    cursor = conn.cursor()
    
    so_hieu_clean = re.sub(r'^(nghị định|thông tư|bộ luật|luật|quyết định)\s+', '', doc_symbol, flags=re.IGNORECASE).strip()
    cursor.execute("""
        SELECT id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh, ngay_co_hieu_luc, tinh_trang_hieu_luc
        FROM documents
        WHERE so_ky_hieu LIKE ? OR title LIKE ?
        LIMIT 3
    """, (f"%{so_hieu_clean}%", f"%{doc_symbol}%"))
    
    rows = cursor.fetchall()
    conn.close()
    
    docs = []
    for r in rows:
        docs.append({
            "doc_id": r[0],
            "title": r[1],
            "so_ky_hieu": r[2],
            "loai_van_ban": r[3],
            "ngay_ban_hanh": r[4],
            "ngay_co_hieu_luc": r[5],
            "tinh_trang_hieu_luc": r[6] or "Còn hiệu lực"
        })
        
    return {
        "query_symbol": doc_symbol,
        "found_documents": docs
    }

ALL_LEGAL_TOOLS = [
    SEARCH_REFERENCED_DOC_TOOL,
    VERIFY_LEGAL_EFFECT_TOOL
]
