"""
Multi-Query Retrieval + Reciprocal Rank Fusion (RRF)
Kỹ thuật chuẩn từ Harvey AI / CoCounsel:
1. Tạo 3 biến thể truy vấn từ câu hỏi gốc
2. Search song song cho từng biến thể
3. Merge kết quả bằng RRF
"""

import re
from typing import List, Dict, Any, Tuple
from app.utils.llm_gateway import LLMGateway
from app.utils.ultimate_retrieval import ultimate_retrieve


# ═══════════════════════════════════════════════════════════════
# 1. CONTEXT RESOLUTION — Giải quyết đại từ mơ hồ
# ═══════════════════════════════════════════════════════════════

CONTEXT_TRIGGER_PATTERN = re.compile(
    r'\b(vậy|thế|nó|anh ấy|chị ấy|người đó|ở trên|như trên|như vậy|'
    r'trường hợp đó|quy định đó|điều đó|luật đó|mức đó|tội đó|hình phạt đó)\b',
    re.IGNORECASE
)

def needs_context_resolution(prompt: str) -> bool:
    """Kiểm tra câu hỏi có cần giải quyết ngữ cảnh không."""
    word_count = len(prompt.split())
    has_ambiguous_ref = bool(CONTEXT_TRIGGER_PATTERN.search(prompt))
    too_short = word_count < 6
    return has_ambiguous_ref or too_short


def resolve_context(prompt: str, recent_history: list) -> str:
    """Nối ngữ cảnh từ tin nhắn trước vào câu hỏi hiện tại."""
    if not recent_history:
        return prompt
    
    # Lấy câu hỏi user gần nhất
    last_user_msg = ""
    for msg in reversed(recent_history):
        if msg.get("role") == "user":
            last_user_msg = msg["content"]
            break
    
    if not last_user_msg:
        return prompt
    
    # Nối context: "Về [câu hỏi trước], [câu hỏi hiện tại]"
    contextualized = f"{last_user_msg}. {prompt}"
    print(f"🔗 [Context Resolution] Merged: '{prompt}' → '{contextualized[:100]}...'")
    return contextualized


# ═══════════════════════════════════════════════════════════════
# 2. ARTICLE-LEVEL EXACT MATCH — Tra cứu Điều luật SQL trực tiếp
# ═══════════════════════════════════════════════════════════════

# Pattern nhận diện tham chiếu Điều luật
ARTICLE_REF_PATTERN = re.compile(
    r'[Đđ]iều\s+(\d+[a-z]?)'
    r'(?:\s*,?\s*[Kk]hoản\s+(\d+))?'
    r'(?:\s*,?\s*[Đđ]iểm\s+([a-zđ]))?'
    r'(?:\s+(?:của\s+|trong\s+|thuộc\s+|theo\s+)?'
    r'((?:Bộ\s+luật|Luật|Nghị\s+định|Thông\s+tư|Pháp\s+lệnh|BLHS|BLDS|BLLĐ)'
    r'(?:\s+[^\n.?!]{2,50})?))?',
    re.IGNORECASE
)

# Bảng mapping tên luật viết tắt → từ khóa search trong title
LAW_ALIASES = {
    "blhs": ["hình sự"],
    "bộ luật hình sự": ["hình sự"],
    "blds": ["dân sự"],
    "bộ luật dân sự": ["dân sự"],
    "bllđ": ["lao động"],
    "bộ luật lao động": ["lao động"],
    "luật hôn nhân": ["hôn nhân", "gia đình"],
    "hôn nhân và gia đình": ["hôn nhân", "gia đình"],
    "hôn nhân gia đình": ["hôn nhân", "gia đình"],
    "luật đất đai": ["đất đai"],
    "luật doanh nghiệp": ["doanh nghiệp"],
    "luật thương mại": ["thương mại"],
    "luật xử lý vi phạm hành chính": ["xử lý vi phạm hành chính"],
    "luật khiếu nại": ["khiếu nại"],
    "luật tố cáo": ["tố cáo"],
    "luật cư trú": ["cư trú"],
    "luật hộ tịch": ["hộ tịch"],
    "luật bảo hiểm xã hội": ["bảo hiểm xã hội"],
    "luật nhà ở": ["nhà ở"],
    "luật xây dựng": ["xây dựng"],
    "luật giao thông đường bộ": ["giao thông đường bộ"],
    "luật phá sản": ["phá sản"],
}


def extract_article_reference(prompt: str) -> Dict[str, Any]:
    """Trích xuất tham chiếu Điều luật từ câu hỏi."""
    match = ARTICLE_REF_PATTERN.search(prompt)
    if not match:
        return None
    
    dieu = match.group(1)
    khoan = match.group(2)
    diem = match.group(3)
    law_name_raw = (match.group(4) or "").strip().rstrip('.,?!;')
    
    # Resolve alias
    law_keywords = []
    if law_name_raw:
        law_lower = law_name_raw.lower().strip()
        for alias, keywords in LAW_ALIASES.items():
            if alias in law_lower:
                law_keywords = keywords
                break
        if not law_keywords:
            # Dùng chính tên luật làm keyword
            law_keywords = [w for w in law_name_raw.split() if len(w) > 2]
    else:
        # TÌM TÊN LUẬT TRONG TOÀN BỘ CÂU HỎI
        prompt_lower = prompt.lower()
        for alias, keywords in LAW_ALIASES.items():
            if alias in prompt_lower:
                law_keywords = keywords
                law_name_raw = alias
                break
    
    return {
        "dieu": dieu,
        "khoan": khoan,
        "diem": diem,
        "law_name": law_name_raw,
        "law_keywords": law_keywords
    }


def article_exact_search(ref: dict, top_k: int = 3) -> Tuple[str, Dict]:
    """Tìm kiếm chính xác nội dung Điều luật bằng SQL trực tiếp."""
    from app.database import get_db_connection
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    dieu = ref["dieu"]
    law_keywords = ref["law_keywords"]
    
    try:
        # Xây dựng WHERE clause
        # Tìm chunk có header chứa "Điều X" trong văn bản có title khớp
        where_parts = [f"c.chunk_header LIKE '%Điều {dieu}%'"]
        params = []
        
        if law_keywords:
            title_conditions = []
            for kw in law_keywords:
                title_conditions.append("d.title LIKE ?")
                params.append(f"%{kw}%")
            where_parts.append(f"({' AND '.join(title_conditions)})")
        
        where_clause = " AND ".join(where_parts)
        
        sql = f"""
            SELECT c.doc_id, c.chunk_header, c.chunk_text, c.chunk_index,
                   d.title, d.so_ky_hieu, d.loai_van_ban, d.tinh_trang_hieu_luc,
                   d.ngay_ban_hanh
            FROM document_chunks c
            JOIN documents d ON c.doc_id = d.id
            WHERE {where_clause}
            ORDER BY 
                CASE WHEN d.tinh_trang_hieu_luc LIKE '%Còn hiệu lực%' THEN 0 ELSE 1 END,
                d.ngay_ban_hanh DESC
            LIMIT ?
        """
        params.append(top_k)
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        if not rows:
            return "", {}
        
        formatted_parts = []
        citation_map = {}
        
        for idx, row in enumerate(rows):
            doc_id, chunk_header, chunk_text, chunk_index, title, so_ky_hieu, loai_van_ban, tinh_trang, ngay_ban_hanh = row
            cid = f"C{idx+1}"
            
            formatted_parts.append(
                f"[{cid}] [{title} - Số hiệu: {so_ky_hieu} - {chunk_header}]\n{chunk_text}"
            )
            citation_map[cid] = {
                "id": doc_id,
                "title": title,
                "so_ky_hieu": so_ky_hieu,
                "loai_van_ban": loai_van_ban,
                "tinh_trang_hieu_luc": tinh_trang,
                "chunk_header": chunk_header,
                "chunk_text": chunk_text
            }
        
        formatted = "\n\n====================\n\n".join(formatted_parts)
        print(f"📌 [Article Exact Match] Found {len(rows)} chunks for Điều {dieu} in '{ref['law_name']}'")
        return formatted, citation_map
        
    except Exception as e:
        print(f"⚠️ Article exact search error: {e}")
        return "", {}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# 3. QUERY DECOMPOSITION — Tách câu hỏi phức tạp
# ═══════════════════════════════════════════════════════════════

def detect_complex_query(prompt: str) -> bool:
    """Phát hiện câu hỏi phức tạp cần tách."""
    question_marks = prompt.count('?')
    has_conditional = bool(re.search(
        r'(?:nếu|giả sử|trường hợp|trong trường hợp).+(?:thì|thế nào|ra sao|như thế nào)',
        prompt, re.IGNORECASE
    ))
    has_multi_parts = bool(re.search(r'(?:\d\)|[a-z]\)|thứ nhất|thứ hai|một là|hai là)', prompt, re.IGNORECASE))
    
    return question_marks >= 2 or has_conditional or has_multi_parts


async def decompose_query(prompt: str) -> List[str]:
    """Tách câu hỏi phức tạp thành các sub-queries bằng LLM."""
    try:
        decompose_instruction = (
            "Tách câu hỏi pháp luật sau thành các câu hỏi con ĐỘC LẬP để tìm kiếm.\n"
            "Mỗi câu hỏi con phải đủ ngữ cảnh để tìm kiếm riêng biệt.\n"
            "Trả lời MỖI CÂU trên MỘT DÒNG, không đánh số, không giải thích.\n"
            "Tối đa 3 câu hỏi con.\n\n"
            f"Câu hỏi gốc: {prompt}\n\nCác câu hỏi con:"
        )
        
        tokens = []
        async for token in LLMGateway.call_stream(
            [{"role": "user", "content": decompose_instruction}],
            "Bạn là công cụ phân tách câu hỏi pháp luật. Chỉ trả lời các câu hỏi con, mỗi câu một dòng.",
            temperature=0.0
        ):
            tokens.append(token)
        
        raw = "".join(tokens).strip()
        sub_queries = [
            line.strip().lstrip('0123456789.-) ').strip()
            for line in raw.split('\n')
            if line.strip() and len(line.strip()) > 8
        ][:3]
        
        if sub_queries:
            print(f"🔀 [Query Decomposition] Split into {len(sub_queries)} sub-queries:")
            for i, sq in enumerate(sub_queries):
                print(f"   [{i+1}] {sq}")
        
        return sub_queries if sub_queries else [prompt]
        
    except Exception as e:
        print(f"⚠️ Query decomposition failed: {e}")
        return [prompt]


# ═══════════════════════════════════════════════════════════════
# 4. MULTI-QUERY RETRIEVAL — Tạo biến thể + search song song
# ═══════════════════════════════════════════════════════════════

async def generate_query_variants(original_query: str) -> List[str]:
    """Tạo 3 biến thể truy vấn: gốc + step-back + keyword extraction."""
    variants = [original_query]
    
    try:
        variant_instruction = (
            "Cho câu hỏi pháp luật Việt Nam sau, tạo 2 biến thể truy vấn tìm kiếm:\n"
            "1. MỘT câu hỏi TỔNG QUÁT hơn (step-back: hỏi về nguyên tắc/khái niệm chung)\n"
            "2. MỘT chuỗi TỪ KHÓA pháp lý chính (chỉ từ khóa, không thành câu)\n\n"
            "Trả lời MỖI biến thể trên MỘT DÒNG, không đánh số.\n\n"
            f"Câu hỏi: {original_query}\n\nBiến thể:"
        )
        
        tokens = []
        async for token in LLMGateway.call_stream(
            [{"role": "user", "content": variant_instruction}],
            "Bạn là công cụ tạo biến thể truy vấn. Chỉ trả lời 2 biến thể, mỗi dòng một cái.",
            temperature=0.0
        ):
            tokens.append(token)
        
        raw = "".join(tokens).strip()
        for line in raw.split('\n'):
            cleaned = line.strip().lstrip('0123456789.-) ').strip()
            if cleaned and len(cleaned) > 5 and cleaned != original_query:
                variants.append(cleaned)
        
        variants = variants[:3]
        print(f"🔄 [Multi-Query] Generated {len(variants)} query variants")
        
    except Exception as e:
        print(f"⚠️ Multi-query generation failed: {e}")
    
    return variants


# ═══════════════════════════════════════════════════════════════
# 5. RECIPROCAL RANK FUSION — Merge kết quả từ nhiều nguồn
# ═══════════════════════════════════════════════════════════════

def reciprocal_rank_fusion(
    results_lists: List[Tuple[str, Dict]],
    k: int = 60
) -> Tuple[str, Dict]:
    """
    Merge kết quả từ nhiều retrieval runs bằng RRF.
    Input: list of (formatted_chunks, citation_map) tuples
    Output: merged (formatted_chunks, citation_map)
    """
    # Parse all chunks and score them
    chunk_scores = {}  # key = (doc_id, chunk_header) → {"score": float, "text": str, "meta": dict}
    
    for run_idx, (formatted, cmap) in enumerate(results_lists):
        if not formatted:
            continue
        
        # Split formatted chunks
        parts = formatted.split("\n\n====================\n\n")
        for rank, part in enumerate(parts):
            # Extract citation anchor from the part
            anchor_match = re.match(r'\[(C\d+)\]', part)
            if not anchor_match:
                continue
            anchor = anchor_match.group(1)
            
            meta = cmap.get(anchor, {})
            doc_id = meta.get("id", 0)
            
            # Extract header for dedup key
            header_match = re.search(r'\[(.+?)\]\n', part)
            header = header_match.group(1) if header_match else f"chunk_{run_idx}_{rank}"
            
            chunk_key = f"{doc_id}_{header}"
            
            # RRF score
            rrf_score = 1.0 / (k + rank + 1)
            
            if chunk_key in chunk_scores:
                chunk_scores[chunk_key]["score"] += rrf_score
            else:
                chunk_scores[chunk_key] = {
                    "score": rrf_score,
                    "text": part,
                    "meta": meta,
                    "doc_id": doc_id
                }
    
    if not chunk_scores:
        return "", {}
    
    # Sort by RRF score
    sorted_chunks = sorted(chunk_scores.values(), key=lambda x: x["score"], reverse=True)
    
    # Re-anchor top results
    formatted_parts = []
    citation_map = {}
    
    for idx, chunk in enumerate(sorted_chunks[:7]):  # Top 7 diverse chunks
        cid = f"C{idx+1}"
        # Re-anchor the text
        text = re.sub(r'\[C\d+\]', f'[{cid}]', chunk["text"], count=1)
        formatted_parts.append(text)
        citation_map[cid] = chunk["meta"]
    
    formatted = "\n\n====================\n\n".join(formatted_parts)
    print(f"🔗 [RRF] Merged {len(results_lists)} runs → {len(citation_map)} unique chunks")
    return formatted, citation_map


# ═══════════════════════════════════════════════════════════════
# 6. HALLUCINATION GUARD — Kiểm tra Điều luật bịa
# ═══════════════════════════════════════════════════════════════

def verify_article_references(response_text: str, context: str) -> str:
    """
    Kiểm tra và đánh dấu các tham chiếu Điều luật trong câu trả lời
    mà không có trong context.
    """
    if not response_text or not context:
        return response_text
    
    context_lower = context.lower()
    
    # Tìm tất cả "Điều X" trong câu trả lời
    article_refs = re.findall(r'Điều\s+(\d+[a-z]?)', response_text)
    
    hallucinated = []
    for dieu in set(article_refs):
        # Kiểm tra xem "Điều X" có xuất hiện trong context không
        if f"điều {dieu}" not in context_lower and f"Điều {dieu}" not in context:
            hallucinated.append(dieu)
    
    if hallucinated:
        print(f"⚠️ [Hallucination Guard] Detected potentially ungrounded articles: Điều {', '.join(hallucinated)}")
        # Không xóa, nhưng log để monitor
        # Trong tương lai có thể thêm footnote cảnh báo
    
    return response_text


# ═══════════════════════════════════════════════════════════════
# 7. MASTER ORCHESTRATOR — Pipeline chính
# ═══════════════════════════════════════════════════════════════

async def enhanced_legal_retrieval(
    prompt: str,
    search_query: str,
    domain_filter: List[str] = None,
    top_k: int = 5,
    recent_history: list = None
) -> Tuple[str, Dict, List[dict]]:
    """
    Pipeline retrieval nâng cao theo chuẩn Legal AI:
    1. Context Resolution
    2. Article Exact Match 
    3. Query Decomposition (if complex)
    4. Multi-Query + RRF
    
    Returns: (formatted_chunks, citation_map, pipeline_info)
    """
    pipeline_info = []
    effective_query = search_query
    
    # ── Step 1: Context Resolution ──
    if recent_history and needs_context_resolution(prompt):
        effective_query = resolve_context(prompt, recent_history)
        pipeline_info.append({"step": "🔗 Đã nối ngữ cảnh từ câu hỏi trước"})
    
    # ── Step 2: Article Exact Match ──
    article_ref = extract_article_reference(prompt)
    article_chunks = ""
    article_citations = {}
    
    if article_ref and article_ref["law_keywords"]:
        article_chunks, article_citations = article_exact_search(article_ref, top_k=3)
        if article_chunks:
            pipeline_info.append({
                "step": f"📌 Tìm thấy Điều {article_ref['dieu']} {article_ref['law_name']}"
            })
    
    # ── Step 3: Check if complex → decompose ──
    sub_queries = [effective_query]
    if detect_complex_query(prompt):
        sub_queries = await decompose_query(prompt)
        if len(sub_queries) > 1:
            pipeline_info.append({
                "step": f"🔀 Tách thành {len(sub_queries)} câu hỏi con"
            })
    
    # ── Step 4: Multi-Query Retrieval ──
    all_results = []
    
    # Nếu có article exact match, thêm vào pool đầu tiên (ưu tiên cao)
    if article_chunks:
        all_results.append((article_chunks, article_citations))
    
    # Search cho từng sub-query
    for sq in sub_queries:
        # Tạo biến thể cho mỗi sub-query (nhưng giới hạn tổng số calls)
        if len(sub_queries) == 1 and not article_chunks:
            # Câu hỏi đơn → tạo multi-query variants
            variants = await generate_query_variants(sq)
            pipeline_info.append({
                "step": f"🔄 Tìm kiếm {len(variants)} biến thể truy vấn"
            })
        else:
            # Đã decompose → mỗi sub-query search 1 lần thôi
            variants = [sq]
        
        for variant in variants:
            chunks, cmap = ultimate_retrieve(
                query=variant,
                domain_filter=domain_filter,
                top_k=top_k
            )
            if chunks:
                all_results.append((chunks, cmap))
    
    # ── Step 5: RRF Merge ──
    if len(all_results) > 1:
        final_chunks, final_citations = reciprocal_rank_fusion(all_results)
        pipeline_info.append({
            "step": f"🔗 Hợp nhất {len(all_results)} nguồn kết quả (RRF)"
        })
    elif len(all_results) == 1:
        final_chunks, final_citations = all_results[0]
    else:
        final_chunks, final_citations = "", {}
    
    return final_chunks, final_citations, pipeline_info
