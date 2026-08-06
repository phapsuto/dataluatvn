import re
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from bs4 import BeautifulSoup, NavigableString

from app.dependencies import require_api_key
from app.database import get_db_connection, get_content_connection, get_memory_db
from app.utils.llm_gateway import LLMGateway
from app.utils.legal_router import route_query
from app.utils.user_memory import LegalUserMemory
from app.utils.ultimate_retrieval import ultimate_retrieve
from app.utils.flare_retrieval import flare_generate_stream

router = APIRouter(prefix="/assistant", tags=["🤖 Trợ lý ảo - AI Chatbot & RAG"])




# ╔══════════════════════════════════════════════════════════════╗
# ║                      SCHEMAS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Câu hỏi pháp luật của người dùng")
    session_id: Optional[str] = Field(None, description="Mã phiên hội thoại để lưu lịch sử")
    access_tier: Optional[str] = Field("CITIZEN", description="Chế độ phổ cập: CITIZEN | ENTERPRISE | JUDICIAL")
    mode: Optional[str] = Field("chat", description="Chế độ: chat hoặc legal_crosscheck")

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
    session_id = req.session_id or "default_user"
    
    if req.mode == "legal_crosscheck":
        from app.utils.ultimate_retrieval import ultimate_retrieve
        from app.utils.llm_gateway import LLMGateway
        from app.utils.clean_text import clean_context_artifacts, strip_thinking_tags
        
        formatted_chunks, citation_map, _ = await ultimate_retrieve(
            query=prompt, domain_filter=[], top_k=5
        )
        crosscheck_prompt = "Dựa vào thông tin luật sau, hãy cho biết hành vi mô tả cấu thành tội gì, thuộc Điều, Khoản nào. TRẢ VỀ JSON: {\"toi_danh\": \"...\", \"dieu\": \"...\"}. CHỈ TRẢ VỀ JSON."
        try:
            tokens = []
            async for token in LLMGateway.call_stream([{"role": "user", "content": f"Luật:\n{formatted_chunks}\n\nHành vi:\n{prompt}"}], crosscheck_prompt):
                tokens.append(token)
            return {
                "response": clean_context_artifacts(strip_thinking_tags("".join(tokens))),
                "citations": list(citation_map.values()),
                "domain": "dan_su",
                "flare_activated": False,
                "search_count": 1
            }
        except Exception as ex:
            raise HTTPException(status_code=500, detail=str(ex))
            
    # ── RAG Gen 3 Facade (Deep Modules) ──
    from app.utils.assistant_facade import process_chat_query
    
    try:
        result = await process_chat_query(
            prompt=prompt,
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
        
        if req.mode == "legal_crosscheck":
            from app.utils.ultimate_retrieval import ultimate_retrieve
            from app.utils.llm_gateway import LLMGateway
            from app.utils.clean_text import clean_context_artifacts, strip_thinking_tags
            import json
            
            formatted_chunks, citation_map, _ = await ultimate_retrieve(
                query=prompt, domain_filter=[], top_k=5
            )
            crosscheck_prompt = "Dựa vào thông tin luật sau, hãy cho biết hành vi mô tả cấu thành tội gì, thuộc Điều, Khoản nào. TRẢ VỀ JSON: {\"toi_danh\": \"...\", \"dieu\": \"...\"}. CHỈ TRẢ VỀ JSON."
            try:
                tokens = []
                async for token in LLMGateway.call_stream([{"role": "user", "content": f"Luật:\n{formatted_chunks}\n\nHành vi:\n{prompt}"}], crosscheck_prompt):
                    tokens.append(token)
                    yield f"event: token\ndata: {json.dumps({'content': token})}\n\n"
                    
                final_text = clean_context_artifacts(strip_thinking_tags("".join(tokens)))
                yield f"event: citations\ndata: {json.dumps({'citations': [c.dict() for c in citation_map.values()], 'domain': 'dan_su', 'flare_activated': False, 'search_count': 1})}\n\n"
                yield "event: done\ndata: {}\n\n"
                return
            except Exception as ex:
                yield f"event: error\ndata: {json.dumps({'error': str(ex)})}\n\n"
                return

        # Step 1: Intent & 5-Axis
        yield f"event: intent_detected\ndata: {json.dumps({'status': 'in_progress', 'step': '5-Axis Intent Classification'})}\n\n"
        
        # Step 2: Run Full Squad Pipeline
        squad_res = await LegalSquadOrchestrator.run_full_pipeline(prompt)
        
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
