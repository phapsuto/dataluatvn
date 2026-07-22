"""
Biệt Đội Multi-Agent Legal Collaborative Squad (4 Sub-Agents)
Hệ thống 4 Sub-Agent chuyên biệt hóa phục vụ tư vấn pháp luật chuyên sâu.
"""

import asyncio
from typing import Dict, Any, List, Optional
from app.utils.legal_router import route_query
from app.utils.query_decomposer import decompose_query, generate_hyde_document
from app.utils.ultimate_retrieval import ultimate_retrieve, apply_lex_conflict_resolution
from app.utils.llm_gateway import LLMGateway
from app.utils.intent_prompts import PROMPT_LEGAL_CONSULTATION

class Router5AxisAgent:
    """Agent 1: Bóc tách 5 trục pháp lý & Định tuyến chuyên ngành."""
    @staticmethod
    async def process(query: str) -> Dict[str, Any]:
        result = route_query(query)
        return {
            "intent": result.get("intent", "GENERAL_QUERY"),
            "domain": result.get("domain", "chung"),
            "five_axes": result.get("five_axes", {})
        }

class SearchHyDEAgent:
    """Agent 2: Phân rã câu hỏi, tạo văn bản giả định HyDE & Tra cứu đa luồng."""
    @staticmethod
    async def process(query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        # Phân rã câu hỏi & Tạo HyDE song song
        sub_queries_task = decompose_query(query, chat_history)
        hyde_task = generate_hyde_document(query)
        
        sub_queries, hyde_doc = await asyncio.gather(sub_queries_task, hyde_task)
        
        # Tra cứu kết hợp cho tất cả sub-queries
        all_chunks = []
        seen_headers = set()
        
        search_queries = list(sub_queries)
        if hyde_doc:
            search_queries.append(hyde_doc)
            
        for q in search_queries:
            result_tuple = await ultimate_retrieve(q, top_k=6)
            # ultimate_retrieve returns (formatted_chunks, citation_map)
            formatted_text, citation_map = result_tuple if isinstance(result_tuple, tuple) else (result_tuple, {})
            if citation_map:
                for cid, info in citation_map.items():
                    if info.get("title") not in seen_headers:
                        seen_headers.add(info.get("title"))
                        all_chunks.append({
                            "document_title": info.get("title"),
                            "document_so_ky_hieu": info.get("so_ky_hieu"),
                            "document_loai_van_ban": info.get("loai_van_ban"),
                            "document_tinh_trang_hieu_luc": info.get("tinh_trang_hieu_luc"),
                            "chunk_header": f"Trích dẫn [{cid}]",
                            "chunk_text": info.get("title")
                        })
                    
        return {
            "sub_queries": sub_queries,
            "hyde_doc": hyde_doc,
            "chunks": all_chunks[:10]
        }

class LexConflictAgent:
    """Agent 3: Phân xử xung đột luật & Kiểm tra tình trạng hiệu lực (Điều 156 VBQPPL)."""
    @staticmethod
    async def process(chunks: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        # Áp dụng Lex Superior / Lex Posterior
        return apply_lex_conflict_resolution(chunks, query)

class MasterDrafterAgent:
    """Agent 4: Tổng hợp bài tư vấn 5 phần chuẩn SOT & Gắn nhãn trích dẫn."""
    @staticmethod
    async def stream_response(
        query: str,
        five_axes: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None
    ):
        context_lines = []
        for idx, c in enumerate(chunks, start=1):
            so_ky_hieu = c.get("document_so_ky_hieu") or "N/A"
            title = c.get("document_title") or ""
            header = c.get("chunk_header") or ""
            text = c.get("chunk_text") or ""
            context_lines.append(f"[C{idx}] [{so_ky_hieu}] {title} - {header}:\n{text}")
            
        context_str = "\n\n".join(context_lines)
        
        history_str = ""
        if chat_history:
            history_str = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in chat_history[-4:]])
            
        user_prompt = f"""Lịch sử hội thoại:
{history_str}

Cơ sở dữ liệu căn cứ pháp lý:
{context_str}

5 Trục pháp lý được bóc tách:
{five_axes}

Câu hỏi của người dùng: "{query}"

Hãy tổng hợp bài tư vấn pháp lý bài bản 5 phần theo đúng định dạng PROMPT_LEGAL_CONSULTATION."""

        messages = [{"role": "user", "content": user_prompt}]
        
        async for token in LLMGateway.call_stream(messages, PROMPT_LEGAL_CONSULTATION, temperature=0.2, max_tokens=4096):
            yield token
            
        # Append Lan Anh interactive follow-up perspective block
        from app.utils.user_role_detector import generate_lan_anh_followups
        domain = five_axes.get("domain", "general") if isinstance(five_axes, dict) else "general"
        followups = generate_lan_anh_followups(query, domain=domain)
        yield followups

class LegalSquadOrchestrator:
    """Bộ điều phối toàn bộ Biệt đội 4 Sub-Agents."""
    @staticmethod
    async def run_full_pipeline(query: str, chat_history: Optional[List[Dict[str, str]]] = None):
        # Step 1: Route & 5-Axis
        route_info = await Router5AxisAgent.process(query)
        
        # Step 2: Search & HyDE
        search_info = await SearchHyDEAgent.process(query, chat_history)
        
        # Step 3: Lex Conflict Resolution
        resolved_chunks = await LexConflictAgent.process(search_info["chunks"], query)
        
        return {
            "route_info": route_info,
            "sub_queries": search_info["sub_queries"],
            "hyde_doc": search_info["hyde_doc"],
            "chunks": resolved_chunks,
            "drafter": MasterDrafterAgent.stream_response(query, route_info["five_axes"], resolved_chunks, chat_history)
        }
