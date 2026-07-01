import re
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from bs4 import BeautifulSoup, NavigableString

from app.dependencies import require_api_key
from app.database import get_memory_db
from app.utils.llm_gateway import LLMGateway
from app.utils.smart_router import analyze_query
from app.utils.user_memory import LegalUserMemory
from app.utils.ultimate_retrieval import ultimate_retrieve
import asyncio
from app.utils.flare_retrieval import flare_generate_stream

router = APIRouter(prefix="/assistant", tags=["🤖 Trợ lý ảo - AI Chatbot & RAG"])


def strip_thinking_tags(text: str) -> str:
    """Loại bỏ <think>...</think> blocks từ output của Gemma/reasoning models."""
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()


def clean_context_artifacts(text: str) -> str:
    """Loại bỏ các từ khóa kỹ thuật thô cứng như [NGỮ CẢNH PHÁP LÝ] trong câu trả lời."""
    if not text:
        return ""
    
    # 1. Các thẻ tiêu đề dạng [NGỮ CẢNH ...] hoặc [TÀI LIỆU ...]
    text = re.sub(r'\[\s*(?:NGỮ CẢNH PHÁP LÝ|NGỮ CẢNH PHÁP LÝ BỔ SUNG|TÀI LIỆU PHÁP LUẬT BỔ SUNG|TÀI LIỆU PHÁP LUẬT)\s*\]', '', text, flags=re.IGNORECASE)
    
    # 2. Câu dẫn thô kiểu "Dựa trên ngữ cảnh...", "Dưới đây là câu trả lời dựa trên...", "Theo tài liệu được cung cấp..."
    text = re.sub(
        r'(?:dựa trên|dựa vào|theo|căn cứ vào)\s+(?:ngữ cảnh pháp lý|ngữ cảnh pháp lý bổ sung|tài liệu pháp luật bổ sung|tài liệu pháp luật|tài liệu|context)(?:\s+(?:được cung cấp|dưới đây|trên|này|chi tiết|bổ sung))*,?\s*',
        '', text, flags=re.IGNORECASE
    )
    
    # 3. Loại bỏ tàn dư của thẻ placeholder [SEARCH: ...] nếu còn sót lại
    text = re.sub(r'\[SEARCH:\s*.*?\]', '', text, flags=re.IGNORECASE)
    
    # Sửa hoa đầu câu nếu ký tự đầu bị chuyển thành chữ thường hoặc bị cắt mất từ đầu tiên
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


# ╔══════════════════════════════════════════════════════════════╗
# ║                      SCHEMAS                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Câu hỏi pháp luật của người dùng")
    session_id: Optional[str] = Field(None, description="Mã phiên hội thoại để lưu lịch sử")

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


def _get_chat_history_text(session_id: str, limit: int = 4) -> str:
    """Helper: Lấy lịch sử chat gần đây từ SQLite."""
    if not session_id:
        return ""
    try:
        m_conn = get_memory_db()
        m_cursor = m_conn.cursor()
        m_cursor.execute(
            "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY message_id DESC LIMIT ?", 
            (session_id, limit)
        )
        rows = m_cursor.fetchall()
        m_conn.close()
        if not rows:
            return ""
        rows.reverse()
        history = "--- LỊCH SỬ TRÒ CHUYỆN TRƯỚC ĐÓ ---\n"
        for role, content in rows:
            role_name = "User" if role == "user" else "Assistant"
            history += f"{role_name}: {content}\n"
        return history + "\n"
    except Exception as e:
        print(f"⚠️ Error reading session message log: {e}")
        return ""


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
    
    # ── TẦNG SEMANTIC CACHE (RAG Gen 3) ──
    try:
        from app.utils.semantic_cache_manager import get_cache_manager
        cache_mgr = get_cache_manager()
        is_hit, cached_response, cached_citations = cache_mgr.lookup(prompt)
        if is_hit:
            print(f"🎯 [Semantic Cache] HIT for query: '{prompt}'")
            
            # Save history to session chat db
            _save_chat_history(session_id, prompt, cached_response)
            
            # Convert citation_map to list of citations
            citations_list = list(cached_citations.values()) if isinstance(cached_citations, dict) else (cached_citations or [])
            return {
                "response": cached_response,
                "citations": citations_list,
                "domain": "cached",
                "flare_activated": False,
                "search_count": 0
            }
    except Exception as e:
        print(f"⚠️ Semantic cache lookup warning: {e}")

    # ── STEP 1 & 2: CONCURRENT ROUTING & MEMORY FETCH (SOTA) ──
    # Run SmartRouter (LLM) and Memory lookup (DB) in parallel to save latency
    chat_history_len = 0
    try:
        m_conn = get_memory_db()
        m_cursor = m_conn.cursor()
        m_cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
        chat_history_len = m_cursor.fetchone()[0]
        m_conn.close()
    except Exception:
        pass

    chat_history_text = _get_chat_history_text(session_id, 4)

    route_task = analyze_query(prompt, chat_history_len)
    memory_task = asyncio.to_thread(LegalUserMemory.get_relevant_memories, session_id, prompt)
    
    route_res, memory_context = await asyncio.gather(route_task, memory_task)
    
    print("\n" + "="*50)
    print(f"🧠 [1. SMART ROUTER] Phân tích query: '{prompt}'")
    print(f"  ↳ Domain: {route_res.get('domain')}")
    print(f"  ↳ Có tính pháp lý: {route_res.get('is_legal')}")
    print(f"  ↳ Trích xuất Metadata: Năm={route_res.get('extracted_year')}, Loại={route_res.get('extracted_doc_type')}, Cơ quan={route_res.get('extracted_issuer')}, Số hiệu={route_res.get('extracted_doc_number')}")
    print(f"  ↳ Cần làm rõ: {route_res.get('needs_clarification')}")
    print(f"  ↳ Search Query tối ưu: '{route_res.get('search_query')}'")
    print("="*50 + "\n")
    
    domain = route_res.get("domain", "dan_su")
    is_legal = route_res.get("is_legal", True)
    search_query = route_res.get("search_query", prompt)
    
    # A. Nếu là chitchat chào hỏi thông thường
    if not is_legal and domain == "chitchat":
        print("💬 [Router] Chitchat detected. Replying directly via LLM.")
        
        system_prompt = (
            "Bạn là LuatBot - Trợ lý pháp lý AI chuyên về luật Việt Nam.\n"
            "Hãy trả lời người dùng một cách thân thiện, lịch sự, ngắn gọn và "
            "nhắc nhở rằng bạn sẵn sàng hỗ trợ các câu hỏi liên quan đến pháp luật Việt Nam."
        )
        if memory_context:
            system_prompt += f"\n\nNgữ cảnh thông tin đã nhớ về người dùng:\n{memory_context}\n(Nếu người dùng hỏi thông tin cá nhân của họ mà khớp với ngữ cảnh trên, hãy trả lời chính xác dựa theo đó)."
        if chat_history_text:
            system_prompt += f"\n\n{chat_history_text}"
            
        try:
            tokens = []
            async for token in LLMGateway.call_stream([{"role": "user", "content": prompt}], system_prompt):
                tokens.append(token)
            ai_reply = clean_context_artifacts(strip_thinking_tags("".join(tokens)))
            
            try:
                LegalUserMemory.save_interaction(session_id, prompt, ai_reply, [])
            except Exception as e:
                print(f"⚠️ Warning: Failed to save chitchat user memory interaction: {e}")
                
            _save_chat_history(session_id, prompt, ai_reply)
                    
            return {
                "response": ai_reply,
                "citations": [],
                "domain": "chitchat",
                "flare_activated": False,
                "search_count": 0
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi gọi LLM Gateway: {str(e)}")
            
    # B. Nếu là câu hỏi ngoài phạm vi pháp luật VN (out of scope)
    if not is_legal and domain == "out_of_scope":
        print("🛑 [Router] Out of scope query detected. Refusing politely.")
        reply = (
            "Tôi là LuatBot, trợ lý chuyên giải đáp pháp luật Việt Nam. "
            "Câu hỏi này nằm ngoài phạm vi hỗ trợ của tôi. Vui lòng đặt câu hỏi liên quan đến luật pháp Việt Nam."
        )
        return {
            "response": reply,
            "citations": [],
            "domain": "out_of_scope",
            "flare_activated": False,
            "search_count": 0
        }
    
    # C. Cần làm rõ (Clarification)
    if route_res.get("needs_clarification") and route_res.get("clarification_question"):
        print("🔮 [Clarification] Query mơ hồ, LLM Router yêu cầu gợi mở...")
        clarification_text = route_res["clarification_question"]
        _save_chat_history(session_id, prompt, clarification_text)
        return {
            "response": clarification_text,
            "citations": [],
            "domain": domain,
            "flare_activated": False,
            "search_count": 0
        }
    
    # ── STEP 3 & 4: UNIFIED RETRIEVAL PIPELINE ──
    # Domain filter (heuristic fallback just in case)
    DOMAIN_FILTERS = {
        "lao_dong": ["Lao động", "BHXH", "Bảo hiểm xã hội", "Công đoàn"],
        "dan_su": ["Dân sự", "Hôn nhân", "Gia đình", "Di chúc", "Thừa kế"],
        "hinh_su": ["Hình sự", "Tố tụng hình sự", "Tội phạm"],
        "dat_dai": ["Đất đai", "Nhà ở", "Bất động sản"],
        "doanh_nghiep": ["Doanh nghiệp", "Đầu tư", "Thương mại"],
        "hanh_chinh": ["Vi phạm hành chính", "Khiếu nại", "Tố cáo"]
    }
    doc_type_filter = DOMAIN_FILTERS.get(domain, [])
    
    print(f"🔍 [Retrieval] SOTA pipeline for: '{search_query}' (Original: '{prompt}') (Domain: {domain})")
    
    formatted_chunks, citation_map, max_score = await ultimate_retrieve(
        query=search_query,
        domain_filter=doc_type_filter,
        top_k=5,
        extracted_year=route_res.get("extracted_year"),
        extracted_doc_type=route_res.get("extracted_doc_type"),
        extracted_issuer=route_res.get("extracted_issuer"),
        extracted_doc_number=route_res.get("extracted_doc_number")
    )
    flare_activated = False
    search_count = 1

    # ── STEP 5: ADAPTIVE FLARE RAG GENERATION (Tầng 5) ──
    final_text = ""
    citations_list = list(citation_map.values())
    
    # SOTA FIX: Dynamic FLARE trigger based on retrieval confidence
    # Score > 500 implies Exact Match or very high Title FTS match in the DB.
    force_simple = max_score > 500
    if force_simple:
        print(f"⚡ [Adaptive RAG] High confidence score ({max_score:.1f}) -> Bypassing FLARE drafting.")
    else:
        print(f"🧠 [Adaptive RAG] Semantic Match score ({max_score:.1f}) -> Activating FLARE drafting.")

    
    if formatted_chunks:
        try:
            async for event in flare_generate_stream(
                query=prompt,
                initial_context=formatted_chunks,
                citation_map=citation_map,
                domain_filter=doc_type_filter,
                custom_model=None,  # Sử dụng model mặc định của FPT provider (Qwen3-32B)
                force_simple=force_simple,
                chat_history_text=chat_history_text
            ):
                ev_type = event.get("type")
                if ev_type == "token":
                    final_text += event["content"]
                elif ev_type == "status":
                    flare_activated = event["flare_activated"]
                    search_count = event["search_count"]
                    citations_list = list(event["citation_map"].values())
        except Exception as ex:
            raise HTTPException(status_code=500, detail=f"Lỗi RAG Generation: {str(ex)}")
    else:
        final_text = "Không tìm thấy tài liệu pháp lý liên quan phù hợp để trả lời câu hỏi của bạn."

    # ── STRIP THINKING TAGS & CONTEXT ARTIFACTS ──
    final_text = clean_context_artifacts(strip_thinking_tags(final_text))

    # ── CẬP NHẬT SEMANTIC CACHE (RAG Gen 3) ──
    # Không cache các câu trả lời thất bại/trống để tránh đóng băng lỗi
    failure_patterns = [
        "không tìm thấy tài liệu",
        "chưa tìm thấy quy định",
        "không có thông tin",
        "ngoài phạm vi",
        "không tìm thấy",
        "chưa tìm thấy",
        "không có dữ liệu",
        "không tồn tại trong",
    ]
    should_cache = (
        final_text 
        and domain not in ["chitchat", "out_of_scope"] 
        and all(p not in final_text.lower() for p in failure_patterns)
    )
    if should_cache:
        try:
            from app.utils.semantic_cache_manager import get_cache_manager
            cache_mgr = get_cache_manager()
            cache_mgr.update(prompt, final_text, citation_map)
        except Exception as e:
            print(f"⚠️ Failed to update semantic cache: {e}")

    # ── STEP 6: SAVE INTERACTION TO MEMORY (Tầng 2) ──
    try:
        LegalUserMemory.save_interaction(session_id, prompt, final_text, citations_list)
    except Exception as e:
        print(f"⚠️ Warning: Failed to save user memory interaction: {e}")
        
    # ── STEP 7: SAVE TO SESSION CHAT HISTORY DB ──
    _save_chat_history(session_id, prompt, final_text)

    return {
        "response": final_text,
        "citations": citations_list,
        "domain": domain,
        "flare_activated": flare_activated,
        "search_count": search_count
    }


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
