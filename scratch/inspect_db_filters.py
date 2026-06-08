import sqlite3
from app.routers.laws import get_province_search_terms, get_ward_search_terms

def test():
    db_path = "vietnamese_legal_documents.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 1. Hanoi terms
    p_terms = get_province_search_terms("01", conn)
    print("Hanoi terms:", p_terms)
    
    # 2. Ba Dinh ward terms
    w_terms = get_ward_search_terms("00004", conn)
    print("Ba Dinh terms:", w_terms)
    
    # 3. Check if any of these match the document ID 1 (Hiến pháp 2013) or other national documents
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, pham_vi, co_quan_ban_hanh FROM documents WHERE id = 1")
    doc1 = cursor.fetchone()
    print("\nDoc 1 (Hiến pháp 2013):")
    print("  Title:", doc1["title"])
    print("  Pham vi:", doc1["pham_vi"])
    print("  Co quan:", doc1["co_quan_ban_hanh"])
    
    # Let's run a query selecting documents that match Hanoi terms
    print("\nMatching Hanoi terms in DB:")
    province_clauses = []
    params = []
    for t in p_terms:
        province_clauses.append("pham_vi LIKE ? OR co_quan_ban_hanh LIKE ?")
        params.extend([f"%{t}%", f"%{t}%"])
    query = f"SELECT id, title, pham_vi, co_quan_ban_hanh FROM documents WHERE {' OR '.join(province_clauses)} LIMIT 5"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    for r in rows:
        print(f"  ID: {r['id']}, Title: {r['title'][:60]}, Pham vi: {r['pham_vi']}, Agency: {r['co_quan_ban_hanh']}")
        
    # Let's check how many total match
    cursor.execute(f"SELECT count(*) FROM documents WHERE {' OR '.join(province_clauses)}", params)
    print("Total Hanoi matches in DB:", cursor.fetchone()[0])
    
    conn.close()

if __name__ == "__main__":
    test()
