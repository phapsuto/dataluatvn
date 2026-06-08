import sqlite3

def main():
    conn = sqlite3.connect("vietnamese_legal_documents.db")
    cursor = conn.cursor()

    print("Creating document_chunks table...")
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

    print("Creating index on doc_id...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_id);")

    print("Creating chunks_fts virtual table...")
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
      chunk_with_meta,
      content=document_chunks,
      content_rowid=id,
      tokenize='unicode61 remove_diacritics 0'
    );
    """)

    print("Creating triggers for FTS5 synchronization...")
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

    conn.commit()
    conn.close()
    print("Database schema upgrade for chunks completed successfully.")

if __name__ == "__main__":
    main()
