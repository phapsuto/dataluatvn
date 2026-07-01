import re
from typing import Dict, Any, List, AsyncGenerator
from app.utils.llm_gateway import LLMGateway
from app.utils.ultimate_retrieval import ultimate_retrieve
from app.utils.intent_prompts import classify_intent

# Prompt instructions to guide the LLM to write [SEARCH: ...] placeholders during drafting
FLARE_DRAFT_SYSTEM_PROMPT = """
Bạn là một Luật sư cấp cao đang lập kế hoạch tra cứu tài liệu pháp luật (Query Planner).

Nhiệm vụ của bạn:
1. Đọc kỹ câu hỏi của người dùng và [CÁC ĐOẠN PHÁP LUẬT] hiện có.
2. Đánh giá xem thông tin hiện có đã ĐỦ để trả lời chính xác, trích dẫn rõ ràng từng Điều khoản hay chưa?
3. Nếu ĐÃ ĐỦ, hãy chỉ trả lời một câu duy nhất: "[SUFFICIENT]". Tuyệt đối không giải thích thêm.
4. Nếu CHƯA ĐỦ hoặc cần xác minh lại Điều khoản/Mức phạt cụ thể, hãy tạo ra các truy vấn tìm kiếm bằng cú pháp `[SEARCH: <từ khóa pháp lý hoặc số hiệu văn bản>]`. Tối đa 3 thẻ.
5. TUYỆT ĐỐI KHÔNG VIẾT NHÁP CÂU TRẢ LỜI. Bạn chỉ được phép suy nghĩ xem cần tìm thêm tài liệu gì, và xuất ra các thẻ [SEARCH: ...].

Ví dụ:
[SEARCH: Điều 128 Bộ luật Hình sự 2015]
[SEARCH: Quy định về súng tự chế Luật Quản lý vũ khí]
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
    custom_model: str = None,
    force_simple: bool = False,
    chat_history_text: str = ""
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Asynchronously yields streaming tokens and metadata for the FLARE process:
    - Pass 1: Generates draft. If [SEARCH: ...] placeholders exist, it triggers active retrieval.
    - Pass 2: Merges new context and streams the final answer tokens back to the user.
    
    Uses Multi-task System Prompts: selects specialized prompt based on user intent
    (explain_simple, summarize, qa_practical, classify, scope, full_analysis).
    """
    word_count = len(query.split())
    is_simple = force_simple or word_count < 25 or (domain_filter and "chitchat" in domain_filter)
    
    # ── INTENT-BASED PROMPT SELECTION ──
    qa_type, intent_system_prompt = classify_intent(query)
    print(f"🎯 [Intent] Classified as '{qa_type}' → using specialized prompt")
    
    # ── FIRST PASS: DRAFT GENERATION ──
    # If the query is very short or simple, we skip the drafting phase to save latency.
    if is_simple:
        # Stream directly from first pass with intent-specific prompt
        print("⚡ [FLARE] Query is simple. Skipping active draft phase.")
        async for token in LLMGateway.call_stream(
            messages=[{"role": "user", "content": query}],
            system_prompt=f"{intent_system_prompt}\n\n{chat_history_text}--- TÀI LIỆU PHÁP LUẬT ---\n{initial_context}",
            custom_model=custom_model
        ):
            yield {"type": "token", "content": token}
        yield {"type": "status", "flare_activated": False, "search_count": 0, "citation_map": citation_map}
        return

    # Triggering Query Planner
    print("🧠 [Fast-FLARE] Running Query Planner...")
    draft_messages = [
        {"role": "system", "content": f"{chat_history_text}--- CÁC ĐOẠN PHÁP LUẬT HIỆN CÓ ---\n{initial_context}"},
        {"role": "user", "content": query}
    ]
    
    try:
        draft_text = await collect_full_llm_response(draft_messages, FLARE_DRAFT_SYSTEM_PROMPT, custom_model=custom_model)
    except Exception as e:
        # Fallback to single-pass stream if FPT cloud or primary model fails
        print(f"⚠️ Draft generation failed: {e}. Fallback to direct stream.")
        async for token in LLMGateway.call_stream(
            messages=[{"role": "user", "content": query}],
            system_prompt=f"{intent_system_prompt}\n\n{chat_history_text}--- TÀI LIỆU PHÁP LUẬT ---\n{initial_context}",
            custom_model=custom_model
        ):
            yield {"type": "token", "content": token}
        yield {"type": "status", "flare_activated": False, "search_count": 0, "citation_map": citation_map}
        return

    # Parse [SEARCH: ...] placeholders
    placeholders = re.findall(r'\[SEARCH:\s*(.*?)\]', draft_text)
    
    context_pool = [initial_context]
    new_citation_map = citation_map.copy()
    search_count = 0
    next_citation_idx = len(citation_map) + 1
    
    if not placeholders or "[SUFFICIENT]" in draft_text:
        print("⚡ [FLARE Planner] Dữ liệu đủ. Bỏ qua tìm kiếm.")
        yield {"type": "meta", "info": "no_search_needed"}
    else:
        # ── ACTIVE RETRIEVAL PHASE ──
        print(f"🔄 [FLARE Planner] Yêu cầu tìm {len(placeholders)} từ khóa...")
        yield {"type": "meta", "info": "active_search_triggered", "keywords": placeholders}
        
        import asyncio
        
        tasks = []
        keywords = [k.strip() for k in placeholders[:3] if k.strip()]
        for keyword in keywords:
            print(f"🔍 [FLARE Active Search] Searching for: '{keyword}'...")
            tasks.append(ultimate_retrieve(keyword, domain_filter=domain_filter, top_k=2))
        
        if tasks:
            results = await asyncio.gather(*tasks)
            for keyword, (formatted_chunks, new_citations, _) in zip(keywords, results):
                search_count += 1
                if formatted_chunks:
                    temp_map = {}
                    
                    for old_anchor, meta in new_citations.items():
                        new_anchor = f"C{next_citation_idx}"
                        temp_map[old_anchor] = new_anchor
                        new_citation_map[new_anchor] = meta
                        next_citation_idx += 1
                        
                    adjusted_chunks = formatted_chunks
                    for old_a, new_a in temp_map.items():
                        adjusted_chunks = adjusted_chunks.replace(f"[{old_a}]", f"[{new_a}]")
                        
                    context_pool.append(adjusted_chunks)
            
    # ── SECOND PASS: FINAL GENERATION ──
    merged_context = "\n\n====================\n\n".join(context_pool)
    print("✍️ [FLARE] Generating final grounded answer...")
    
    final_messages = [
        {"role": "system", "content": f"{chat_history_text}--- TÀI LIỆU PHÁP LUẬT BỔ SUNG ---\n{merged_context}"},
        {"role": "user", "content": query}
    ]
    
    async for token in LLMGateway.call_stream(final_messages, intent_system_prompt, temperature=0.1, custom_model=custom_model):
        yield {"type": "token", "content": token}
        
    yield {
        "type": "status", 
        "flare_activated": True, 
        "search_count": search_count, 
        "citation_map": new_citation_map
    }
