import re
import requests
import json
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
    
    # ── STEP 1: SEMANTIC ROUTING (Tầng 1) ──
    route_res = route_query(prompt)
    domain = route_res["domain"]
    
    # A. Nếu là chitchat chào hỏi thông thường
    if not route_res["is_legal"] and domain == "chitchat":
        print(f"💬 [Router] Chitchat detected. Replying directly via LLM.")
        
        # ── STEP 2: LOAD LONG-TERM MEMORY (Tầng 2) ──
        memory_context = LegalUserMemory.get_relevant_memories(session_id, prompt)
        
        system_prompt = (
            "Bạn là LuatBot - Trợ lý pháp lý AI chuyên về luật Việt Nam.\n"
            "Hãy trả lời người dùng một cách thân thiện, lịch sự, ngắn gọn và "
            "nhắc nhở rằng bạn sẵn sàng hỗ trợ các câu hỏi liên quan đến pháp luật Việt Nam."
        )
        if memory_context:
            system_prompt += f"\n\nNgữ cảnh thông tin đã nhớ về người dùng:\n{memory_context}\n(Nếu người dùng hỏi thông tin cá nhân của họ mà khớp với ngữ cảnh trên, hãy trả lời chính xác dựa theo đó)."
            
        try:
            tokens = []
            async for token in LLMGateway.call_stream([{"role": "user", "content": prompt}], system_prompt):
                tokens.append(token)
            ai_reply = "".join(tokens)
            
            # ── STEP 6: SAVE INTERACTION TO MEMORY (Tầng 2) ──
            try:
                LegalUserMemory.save_interaction(session_id, prompt, ai_reply, [])
            except Exception as e:
                print(f"⚠️ Warning: Failed to save chitchat user memory interaction: {e}")
                
            # ── STEP 7: SAVE TO SESSION CHAT HISTORY DB ──
            if session_id:
                try:
                    m_conn = get_memory_db()
                    m_cursor = m_conn.cursor()
                    
                    # Check if session exists
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
                        (session_id, "assistant", ai_reply, now_iso)
                    )
                    m_conn.commit()
                    m_conn.close()
                except Exception as e:
                    print(f"⚠️ Error saving session message log: {e}")
                    
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
        
    # ── STEP 2: LOAD LONG-TERM MEMORY (Tầng 2) ──
    memory_context = LegalUserMemory.get_relevant_memories(session_id, prompt)
    
    # ── STEP 3 & 4: ADAPTIVE RETRIEVAL (Tầng 3 + 4) ──
    if route_res.get("routing_level") == 2:
        # Level 2: Simple Lookup using FTS5 (no vector, no graph)
        print(f"⚡ [Adaptive Routing] Level 2 (Simple Lookup) detected for query: '{prompt}'")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Match using FTS5 on chunks_fts
        query_terms = " AND ".join([f'"{w}"' for w in prompt.split() if len(w) > 1])
        fts_query = """
            SELECT c.doc_id, c.chunk_header, c.chunk_text, d.title, d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc
            FROM document_chunks c
            JOIN documents d ON c.doc_id = d.id
            JOIN chunks_fts f ON f.rowid = c.id
            WHERE chunks_fts MATCH ?
            LIMIT 3
        """
        formatted_parts = []
        citation_map = {}
        try:
            cursor.execute(fts_query, (query_terms,))
            rows = cursor.fetchall()
            for r_idx, row in enumerate(rows):
                doc_id, chunk_header, chunk_text, title, so_ky_hieu, loai_van_ban, tinh_trang = row
                cid_label = f"C{r_idx+1}"
                formatted_parts.append(f"[{cid_label}] [{title} - Số hiệu: {so_ky_hieu} - {chunk_header}]\n{chunk_text}")
                citation_map[cid_label] = {
                    "id": doc_id,
                    "title": title,
                    "so_ky_hieu": so_ky_hieu,
                    "loai_van_ban": loai_van_ban,
                    "tinh_trang_hieu_luc": tinh_trang
                }
            formatted_chunks = "\n\n====================\n\n".join(formatted_parts)
        except Exception as e:
            print(f"⚠️ Level 2 FTS lookup fallback to ultimate_retrieve due to: {e}")
            formatted_chunks, citation_map = ultimate_retrieve(query=prompt, domain_filter=route_res["doc_type_filter"], top_k=3)
        finally:
            conn.close()
            
        flare_activated = False
        search_count = 0
    else:
        # Level 3: Complex Retrieval (FTS5 + FAISS + HippoRAG Graph Expansion + Cohere Rerank)
        print(f"🔍 [Retrieval] Searching database for Level 3 query: '{prompt}' (Filters: {route_res['doc_type_filter']})")
        formatted_chunks, citation_map = ultimate_retrieve(
            query=prompt,
            domain_filter=route_res["doc_type_filter"],
            top_k=5
        )
        flare_activated = False
        search_count = 1

    # ── STEP 5: SPECULATIVE RAG (DRAFT-THEN-VERIFY) (Tầng 5) ──
    final_text = ""
    citations_list = list(citation_map.values())
    
    if formatted_chunks:
        try:
            import asyncio
            
            # Helper to get full response from LLM
            async def get_llm_response(msgs: List[Dict[str, str]], sys_p: str, prov: str) -> str:
                old_prov = LLMGateway._active_provider
                LLMGateway._active_provider = prov
                try:
                    tokens = []
                    async for token in LLMGateway.call_stream(msgs, sys_p):
                        tokens.append(token)
                    return "".join(tokens)
                finally:
                    LLMGateway._active_provider = old_prov

            # Split context chunks
            chunks_list = formatted_chunks.split("\n\n====================\n\n")
            
            # Partition chunks into subsets for parallel drafting
            subsets = []
            if len(chunks_list) > 3:
                subsets.append(chunks_list[:3])
                subsets.append(chunks_list[3:])
            else:
                subsets.append(chunks_list)
                
            # Draft generation in parallel using gemini (Gemini 2.0 Flash)
            async def generate_draft(sub_chunks: List[str], idx: int) -> str:
                context = "\n\n".join(sub_chunks)
                sys_prompt = (
                    "Bạn là trợ lý pháp lý ảo. Hãy đọc kỹ phần tài liệu pháp luật được cung cấp dưới đây và viết một bản thảo nháp ngắn gọn (dưới 200 từ) trả lời câu hỏi của người dùng.\n"
                    "Trích dẫn chính xác ký hiệu neo [C1], [C2], v.v. từ tài liệu gốc. Nếu tài liệu không liên quan đến câu hỏi, hãy ghi 'Không có thông tin liên quan'.\n"
                    f"--- Tài liệu gốc ---\n{context}"
                )
                return await get_llm_response([{"role": "user", "content": prompt}], sys_prompt, "gemini")

            draft_tasks = [generate_draft(sub, idx) for idx, sub in enumerate(subsets)]
            drafts = await asyncio.gather(*draft_tasks, return_exceptions=True)
            
            clean_drafts = []
            for d in drafts:
                if isinstance(d, str) and "Không có thông tin liên quan" not in d:
                    clean_drafts.append(d)
                    
            if not clean_drafts:
                clean_drafts = [str(d) for d in drafts if isinstance(d, str)]
                
            # Verification step on the active provider (e.g. gemini_pro or fpt)
            drafts_context = "\n\n=== BẢN THẢO NHÁP PHÁP LÝ ===\n" + "\n\n".join(clean_drafts)
            
            verify_system_prompt = (
                "Bạn là LuatBot - Trợ lý pháp lý AI chuyên sâu về luật Việt Nam.\n"
                "Dưới đây là câu hỏi của người dùng kèm theo các bản thảo nháp pháp lý được tổng hợp từ tài liệu gốc chính xác.\n"
                "Nhiệm vụ của bạn:\n"
                "1. Đối soát các bản thảo nháp này, loại bỏ các thông tin mâu thuẫn, sai lệch hoặc không chính xác.\n"
                "2. Tổng hợp thành một câu trả lời hoàn chỉnh, chuyên nghiệp, chính xác 100% bằng Tiếng Việt.\n"
                "3. Giữ nguyên và khóa chặt các trích dẫn neo [C1], [C2] từ các bản thảo nháp để người dùng đối chiếu.\n"
                f"{drafts_context}"
            )
            
            tokens = []
            async for token in LLMGateway.call_stream([{"role": "user", "content": prompt}], verify_system_prompt):
                tokens.append(token)
            final_text = "".join(tokens)
            
        except Exception as e:
            print(f"⚠️ Speculative RAG failed: {e}. Fallback to standard FLARE generation.")
            try:
                async for event in flare_generate_stream(
                    query=prompt,
                    initial_context=formatted_chunks,
                    citation_map=citation_map,
                    domain_filter=route_res["doc_type_filter"]
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
        
    # ── STEP 6: SAVE INTERACTION TO MEMORY (Tầng 2) ──
    try:
        LegalUserMemory.save_interaction(session_id, prompt, final_text, citations_list)
    except Exception as e:
        print(f"⚠️ Warning: Failed to save user memory interaction: {e}")
        
    # ── STEP 7: SAVE TO SESSION CHAT HISTORY DB ──
    if session_id:
        try:
            m_conn = get_memory_db()
            m_cursor = m_conn.cursor()
            
            # Check if session exists
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
                (session_id, "assistant", final_text, now_iso)
            )
            m_conn.commit()
            m_conn.close()
        except Exception as e:
            print(f"⚠️ Error saving session message log: {e}")

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
