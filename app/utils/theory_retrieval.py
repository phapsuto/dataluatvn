#!/usr/bin/env python3
"""
app/utils/theory_retrieval.py
==============================
Module truy xuất Tri thức Lý luận & Giáo trình Pháp luật từ Sub-Dataset legal_theory_mind.db.
Cung cấp các hàm:
- search_legal_theory(query, top_k=3): Tìm kiếm toàn văn FTS5 trong khối tri thức lý luận.
- format_theory_context(results): Định dạng tri thức lý thuyết hỗ trợ RAG LLM.
"""

import os
import sqlite3
import logging
from typing import List, Dict, Any

logger = logging.getLogger("TheoryRetrieval")

THEORY_DB_PATH = "/Users/tonguyen/Library/CloudStorage/OneDrive-Personal/DrTo/luatvietnam/data/legal_theory_mind.db"

def search_legal_theory(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Tìm kiếm FTS5 trong cơ sở dữ liệu con legal_theory_mind.db.
    """
    if not os.path.exists(THEORY_DB_PATH):
        logger.warning(f"Chưa tìm thấy DB lý luận tại {THEORY_DB_PATH}")
        return []

    results = []
    try:
        conn = sqlite3.connect(THEORY_DB_PATH)
        cursor = conn.cursor()

        # Làm sạch query cho FTS5
        clean_query = query.replace('"', '').replace("'", '').strip()
        words = [w for w in clean_query.split() if len(w) > 1]
        if not words:
            conn.close()
            return []

        fts_query = " OR ".join(words)

        cursor.execute("""
        SELECT source_table, source_id, title, content, category
        FROM fts_theory
        WHERE fts_theory MATCH ?
        LIMIT ?
        """, (fts_query, top_k))

        rows = cursor.fetchall()
        for row in rows:
            source_table, source_id, title, content, category = row
            
            # Lấy thông tin chi tiết từ bảng nguồn
            if source_table == "curriculum_topics":
                cursor.execute("""
                SELECT degree_level, subject, topic_title, core_concept, theoretical_framework, source_university
                FROM curriculum_topics WHERE id = ?
                """, (source_id,))
                topic_row = cursor.fetchone()
                if topic_row:
                    degree, subj, t_title, concept, framework, univ = topic_row
                    results.append({
                        "type": "curriculum_topic",
                        "degree_level": degree,
                        "subject": subj,
                        "title": t_title,
                        "concept": concept,
                        "content": framework,
                        "university": univ
                    })
            elif source_table == "legal_doctrines":
                cursor.execute("""
                SELECT doctrine_name, category, definition, jurisprudence_stance, related_articles
                FROM legal_doctrines WHERE id = ?
                """, (source_id,))
                doc_row = cursor.fetchone()
                if doc_row:
                    d_name, cat, dfn, stance, articles = doc_row
                    results.append({
                        "type": "legal_doctrine",
                        "category": cat,
                        "title": d_name,
                        "definition": dfn,
                        "content": stance,
                        "related_articles": articles
                    })

        conn.close()
    except Exception as e:
        logger.error(f"Lỗi khi tìm kiếm DB lý luận: {e}")

    return results

def format_theory_context(theory_results: List[Dict[str, Any]]) -> str:
    """
    Chuyển đổi kết quả tìm kiếm lý luận thành chuỗi Context đẹp cho LLM RAG.
    """
    if not theory_results:
        return ""

    lines = ["🎓 **KHUNG LÝ LUẬN & TRIẾT HỌC PHÁP LÝ BỔ TRỢ (LEGAL MIND CONTEXT):**"]
    for idx, item in enumerate(theory_results, 1):
        if item["type"] == "curriculum_topic":
            lines.append(
                f"\n--- [Lý luận {idx} - Trình độ: {item['degree_level']} ({item['university']})] ---"
                f"\n📌 **Môn học/Bài giảng**: {item['subject']} - {item['title']}"
                f"\n💡 **Khái niệm cốt lõi**: {item['concept']}"
                f"\n🧠 **Khung lý luận chuyên sâu**: {item['content']}"
            )
        elif item["type"] == "legal_doctrine":
            lines.append(
                f"\n--- [Học thuyết Pháp lý {idx} - Chuyên ngành: {item['category']}] ---"
                f"\n⚖️ **Học thuyết/Nguyên lý**: {item['title']}"
                f"\n📖 **Định nghĩa**: {item['definition']}"
                f"\n🔍 **Quan điểm Pháp lý học**: {item['content']}"
                f"\n📜 **Căn cứ liên quan**: {item.get('related_articles', 'N/A')}"
            )

    return "\n".join(lines)

if __name__ == "__main__":
    test_res = search_legal_theory("Cấu trúc quy phạm pháp luật và suy đoán vô tội")
    print(format_theory_context(test_res))
