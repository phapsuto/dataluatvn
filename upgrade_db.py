import sqlite3
import os

DB_NAME = "vietnamese_legal_documents.db"

def main():
    if not os.path.exists(DB_NAME):
        print(f"File {DB_NAME} không tồn tại!")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(documents)")
    columns = [row[1] for row in cursor.fetchall()]

    if "has_content" not in columns:
        print("Đang thêm cột 'has_content' vào bảng 'documents'...")
        cursor.execute("ALTER TABLE documents ADD COLUMN has_content INTEGER DEFAULT 0")
        
    print("Đang đánh dấu các văn bản có nội dung HTML...")
    # Nếu content chưa bị tách (nằm trong DB chính)
    cursor.execute("""
        UPDATE documents 
        SET has_content = 1 
        WHERE content_html IS NOT NULL AND content_html != ''
    """)
    
    # Nếu content đã bị tách (nằm trong content_store.db)
    if os.path.exists("content_store.db"):
        print("Phát hiện content_store.db, đang đồng bộ cờ has_content...")
        abs_path = os.path.abspath("content_store.db")
        cursor.execute(f"ATTACH DATABASE '{abs_path}' AS content_db")
        cursor.execute("""
            UPDATE documents
            SET has_content = 1
            WHERE id IN (
                SELECT doc_id FROM content_db.document_content 
                WHERE content_html IS NOT NULL AND content_html != ''
            )
        """)
        cursor.execute("DETACH DATABASE content_db")
        
    conn.commit()

    cursor.execute("SELECT count(*) FROM documents WHERE has_content = 1")
    count = cursor.fetchone()[0]
    print(f"Thành công! Đã đánh dấu {count} văn bản có chứa nội dung (has_content = 1).")

    conn.close()

if __name__ == "__main__":
    main()
