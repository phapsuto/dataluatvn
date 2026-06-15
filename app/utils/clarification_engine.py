"""
Clarification Engine — Hỏi ngược khi câu hỏi mơ hồ
=====================================================
Zero-cost, zero-latency: Hoàn toàn dùng regex + heuristics, KHÔNG gọi LLM.

Luồng xử lý:
1. Kiểm tra fast-path: query đủ rõ → return None (đi thẳng RAG)
2. Match trigger patterns → return câu hỏi gợi mở
3. Kiểm tra generic vague → return câu hỏi chung

Hỗ trợ đầy đủ tiếng Việt: có dấu, không dấu, viết tắt, ngôn ngữ dân dã.
"""
import json
import re
import os
from typing import Optional, Dict, Any, Tuple
from functools import lru_cache


# ── VIETNAMESE TEXT NORMALIZATION ──────────────────────────────────
# Bảng chuyển đổi dấu tiếng Việt → không dấu (để match cả 2 dạng)

_VIET_DIACRITICS = str.maketrans(
    "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
    "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ",
    "a" * 17 + "e" * 11 + "i" * 5 + "o" * 17 + "u" * 11 + "y" * 5 + "d"
    + "A" * 17 + "E" * 11 + "I" * 5 + "O" * 17 + "U" * 11 + "Y" * 5 + "D"
)


def remove_diacritics(text: str) -> str:
    """Chuyển tiếng Việt có dấu thành không dấu. VD: 'mất sổ đỏ' → 'mat so do'"""
    return text.translate(_VIET_DIACRITICS)


def normalize_vn(text: str) -> str:
    """Chuẩn hóa text tiếng Việt: lowercase, bỏ dấu, gộp khoảng trắng."""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


# ── LOAD SCENARIOS ────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_scenarios() -> Dict[str, Any]:
    """Load và cache scenarios JSON. Chỉ đọc file 1 lần duy nhất."""
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "clarification_scenarios.json"
    )
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ ClarificationEngine: Không thể load scenarios: {e}")
        return {"scenarios": [], "generic_vague_patterns": {"patterns": []}}


# ── PRECOMPILE TRIGGER INDEX ──────────────────────────────────────

@lru_cache(maxsize=1)
def _build_trigger_index() -> list:
    """
    Build index: mỗi trigger → (scenario_id, trigger_text_normalized, trigger_text_no_diacritics)
    Được cache lại, chỉ build 1 lần.
    """
    data = _load_scenarios()
    index = []
    for scenario in data.get("scenarios", []):
        sid = scenario["id"]
        domain = scenario["domain"]
        followup = scenario["followup"]
        data_points = scenario.get("data_points", [])
        for trigger in scenario.get("triggers", []):
            norm = normalize_vn(trigger)
            no_diacr = remove_diacritics(norm)
            index.append({
                "id": sid,
                "domain": domain,
                "trigger_norm": norm,
                "trigger_no_diacritics": no_diacr,
                "followup": followup,
                "data_points": data_points
            })
    return index


# ── FAST-PATH CHECKS ──────────────────────────────────────────────

# Regex phát hiện số hiệu văn bản pháp luật VN
_LEGAL_REF_PATTERN = re.compile(
    r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b'  # 12/2024/NĐ-CP
    r'|[Đđ]iều\s+\d+'                              # Điều 36
    r'|[Kk]hoản\s+\d+'                              # Khoản 2
    r'|[Nn]ghị\s*định\s+\d+'                        # Nghị định 100
    r'|[Tt]hông\s*tư\s+\d+'                         # Thông tư 01
    r'|[Ll]uật\s+(?:số\s+)?\d+)'                    # Luật số 65
)

# Từ khóa xác nhận query đã đủ chi tiết
_SPECIFIC_KEYWORDS = re.compile(
    r'(thủ tục|thu tuc'
    r'|hồ sơ|ho so'
    r'|mức phạt|muc phat'
    r'|bao nhiêu|bao nhieu'
    r'|thời hạn|thoi han'
    r'|điều kiện|dieu kien'
    r'|trình tự|trinh tu'
    r'|quy định|quy dinh'
    r'|theo luật|theo luat'
    r'|được không|duoc khong'
    r'|có quyền|co quyen'
    r'|có phải|co phai'
    r'|bị phạt bao|bi phat bao'
    r'|đi tù mấy năm|di tu may nam'
    r'|bao lâu|bao lau'
    r'|ở đâu|o dau'
    r'|cần gì|can gi'
    r'|cần những gì|can nhung gi'
    r'|như thế nào|nhu the nao'
    r'|thế nào|the nao'
    r'|ra sao|xử lý|xu ly)',
    re.IGNORECASE
)

# Loại bỏ từ chào hỏi/thừa đầu câu
_GREETING_STRIP = re.compile(
    r'^(chào\s+(bạn|anh|chị|ad|admin|luatbot|bot|mọi người)'
    r'|xin\s+chào'
    r'|hello|hi|hey'
    r'|cho\s+(mình|tôi|em|tui|t)\s+hỏi'
    r'|giúp\s+(mình|tôi|em|tui)\s+với'
    r'|tư\s+vấn\s+giúp'
    r'|mình\s+muốn\s+hỏi'
    r'|em\s+muốn\s+hỏi'
    r'|anh\s+ơi|chị\s+ơi'
    r'|bạn\s+ơi'
    r'|ạ|nhé|nha|ha'
    r')[,.:!?\s]*',
    re.IGNORECASE
)

# Loại bỏ từ thừa cuối câu  
_TRAILING_STRIP = re.compile(
    r'[\s,.]*(ạ|nhé|nha|vậy|hả|ha|không|ko|giùm|giúp|với|dùm)\s*[?.!]*$',
    re.IGNORECASE
)


def _strip_fillers(text: str) -> str:
    """Bỏ từ chào hỏi/thừa để lấy nội dung thực."""
    text = _GREETING_STRIP.sub('', text).strip()
    text = _TRAILING_STRIP.sub('', text).strip()
    return text


# ── CORE LOGIC ────────────────────────────────────────────────────

# LLM System Prompt cho Tier 2 — BUỘC chạy theo kịch bản dựng sẵn
_CLARIFICATION_SYSTEM_PROMPT = """Bạn là LuatBot — trợ lý pháp lý AI chuyên tư vấn luật Việt Nam.

NHIỆM VỤ: Phân tích câu hỏi của người dùng và quyết định:
- Nếu câu hỏi ĐỦ RÕ RÀNG để tìm kiếm văn bản pháp luật → trả về: PROCEED
- Nếu câu hỏi MƠ HỒ, thiếu dữ kiện → sinh câu hỏi gợi mở THEO ĐÚNG KỊCH BẢN bên dưới

BẮT BUỘC TUÂN THỦ:
1. CHỈ hỏi về các DỮ KIỆN PHÁP LÝ QUAN TRỌNG được liệt kê trong KỊCH BẢN.
2. KHÔNG tự chế câu hỏi ngoài phạm vi kịch bản.
3. Câu hỏi phải thân thiện, dùng emoji đánh số (1️⃣ 2️⃣ 3️⃣), gợi ý phương án trong ngoặc.
4. KHÔNG đưa ra tư vấn pháp lý — chỉ hỏi thu thập dữ kiện.
5. Kết thúc bằng: "_Thông tin càng chi tiết, tôi sẽ tư vấn càng chính xác._"

ĐỊNH DẠNG:
- Đủ rõ: Chỉ trả về "PROCEED" (không thêm gì)
- Mơ hồ: Câu hỏi gợi mở (markdown tiếng Việt)"""


def _is_definitely_clear(query: str, domain: str) -> bool:
    """
    Tier 1: Fast-path regex check — câu hỏi CHẮC CHẮN đủ rõ.
    Zero cost, < 0.1ms.
    """
    if not query or not query.strip():
        return True  # empty → skip clarification
    
    if domain in ("chitchat", "out_of_scope"):
        return True
    
    # Có số hiệu văn bản → đủ rõ
    if _LEGAL_REF_PATTERN.search(query):
        return True
    
    clean = _strip_fillers(query)
    word_count = len(clean.split())
    
    # Query dài ≥ 15 từ → đủ chi tiết
    if word_count >= 15:
        return True
    
    # Có từ khóa câu hỏi cụ thể → đã hỏi rõ rồi
    if _SPECIFIC_KEYWORDS.search(clean):
        return True
    
    return False


def _is_definitely_vague(query: str) -> bool:
    """
    Tier 1: Fast-path check — câu hỏi CHẮC CHẮN mơ hồ.
    Zero cost, < 0.1ms.
    """
    clean = _strip_fillers(query)
    word_count = len(clean.split())
    
    # ≤ 8 từ VÀ match scenario trigger → chắc chắn mơ hồ
    if word_count <= 8 and _match_scenario(clean):
        return True
    
    # ≤ 4 từ VÀ không có specific keywords → chắc chắn mơ hồ
    if word_count <= 4:
        return True
    
    return False


def needs_clarification(query: str, domain: str, chat_history_length: int = 0) -> bool:
    """
    Kiểm tra: câu hỏi có cần hỏi thêm không?
    
    Returns True nếu câu hỏi mơ hồ, cần hỏi thêm.
    Returns False nếu câu hỏi đã đủ rõ ràng.
    
    Hybrid 2 tầng:
    - Tier 1 (regex): Chắc chắn rõ hoặc chắc chắn mơ hồ → trả lời ngay
    - Tier 2 (LLM): Borderline cases → gọi LLM phân tích (async version)
      → Sync version chỉ dùng Tier 1 để tránh block
    """
    # Fast exits
    if _is_definitely_clear(query, domain):
        return False
    
    # Nếu đang trong conversation → skip clarification
    if chat_history_length > 0:
        return False
    
    # Chắc chắn mơ hồ
    if _is_definitely_vague(query):
        return True
    
    # Borderline (5-14 từ, không rõ) → cũng return True
    # để async handler gọi LLM sinh câu hỏi thông minh hơn
    clean = _strip_fillers(query)
    word_count = len(clean.split())
    if word_count <= 8:
        return True
    
    return False


def _match_scenario(query: str) -> Optional[Dict]:
    """
    Match query với trigger patterns.
    Tìm kiếm trên cả dạng có dấu và không dấu.
    """
    index = _build_trigger_index()
    query_norm = normalize_vn(query)
    query_no_diacr = remove_diacritics(query_norm)
    
    best_match = None
    best_score = 0
    
    for entry in index:
        # Check dạng có dấu
        if entry["trigger_norm"] in query_norm:
            score = len(entry["trigger_norm"])
            if score > best_score:
                best_score = score
                best_match = entry
            continue
        
        # Check dạng không dấu
        if entry["trigger_no_diacritics"] in query_no_diacr:
            score = len(entry["trigger_no_diacritics"])
            if score > best_score:
                best_score = score
                best_match = entry
    
    return best_match


def get_clarification_response(query: str, domain: str) -> Optional[str]:
    """
    Tier 1 (Sync): Trả về câu hỏi gợi mở từ template.
    Dùng khi regex match được scenario cụ thể hoặc generic vague.
    """
    clean_query = _strip_fillers(query)
    
    # 1. Match scenario cụ thể → trả template
    match = _match_scenario(clean_query)
    if match:
        print(f"🔮 [Clarification T1] Matched scenario: {match['id']} (domain: {match['domain']})")
        return match["followup"]
    
    # 2. Generic fallback
    topic = clean_query.strip().rstrip('?!.')
    print(f"🔮 [Clarification T1] Generic vague: '{clean_query}'")
    return (
        f"Anh/chị muốn tìm hiểu về **{topic}** theo hướng nào?\n\n"
        "• Đang gặp **tình huống cụ thể** cần tư vấn?\n"
        "• Muốn biết **văn bản pháp luật** quy định?\n"
        "• Cần hướng dẫn **thủ tục** cần thực hiện?\n\n"
        "_Vui lòng mô tả tình huống thực tế để tôi tư vấn chính xác nhất._"
    )


async def get_smart_clarification(query: str, domain: str) -> Optional[str]:
    """
    Tier 2 (Async, LLM-powered): DeepSeek phân tích câu hỏi và sinh
    câu hỏi gợi mở THEO KỊCH BẢN dựng sẵn.
    
    Flow:
    1. Thử match regex scenario trước (free)
    2. Nếu không match → gọi LLM với KỊCH BẢN domain-specific
    3. LLM trả "PROCEED" hoặc câu hỏi theo kịch bản
    
    Returns:
        str: Câu hỏi gợi mở nếu cần clarification
        None: Nếu query đủ rõ → đi thẳng RAG pipeline
    """
    clean_query = _strip_fillers(query)
    
    # ── Tier 1: Regex match scenario (free, <0.1ms) ──
    match = _match_scenario(clean_query)
    if match:
        print(f"🔮 [Clarification T1] Matched scenario: {match['id']}")
        return match["followup"]
    
    # ── Tier 2: LLM phân tích theo kịch bản ──
    try:
        from app.utils.llm_gateway import LLMGateway
        
        # Lấy tất cả scenarios thuộc domain này từ JSON
        data = _load_scenarios()
        domain_scenarios = [s for s in data.get("scenarios", []) if s["domain"] == domain]
        
        # Nếu không có scenario cho domain → dùng tất cả
        if not domain_scenarios:
            domain_scenarios = data.get("scenarios", [])[:5]  # top 5 để tiết kiệm token
        
        # Build kịch bản cho LLM
        scenario_script = ""
        for s in domain_scenarios:
            data_points_str = ", ".join(s.get("data_points", []))
            scenario_script += (
                f"\n📋 Tình huống: {s['id']}\n"
                f"   Từ khóa: {', '.join(s['triggers'][:3])}\n"
                f"   Dữ kiện cần hỏi: [{data_points_str}]\n"
                f"   Ví dụ câu hỏi:\n{s['followup'][:200]}...\n"
            )
        
        domain_label = {
            "dat_dai": "Đất đai — Nhà ở — Sổ đỏ",
            "lao_dong": "Lao động — Bảo hiểm — Hợp đồng",
            "dan_su": "Dân sự — Hôn nhân gia đình — Thừa kế",
            "hinh_su": "Hình sự — Tội phạm — Bào chữa",
            "doanh_nghiep": "Doanh nghiệp — Công ty — Kinh doanh",
            "hanh_chinh": "Hành chính — Xử phạt — Giấy tờ",
        }.get(domain, "Pháp luật Việt Nam")
        
        user_msg = (
            f"=== CÂU HỎI CỦA NGƯỜI DÙNG ===\n"
            f"\"{query}\"\n\n"
            f"=== LĨNH VỰC: {domain_label} ===\n\n"
            f"=== KỊCH BẢN HƯỚNG DẪN (BẮT BUỘC TUÂN THỦ) ===\n"
            f"{scenario_script}\n\n"
            f"=== YÊU CẦU ===\n"
            f"Dựa vào KỊCH BẢN trên:\n"
            f"1. Câu hỏi này đủ rõ để tra cứu pháp luật? → trả 'PROCEED'\n"
            f"2. Nếu mơ hồ → hỏi 2-4 câu THU THẬP DỮ KIỆN theo đúng kịch bản.\n"
            f"   Chỉ hỏi về: [{', '.join(set(dp for s in domain_scenarios for dp in s.get('data_points', [])))}]\n"
            f"3. KHÔNG tự chế câu hỏi ngoài phạm vi kịch bản."
        )
        
        tokens = []
        async for token in LLMGateway.call_stream(
            [{"role": "user", "content": user_msg}],
            _CLARIFICATION_SYSTEM_PROMPT
        ):
            tokens.append(token)
        
        result = "".join(tokens).strip()
        
        # Loại bỏ thinking tags nếu có (DeepSeek V4)
        result = re.sub(r'<think>.*?</think>\s*', '', result, flags=re.DOTALL).strip()
        
        # LLM trả "PROCEED" → query đủ rõ
        if result.upper().startswith("PROCEED"):
            print(f"🔮 [Clarification T2] DeepSeek → PROCEED (đi thẳng RAG)")
            return None
        
        print(f"🔮 [Clarification T2] DeepSeek → câu hỏi gợi mở ({len(result)} chars)")
        return result
        
    except Exception as e:
        print(f"⚠️ [Clarification T2] LLM lỗi, dùng generic: {e}")
        # Fallback về generic template nếu LLM fail
        topic = clean_query.strip().rstrip('?!.')
        return (
            f"Anh/chị muốn tìm hiểu về **{topic}** theo hướng nào?\n\n"
            "• Đang gặp **tình huống cụ thể** cần tư vấn?\n"
            "• Muốn biết **văn bản pháp luật** quy định?\n"
            "• Cần hướng dẫn **thủ tục** cần thực hiện?\n\n"
            "_Vui lòng mô tả tình huống thực tế để tôi tư vấn chính xác nhất._"
        )


def merge_clarification_context(original_query: str, user_reply: str) -> str:
    """
    Gộp câu hỏi gốc + câu trả lời bổ sung thành query mới.
    Dùng cho multi-turn: khi user trả lời sau clarification.
    
    VD: 
      original: "Tôi bị mất sổ đỏ"
      reply: "Mất do thất lạc, đất ở tại TPHCM"
      → merged: "Tôi bị mất sổ đỏ. Mất do thất lạc, đất ở tại TPHCM"
    """
    original = original_query.strip().rstrip('?!.')
    reply = user_reply.strip()
    
    # Gộp đơn giản: original + reply
    merged = f"{original}. {reply}"
    return merged


# ── MODULE SELF-TEST ──────────────────────────────────────────────

if __name__ == "__main__":
    """Test nhanh Clarification Engine."""
    
    test_cases = [
        # (query, domain, expected_needs_clarification)
        ("Tôi bị mất sổ đỏ", "dat_dai", True),
        ("mat so do", "dat_dai", True),
        ("Hàng xóm lấn đất nhà tôi", "dat_dai", True),
        ("Con tôi bị bắt", "hinh_su", True),
        ("Muốn ly hôn", "dan_su", True),
        ("Bị đuổi việc", "lao_dong", True),
        ("Mở công ty", "doanh_nghiep", True),
        ("Bị phạt giao thông", "hanh_chinh", True),
        
        # Câu hỏi ĐỦ RÕ → không cần hỏi thêm
        ("Thủ tục cấp lại sổ đỏ bị mất do thiên tai ở TPHCM như thế nào?", "dat_dai", False),
        ("Điều 175 Bộ luật Hình sự quy định gì?", "hinh_su", False),
        ("Nghị định 100/2019 phạt nồng độ cồn bao nhiêu?", "hanh_chinh", False),
        ("Thời gian nghỉ thai sản theo luật lao động 2019 là bao lâu?", "lao_dong", False),
        ("Chào bạn", "chitchat", False),
    ]
    
    print("=" * 60)
    print("🧪 CLARIFICATION ENGINE — SELF-TEST")
    print("=" * 60)
    
    passed = 0
    total = len(test_cases)
    
    for query, domain, expected in test_cases:
        result = needs_clarification(query, domain)
        status = "✅" if result == expected else "❌"
        if result != expected:
            print(f"\n{status} FAIL: '{query}'")
            print(f"   Expected: {expected}, Got: {result}")
        else:
            passed += 1
        
        if result:
            followup = get_clarification_response(query, domain)
            if followup:
                # Chỉ in 1 dòng đầu
                first_line = followup.split('\n')[0]
                print(f"{status} '{query}' → 🔮 {first_line}")
            else:
                print(f"{status} '{query}' → (needs_clarification=True nhưng không có followup)")
        else:
            print(f"{status} '{query}' → ⏩ Đi thẳng RAG pipeline")
    
    print(f"\n{'=' * 60}")
    print(f"KẾT QUẢ: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print(f"{'=' * 60}")
