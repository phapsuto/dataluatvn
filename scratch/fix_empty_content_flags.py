import sqlite3
from bs4 import BeautifulSoup
import os

DB_NAME = "vietnamese_legal_documents.db"
CONTENT_DB = "content_store.db"

def main():
    if not os.path.exists(DB_NAME) or not os.path.exists(CONTENT_DB):
        print("Database files not found.")
        return

    print("Connecting to databases...")
    c_conn = sqlite3.connect(CONTENT_DB)
    m_conn = sqlite3.connect(DB_NAME)

    c_cursor = c_conn.cursor()
    m_cursor = m_conn.cursor()

    print("Fetching documents from content store...")
    c_cursor.execute("SELECT doc_id, content_html FROM document_content")
    
    empty_ids = []
    checked = 0
    
    # We will fetch in batches to avoid high memory usage
    while True:
        rows = c_cursor.fetchmany(10000)
        if not rows:
            break
        for doc_id, html in rows:
            checked += 1
            if not html:
                empty_ids.append(doc_id)
                continue
            
            # Simple fast checks before calling BeautifulSoup
            if len(html) < 450:
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text().strip()
                if not text:
                    empty_ids.append(doc_id)
                    
        print(f"Checked {checked} documents...")

    print(f"Found {len(empty_ids)} documents with empty text content out of {checked} total checked.")
    
    if empty_ids:
        print("Updating has_content = 0 in main database...")
        # Update in batches of 999 (SQLite limit for parameter count)
        batch_size = 900
        for i in range(0, len(empty_ids), batch_size):
            batch = empty_ids[i:i+batch_size]
            placeholders = ",".join(["?"] * len(batch))
            m_cursor.execute(
                f"UPDATE documents SET has_content = 0 WHERE id IN ({placeholders})",
                batch
            )
        m_conn.commit()
        print("Successfully updated has_content = 0 in main database.")
    
    c_conn.close()
    m_conn.close()

if __name__ == "__main__":
    main()
