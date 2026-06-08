import sqlite3
import re
from bs4 import BeautifulSoup
import sys

def extract_modifications():
    conn = sqlite3.connect('vietnamese_legal_documents.db')
    conn_content = sqlite3.connect('content_store.db')
    cursor = conn.cursor()
    cursor_content = conn_content.cursor()

    # Find all relationships where doc A modifies doc B
    # doc_id = modifying document, other_doc_id = modified document
    cursor.execute("""
        SELECT doc_id, other_doc_id, relationship
        FROM relationships
        WHERE relationship IN ('Văn bản được sửa đổi', 'Văn bản sửa đổi', 'Văn bản được bổ sung', 'Văn bản bổ sung')
    """)
    rels = cursor.fetchall()

    print(f"Found {len(rels)} potential modification relationships.")
    
    # We will just process a few for testing, or all if it's fast
    # To be safe and fast for this demo, let's prioritize Penal code 2015 (96122) as the modified document
    target_modified_docs = {96122}

    processed = 0
    inserted = 0

    for doc_id, other_doc_id, rel in rels:
        # For demonstration, only process if it modifies Penal Code
        if other_doc_id not in target_modified_docs and doc_id not in target_modified_docs:
            continue
            
        modified_doc_id = other_doc_id if 'được' in rel else doc_id
        modifying_doc_id = doc_id if 'được' in rel else other_doc_id

        # Read content of the modifying document
        cursor_content.execute("SELECT content_html FROM document_content WHERE doc_id = ?", (modifying_doc_id,))
        row = cursor_content.fetchone()
        if not row or not row[0]:
            continue

        html = row[0]
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)

        # Naive regex to find amended articles
        # E.g., "Sửa đổi, bổ sung khoản 1 Điều 173" -> captures "173"
        # E.g., "Sửa đổi Điều 173" -> captures "173"
        pattern = r'Sửa đổi.*?Điều\s+(\d+[A-Z]?)'
        matches = re.finditer(pattern, text, re.IGNORECASE)

        for match in matches:
            article_num = match.group(1)
            article_name = f"Điều {article_num}"
            # Extract a snippet context
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 200)
            snippet = text[start:end]

            cursor.execute("""
                INSERT INTO article_modifications (doc_id, article_name, modified_by_doc_id, modified_text)
                VALUES (?, ?, ?, ?)
            """, (modified_doc_id, article_name, modifying_doc_id, snippet))
            inserted += 1

        processed += 1

    conn.commit()
    print(f"Processed {processed} modifying documents, inserted {inserted} modifications.")
    conn.close()
    conn_content.close()

if __name__ == '__main__':
    extract_modifications()
