import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from bs4 import BeautifulSoup, NavigableString

from app.dependencies import require_api_key
from app.database import get_memory_db
from app.utils.llm_gateway import LLMGateway
from app.utils.user_memory import LegalUserMemory
from app.utils.file_parsers import parse_file
from app.utils.legal_doc_analyzer import (
    LegalDocumentAnalyzer,
    AttachmentSessionManager,
    MAX_FILE_SIZE_BYTES,
    MAX_ATTACHMENTS_PER_SESSION
)

router = APIRouter(prefix="/assistant", tags=["🤖 Trợ lý ảo - AI Chatbot & RAG"])




# ╔══════════════════════════════════════════════════════════════╗
# ║                      SCHEMAS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Câu hỏi pháp luật của người dùng")
    session_id: Optional[str] = Field(None, description="Mã phiên hội thoại để lưu lịch sử")
    access_tier: Optional[str] = Field("CITIZEN", description="Chế độ phổ cập: CITIZEN | ENTERPRISE | JUDICIAL")
    attachment_id: Optional[str] = Field(None, description="Mã file đính kèm đã upload để phân tích pháp lý")
    attachment_context: Optional[str] = Field(None, description="Tóm tắt/nội dung tài liệu đính kèm")


class Citation(BaseModel):
    id: int
    title: str
    so_ky_hieu: Optional[str]
    loai_van_ban: Optional[str] = None
    tinh_trang_hieu_luc: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    citations: List[Citation]
    domain: Optional[str] = None
    flare_activated: Optional[bool] = None
    search_count: Optional[int] = None
    access_tier: Optional[str] = Field(None, description="Chế độ phổ cập đã áp dụng")
    dvs_status: Optional[str] = Field(None, description="Trạng thái kiểm chứng DVS Shield")
    npl_payload: Optional[Dict[str, Any]] = Field(None, description="Sổ cái chứng minh pháp lý Normative Proof Ledger")
    blind_spots: Optional[List[Dict[str, Any]]] = Field(None, description="Các điểm mù dữ kiện đã nhận diện")

class SwitchProviderRequest(BaseModel):
    provider: str


# ╔══════════════════════════════════════════════════════════════╗
# ║                      HELPERS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

def clean_html(html_str: str) -> str:
    """Converts raw HTML content to a clean, readable Markdown format for the LLM."""
    if not html_str:
        return ""
    
    soup = BeautifulSoup(html_str, "html.parser")
    for script_or_style in soup(["script", "style", "head", "title", "meta", "link"]):
        script_or_style.decompose()

    def convert_element(element) -> str:
        if isinstance(element, NavigableString):
            return element.string if element.string else ""
            
        tag_name = element.name
        
        if tag_name == "tr":
            cells = []
            is_header = False
            for child in element.children:
                if child.name in ["td", "th"]:
                    cell_text = "".join(convert_element(c) for c in child.children).strip()
                    cell_text = cell_text.replace("\n", " ")
                    if child.name == "th":
                        is_header = True
                        cells.append(f"**{cell_text}**")
                    else:
                        cells.append(cell_text)
            if cells:
                row_str = "| " + " | ".join(cells) + " |"
                if is_header:
                    separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                    return f"\n{row_str}\n{separator}"
                return f"\n{row_str}"
            return ""
            
        children_text = "".join(convert_element(child) for child in element.children)
        
        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            return f"\n\n{'#' * level} {children_text.strip()}\n\n"
        elif tag_name == "p":
            return f"\n\n{children_text.strip()}\n\n"
        elif tag_name == "div":
            return f"\n{children_text.strip()}\n"
        elif tag_name == "br":
            return "\n"
        elif tag_name == "li":
            return f"\n- {children_text.strip()}"
        elif tag_name in ["ul", "ol"]:
            return f"\n{children_text}\n"
        elif tag_name in ["strong", "b"]:
            inner = children_text.strip()
            return f" **{inner}** " if inner else ""
        elif tag_name in ["em", "i"]:
            inner = children_text.strip()
            return f" *{inner}* " if inner else ""
        elif tag_name == "table":
            return f"\n\n{children_text.strip()}\n\n"
            
        return children_text

    markdown_text = convert_element(soup)
    markdown_text = "\n".join(line.strip() for line in markdown_text.splitlines())
    markdown_text = re.sub(r'[ \t]+', ' ', markdown_text)
    markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)
    
    return markdown_text.strip()


def _save_chat_history(session_id: str, prompt: str, response: str):
    """Helper: Lưu lịch sử hội thoại vào session DB (tránh duplicate code)."""
    if not session_id:
        return
    try:
        m_conn = get_memory_db()
        m_cursor = m_conn.cursor()
        m_cursor.execute("SELECT 1 FROM chat_sessions WHERE session_id = ?", (session_id,))
        if not m_cursor.fetchone():
            now_iso = datetime.now(timezone.utc).isoformat()
            m_cursor.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", ('default_user',))
            if not m_cursor.fetchone():
                m_cursor.execute(
                    "INSERT INTO user_profiles (user_id, full_name, created_at) VALUES (?, ?, ?)",
                    ('default_user', 'Default Portal User', now_iso)
                )
            m_cursor.execute(
                "INSERT INTO chat_sessions (session_id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                (session_id, 'default_user', prompt[:30] + ('...' if len(prompt) > 30 else ''), now_iso)
            )
            m_conn.commit()
        now_iso = datetime.now(timezone.utc).isoformat()
        m_cursor.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, "user", prompt, now_iso)
        )
        m_cursor.execute(
            "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, "assistant", response, now_iso)
        )
        m_conn.commit()
        m_conn.close()
    except Exception as e:
        print(f"⚠️ Error saving session message log: {e}")


# ╔══════════════════════════════════════════════════════════════╗
# ║                      ROUTERS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

def _enrich_prompt_with_attachment(prompt: str, attachment_id: Optional[str], attachment_context: Optional[str], session_id: Optional[str] = None) -> str:
    if attachment_id:
        att = AttachmentSessionManager.get_attachment(attachment_id)
        if att:
            doc_preview = att['content_text'][:6000] if len(att['content_text']) > 6000 else att['content_text']
            return (
                f"{prompt}\n\n"
                f"--- [NGỮ CẢNH TÀI LIỆU ĐÍNH KÈM: {att['filename']} ({att['doc_type']})] ---\n"
                f"**Tóm tắt cấu trúc tài liệu:**\n{att['structured_summary']}\n\n"
                f"**Trích đoạn nội dung văn bản:**\n{doc_preview}\n\n"
                f"--- [YÊU CẦU ĐỐI CHIẾU PHÁP LÝ VIỆT NAM] ---\n"
                f"Hãy tư vấn dựa trên quy định pháp luật Việt Nam hiện hành và đối chiếu chi tiết với tài liệu đính kèm trên theo đúng phong cách Trợ lý Lan Anh."
            )
    elif attachment_context:
        return (
            f"{prompt}\n\n"
            f"--- [NGỮ CẢNH TÀI LIỆU ĐÍNH KÈM] ---\n"
            f"{attachment_context}\n\n"
            f"--- [YÊU CẦU ĐỐI CHIẾU PHÁP LÝ VIỆT NAM] ---\n"
            f"Hãy tư vấn dựa trên quy định pháp luật Việt Nam hiện hành và đối chiếu chi tiết với tài liệu đính kèm trên theo đúng phong cách Trợ lý Lan Anh."
        )
    elif session_id:
        atts = AttachmentSessionManager.get_session_attachments(session_id)
        if atts:
            recent_atts = atts[:2]
            combined_summary = []
            combined_text = []
            for a in recent_atts:
                combined_summary.append(f"- **{a['filename']} ({a['doc_type']}):**\n{a['structured_summary']}")
                preview = a['content_text'][:4000] if len(a['content_text']) > 4000 else a['content_text']
                combined_text.append(f"### Tài liệu: {a['filename']}\n{preview}")
            summary_str = "\n\n".join(combined_summary)
            text_str = "\n\n".join(combined_text)
            return (
                f"{prompt}\n\n"
                f"--- [NGỮ CẢNH CÁC TÀI LIỆU ĐÍNH KÈM TRONG PHIÊN HỘI THOẠI] ---\n"
                f"**Tổng hợp tóm tắt tài liệu:**\n{summary_str}\n\n"
                f"**Trích đoạn nội dung tài liệu:**\n{text_str}\n\n"
                f"--- [YÊU CẦU ĐỐI CHIẾU PHÁP LÝ VIỆT NAM] ---\n"
                f"Hãy tư vấn dựa trên quy định pháp luật Việt Nam hiện hành và đối chiếu chi tiết với các tài liệu đính kèm trên theo đúng phong cách Trợ lý Lan Anh."
            )
    return prompt


# ╔══════════════════════════════════════════════════════════════╗
# ║                      ROUTERS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

@router.post("/upload-attachment", summary="Tải lên tài liệu đính kèm (Ảnh, PDF, Word) cho Trợ lý Lan Anh")
async def upload_attachment(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form("default_user"),
    _key=Depends(require_api_key)
):
    """
    Tải lên tài liệu đính kèm (tối đa 8MB/file, 10 file/phiên):
    - Đọc nội dung đa phương thức: PDF, DOCX, DOC, TXT, CSV, Hình ảnh (PNG/JPG/WEBP).
    - Hỗ trợ OCR hình ảnh/PDF scan bằng FPT Cloud Vision và fallback Tesseract OCR.
    - Phân tích cấu trúc pháp lý tự động bằng FPT Cloud LLM.
    """
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Dung lượng file vượt quá giới hạn 8MB (file tải lên: {len(file_bytes)/1024/1024:.2f} MB)."
        )
        
    try:
        content_text = parse_file(file.filename, file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi khi đọc tài liệu: {str(e)}")

    if not content_text or len(content_text.strip()) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Không trích xuất được nội dung từ file '{file.filename}'. File có thể bị trống, hỏng, hoặc là file quét (scanned) không có OCR."
        )
        
    try:
        analysis = await LegalDocumentAnalyzer.analyze_attachment(content_text, file.filename)
        doc_type = analysis.get("doc_type", "Tài liệu pháp lý")
        structured_summary = analysis.get("structured_summary", "")
        
        ext = file.filename.split(".")[-1].upper() if "." in file.filename else "DOC"
        saved = AttachmentSessionManager.save_attachment(
            session_id=session_id or "default_user",
            filename=file.filename,
            file_type=ext,
            content_text=content_text,
            structured_summary=structured_summary,
            doc_type=doc_type
        )
        return {
            "status": "success",
            "attachment_id": saved["attachment_id"],
            "filename": saved["filename"],
            "file_type": saved["file_type"],
            "doc_type": saved["doc_type"],
            "structured_summary": saved["structured_summary"]
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý tài liệu đính kèm: {str(e)}")


@router.get("/attachments/{session_id}", summary="Lấy danh sách tài liệu đính kèm của phiên")
def get_session_attachments(session_id: str, _key=Depends(require_api_key)):
    """Trả về danh sách tài liệu đã đính kèm trong phiên hội thoại."""
    attachments = AttachmentSessionManager.get_session_attachments(session_id)
    # Remove large content_text from response to keep payload light
    res = []
    for att in attachments:
        res.append({
            "attachment_id": att["attachment_id"],
            "filename": att["filename"],
            "file_type": att["file_type"],
            "doc_type": att["doc_type"],
            "structured_summary": att["structured_summary"],
            "created_at": att["created_at"]
        })
    return {"attachments": res}


@router.delete("/attachments/session/{session_id}", summary="Xóa toàn bộ tài liệu đính kèm của một phiên")
def clear_session_attachments(session_id: str, _key=Depends(require_api_key)):
    """Xóa toàn bộ tài liệu đính kèm khỏi phiên làm việc."""
    count = AttachmentSessionManager.clear_session(session_id)
    return {"status": "success", "deleted_count": count, "message": f"Đã xóa {count} tài liệu khỏi phiên."}


@router.delete("/attachments/{attachment_id}", summary="Xóa một tài liệu đính kèm")
def delete_attachment(attachment_id: str, _key=Depends(require_api_key)):
    """Xóa tài liệu khỏi phiên làm việc."""
    success = AttachmentSessionManager.delete_attachment(attachment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu đính kèm.")
    return {"status": "success", "message": "Đã xóa tài liệu đính kèm."}


@router.post("/chat", response_model=ChatResponse, summary="Hỏi đáp pháp luật tích hợp RAG 7 Tầng")
async def chat_with_assistant(req: ChatRequest, _key=Depends(require_api_key)):
    """
    Hỏi đáp pháp luật với Trợ lý ảo AI - Kiến trúc 7 Tầng:
    1. Định tuyến ý định siêu tốc qua Semantic Router (local GPU).
    2. Nạp ngữ cảnh bộ nhớ dài hạn của User qua Mem0.
    3. Tra cứu văn bản kết hợp FTS5, Vector Search, và Graph Expansion.
    4. Rerank ứng viên tối ưu qua Cohere API / local similarity.
    5. Chạy luồng kiểm soát ảo giác chủ động FLARE.
    6. Trích dẫn chuẩn xác P-Cite Citation Lock.
    """
    prompt = req.prompt.strip()
    # LOG-2 fix: session_id phải luôn có giá trị hợp lệ, không gộp tất cả vào "default_user"
    session_id = req.session_id or f"anon_{hash(req.prompt[:30])}"
    session_id = session_id.strip() or f"anon_{hash(req.prompt[:30])}"
    
    # Enrich prompt with attachment context if attachment_id, attachment_context, or active session attachments present
    enriched_prompt = _enrich_prompt_with_attachment(
        prompt=prompt,
        attachment_id=req.attachment_id,
        attachment_context=req.attachment_context,
        session_id=session_id
    )
    
    # ── RAG Gen 3 Facade (Deep Modules) ──
    from app.utils.assistant_facade import process_chat_query
    
    try:
        result = await process_chat_query(
            prompt=enriched_prompt,
            session_id=session_id,
            persona_key="default",
            save_chat_history_callback=_save_chat_history,
            access_tier=(req.access_tier or "CITIZEN").upper()
        )
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý câu hỏi: {str(e)}")


@router.get("/providers", summary="Lấy trạng thái các LLM providers")
def get_providers(_key=Depends(require_api_key)):
    """Trả về trạng thái model đang active, fallback chain và danh sách providers hợp lệ."""
    return LLMGateway.get_status()


@router.post("/switch-provider", summary="Đổi LLM provider active runtime")
def switch_provider(req: SwitchProviderRequest, _key=Depends(require_api_key)):
    """Chuyển đổi nhà cung cấp LLM tức thời mà không cần khởi động lại máy chủ."""
    try:
        return LLMGateway.switch_provider(req.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/user-profile/{user_id}", summary="Xuất hồ sơ ghi nhớ người dùng")
def get_user_profile(user_id: str, _key=Depends(require_api_key)):
    """Lấy danh sách các chủ đề quan tâm và tài liệu đã xem của user từ long-term memory."""
    return LegalUserMemory.get_user_profile(user_id)


@router.post("/stream", summary="SSE Real-time Multi-stage Legal Assistant Stream")
async def assistant_stream(req: ChatRequest, _key=Depends(require_api_key)):
    """
    Endpoint Server-Sent Events (SSE) phát lại tiến trình suy luận 6 bước thời gian thực.
    """
    from fastapi.responses import StreamingResponse
    from app.agents.legal_squad import LegalSquadOrchestrator
    
    async def sse_generator():
        prompt = req.prompt.strip()
        session_id = req.session_id or "default_session"
        
        enriched_prompt = _enrich_prompt_with_attachment(
            prompt=prompt,
            attachment_id=req.attachment_id,
            attachment_context=req.attachment_context,
            session_id=session_id
        )
        
        # Step 1: Intent & 5-Axis
        yield f"event: intent_detected\ndata: {json.dumps({'status': 'in_progress', 'step': '5-Axis Intent Classification'})}\n\n"
        
        # Step 2: Run Full Squad Pipeline
        squad_res = await LegalSquadOrchestrator.run_full_pipeline(enriched_prompt)
        
        sub_queries = squad_res.get("sub_queries", [prompt])
        yield f"event: sub_queries\ndata: {json.dumps({'sub_queries': sub_queries})}\n\n"
        
        hyde_doc = squad_res.get("hyde_doc")
        if hyde_doc:
            yield f"event: hyde_generated\ndata: {json.dumps({'hyde_doc': hyde_doc})}\n\n"
            
        chunks = squad_res.get("chunks", [])
        yield f"event: retrieval_done\ndata: {json.dumps({'found_chunks': len(chunks)})}\n\n"
        
        # Step 3: Stream Answer Tokens
        drafter_gen = squad_res["drafter"]
        async for token in drafter_gen:
            yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
            
        yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

