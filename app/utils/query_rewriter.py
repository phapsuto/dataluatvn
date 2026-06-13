import re
from typing import List, Dict, Any, Optional
from app.utils.llm_gateway import LLMGateway
from app.database import get_memory_db

SYSTEM_PROMPT = """Bạn là chuyên gia tinh chỉnh từ khóa tìm kiếm pháp luật Việt Nam. 
Nhiệm vụ của bạn là chuyển đổi câu hỏi tự nhiên của người dùng thành một câu truy vấn tìm kiếm (Search Query) ngắn gọn, chứa các từ khóa pháp lý cốt lõi nhằm phục vụ cho hệ thống tìm kiếm văn bản pháp luật (FTS/Vector Search).

### Nguyên tắc viết lại bắt buộc:
1. Chỉ trả về duy nhất chuỗi từ khóa tìm kiếm mới. KHÔNG giải thích, KHÔNG có lời mở đầu/kết thúc, KHÔNG định dạng markdown thừa thãi, KHÔNG chứa dấu ngoặc kép bọc ngoài câu truy vấn trừ khi đó là cụm từ cần tìm chính xác.
2. Lược bỏ hoàn toàn từ thừa, từ chào hỏi, từ cảm thán hoặc giao tiếp (Ví dụ: "chào bạn", "cho mình hỏi", "giúp mình với", "hả admin", "nhé", "ạ", "cảm ơn").
3. Chuyển đổi ngôn từ dân dã sang thuật ngữ pháp lý chuẩn xác của Việt Nam:
   - "giật đồ", "cướp điện thoại" -> "cướp giật tài sản"
   - "mua bán đất bằng giấy viết tay" -> "chuyển nhượng quyền sử dụng đất bằng giấy tờ viết tay"
   - "quỵt tiền", "bùng nợ" -> "lạm dụng tín nhiệm chiếm đoạt tài sản" hoặc "trốn tránh nghĩa vụ trả nợ"
   - "bị đuổi việc vô lý" -> "đơn phương chấm dứt hợp đồng lao động trái pháp luật"
4. Căn cứ vào Lịch sử trò chuyện để điền khuyết ngữ cảnh bị thiếu trong câu hỏi mới của người dùng (Conversational Coreference Resolution):
   - Lượt 1: hỏi về "tội trộm cắp tài sản".
   - Lượt 2: hỏi "dưới 2 triệu bị phạt thế nào?" -> Viết lại câu hỏi lượt 2 thành: "hình phạt tội trộm cắp tài sản dưới 2 triệu đồng".
5. Giữ nguyên số hiệu điều khoản hoặc số hiệu văn bản pháp luật nếu người dùng có nhắc đến (Ví dụ: "Điều 3 Nghị định 100/2019" -> giữ nguyên "Điều 3 Nghị định 100/2019").

### Ví dụ minh họa (Few-shot):
- User: "Chào admin, cho mình hỏi mua đất bằng giấy viết tay có được cấp sổ đỏ không ạ?"
  -> Output: cấp sổ đỏ đối với đất chuyển nhượng bằng giấy viết tay
  
- User: "Tội cố ý gây thương tích bị đi tù mấy năm?"
  -> Output: mức hình phạt tội cố ý gây thương tích

- [Context: Lịch sử chat đang trao đổi về "thủ tục ly hôn"]
  User: "Thế nộp đơn ở đâu hả bạn?"
  -> Output: thẩm quyền tòa án giải quyết thủ tục ly hôn
"""

async def rewrite_user_query(query: str, session_id: Optional[str] = None) -> str:
    # ── Fast Path Heuristics ──
    # 1. Nếu query quá ngắn (< 3 từ) -> không cần rewrite
    words = query.strip().split()
    if len(words) < 4:
        return query

    # 2. Nếu là số hiệu văn bản hoặc điều khoản cụ thể -> không cần rewrite
    if re.search(r'[Đđ]iều\s+\d+', query) or re.search(r'(\b\d+[\w\-\/]*\/[A-Za-zĐđÀ-ỹ0-9\-]+\b|\b\d+-[A-Za-zĐđÀ-ỹ]{2,}\b)', query):
        return query

    # Lấy lịch sử hội thoại từ Memory DB (tối đa 3 lượt gần nhất để tránh loãng ngữ cảnh)
    chat_history = []
    if session_id:
        try:
            m_conn = get_memory_db()
            m_cursor = m_conn.cursor()
            m_cursor.execute("""
                SELECT role, content FROM chat_messages 
                WHERE session_id = ? 
                ORDER BY message_id DESC LIMIT 6
            """, (session_id,))
            rows = m_cursor.fetchall()
            m_conn.close()
            
            # Đảo ngược lại vì đang lấy DESC
            for r in reversed(rows):
                chat_history.append({"role": r[0], "content": r[1]})
        except Exception as e:
            print(f"⚠️ QueryRewriter: Lỗi đọc lịch sử hội thoại: {e}")

    # Chuẩn bị payload tin nhắn gửi cho LLM
    messages = []
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Thêm câu hỏi hiện tại
    messages.append({"role": "user", "content": f"Hãy tối ưu câu hỏi sau: {query}"})

    try:
        tokens = []
        async for token in LLMGateway.call_stream(messages, SYSTEM_PROMPT, temperature=0.0):
            tokens.append(token)
        rewritten = "".join(tokens).strip()
        
        # Hậu xử lý nếu LLM trả về rỗng hoặc chứa văn bản thừa
        rewritten = re.sub(r'^(Từ khóa:|Query:|Từ khóa tìm kiếm:|Viết lại:|search query:)\s*', '', rewritten, flags=re.IGNORECASE)
        rewritten = rewritten.strip().strip('"').strip("'")
        
        if rewritten:
            print(f"🔄 [QueryRewriter] '{query}' ──> '{rewritten}'")
            return rewritten
    except Exception as e:
        print(f"⚠️ QueryRewriter error: {e}. Fallback to original query.")
        
    return query
