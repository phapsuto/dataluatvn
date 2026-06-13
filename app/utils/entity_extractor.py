import re
import sqlite3
from typing import List, Dict, Any, Set
from app.database import get_db_connection
from app.routers.laws import normalize_spelling

_LAWS_CACHE = None

def load_laws_cache():
    """Tải danh sách các Luật, Bộ luật, Hiến pháp, Pháp lệnh vào RAM."""
    global _LAWS_CACHE
    if _LAWS_CACHE is not None:
        return _LAWS_CACHE
    
    _LAWS_CACHE = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh 
            FROM documents 
            WHERE loai_van_ban IN ('Luật', 'Bộ luật', 'Hiến pháp', 'Pháp lệnh')
        """)
        for row in cursor.fetchall():
            doc_id, title, so_ky_hieu, loai_van_ban, ngay_ban_hanh = row
            # Normalize spelling
            title_norm = normalize_spelling(title or "").strip()
            type_norm = normalize_spelling(loai_van_ban or "").strip()
            
            # Key normalized title for exact matching
            normalized_title = normalize_title_for_matching(title_norm)
            normalized_type = normalize_title_for_matching(type_norm)
            
            _LAWS_CACHE.append({
                "id": doc_id,
                "title": title_norm,
                "so_ky_hieu": so_ky_hieu,
                "loai_van_ban": loai_van_ban,
                "normalized_title": normalized_title,
                "normalized_type": normalized_type
            })
        conn.close()
        print(f"ℹ️ Loaded {len(_LAWS_CACHE)} laws/codes into entity extractor cache")
    except Exception as e:
        print(f"⚠️ Error loading laws cache: {e}")
        _LAWS_CACHE = []
    return _LAWS_CACHE

def normalize_title_for_matching(text: str) -> str:
    """Chuẩn hóa chuỗi bằng cách viết thường, xóa dấu tiếng Việt, xóa khoảng trắng và từ nối."""
    if not text:
        return ""
    text = text.lower()
    # Loại bỏ các từ nối phổ biến trong tiếng Việt hành chính để so khớp linh hoạt
    text = re.sub(r'\b(và|của|về|với|tại|trong|cho|nhằm|để|nước|cộng|hòa|xã|hội|chủ|nghĩa|việt|nam)\b', '', text)
    # Loại bỏ dấu tiếng Việt (giúp khớp cả khi gõ không dấu)
    import unicodedata
    text = unicodedata.normalize('NFD', text)
    text = re.sub(r'[\u0300-\u036f]', '', text)
    text = text.replace('đ', 'd').replace('Đ', 'D')
    # Loại bỏ ký tự đặc biệt và khoảng trắng
    text = re.sub(r'[^\w]', '', text)
    return text

def expand_abbreviations(text: str) -> str:
    """Mở rộng các từ viết tắt luật phổ biến."""
    text = text.lower()
    text = re.sub(r'\bblds\b', 'bộ luật dân sự', text)
    text = re.sub(r'\bblhs\b', 'bộ luật hình sự', text)
    text = re.sub(r'\bbllđ\b', 'bộ luật lao động', text)
    text = re.sub(r'\blđđ\b', 'luật đất đai', text)
    text = re.sub(r'\bhngđ\b', 'hôn nhân gia đình', text)
    text = re.sub(r'\btt-bgtvt\b', 'thông tư bộ giao thông vận tải', text)
    return text

def extract_entities(query: str) -> Set[int]:
    """
    Trích xuất các thực thể văn bản pháp luật từ câu hỏi.
    Trả về set các doc_id tìm được.
    """
    doc_ids = set()
    if not query:
        return doc_ids
    
    # 1. Chuẩn hóa câu hỏi
    q_spelled = normalize_spelling(query)
    q_expanded = expand_abbreviations(q_spelled)
    q_norm = normalize_title_for_matching(q_expanded)
    
    # 2. Khớp danh mục Luật / Bộ luật từ RAM Cache
    laws = load_laws_cache()
    for law in laws:
        normalized_title = law["normalized_title"]
        normalized_type = law["normalized_type"]
        
        # Tạo chuỗi so khớp kết hợp, ví dụ "luatdatdai", "boluatdansu"
        match_key = f"{normalized_type}{normalized_title}"
        
        if match_key in q_norm:
            doc_ids.add(law["id"])
            
    # 3. Khớp các Nghị định, Thông tư theo Số hiệu viết tắt trong câu hỏi
    # Mẫu 1: "Nghị định 15/2020" hoặc "Thông tư 24/2018"
    pattern1 = re.compile(
        r'(nghị định|thông tư|quyết định|nghị quyết|pháp lệnh)\s+(?:số\s+)?(\d+)/(\d{4})',
        re.IGNORECASE
    )
    # Mẫu 2: "Nghị định 15 năm 2020"
    pattern2 = re.compile(
        r'(nghị định|thông tư|quyết định|nghị quyết|pháp lệnh)\s+(?:số\s+)?(\d+)\s+năm\s+(\d{4})',
        re.IGNORECASE
    )
    # Mẫu 3: "Nghị định 15" (không có năm, lấy cái mới nhất có số hiệu khớp)
    pattern3 = re.compile(
        r'\b(nghị định|thông tư)\s+(?:số\s+)?(\d+)\b',
        re.IGNORECASE
    )
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check pattern 1 & 2
        for match in pattern1.finditer(q_expanded) or []:
            doc_type = normalize_document_type(match.group(1))
            num = match.group(2)
            year = match.group(3)
            search_pattern = f"{num}/{year}/%"
            
            cursor.execute(
                "SELECT id FROM documents WHERE loai_van_ban = ? AND so_ky_hieu LIKE ? LIMIT 5",
                (doc_type, search_pattern)
            )
            for row in cursor.fetchall():
                doc_ids.add(row[0])
                
        for match in pattern2.finditer(q_expanded) or []:
            doc_type = normalize_document_type(match.group(1))
            num = match.group(2)
            year = match.group(3)
            search_pattern = f"{num}/{year}/%"
            
            cursor.execute(
                "SELECT id FROM documents WHERE loai_van_ban = ? AND so_ky_hieu LIKE ? LIMIT 5",
                (doc_type, search_pattern)
            )
            for row in cursor.fetchall():
                doc_ids.add(row[0])
                
        # Check pattern 3 if no doc_id found yet
        if not doc_ids:
            for match in pattern3.finditer(q_expanded) or []:
                doc_type = normalize_document_type(match.group(1))
                num = match.group(2)
                search_pattern = f"{num}/%"
                
                cursor.execute("""
                    SELECT id FROM documents 
                    WHERE loai_van_ban = ? AND so_ky_hieu LIKE ? 
                    ORDER BY ngay_ban_hanh DESC LIMIT 3
                """, (doc_type, search_pattern))
                for row in cursor.fetchall():
                    doc_ids.add(row[0])
                    
        conn.close()
    except Exception as e:
        print(f"⚠️ Error extracting num/year entities: {e}")
        
    return doc_ids

def normalize_document_type(text: str) -> str:
    """Chuẩn hóa tên loại văn bản tương ứng với DB."""
    text = text.lower().strip()
    if "nghị định" in text:
        return "Nghị định"
    elif "thông tư" in text:
        return "Thông tư"
    elif "quyết định" in text:
        return "Quyết định"
    elif "nghị quyết" in text:
        return "Nghị quyết"
    elif "pháp lệnh" in text:
        return "Pháp lệnh"
    return text.capitalize()
