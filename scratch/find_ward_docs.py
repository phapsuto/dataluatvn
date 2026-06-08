import sqlite3

def find_wards_with_docs():
    db_path = "vietnamese_legal_documents.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Let's query wards and join with documents using LIKE
    print("Finding wards that match at least one document...")
    cursor.execute("SELECT code, name, full_name, province_code FROM wards")
    wards = cursor.fetchall()
    
    found = 0
    for w in wards:
        # Check if the name or full_name matches any document's pham_vi or co_quan_ban_hanh
        name = w["name"]
        fullname = w["full_name"]
        cursor.execute("SELECT count(*) FROM documents WHERE pham_vi LIKE ? OR co_quan_ban_hanh LIKE ?", (f"%{name}%", f"%{name}%"))
        count = cursor.fetchone()[0]
        if count > 0:
            print(f"Ward Code: {w['code']}, Name: {fullname}, Province: {w['province_code']} -> Matches {count} documents")
            found += 1
            if found >= 10:
                break
                
    conn.close()

if __name__ == "__main__":
    find_wards_with_docs()
