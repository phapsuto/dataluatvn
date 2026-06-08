import sqlite3
import os

db1 = "vietnamese_legal_documents.db"
db2 = "content_store.db"

if os.path.exists(db1):
    conn = sqlite3.connect(db1)
    c = conn.cursor()
    c.execute("PRAGMA table_info(documents)")
    cols = [col[1] for col in c.fetchall()]
    if "content_html" in cols:
        c.execute("SELECT COUNT(*) FROM documents")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM documents WHERE content_html IS NULL OR content_html = ''")
        empty = c.fetchone()[0]
        print(f"Trong DB chính (documents): Tổng {total} văn bản. Có {empty} văn bản trống nội dung ({(empty/total)*100:.2f}%).")
    else:
        print("Cột content_html không còn nằm trong DB chính (đã bị tách).")
    conn.close()

if os.path.exists(db2):
    conn = sqlite3.connect(db2)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM document_content")
    total2 = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM document_content WHERE content_html IS NULL OR content_html = ''")
    empty2 = c.fetchone()[0]
    print(f"Trong DB tách (content_store.db): Tổng {total2} văn bản. Có {empty2} văn bản trống nội dung ({(empty2/total2)*100:.2f}%).")
else:
    print("Chưa có file content_store.db (chưa chạy split_content_db.py).")
