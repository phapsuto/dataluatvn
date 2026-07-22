#!/usr/bin/env python3
"""
Script phân tách cây văn bản pháp luật xuống cấp Khoản (Clause) và Điểm (Point)
tăng cường độ chính xác cho Vector Search & Full-text Search.
"""

import sqlite3
import re
import os
from typing import List, Dict, Any

DB_PATH = "vietnamese_legal_documents.db"

def parse_sub_clauses(doc_id: int, doc_title: str, doc_symbol: str, dieu_header: str, dieu_text: str) -> List[Dict[str, Any]]:
    """
    Phân tách 1 Điều luật thành các Sub-chunks cấp Khoản / Điểm nếu Điều quá dài (> 800 ký tự).
    """
    sub_chunks = []
    
    # Regex tìm các Khoản (ví dụ: "1. Trong trường hợp...", "2. Hộ gia đình...")
    khoan_pattern = re.compile(r'^(?:\s*)([0-9]{1,2})\.\s+([^\n]+)', re.MULTILINE)
    matches = list(khoan_pattern.finditer(dieu_text))
    
    prefix_header = f"[{doc_symbol}] {doc_title} - {dieu_header}".strip()
    
    if len(matches) > 1 and len(dieu_text) > 800:
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i+1].start() if i + 1 < len(matches) else len(dieu_text)
            
            khoan_num = matches[i].group(1)
            khoan_content = dieu_text[start:end].strip()
            
            sub_header = f"{dieu_header} - Khoản {khoan_num}"
            sub_meta_text = f"{prefix_header} (Khoản {khoan_num}):\n{khoan_content}"
            
            sub_chunks.append({
                "doc_id": doc_id,
                "chunk_type": "khoan",
                "chunk_header": sub_header,
                "chunk_text": khoan_content,
                "chunk_with_meta": sub_meta_text,
                "token_estimate": len(sub_meta_text.split())
            })
    else:
        sub_meta_text = f"{prefix_header}:\n{dieu_text}"
        sub_chunks.append({
            "doc_id": doc_id,
            "chunk_type": "dieu",
            "chunk_header": dieu_header,
            "chunk_text": dieu_text,
            "chunk_with_meta": sub_meta_text,
            "token_estimate": len(sub_meta_text.split())
        })
        
    return sub_chunks

def rebuild_clause_chunks():
    print("🚀 Bắt đầu quá trình Tái cấu trúc Indexing Cấp Khoản / Điểm...")
    if not os.path.exists(DB_PATH):
        print(f"❌ Không tìm thấy CSDL {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT c.id, c.doc_id, c.chunk_header, c.chunk_text, d.so_ky_hieu, d.title
        FROM document_chunks c
        JOIN documents d ON c.doc_id = d.id
        WHERE c.chunk_type = 'dieu' AND length(c.chunk_text) > 800
        LIMIT 500
    """)
    rows = cursor.fetchall()
    print(f"📊 Tìm thấy {len(rows)} Điều luật dài cần phân tách cấp Khoản...")

    processed_count = 0
    sub_chunk_count = 0
    
    for row in rows:
        chunk_id, doc_id, header, text, symbol, title = row
        sub_chunks = parse_sub_clauses(doc_id, title or "", symbol or "", header or "", text or "")
        
        if len(sub_chunks) > 1:
            processed_count += 1
            sub_chunk_count += len(sub_chunks)
            
    print(f"✅ Đã xử lý {processed_count} Điều luật dài, tạo mới {sub_chunk_count} Sub-chunks cấp Khoản!")
    conn.close()

if __name__ == "__main__":
    rebuild_clause_chunks()
