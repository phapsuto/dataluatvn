import re
from typing import Dict, Any, List, Tuple, AsyncGenerator
from app.utils.llm_gateway import LLMGateway
from app.utils.ultimate_retrieval import ultimate_retrieve

# Prompt instructions to guide the LLM to write [SEARCH: ...] placeholders during drafting
FLARE_DRAFT_SYSTEM_PROMPT = """
Bạn là LuatBot — trợ lý pháp lý AI chuyên về pháp luật Việt Nam.

QUY TẮC ĐẶC BIỆT KHI SOẠN THẢO NHÁP (FLARE MODE):
1. Dựa trên [CÁC ĐOẠN PHÁP LUẬT] hiện có để nháp câu trả lời.
2. Nếu câu trả lời cần nhắc tới một điều luật, một số hiệu văn bản, hoặc một quy định cụ thể mà [CÁC ĐOẠN PHÁP LUẬT] hiện tại CHƯA cung cấp:
   -> Hãy chèn thẻ placeholder dạng `[SEARCH: <từ khóa pháp lý cụ thể hoặc số ký hiệu văn bản cần tìm>]` ngay tại vị trí cần thông tin đó.
   -> Ví dụ: "Thời giờ làm việc của người lao động bình thường là [SEARCH: thời giờ làm việc bình thường bộ luật lao động 2019] và được trích dẫn theo [C1]."
3. Sau placeholder, tiếp tục viết phần còn lại của câu trả lời nháp bình thường.
4. Trích dẫn neo [Cx] cho các thông tin có sẵn bình thường.
5. Tuyệt đối không tự bịa thông tin nếu thiếu, bắt buộc phải dùng thẻ [SEARCH: ...] để yêu cầu hệ thống tra cứu.
"""

FLARE_FINAL_SYSTEM_PROMPT = """
Bạn là LuatBot — trợ lý pháp lý AI chuyên về pháp luật Việt Nam.

QUY TẮC TUYỆT ĐỐI (Citation & Groundedness):
1. Hãy viết câu trả lời hoàn chỉnh dựa trên [NGỮ CẢNH PHÁP LÝ] bổ sung dưới đây.
2. Mỗi khẳng định pháp lý bắt buộc phải kèm theo ký hiệu neo trích dẫn: "Người lao động có quyền X [C1]".
3. Tuyệt đối KHÔNG sử dụng thẻ placeholder `[SEARCH: ...]` trong câu trả lời này nữa.
4. Nếu vẫn thiếu thông tin, hãy tuyên bố rõ không tìm thấy quy định trong dữ liệu và khuyến nghị liên hệ luật sư. Không bịa đặt thông tin.
"""

async def collect_full_llm_response(messages: List[Dict[str, str]], system_prompt: str, custom_model: str = None) -> str:
    """Helper to collect all stream tokens from LLMGateway into a single string."""
    tokens = []
    try:
        async for token in LLMGateway.call_stream(messages, system_prompt, temperature=0.1, custom_model=custom_model):
            tokens.append(token)
    except Exception as e:
        print(f"⚠️ Error collecting LLM response: {e}")
        raise e
    return "".join(tokens)

async def flare_generate_stream(
    query: str, 
    initial_context: str, 
    citation_map: Dict[str, Dict[str, Any]],
    domain_filter: List[str] = None,
    custom_model: str = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Asynchronously yields streaming tokens and metadata for the FLARE process:
    - Pass 1: Generates draft. If [SEARCH: ...] placeholders exist, it triggers active retrieval.
    - Pass 2: Merges new context and streams the final answer tokens back to the user.
    """
    word_count = len(query.split())
    is_simple = word_count < 15 or (domain_filter and "chitchat" in domain_filter)
    
    # ── FIRST PASS: DRAFT GENERATION ──
    # If the query is very short or simple, we skip the drafting phase to save latency.
    if is_simple:
        # Stream directly from first pass
        print("⚡ [FLARE] Query is simple. Skipping active draft phase.")
        async for token in LLMGateway.call_stream(
            messages=[{"role": "user", "content": query}],
            system_prompt=f"{FLARE_FINAL_SYSTEM_PROMPT}\n\n--- NGỮ CẢNH PHÁP LÝ ---\n{initial_context}",
            custom_model=custom_model
        ):
            yield {"type": "token", "content": token}
        yield {"type": "status", "flare_activated": False, "search_count": 0, "citation_map": citation_map}
        return

    # Triggering Draft generation
    print("🧠 [FLARE] Generating draft answer...")
    draft_messages = [
        {"role": "system", "content": f"--- CÁC ĐOẠN PHÁP LUẬT HIỆN CÓ ---\n{initial_context}"},
        {"role": "user", "content": query}
    ]
    
    try:
        draft_text = await collect_full_llm_response(draft_messages, FLARE_DRAFT_SYSTEM_PROMPT, custom_model=custom_model)
    except Exception as e:
        # Fallback to single-pass stream if FPT cloud or primary model fails
        print(f"⚠️ Draft generation failed: {e}. Fallback to direct stream.")
        async for token in LLMGateway.call_stream(
            messages=[{"role": "user", "content": query}],
            system_prompt=f"{FLARE_FINAL_SYSTEM_PROMPT}\n\n--- NGỮ CẢNH PHÁP LÝ ---\n{initial_context}",
            custom_model=custom_model
        ):
            yield {"type": "token", "content": token}
        yield {"type": "status", "flare_activated": False, "search_count": 0, "citation_map": citation_map}
        return

    # Parse [SEARCH: ...] placeholders
    placeholders = re.findall(r'\[SEARCH:\s*(.*?)\]', draft_text)
    
    if not placeholders:
        # If no placeholders found, we simply stream the already-generated draft text instantly
        print("⚡ [FLARE] No missing details found in draft. Serving draft directly.")
        yield {"type": "meta", "info": "no_search_needed"}
        # Emit draft text token by token to match stream behavior
        for token in re.split(r'(\s+)', draft_text):
            yield {"type": "token", "content": token}
        yield {"type": "status", "flare_activated": False, "search_count": 0, "citation_map": citation_map}
        return

    # ── ACTIVE RETRIEVAL PHASE ──
    print(f"🔄 [FLARE] Found {len(placeholders)} placeholders. Triggering active search...")
    yield {"type": "meta", "info": "active_search_triggered", "keywords": placeholders}
    
    context_pool = [initial_context]
    new_citation_map = citation_map.copy()
    search_count = 0
    next_citation_idx = len(citation_map) + 1
    
    for keyword in placeholders[:3]:  # Limit to top 3 placeholders to avoid infinite search loops
        keyword = keyword.strip()
        if not keyword:
            continue
            
        print(f"🔍 [FLARE Active Search] Searching for: '{keyword}'...")
        formatted_chunks, new_citations = ultimate_retrieve(keyword, domain_filter=domain_filter, top_k=2)
        search_count += 1
        
        if formatted_chunks:
            # Map new citations to higher indexes (e.g. C6, C7...)
            mapped_chunks = []
            temp_map = {}
            
            for old_anchor, meta in new_citations.items():
                new_anchor = f"C{next_citation_idx}"
                temp_map[old_anchor] = new_anchor
                new_citation_map[new_anchor] = meta
                next_citation_idx += 1
                
            # Replace C1, C2 in new chunks with updated C6, C7 anchors
            adjusted_chunks = formatted_chunks
            for old_a, new_a in temp_map.items():
                adjusted_chunks = adjusted_chunks.replace(f"[{old_a}]", f"[{new_a}]")
                
            context_pool.append(adjusted_chunks)
            
    # ── SECOND PASS: FINAL GENERATION ──
    merged_context = "\n\n====================\n\n".join(context_pool)
    print("✍️ [FLARE] Generating final grounded answer...")
    
    final_messages = [
        {"role": "system", "content": f"--- NGỮ CẢNH PHÁP LÝ BỔ SUNG ---\n{merged_context}"},
        {"role": "user", "content": query}
    ]
    
    async for token in LLMGateway.call_stream(final_messages, FLARE_FINAL_SYSTEM_PROMPT, temperature=0.1, custom_model=custom_model):
        yield {"type": "token", "content": token}
        
    yield {
        "type": "status", 
        "flare_activated": True, 
        "search_count": search_count, 
        "citation_map": new_citation_map
    }
