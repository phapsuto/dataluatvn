import os
import re
import sqlite3
import requests
from typing import List
from app.config import FPT_CLOUD_API_KEY, MEMORY_DB

# Cấu hình API FPT Cloud
FPT_URL = "https://mkp-api.fptcloud.com/v1/chat/completions"
FPT_MODEL = "gemma-4-31B-it"
API_TIMEOUT = 2.5  # Giới hạn timeout 2.5s để bảo vệ độ trễ API

def init_cache_db():
    """Khởi tạo bảng cache query expansion trong SQLite memory db."""
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_expansion_cache (
                query_text TEXT PRIMARY KEY,
                expanded_terms TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Không thể khởi tạo cache DB: {e}")

def get_cached_expansion(query: str) -> Optional[List[str]]:
    """Đọc từ cache SQLite."""
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT expanded_terms FROM query_expansion_cache WHERE query_text = ?", (query.lower().strip(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return [t.strip() for t in row[0].split(",") if t.strip()]
    except Exception as e:
        print(f"⚠️ Lỗi đọc cache query expansion: {e}")
    return None

def set_cached_expansion(query: str, terms: List[str]):
    """Ghi kết quả vào cache SQLite."""
    if not terms:
        return
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cursor = conn.cursor()
        terms_str = ",".join(terms)
        cursor.execute(
            "INSERT OR REPLACE INTO query_expansion_cache (query_text, expanded_terms) VALUES (?, ?)",
            (query.lower().strip(), terms_str)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi ghi cache query expansion: {e}")

def should_expand_query(q: str) -> bool:
    """
    Chỉ kích hoạt Query Expansion khi:
    - Query dài hơn 3 từ (là câu hỏi tự nhiên phức tạp).
    - Không phải là số ký hiệu thuần túy (bắt đầu bằng dạng số hiệu).
    """
    clean_q = q.strip()
    if not clean_q:
        return False
        
    # Loại trừ số hiệu (ví dụ chứa định dạng số/ngày/tháng hoặc số ký hiệu viết tắt)
    if re.search(r'\b\d+/', clean_q):
        return False
        
    words = clean_q.split()
    if len(words) <= 3:
        return False
        
    return True

def expand_query(q: str) -> List[str]:
    """
    Gọi LLM để tìm 2-3 cụm từ đồng nghĩa hoặc thuật ngữ pháp lý tương đương.
    Có cơ chế cache và timeout fallback an toàn.
    """
    if not should_expand_query(q):
        return []
        
    q_clean = q.lower().strip()
    
    # 1. Kiểm tra cache
    cached = get_cached_expansion(q_clean)
    if cached is not None:
        return cached

    # 2. Chuẩn bị gọi LLM FPT Cloud
    if not FPT_CLOUD_API_KEY:
        print("⚠️ FPT_CLOUD_API_KEY chưa được cấu hình. Bỏ qua Query Expansion.")
        return []
        
    headers = {
        "Authorization": f"Bearer {FPT_CLOUD_API_KEY}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "Bạn là trợ lý đắc lực cho hệ thống tìm kiếm pháp luật Việt Nam.\n"
        "Nhiệm vụ của bạn là đọc câu hỏi của người dùng và trả về chính xác từ 2 đến 3 từ khóa hoặc cụm từ đồng nghĩa, hoặc thuật ngữ pháp lý tương đương liên quan trực tiếp nhất đến câu hỏi.\n"
        "Quy tắc tuyệt đối:\n"
        "- Chỉ trả về các cụm từ cách nhau bằng dấu phẩy.\n"
        "- KHÔNG viết thêm bất kỳ lời giải thích, mở đầu, kết luận hoặc markdown nào khác."
    )
    
    payload = {
        "model": FPT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "thủ tục ly hôn và chia đất"},
            {"role": "assistant", "content": "chấm dứt hôn nhân, phân chia tài sản chung, quyền sử dụng đất"},
            {"role": "user", "content": "bị công an bắt xe máy phạt bao nhiêu tiền"},
            {"role": "assistant", "content": "tạm giữ phương tiện giao thông, xử phạt vi phạm hành chính, luật giao thông đường bộ"},
            {"role": "user", "content": q}
        ],
        "temperature": 0.3,
        "max_tokens": 100
    }
    
    # 3. Gọi API với Timeout Fallback
    try:
        response = requests.post(FPT_URL, json=payload, headers=headers, timeout=API_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            
            # Parsing và làm sạch
            terms = [t.strip() for t in content.split(",") if t.strip()]
            
            # Chỉ lấy tối đa 3 terms để tránh nhiễu
            terms = terms[:3]
            
            # Ghi vào cache
            if terms:
                set_cached_expansion(q_clean, terms)
                return terms
        else:
            print(f"⚠️ API FPT Cloud trả về mã lỗi: {response.status_code} | {response.text}")
    except requests.Timeout:
        print(f"⌛ Timeout ({API_TIMEOUT}s) khi gọi FPT Cloud API cho query: '{q}'. Fallback sử dụng query gốc.")
    except Exception as e:
        print(f"⚠️ Lỗi kết nối khi gọi FPT Cloud API: {e}")
        
    return []

# Khởi tạo cache db khi module được import
init_cache_db()
