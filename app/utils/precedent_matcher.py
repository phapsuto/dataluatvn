#!/usr/bin/env python3
"""
app/utils/precedent_matcher.py
================================
Module Áp dụng Án lệ Thông minh — Matching án lệ theo tình tiết tương tự.

Sử dụng kết hợp:
1. FTS5 full-text search trong bảng `real_precedents` (1,963 án lệ/bản án)
2. Keyword-based matching theo loại vụ án (case_type)
3. Truy xuất nguyên tắc pháp lý (principle_text) và điều luật áp dụng (applied_article_code)

Kết quả trả về cho LLM dưới dạng structured context để AI phân tích:
- So sánh tình tiết tương tự (similar facts)
- Phân biệt tình tiết khác biệt (distinguishing)
- Áp dụng nguyên tắc stare decisis
"""

import os
import re
import sqlite3
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("PrecedentMatcher")

THEORY_DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

# Mapping từ khóa câu hỏi → case_type trong DB
CASE_TYPE_MAPPING = {
    "hình sự": ["Hình sự"],
    "dân sự": ["Dân sự"],
    "lao động": ["Lao động"],
    "kinh doanh": ["Kinh doanh thương mại", "Kinh doanh"],
    "thương mại": ["Kinh doanh thương mại", "Thương mại"],
    "hành chính": ["Hành chính"],
    "hôn nhân": ["Hôn nhân và gia đình", "Hôn nhân gia đình"],
    "ly hôn": ["Hôn nhân và gia đình"],
    "đất đai": ["Dân sự"],  # Tranh chấp đất đai thường xử dân sự
    "thừa kế": ["Dân sự"],
}


def search_precedents(
    query: str,
    case_type: Optional[str] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Tìm kiếm Án lệ/Bản án liên quan đến câu hỏi pháp lý.
    
    Args:
        query: Câu hỏi hoặc mô tả tình huống pháp lý
        case_type: Loại vụ án (nếu đã biết, ví dụ: "Hình sự", "Dân sự")
        top_k: Số lượng kết quả tối đa
    
    Returns:
        Danh sách Dict chứa thông tin Án lệ liên quan
    """
    if not os.path.exists(THEORY_DB_PATH):
        logger.warning(f"DB không tồn tại: {THEORY_DB_PATH}")
        return []
    
    results = []
    conn = sqlite3.connect(THEORY_DB_PATH)
    c = conn.cursor()
    
    try:
        # 1. Detect case_type từ query nếu chưa có
        if not case_type:
            q_lower = query.lower()
            for keyword, types in CASE_TYPE_MAPPING.items():
                if keyword in q_lower:
                    case_type = types[0]
                    break
        
        # 2. FTS5 search in fts_theory for precedent entries
        clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
        words = [w for w in clean_query.split() if len(w) > 1]
        
        if not words:
            conn.close()
            return []
        
        # Build FTS query with most relevant keywords
        fts_words = words[:8]
        fts_query = " OR ".join(fts_words)
        
        c.execute("""
        SELECT source_id, title, content, rank
        FROM fts_theory
        WHERE source_table = 'real_precedents'
          AND fts_theory MATCH ?
        ORDER BY rank
        LIMIT ?
        """, (fts_query, top_k * 2))
        
        fts_ids = []
        for row in c.fetchall():
            fts_ids.append(row[0])
        
        # 3. Also do direct search in real_precedents by case_type
        if case_type:
            c.execute("""
            SELECT id FROM real_precedents
            WHERE case_type LIKE ?
            LIMIT ?
            """, (f"%{case_type}%", top_k))
            for row in c.fetchall():
                if row[0] not in fts_ids:
                    fts_ids.append(row[0])
        
        # 4. Fetch full details for matched IDs
        unique_ids = list(set(fts_ids))[:top_k]
        
        for pid in unique_ids:
            c.execute("""
            SELECT id, doc_name, precedent_number, case_type, court_level,
                   issuing_authority, year, principle_text, full_text,
                   applied_article_code, source_url
            FROM real_precedents WHERE id = ?
            """, (pid,))
            
            row = c.fetchone()
            if row:
                results.append({
                    "id": row[0],
                    "doc_name": row[1],
                    "precedent_number": row[2],
                    "case_type": row[3],
                    "court_level": row[4],
                    "issuing_authority": row[5],
                    "year": row[6],
                    "principle_text": row[7],
                    "full_text": row[8],
                    "applied_articles": row[9],
                    "source_url": row[10],
                })
        
    except Exception as e:
        logger.error(f"Precedent search error: {e}")
    finally:
        conn.close()
    
    return results


def format_precedent_context(precedents: List[Dict[str, Any]], max_chars_per_precedent: int = 2000) -> str:
    """
    Định dạng danh sách Án lệ thành context block cho LLM.
    """
    if not precedents:
        return ""
    
    parts = ["\n---\n## 📜 ÁN LỆ / BẢN ÁN LIÊN QUAN\n"]
    
    for i, p in enumerate(precedents, 1):
        block = f"\n### Án lệ #{i}: {p.get('doc_name', 'N/A')}\n"
        
        if p.get('precedent_number'):
            block += f"- **Số hiệu**: {p['precedent_number']}\n"
        if p.get('case_type'):
            block += f"- **Loại vụ án**: {p['case_type']}\n"
        if p.get('court_level'):
            block += f"- **Cấp Tòa**: {p['court_level']}\n"
        if p.get('issuing_authority'):
            block += f"- **Cơ quan ban hành**: {p['issuing_authority']}\n"
        if p.get('year'):
            block += f"- **Năm**: {p['year']}\n"
        if p.get('applied_articles'):
            block += f"- **Điều luật áp dụng**: {p['applied_articles']}\n"
        
        if p.get('principle_text'):
            block += f"\n**Nguyên tắc pháp lý**:\n{p['principle_text'][:1000]}\n"
        
        if p.get('full_text'):
            full_text = p['full_text']
            if len(full_text) > max_chars_per_precedent:
                full_text = full_text[:max_chars_per_precedent] + "...(trích lược)"
            block += f"\n**Nội dung bản án**:\n{full_text}\n"
        
        if p.get('source_url'):
            block += f"\n🔗 [Nguồn]({p['source_url']})\n"
        
        parts.append(block)
    
    parts.append("\n---\n")
    parts.append("**Hướng dẫn sử dụng Án lệ**: So sánh tình tiết vụ việc hiện tại với tình tiết trong Án lệ trên.")
    parts.append("Nếu tình tiết TƯƠNG TỰ → áp dụng nguyên tắc pháp lý đã xác lập.")
    parts.append("Nếu tình tiết KHÁC BIỆT → nêu rõ điểm khác biệt (distinguishing).\n")
    
    return "\n".join(parts)


def get_precedent_stats() -> Dict[str, int]:
    """Trả về thống kê Án lệ trong DB."""
    if not os.path.exists(THEORY_DB_PATH):
        return {}
    
    conn = sqlite3.connect(THEORY_DB_PATH)
    c = conn.cursor()
    
    stats = {}
    c.execute("SELECT COUNT(*) FROM real_precedents")
    stats["total"] = c.fetchone()[0]
    
    c.execute("SELECT case_type, COUNT(*) FROM real_precedents GROUP BY case_type ORDER BY COUNT(*) DESC")
    stats["by_case_type"] = {row[0]: row[1] for row in c.fetchall()}
    
    conn.close()
    return stats


if __name__ == "__main__":
    # Test
    print("📊 Thống kê Án lệ:")
    stats = get_precedent_stats()
    print(f"  Tổng: {stats.get('total', 0)} án lệ/bản án")
    for ct, cnt in stats.get("by_case_type", {}).items():
        print(f"  - {ct}: {cnt}")
    
    print("\n🔍 Test tìm kiếm:")
    results = search_precedents("tranh chấp hợp đồng mua bán nhà đất")
    print(f"  Tìm thấy: {len(results)} án lệ liên quan")
    for r in results:
        print(f"  - {r.get('doc_name', 'N/A')} | {r.get('case_type', 'N/A')} | {r.get('year', 'N/A')}")
    
    if results:
        ctx = format_precedent_context(results)
        print(f"\n📝 Context length: {len(ctx)} chars")
