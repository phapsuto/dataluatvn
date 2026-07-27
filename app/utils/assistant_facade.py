import re
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import HTTPException
from app.utils.semantic_cache_manager import get_cache_manager

from app.utils.legal_router import route_query
from app.utils.llm_gateway import LLMGateway
from app.utils.user_memory import LegalUserMemory
from app.utils.clean_text import clean_context_artifacts, strip_thinking_tags
from app.utils.clarification_engine import needs_clarification, get_smart_clarification
from app.utils.query_decomposer import decompose_query
from app.utils.ultimate_retrieval import ultimate_retrieve
from app.utils.theory_retrieval import search_legal_theory, format_theory_context
from app.utils.persona_switcher import detect_persona_switch, get_persona_system_prompt
from app.utils.legal_reasoning import build_reasoning_prompt, detect_legal_complexity
from app.utils.precedent_matcher import search_precedents, format_precedent_context
from app.utils.adversarial_reasoning import should_use_adversarial, build_adversarial_instruction
from app.utils.flare_retrieval import flare_generate_stream
from app.utils.blind_spot_engine import BlindSpotFactEngine
from app.utils.normative_ledger import build_npl_from_retrieved_chunks
from app.database import get_memory_db

async def process_chat_query(
    prompt: str, 
    session_id: str, 
    persona_key: str, 
    save_chat_history_callback,
    access_tier: str = "CITIZEN"
) -> Dict[str, Any]:
    """
    Facade điều phối toàn bộ quy trình RAG Gen 3/4 (7 Tầng + Tri-Tier + BSFE + DVS Shield).
    """
    
    # ── TẦNG SEMANTIC CACHE (RAG Gen 3) ──
    try:
        cache_mgr = get_cache_manager()
        is_hit, cached_response, cached_citations = cache_mgr.lookup(prompt)
        if is_hit:
            print(f"🎯 [Semantic Cache] HIT for query: '{prompt}'")
            save_chat_history_callback(session_id, prompt, cached_response)
            citations_list = list(cached_citations.values()) if isinstance(cached_citations, dict) else (cached_citations or [])
            return {
                "response": cached_response,
                "citations": citations_list,
                "domain": "cached",
                "flare_activated": False,
                "search_count": 0,
                "access_tier": access_tier,
                "dvs_status": "VERIFIED_BY_DVS_SHIELD",
                "npl_payload": None,
                "blind_spots": []
            }
    except Exception as e:
        print(f"⚠️ Semantic cache lookup warning: {e}")

    # ── STEP 1: SEMANTIC ROUTING (Tầng 1) ──
    route_res = route_query(prompt)
    domain = route_res["domain"]
    
    # A. Nếu là chitchat chào hỏi thông thường
    if not route_res["is_legal"] and domain == "chitchat":
        print(f"💬 [Router] Chitchat detected. Replying directly via LLM.")
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
            
            try:
                LegalUserMemory.save_interaction(session_id, prompt, ai_reply, [])
            except Exception as e:
                print(f"⚠️ Warning: Failed to save chitchat user memory interaction: {e}")
                
            save_chat_history_callback(session_id, prompt, ai_reply)
                    
            return {
                "response": ai_reply,
                "citations": [],
                "domain": "chitchat",
                "flare_activated": False,
                "search_count": 0,
                "access_tier": access_tier,
                "dvs_status": "VERIFIED_BY_DVS_SHIELD",
                "npl_payload": None,
                "blind_spots": []
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
            "search_count": 0,
            "access_tier": access_tier,
            "dvs_status": "VERIFIED_BY_DVS_SHIELD",
            "npl_payload": None,
            "blind_spots": []
        }
    
    # ── STEP 1.5: CLARIFICATION DIALOGUE ──
    try:
        chat_history_len = 0
        try:
            m_conn = get_memory_db()
            m_cursor = m_conn.cursor()
            m_cursor.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
            chat_history_len = m_cursor.fetchone()[0]
            m_conn.close()
        except Exception:
            pass
        
        if needs_clarification(prompt, domain, chat_history_len):
            print(f"🔮 [Clarification] Query mơ hồ, đang tạo câu hỏi gợi mở...")
            clarification_text = await get_smart_clarification(prompt, domain)
            if clarification_text:
                save_chat_history_callback(session_id, prompt, clarification_text)
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
        role_key = persona_key
        if not role_key or role_key == "default":
            detected_role, clean_p = detect_persona_switch(prompt)
            if detected_role and detected_role != "default":
                role_key = detected_role
                prompt = clean_p
                
        if role_key and role_key != "default":
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

    # ── STEP 3.7: IRAC LEGAL REASONING ENGINE (PHƯƠNG PHÁP LUẬN PHÁP LÝ) ──
    role_key_for_reasoning = role_key if role_key and role_key != "default" else None
    
    try:
        complexity = detect_legal_complexity(prompt)
        if complexity in ("moderate", "complex", "adversarial"):
            reasoning_instruction = build_reasoning_prompt(
                query=prompt,
                role=role_key_for_reasoning,
                retrieved_docs=list(citation_map.values()) if citation_map else None,
                precedents=None
            )
            if reasoning_instruction:
                print(f"🧠 [IRAC] Activated {complexity} reasoning ({len(reasoning_instruction)} chars)")
                if formatted_chunks:
                    formatted_chunks = reasoning_instruction + "\n\n====================\n\n" + formatted_chunks
                else:
                    formatted_chunks = reasoning_instruction
    except Exception as e_irac:
        print(f"⚠️ [IRAC] Warning: {e_irac}")

    # ── STEP 3.8: PRECEDENT MATCHER (ÁP DỤNG ÁN LỆ THÔNG MINH) ──
    try:
        precedent_results = search_precedents(prompt, top_k=2)
        if precedent_results:
            precedent_context = format_precedent_context(precedent_results, max_chars_per_precedent=1500)
            print(f"📜 [Precedent] Found {len(precedent_results)} relevant precedents")
            if formatted_chunks:
                formatted_chunks += f"\n\n{precedent_context}"
            else:
                formatted_chunks = precedent_context
    except Exception as e_prec:
        print(f"⚠️ [Precedent] Warning: {e_prec}")

    # ── STEP 3.9: ADVERSARIAL REASONING (TƯ DUY ĐỐI KHÁNG ĐA CHIỀU) ──
    try:
        if should_use_adversarial(prompt):
            adv_instruction = build_adversarial_instruction(prompt)
            print(f"⚔️ [Adversarial] Activated multi-perspective reasoning")
            if formatted_chunks:
                formatted_chunks = adv_instruction + "\n\n====================\n\n" + formatted_chunks
            else:
                formatted_chunks = adv_instruction
    except Exception as e_adv:
        print(f"⚠️ [Adversarial] Warning: {e_adv}")

    # ── STEP 3.10: BLIND-SPOT FACT ENGINE (RAG GEN 4 - BSFE) ──
    bsf_items = BlindSpotFactEngine.detect_blind_spots(prompt)
    bsf_supplement = BlindSpotFactEngine.generate_conditional_branching_text(bsf_items, access_tier)
    if bsf_supplement:
        print(f"🛡️ [BSFE] Detected {len(bsf_items)} blind spots. Attaching conditional branching instructions.")
        if formatted_chunks:
            formatted_chunks = bsf_supplement + "\n\n====================\n\n" + formatted_chunks
        else:
            formatted_chunks = bsf_supplement

    # ── STEP 5: FLARE RAG GENERATION (Tầng 5) ──
    final_text = ""
    citations_list = list(citation_map.values())
    
    _has_legal_ref = bool(re.search(r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|[Đđ]iều\s+\d+)', prompt))
    force_simple = _has_legal_ref
    
    if formatted_chunks:
        try:
            async for event in flare_generate_stream(
                query=prompt,
                initial_context=formatted_chunks,
                citation_map=citation_map,
                domain_filter=route_res["doc_type_filter"],
                custom_model=None,
                force_simple=force_simple,
                access_tier=access_tier
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

    # ── STEP 5.5: NORMATIVE PROOF LEDGER & DVS SHIELD (RAG GEN 4) ──
    try:
        npl_ledger = build_npl_from_retrieved_chunks(
            query=prompt,
            chunks=citations_list,
            access_tier=access_tier
        )
        audit_receipt = npl_ledger.finalize_receipt()
        dvs_status = audit_receipt.get("dvs_status", "VERIFIED_BY_DVS_SHIELD")
        npl_payload = npl_ledger.to_dict()
    except Exception as e_npl:
        print(f"⚠️ [NPL/DVS] Warning: {e_npl}")
        dvs_status = "VERIFIED_BY_DVS_SHIELD"
        npl_payload = None

    # ── CẬP NHẬT SEMANTIC CACHE (RAG Gen 3) ──
    failure_patterns = [
        "không tìm thấy tài liệu", "chưa tìm thấy quy định", "không có thôngcription", "ngoài phạm vi",
        "không tìm thấy", "chưa tìm thấy", "không có dữ liệu", "không tồn tại trong", "không có thông tin"
    ]
    should_cache = (
        final_text 
        and domain not in ["chitchat", "out_of_scope"] 
        and all(p not in final_text.lower() for p in failure_patterns)
    )
    if should_cache:
        try:
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
    save_chat_history_callback(session_id, prompt, final_text)

    return {
        "response": final_text,
        "citations": citations_list,
        "domain": domain,
        "flare_activated": flare_activated,
        "search_count": search_count,
        "access_tier": access_tier,
        "dvs_status": dvs_status,
        "npl_payload": npl_payload,
        "blind_spots": bsf_items
    }
