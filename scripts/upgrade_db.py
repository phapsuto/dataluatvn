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
    if os.path.isfile("content_store.db"):
        print("Phát hiện file content_store.db, đang đồng bộ cờ has_content (không dùng ATTACH để tránh lỗi lock)...")
        
        # Kết nối độc lập tới content_store.db
        db_path = os.path.abspath("content_store.db")
        conn2 = sqlite3.connect(db_path)
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT doc_id FROM document_content WHERE content_html IS NOT NULL AND content_html != ''")
        doc_ids = [row[0] for row in cursor2.fetchall()]
        conn2.close()
        
        if doc_ids:
            print(f"Tìm thấy {len(doc_ids)} văn bản có HTML trong content_store.db. Đang cập nhật...")
            # SQLite giới hạn số lượng biến (999) trong 1 câu lệnh IN, nên ta chia nhỏ (chunk)
            chunk_size = 500
            for i in range(0, len(doc_ids), chunk_size):
                chunk = doc_ids[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(f"UPDATE documents SET has_content = 1 WHERE id IN ({placeholders})", chunk)
        
    conn.commit()

    cursor.execute("SELECT count(*) FROM documents WHERE has_content = 1")
    count = cursor.fetchone()[0]
    print(f"Thành công! Đã đánh dấu {count} văn bản có chứa nội dung (has_content = 1).")

    conn.close()

if __name__ == "__main__":
    main()
