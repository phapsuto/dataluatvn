import sqlite3

content_conn = sqlite3.connect("content_store.db")
cursor = content_conn.cursor()
cursor.execute("SELECT doc_id, content_html FROM document_content WHERE content_html IS NOT NULL AND length(content_html) > 1000 LIMIT 3")
rows = cursor.fetchall()
content_conn.close()

for i, (doc_id, content_html) in enumerate(rows):
    print(f"=== Document ID: {doc_id} ===")
    print(f"HTML Length: {len(content_html)}")
    print("Snippet:")
    print(content_html[:1500])
    print("...\n")
