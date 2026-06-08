import pyarrow.parquet as pq
import sqlite3
import random
import sys
import os
import re

# Add project root to PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routers.laws import parse_fts_query

MAIN_DB = "vietnamese_legal_documents.db"

def extract_fts_snippet(context_text):
    clean = re.sub(r'[^\w\s]', ' ', context_text)
    words = [w for w in clean.split() if len(w) >= 3]
    top = sorted(set(words), key=len, reverse=True)[:5]
    return " AND ".join(top)

def normalize_spelling(text: str) -> str:
    if not text:
        return ""
    text = text.replace('òa', 'o\u00e0').replace('óa', 'o\u00e1').replace('ỏa', 'o\u1ea3').replace('õa', 'o\u00e3').replace('ọa', 'o\u1ea1')
    text = text.replace('òe', 'o\u00e8').replace('óe', 'o\u00e9').replace('ỏe', 'o\u1ebd').replace('õe', 'o\u1ebd').replace('ọe', 'o\u1eb9')
    text = text.replace('ủy', 'u\u1ef7').replace('úy', 'u\u00fd').replace('ùy', 'u\u1ef3').replace('ũy', 'u\u1ef5').replace('ụy', 'u\u1ef9')
    text = text.replace('Òa', 'O\u00e0').replace('Óa', 'O\u00e1').replace('Ỏa', 'O\u1ea3').replace('Õa', 'O\u00e3').replace('Ọa', 'O\u1ea1')
    text = text.replace('Òe', 'O\u00e8').replace('Óe', 'O\u00e9').replace('Ỏe', 'O\u1ebd').replace('Õe', 'O\u1ebd').replace('Ọe', 'O\u1eb9')
    text = text.replace('Ủy', 'U\u1ef7').replace('Úy', 'U\u00fd').replace('Ùy', 'U\u1ef3').replace('Ũy', 'U\u1ef5').replace('Ụy', 'U\u1ef9')
    return text

VIETNAMESE_STOPWORDS = {
    "tôi", "tui", "mình", "ta", "chúng", "các", "những", "một", "này", "đó", "kia",
    "nào", "gì", "nào", "ai", "đâu", "sao", "bao", "mấy",
    "của", "và", "với", "trong", "trên", "dưới", "ngoài", "giữa", "bên", "về",
    "cho", "đến", "từ", "tại", "theo", "bằng", "qua", "vào", "hay", "hoặc",
    "nhưng", "mà", "rằng", "nếu", "khi", "vì", "do", "bởi", "để",
    "đã", "đang", "sẽ", "sắp", "vẫn", "còn", "rất", "lắm", "quá", "hơn",
    "nhất", "không", "chưa", "chẳng", "nên", "cần", "phải", "được", "bị",
    "có", "là", "thì", "cũng", "lại", "rồi", "mới", "cứ", "đều",
    "thế", "như", "thế nào", "như thế nào", "bao nhiêu", "vậy",
    "việc", "cái", "con", "người", "điều", "khoản",
}

def parse_fts_query_chunk(q: str) -> str:
    q_clean = re.sub(r'[^\w\s]', ' ', q).strip()
    all_words = [w for w in q_clean.split() if w]
    if not all_words:
        return ""
    all_words = [normalize_spelling(w) for w in all_words]
    keywords = [w for w in all_words if w.lower() not in VIETNAMESE_STOPWORDS and len(w) > 1]
    if not keywords:
        keywords = [w for w in all_words if len(w) > 1]
    if not keywords:
        keywords = all_words
        
    if len(keywords) == 1:
        return f"{keywords[0]}*"
        
    phrase = " ".join(keywords)
    and_q = " AND ".join(keywords)
    or_q = " OR ".join(keywords)
    return f'"{phrase}" OR ({and_q}) OR ({or_q})'

def main():
    test_df = pq.read_table("data/yuITC/test.parquet").to_pandas()
    db_conn = sqlite3.connect(MAIN_DB)
    cursor = db_conn.cursor()
    
    random.seed(42)
    sample_indices = random.sample(range(len(test_df)), 5)
    
    for idx in sample_indices:
        row = test_df.iloc[idx]
        question = row["question"]
        contexts = list(row["context_list"])
        
        # Ground truth mapping
        gt_ids = set()
        for ctx in contexts:
            snippet = extract_fts_snippet(str(ctx))
            if snippet:
                # normalize snippet spelling
                snippet_norm = normalize_spelling(snippet)
                cursor.execute(
                    "SELECT rowid FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT 3",
                    (snippet_norm,)
                )
                for r in cursor.fetchall():
                    gt_ids.add(r[0])
        
        # Search FTS5 Document-level
        fts_query = parse_fts_query(question)
        doc_results = []
        if fts_query:
            try:
                cursor.execute(
                    "SELECT rowid FROM content_fts WHERE content_fts MATCH ? ORDER BY rank LIMIT 10",
                    (fts_query,)
                )
                doc_results = [r[0] for r in cursor.fetchall()]
            except Exception as e:
                pass
                
        # Search FTS5 Chunk-level
        chunk_query = parse_fts_query_chunk(question)
        chunk_results = []
        if chunk_query:
            try:
                # Note: chunks in database were NOT normalized yet, but let's see if query normalization helps
                cursor.execute("""
                    SELECT doc_id FROM chunks_fts
                    JOIN document_chunks ON chunks_fts.rowid = document_chunks.id
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT 30
                """, (chunk_query,))
                seen = set()
                for (doc_id,) in cursor.fetchall():
                    if doc_id not in seen:
                        seen.add(doc_id)
                        chunk_results.append(doc_id)
            except Exception as e:
                print(f"Chunk search error: {e}")
                
        print(f"\nQuestion: {question}")
        print(f"FTS Query Chunk: {chunk_query}")
        print(f"GT Document IDs: {gt_ids}")
        print(f"Document-level results: {doc_results}")
        print(f"Chunk-level results: {chunk_results[:10]}")
        print(f"Doc hit: {any(d in gt_ids for d in doc_results)}")
        print(f"Chunk hit: {any(d in gt_ids for d in chunk_results[:10])}")
        
    db_conn.close()

if __name__ == "__main__":
    main()
