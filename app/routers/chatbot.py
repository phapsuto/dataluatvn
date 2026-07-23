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


def strip_thinking_tags(text: str) -> str:
    """Loại bỏ <think>...</think> blocks từ output của Gemma/reasoning models."""
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL).strip()


def clean_context_artifacts(text: str) -> str:
    """Loại bỏ các từ khóa kỹ thuật thô cứng, câu chúc thừa và dọn dẹp khoảng cách dòng."""
    if not text:
        return ""
    
    # 1. Loại bỏ hoàn toàn khối "Lời chúc từ Lan Anh" nếu còn xuất hiện
    text = re.sub(r'(?:💖|\*\*)*\s*Lời chúc từ Lan Anh[\s\S]*?(?=\n\s*(?:⚠️|\*\*Lưu ý|💬|👉)|$)', '', text, flags=re.IGNORECASE)

    # 2. Các thẻ tiêu đề dạng [NGỮ CẢNH ...] hoặc [TÀI LIỆU ...]
    text = re.sub(r'\[\s*(?:NGỮ CẢNH PHÁP LÝ|NGỮ CẢNH PHÁP LÝ BỔ SUNG|TÀI LIỆU PHÁP LUẬT BỔ SUNG|TÀI LIỆU PHÁP LUẬT)\s*\]', '', text, flags=re.IGNORECASE)
    
    # 3. Câu dẫn thô độc lập đầu dòng dạng "Dựa trên ngữ cảnh...", "Theo tài liệu được cung cấp..."
    text = re.sub(
        r'^\s*(?:dựa trên|dựa vào|theo|căn cứ vào)\s+(?:ngữ cảnh pháp lý|ngữ cảnh|tài liệu pháp luật|tài liệu|context)(?:\s+(?:được cung cấp|dưới đây|trên|này|chi tiết|bổ sung))*,?\s*',
        '', text, flags=re.IGNORECASE | re.MULTILINE
    )
    
    # 4. Loại bỏ tàn dư của thẻ placeholder [SEARCH: ...] nếu còn sót lại
    text = re.sub(r'\[SEARCH:\s*.*?\]', '', text, flags=re.IGNORECASE)
    
    # 5. Loại bỏ các dòng tiêu đề kịch bản thô bị in nhầm từ System Prompt
    text = re.sub(r'(?:🌸|📌|⚖️|🔍|💡|🛠️|💖|⚠️)\s*\[?\s*(?:Lời chào|Vấn đề pháp lý|Cơ sở pháp lý|Phân tích chi tiết|Kết luận|Khuyến nghị|Lời chúc|Lưu ý|Lưu ý nhỏ).*?\]?\n?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(?:Vì người dùng|Cần đảm bảo|Viết bằng giọng|Cấu trúc phản hồi|Trả lời:).*?\n', '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # 6. Loại bỏ suy nghĩ nội bộ (internal thinking preamble) trước icon chào mừng 🌸 của Lan Anh
    if "🌸" in text and not text.strip().startswith("🌸"):
        text = "🌸" + text.split("🌸", 1)[1]
    
    # 7. Dọn dẹp nhiều dòng trống liên tiếp (chỉ giữ tối đa 1 dòng trống \n\n)
    text = re.sub(r'\n{3,}', '\n\n', text)

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

    # ── STEP 1: SEMANTIC ROUTING (Tầng 1) ──
    route_res = route_query(prompt)
    domain = route_res["domain"]
    
    # A. Nếu là chitchat chào hỏi thông thường
    if not route_res["is_legal"] and domain == "chitchat":
        print(f"💬 [Router] Chitchat detected. Replying directly via LLM.")
        
        # ── STEP 2: LOAD LONG-TERM MEMORY (Tầng 2) ──
        memory_context = LegalUserMemory.get_relevant_memories(session_id, prompt)
        
        system_prompt = (
            "Bạn là \"Lan Anh\" — Trợ lý Pháp lý Thông minh, Ấm áp, Thấu hiểu và Chu đáo.\n"
            "Hãy trả lời người dùng một cách thân thiện, ngọt ngào, lịch sự, ân cần và "
            "nhắc nhở rằng Lan Anh luôn sẵn sàng hỗ trợ các câu hỏi liên quan đến pháp luật Việt Nam nha."
        )
        if memory_context:
            system_prompt += f"\n\nNgữ cảnh thông tin đã nhớ về người dùng:\n{memory_context}\n(Nếu người dùng hỏi thông tin cá nhân của họ mà khớp với ngữ cảnh trên, hãy trả lời chính xác dựa theo đó)."
            
        try:
            tokens = []
            async for token in LLMGateway.call_stream([{"role": "user", "content": prompt}], system_prompt):
                tokens.append(token)
            ai_reply = clean_context_artifacts(strip_thinking_tags("".join(tokens)))
            
            # ── STEP 6: SAVE INTERACTION TO MEMORY (Tầng 2) ──
            try:
                LegalUserMemory.save_interaction(session_id, prompt, ai_reply, [])
            except Exception as e:
                print(f"⚠️ Warning: Failed to save chitchat user memory interaction: {e}")
                
            # ── STEP 7: SAVE TO SESSION CHAT HISTORY DB ──
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
    if domain == "out_of_scope":
        print(f"🛑 [Router] Out of scope query detected. Refusing politely.")
        reply = (
            "Dạ Lan Anh là Trợ lý Pháp lý Thông minh chuyên giải đáp các vấn đề pháp luật Việt Nam ạ. "
            "Câu hỏi này nằm ngoài phạm vi chuyên môn pháp lý của Lan Anh. Anh/Chị vui lòng đặt câu hỏi liên quan đến luật pháp Việt Nam để Lan Anh hỗ trợ tốt nhất nha!"
        )
        return {
            "response": reply,
            "citations": [],
            "domain": "out_of_scope",
            "flare_activated": False,
            "search_count": 0
        }
    
    # ── STEP 1.5: CLARIFICATION DIALOGUE ──
    # Kiểm tra câu hỏi có mơ hồ không → hỏi gợi mở thay vì trả kết quả kém
    try:
        from app.utils.clarification_engine import (
            needs_clarification, get_smart_clarification
        )
        
        # Đếm history length để skip clarification cho follow-up messages
        chat_history_len = 0
        try:
            m_conn = get_memory_db()
            m_cursor = m_conn.cursor()
            m_cursor.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?",
                (session_id,)
            )
            chat_history_len = m_cursor.fetchone()[0]
            m_conn.close()
        except Exception:
            pass
        
        if needs_clarification(prompt, domain, chat_history_len):
            print(f"🔮 [Clarification] Query mơ hồ, đang tạo câu hỏi gợi mở...")
            
            # Tier 2: Gọi DeepSeek (async) với kịch bản domain-specific
            clarification_text = await get_smart_clarification(prompt, domain)
            
            if clarification_text:
                # Lưu vào history để lượt sau không hỏi lại
                _save_chat_history(session_id, prompt, clarification_text)
                
                return {
                    "response": clarification_text,
                    "citations": [],
                    "domain": domain,
                    "flare_activated": False,
                    "search_count": 0
                }
    except Exception as e:
        print(f"⚠️ [Clarification] Lỗi, bỏ qua và chạy RAG bình thường: {e}")
        
    # ── STEP 2: LOAD LONG-TERM MEMORY (Tầng 2) ──
    memory_context = LegalUserMemory.get_relevant_memories(session_id, prompt)
    
    # ── STEP 2.5: MULTI-QUERY DECOMPOSITION ENGINE ──
    from app.utils.query_decomposer import decompose_query
    sub_queries = await decompose_query(prompt)
    print(f"🔀 [Decomposer] Generated {len(sub_queries)} sub-queries for query '{prompt}': {sub_queries}")
    
    # ── STEP 3 & 4: UNIFIED RETRIEVAL PIPELINE ACROSS SUB-QUERIES ──
    combined_chunks = []
    combined_citations = {}
    
    for sq in sub_queries:
        chunks_text, cit_map = await ultimate_retrieve(
            query=sq,
            domain_filter=route_res["doc_type_filter"],
            top_k=4,
            extracted_year=route_res.get("extracted_year"),
            extracted_doc_type=route_res.get("extracted_doc_type"),
            extracted_issuer=route_res.get("extracted_issuer")
        )
        if chunks_text:
            combined_chunks.append(chunks_text)
            combined_citations.update(cit_map)
            
    formatted_chunks = "\n\n====================\n\n".join(combined_chunks) if combined_chunks else ""
    
    # ── STEP 3.5: LEGAL THEORY & ACADEMIC MIND RETRIEVAL (BỘ NÃO LÝ LUẬN) ──
    try:
        from app.utils.theory_retrieval import search_legal_theory, format_theory_context
        theory_results = search_legal_theory(prompt, top_k=3)
        if theory_results:
            theory_context = format_theory_context(theory_results)
            print(f"🧠 [LegalMind] Loaded {len(theory_results)} academic theory contexts for prompt.")
            if formatted_chunks:
                formatted_chunks += f"\n\n====================\n\n{theory_context}"
            else:
                formatted_chunks = theory_context
    except Exception as e_theory:
        print(f"⚠️ [TheoryRetrieval] Warning: {e_theory}")

    # ── STEP 3.6: PERSONA SWITCHER ENGINE (5 CHỨC DANH TƯ PHÁP) ──
    try:
        from app.utils.persona_switcher import detect_persona_switch, get_persona_system_prompt
        role_key, clean_p = detect_persona_switch(prompt)
        if role_key and role_key != "default":
            prompt = clean_p
            persona_prompt = get_persona_system_prompt(role_key)
            print(f"🎭 [PersonaSwitch] Activated role '{role_key}' for query.")
            if formatted_chunks:
                formatted_chunks = f"{persona_prompt}\n\n====================\n\n" + formatted_chunks
            else:
                formatted_chunks = persona_prompt
    except Exception as e_persona:
        print(f"⚠️ [PersonaSwitch] Warning: {e_persona}")

    citation_map = combined_citations
    flare_activated = False
    search_count = len(sub_queries)

    # ── STEP 5: FLARE RAG GENERATION (Tầng 5) ──
    final_text = ""
    citations_list = list(citation_map.values())
    
    # Detect if top result was exact match → skip FLARE draft for speed
    has_exact_match = any("is_exact_match" not in str(v) for v in citation_map.values()) if not citation_map else False
    # Simpler: check if query contains a legal symbol that was matched
    import re as _re
    _has_legal_ref = bool(_re.search(r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|[Đđ]iều\s+\d+)', prompt))
    force_simple = _has_legal_ref  # Skip FLARE draft when query has explicit legal references
    
    if formatted_chunks:
        try:
            async for event in flare_generate_stream(
                query=prompt,
                initial_context=formatted_chunks,
                citation_map=citation_map,
                domain_filter=route_res["doc_type_filter"],
                custom_model=None,  # Sử dụng model mặc định của FPT provider (Qwen3-32B)
                force_simple=force_simple
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

    # ── TÍCH HỢP GỢI Ý TƯƠNG TÁC KẾ TIẾP CỦA LAN ANH ──
    if final_text and "Không tìm thấy tài liệu" not in final_text:
        from app.utils.user_role_detector import generate_lan_anh_followups
        followups = generate_lan_anh_followups(prompt, domain=domain or "general")
        if followups and followups.strip() not in final_text:
            final_text += f"\n{followups}"

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
