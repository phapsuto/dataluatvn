from bs4 import BeautifulSoup

def analyze_phapluat_detail():
    with open("scratch/phapluat_new_tab.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    print("--- PHAPLUAT.GOV.VN DETAIL PAGE ANALYSIS ---")
    
    # Let's search for tables on the page
    tables = soup.find_all("table")
    print(f"Found {len(tables)} tables.")
    for i, t in enumerate(tables):
        print(f"\nTable {i}:")
        for tr in t.find_all("tr")[:10]:
            print(f"  {tr.get_text().strip().replace('\n', ' ')}")
            
    # Let's search for lists or meta sections
    print("\nSearching for meta items:")
    meta_keywords = ["Cơ quan ban hành", "Số hiệu", "Ngày ban hành", "Người ký", "Ngày áp dụng", "Hiệu lực"]
    for kw in meta_keywords:
        el = soup.find(string=lambda t: t and kw in t)
        if el:
            print(f"  Found '{kw}': Parent tag is <{el.parent.name}> | text: {el.parent.get_text().strip()[:150]}")
            # Try to print parent's parent
            p = el.parent.parent
            if p:
                print(f"    Parent's parent text: {p.get_text().strip()[:200]}")
                
    # Find the main text content div
    # Often it has classes like "content", "fulltext", "detail", "noidung", "law-content"
    print("\nPossible content divs:")
    content_divs = []
    for d in soup.find_all("div", class_=True):
        classes = d.get('class')
        class_str = ' '.join(classes)
        if any(c in class_str for c in ['content', 'noidung', 'detail', 'fulltext', 'noi-dung', 'active']):
            content_divs.append((d, len(d.get_text())))
            
    content_divs.sort(key=lambda x: x[1], reverse=True)
    for d, length in content_divs[:8]:
        print(f"  Class: {d.get('class')} | length: {length}")
        if 500 < length < 200000:
            print("    Preview:")
            print(d.get_text()[:400].strip())
            print("-" * 50)

if __name__ == "__main__":
    analyze_phapluat_detail()
