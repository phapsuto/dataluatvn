import json
import re
from typing import Dict, Any
from app.utils.llm_gateway import LLMGateway

SMART_ROUTER_SYSTEM_PROMPT = """Bạn là Bộ Định Tuyến Thông Minh (Smart Router) của hệ thống Trợ lý Pháp luật Việt Nam.
Nhiệm vụ của bạn là phân tích câu hỏi của người dùng và trả về một chuỗi JSON duy nhất, hợp lệ.
KHÔNG giải thích, KHÔNG trả lời câu hỏi pháp lý, chỉ trả về JSON.

Các lĩnh vực (domain) hợp lệ:
- "lao_dong": Lao động, BHXH, tiền lương, đuổi việc, thai sản...
- "dan_su": Dân sự, hợp đồng, hôn nhân, ly dị, thừa kế, di chúc...
- "hinh_su": Hình sự, tội phạm, tố tụng, án tù, lừa đảo, trộm cắp...
- "dat_dai": Đất đai, sổ đỏ, quy hoạch, giải tỏa, tranh chấp nhà cửa...
- "doanh_nghiep": Doanh nghiệp, thành lập công ty, cổ phần, phá sản...
- "hanh_chinh": Hành chính, phạt giao thông, căn cước, hộ chiếu, giấy phép...
- "chitchat": Lời chào hỏi (hello, hi, cảm ơn, bạn là ai...).
- "out_of_scope": Nấu ăn, lập trình, y tế, bóng đá...

Quy tắc bóc tách (Entities):
- extracted_year: Năm (số nguyên, ví dụ: 2024). Trích xuất từ số hiệu (12/2024/NĐ-CP) hoặc câu (năm 2024). Nếu không rõ, để null.
- extracted_doc_type: Loại văn bản (Luật, Nghị định, Thông tư, Quyết định, Nghị quyết...). Viết hoa chữ đầu. Để null nếu không có.
- extracted_issuer: Cơ quan ban hành (Chính phủ, Quốc hội, Bộ Tài chính, UBND...). Để null nếu không có.
- extracted_doc_number: Số ký hiệu hoặc Điều khoản cụ thể (VD: "12/2024/NĐ-CP", "Điều 15", "Khoản 2"). Giữ nguyên format gốc. Để null nếu không có.

Quy tắc Clarification (Làm rõ):
- Nếu câu hỏi quá ngắn hoặc thiếu dữ kiện quan trọng (VD: "Mất sổ đỏ thì sao?", "Bị đuổi việc", "Đóng bảo hiểm bao lâu"), hãy set `needs_clarification`: true và viết một câu hỏi ngược thân thiện `clarification_question` để xin thêm chi tiết (VD: "Bạn bị mất sổ đỏ do thất lạc hay do thiên tai hỏa hoạn? Đất của bạn thuộc tỉnh nào?").
- Nếu câu hỏi đã đủ dài và rõ (>= 15 từ, hoặc có số hiệu cụ thể), set `needs_clarification`: false, `clarification_question`: null.

Quy tắc Search Query (Rewrite):
- Chuyển đổi câu hỏi gốc thành chuỗi từ khóa tối ưu cho công cụ tìm kiếm Full-Text Search.
- Bỏ các từ vô nghĩa (cho tôi hỏi, theo luật hiện hành, như thế nào, ra sao...).
- VD: "Cho mình hỏi luật quy định thế nào về mức phạt nồng độ cồn xe máy" -> "mức phạt nồng độ cồn xe máy".

Output Format (JSON strictly):
{
    "domain": "string (một trong các giá trị hợp lệ)",
    "is_legal": boolean (true nếu thuộc 6 lĩnh vực pháp luật, false nếu chitchat/out_of_scope),
    "extracted_year": int or null,
    "extracted_doc_type": "string or null",
    "extracted_issuer": "string or null",
    "extracted_doc_number": "string or null",
    "needs_clarification": boolean,
    "clarification_question": "string or null",
    "search_query": "string"
}
"""

async def analyze_query(query: str, chat_history_len: int = 0) -> Dict[str, Any]:
    """
    Phân tích câu hỏi bằng LLM theo mô hình One-Shot.
    Nếu đang trong luồng hội thoại (chat_history_len > 0), giảm thiểu việc hỏi ngược.
    """
    # Fast regex path for purely chitchat to save LLM cost
    query_clean = re.sub(r'[^\w\s]', '', query.strip().lower())
    words = query_clean.split()
    short_chitchat = {"chào", "hello", "hi", "thanks", "cảm ơn", "cám ơn", "tạm biệt", "bye"}
    if len(words) <= 3 and any(w in short_chitchat for w in words):
        return {
            "domain": "chitchat",
            "is_legal": False,
            "extracted_year": None,
            "extracted_doc_type": None,
            "extracted_issuer": None,
            "extracted_doc_number": None,
            "needs_clarification": False,
            "clarification_question": None,
            "search_query": query
        }

    user_prompt = f"Câu hỏi: \"{query}\"\n(Lịch sử chat: {chat_history_len} tin nhắn trước đó. Bỏ qua clarification nếu đang trong ngữ cảnh chat liên tục)."
    
    try:
        raw_response = await LLMGateway.call_async(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=SMART_ROUTER_SYSTEM_PROMPT,
            temperature=0.0,  # Strict mode
            response_format={"type": "json_object"}
        )
        
        # Clean potential markdown JSON wrapping
        clean_json = raw_response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
            
        data = json.loads(clean_json.strip())
        
        # Override clarification if in middle of chat
        if chat_history_len > 0:
            data["needs_clarification"] = False
            data["clarification_question"] = None
            
        return data
        
    except Exception as e:
        print(f"⚠️ SmartRouter failed: {e}. Falling back to default values.")
        # Graceful fallback so system doesn't crash
        return {
            "domain": "dan_su", # Default safe legal domain
            "is_legal": True,
            "extracted_year": None,
            "extracted_doc_type": None,
            "extracted_issuer": None,
            "extracted_doc_number": None,
            "needs_clarification": False,
            "clarification_question": None,
            "search_query": query
        }
