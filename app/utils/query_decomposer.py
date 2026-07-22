import re
import json
from typing import List, Dict, Any, Optional
from app.utils.llm_gateway import LLMGateway

SYSTEM_PROMPT_DECOMPOSE = """Bạn là chuyên gia phân rã truy vấn pháp luật Việt Nam.
Nhiệm vụ của bạn là phân tích câu hỏi người dùng và tách thành các câu hỏi tìm kiếm đơn lẻ, độc lập (Sub-queries), chứa đầy đủ ngữ cảnh để tra cứu cơ sở dữ liệu luật.

QUY TẮC PHÂN RÃ:
1. Nếu câu hỏi đơn giản (chỉ hỏi 1 vấn đề đơn lẻ), trả về đúng 1 câu hỏi đó.
2. Nếu câu hỏi phức hợp (hỏi nhiều vấn đề, ví dụ cả về mức phạt, thẩm quyền và thủ tục), hãy tách thành 2-3 sub-queries độc lập.
3. Nếu có Lịch sử hội thoại, hãy bổ sung ngữ cảnh bị khuyết vào từng sub-query (Conversational Coreference Resolution).
4. Chuẩn hóa thuật ngữ dân dã sang thuật ngữ pháp lý Việt Nam.
5. Định dạng đầu ra BẮT BUỘC là JSON object hợp lệ với duy nhất key "queries":
```json
{
  "queries": ["sub query 1", "sub query 2"]
}
```
"""

async def decompose_query(query: str, chat_history: Optional[List[Dict[str, str]]] = None) -> List[str]:
    """
    Phân rã câu hỏi người dùng thành danh sách các sub-queries tìm kiếm.
    """
    words = query.strip().split()
    # Nếu câu hỏi không có dấu hiệu phức hợp (nhiều vế/nhiều dấu hỏi) hoặc dưới 30 từ, skip LLM call
    has_multi_topic = bool(re.search(r'\?.*\?|vừa.*vừa|đồng thời|vừa\s+\w+\s+vừa|ngoài ra|mặt khác', query, re.IGNORECASE))
    if not has_multi_topic or len(words) < 30:
        return [query]

    # Chuẩn bị tin nhắn gửi tới LLM
    user_content = f"Câu hỏi của người dùng: \"{query}\""
    if chat_history:
        history_str = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in chat_history[-4:]])
        user_content = f"Lịch sử hội thoại:\n{history_str}\n\nCâu hỏi mới nhất: \"{query}\""

    messages = [{"role": "user", "content": user_content}]
    
    try:
        tokens = []
        async for token in LLMGateway.call_stream(messages, SYSTEM_PROMPT_DECOMPOSE, temperature=0.0, max_tokens=300):
            tokens.append(token)
            
        raw_resp = "".join(tokens)
        clean_json = re.sub(r'```json\s*|\s*```', '', raw_resp).strip()
        data = json.loads(clean_json)
        queries = data.get("queries", [])
        
        if isinstance(queries, list) and len(queries) > 0:
            # Lọc bỏ các query rỗng
            clean_queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
            if clean_queries:
                return clean_queries[:4]  # Tối đa 4 sub-queries
    except Exception as e:
        print(f"⚠️ Query decomposition error: {e}")
        
    return [query]

SYSTEM_PROMPT_HYDE = """Bạn là chuyên gia soạn thảo giả định văn bản pháp luật Việt Nam.
Nhiệm vụ của bạn là dựa vào câu hỏi dân dã của người dùng để viết lại thành 1 đoạn văn bản pháp luật giả định (Hypothetical Legal Document) ngắn 2-3 câu, chứa các thuật ngữ pháp lý chính thức.
Ví dụ: "Làm sao để không bị thu hồi nhà?" -> "Theo quy định tại Luật Đất đai, trường hợp thu hồi đất ở phải đảm bảo điều kiện bồi thường, tái định cư và đúng thẩm quyền ban hành quyết định thu hồi đất."
Chỉ trả về duy nhất 1 đoạn văn bản giả định, không giải thích thêm."""

async def generate_hyde_document(query: str) -> Optional[str]:
    """
    Sinh đoạn văn bản pháp luật giả định (HyDE) để tăng độ chính xác tra cứu vector với các câu hỏi dân dã.
    """
    colloquial_keywords = ["làm sao", "thế nào", "có bị làm sao", "bùng nợ", "bị đuổi việc", "quỵt tiền", "giật đồ"]
    q_lower = query.lower()
    if not any(kw in q_lower for kw in colloquial_keywords):
        return None
        
    try:
        messages = [{"role": "user", "content": f"Viết đoạn pháp luật giả định cho câu hỏi: \"{query}\""}]
        tokens = []
        async for token in LLMGateway.call_stream(messages, SYSTEM_PROMPT_HYDE, temperature=0.2, max_tokens=150):
            tokens.append(token)
        hypo_doc = "".join(tokens).strip()
        if hypo_doc:
            return hypo_doc
    except Exception as e:
        print(f"⚠️ HyDE generation error: {e}")
    return None
