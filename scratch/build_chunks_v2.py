#!/usr/bin/env python3
"""
GĐ1-HĐ1: Parse HTML and build document_chunks using optimized Multiprocessing.
"""

import sqlite3
import re
import os
import sys
import argparse
import time
import multiprocessing
from bs4 import BeautifulSoup

# Global database connection variables for workers
_conn = None
_cursor = None

def clean_text(text):
    if not text:
        return ""
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

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

def split_large_chunk(text, max_words=400, overlap=100):
    words = text.split()
    if len(words) <= max_words:
        return [text]
    
    sub_chunks = []
    start = 0
    while start < len(words):
        end = start + max_words
        sub_chunk = " ".join(words[start:end])
        sub_chunks.append(sub_chunk)
        start += (max_words - overlap)
        if start >= len(words) - overlap:
            if len(words) - start > 50:
                sub_chunks.append(" ".join(words[start:]))
            break
    return sub_chunks

def parse_html_to_chunks(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    content_container = soup.find(id="content") or soup.find(class_="noi-dung") or soup
    
    # Remove script and style elements
    for script in content_container(["script", "style"]):
        script.extract()
        
    # Inject newlines after block elements
    block_tags = ['p', 'br', 'div', 'tr', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'td']
    for tag in content_container.find_all(block_tags):
        tag.insert_after('\n')
        
    text = content_container.get_text()
    lines = [clean_text(line) for line in text.split('\n')]
    paragraphs = [line for line in lines if line]
    
    raw_chunks = []
    current_chunk = []
    current_header = "Phần mở đầu"
    current_type = "preamble"
    
    article_pattern = re.compile(r'^Điều\s+(\d+[a-zA-Z]*)\s*[\.\-:]?\s*(.*)', re.IGNORECASE)
    chapter_pattern = re.compile(r'^(Chương|Phần|Mục)\s+([IVXLCDM\d]+)\s*[\.\-:]?\s*(.*)', re.IGNORECASE)
    
    for para in paragraphs:
        match_art = article_pattern.match(para)
        match_chap = chapter_pattern.match(para)
        
        if match_chap:
            current_header = para
            current_chunk.append(para)
        elif match_art:
            if current_chunk:
                raw_chunks.append({
                    "chunk_type": current_type,
                    "chunk_header": current_header,
                    "chunk_text": "\n".join(current_chunk)
                })
                current_chunk = []
            
            art_num = match_art.group(1)
            art_title = match_art.group(2)
            current_header = f"Điều {art_num}"
            if art_title:
                current_header += f": {art_title[:100]}"
            current_type = "dieu"
            current_chunk.append(para)
        else:
            current_chunk.append(para)
            
    if current_chunk:
        raw_chunks.append({
            "chunk_type": current_type,
            "chunk_header": current_header,
            "chunk_text": "\n".join(current_chunk)
        })
        
    final_chunks = []
    chunk_index = 0
    for rc in raw_chunks:
        text = rc["chunk_text"]
        words_count = len(text.split())
        
        if words_count <= 400:
            final_chunks.append({
                "chunk_index": chunk_index,
                "chunk_type": rc["chunk_type"],
                "chunk_header": rc["chunk_header"],
                "chunk_text": text,
                "token_estimate": words_count
            })
            chunk_index += 1
        else:
            sub_texts = split_large_chunk(text, max_words=400, overlap=100)
            for sub_idx, sub_text in enumerate(sub_texts):
                sub_header = f"{rc['chunk_header']} (Phần {sub_idx + 1})"
                final_chunks.append({
                    "chunk_index": chunk_index,
                    "chunk_type": rc["chunk_type"],
                    "chunk_header": sub_header,
                    "chunk_text": sub_text,
                    "token_estimate": len(sub_text.split())
                })
                chunk_index += 1
                
    return final_chunks

def init_worker(main_db, content_db):
    global _conn, _cursor
    _conn = sqlite3.connect(main_db)
    _conn.execute(f"ATTACH DATABASE '{content_db}' AS content_db")
    _cursor = _conn.cursor()

def worker_process_batch(doc_ids):
    global _cursor
    chunks_data = []
    if not doc_ids:
        return chunks_data
        
    placeholders = ",".join(["?"] * len(doc_ids))
    query = f"""
    SELECT d.id, d.title, d.so_ky_hieu, d.loai_van_ban, c.content_html
    FROM documents d
    JOIN content_db.document_content c ON d.id = c.doc_id
    WHERE d.id IN ({placeholders})
    """
    try:
        _cursor.execute(query, doc_ids)
        rows = _cursor.fetchall()
        for row in rows:
            doc_id, title, so_ky_hieu, loai_van_ban, content_html = row
            title = normalize_spelling(title or "")
            so_ky_hieu = normalize_spelling(so_ky_hieu or "")
            loai_van_ban = normalize_spelling(loai_van_ban or "")
            
            chunks = parse_html_to_chunks(content_html)
            for c in chunks:
                chunk_header = normalize_spelling(c["chunk_header"] or "")
                chunk_text = normalize_spelling(c["chunk_text"] or "")
                chunk_with_meta = f"[{so_ky_hieu}] [{loai_van_ban}] [{title}] [{chunk_header}]\n{chunk_text}"
                
                chunks_data.append((
                    doc_id,
                    c["chunk_index"],
                    c["chunk_type"],
                    chunk_header,
                    chunk_text,
                    chunk_with_meta,
                    c["token_estimate"]
                ))
    except Exception as e:
        # Soft failure to prevent child process from dying completely
        pass
    return chunks_data

def main():
    parser = argparse.ArgumentParser(description="Build document chunks database table.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents processed.")
    parser.add_argument("--reset", action="store_true", help="Reset document_chunks table and rebuild FTS.")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes.")
    args = parser.parse_args()

    main_db = "vietnamese_legal_documents.db"
    content_db = "content_store.db"

    if not os.path.exists(main_db) or not os.path.exists(content_db):
        print(f"Error: Databases do not exist.")
        sys.exit(1)

    conn = sqlite3.connect(main_db)
    conn.execute(f"ATTACH DATABASE '{content_db}' AS content_db")
    cursor = conn.cursor()

    if args.reset:
        print("🗑️ Resetting document_chunks and chunks_fts tables...")
        cursor.execute("DROP TRIGGER IF EXISTS tbl_chunks_ai")
        cursor.execute("DROP TRIGGER IF EXISTS tbl_chunks_ad")
        cursor.execute("DROP TRIGGER IF EXISTS tbl_chunks_au")
        cursor.execute("DROP TABLE IF EXISTS chunks_fts")
        cursor.execute("DROP TABLE IF EXISTS document_chunks")
        
        # Recreate tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          doc_id INTEGER NOT NULL,
          chunk_index INTEGER NOT NULL,
          chunk_type TEXT DEFAULT 'dieu',
          chunk_header TEXT,
          chunk_text TEXT NOT NULL,
          chunk_with_meta TEXT,
          token_estimate INTEGER,
          FOREIGN KEY (doc_id) REFERENCES documents(id)
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_id);")
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
          chunk_with_meta,
          content=document_chunks,
          content_rowid=id,
          tokenize='unicode61 remove_diacritics 0'
        );
        """)
        conn.commit()

    # Get processed documents
    processed_doc_ids = set()
    if not args.reset:
        cursor.execute("SELECT DISTINCT doc_id FROM document_chunks")
        processed_doc_ids = {row[0] for row in cursor.fetchall()}
        print(f"Already processed: {len(processed_doc_ids)} documents.")

    # Only select doc_id from content_store to minimize memory overhead
    select_sql = "SELECT doc_id FROM content_db.document_content"
    cursor.execute(select_sql)
    all_doc_ids = [row[0] for row in cursor.fetchall()]
    
    to_process = [d for d in all_doc_ids if d not in processed_doc_ids]
            
    if args.limit:
        to_process = to_process[:args.limit]

    total = len(to_process)
    print(f"Found {total} documents to process.")

    if total == 0:
        print("No documents to process. Done!")
        conn.close()
        return

    start_time = time.time()
    processed_count = 0
    total_chunks = 0
    
    pool_size = args.workers or min(8, multiprocessing.cpu_count() or 4)
    print(f"🚀 Using multiprocessing Pool with {pool_size} workers...")
    
    # We partition into batches of 200 documents per task
    batch_size = 200
    batches = [to_process[i:i + batch_size] for i in range(0, total, batch_size)]
    
    # Initialize the worker processes with the DB paths so they connect once
    init_args = (os.path.abspath(main_db), os.path.abspath(content_db))
    
    with multiprocessing.Pool(processes=pool_size, initializer=init_worker, initargs=init_args) as pool:
        # Using imap_unordered for better streaming and memory efficiency
        for batch_chunks in pool.imap_unordered(worker_process_batch, batches):
            if batch_chunks:
                # Insert chunks
                cursor.executemany("""
                INSERT INTO document_chunks 
                (doc_id, chunk_index, chunk_type, chunk_header, chunk_text, chunk_with_meta, token_estimate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, batch_chunks)
                conn.commit()
                total_chunks += len(batch_chunks)
                
            processed_count += batch_size
            if processed_count > total:
                processed_count = total
                
            if processed_count % 1000 == 0 or processed_count == total:
                elapsed = time.time() - start_time
                speed = processed_count / elapsed if elapsed > 0 else 0
                sys.stdout.write(
                    f"\rProcessed: {processed_count}/{total} docs | "
                    f"Total Chunks: {total_chunks} | "
                    f"Speed: {speed:.1f} docs/sec | "
                    f"Elapsed: {elapsed:.1f}s"
                )
                sys.stdout.flush()
                
    print("\n✍️ Re-creating triggers and rebuilding FTS5 index...")
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS tbl_chunks_ai AFTER INSERT ON document_chunks BEGIN
      INSERT INTO chunks_fts(rowid, chunk_with_meta) VALUES (new.id, new.chunk_with_meta);
    END;
    """)
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS tbl_chunks_ad AFTER DELETE ON document_chunks BEGIN
      INSERT INTO chunks_fts(chunks_fts, rowid, chunk_with_meta) VALUES('delete', old.id, old.chunk_with_meta);
    END;
    """)
    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS tbl_chunks_au AFTER UPDATE ON document_chunks BEGIN
      INSERT INTO chunks_fts(chunks_fts, rowid, chunk_with_meta) VALUES('delete', old.id, old.chunk_with_meta);
      INSERT INTO chunks_fts(rowid, chunk_with_meta) VALUES (new.id, new.chunk_with_meta);
    END;
    """)
    
    print("🔄 Rebuilding FTS index from document_chunks (this may take a moment)...")
    rebuild_start = time.time()
    cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');")
    conn.commit()
    print(f"✅ FTS rebuild finished in {time.time() - rebuild_start:.1f}s")
    
    print("\n✅ Done!")
    print(f"Processed: {processed_count} documents.")
    print(f"Created: {total_chunks} chunks.")
    
    conn.close()

if __name__ == "__main__":
    # Ensure correct start method on macOS
    multiprocessing.freeze_support()
    main()
