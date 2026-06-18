from bs4 import BeautifulSoup
import re

def analyze_luatvietnam():
    print("--- LUATVIETNAM.VN ANALYSIS ---")
    with open("scratch/luatvietnam.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    
    # Let's search for links containing "/van-ban/" or ending in ".html"
    links = soup.find_all("a", href=True)
    vb_links = []
    for l in links:
        href = l['href']
        text = l.get_text().strip()
        # Find document links - usually they look like /van-ban/...
        if "/van-ban/" in href and len(text) > 15:
            vb_links.append((href, text))
            
    print(f"Found {len(vb_links)} possible document links:")
    for href, text in vb_links[:15]:
        print(f"  Href: {href} | Text: {text[:60]}")
        
    # Let's search for tables or list blocks
    # Look for elements with class names containing "doc", "list", "item", "law"
    print("\nProminent class names:")
    classes = set()
    for el in soup.find_all(class_=True):
        for c in el['class']:
            if any(k in c.lower() for k in ['doc', 'list', 'item', 'law', 'vanban', 'card', 'table']):
                classes.add(c)
    print(list(classes)[:20])

def analyze_phapluat():
    print("\n--- PHAPLUAT.GOV.VN ANALYSIS ---")
    with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    links = soup.find_all("a", href=True)
    vb_links = []
    for l in links:
        href = l['href']
        text = l.get_text().strip()
        # vbpl links usually have dynamic endpoints or IDs
        if ("/chi-tiet/" in href or "/van-ban/" in href or "id=" in href) and len(text) > 10:
            vb_links.append((href, text))
            
    print(f"Found {len(vb_links)} possible document links:")
    for href, text in vb_links[:15]:
        print(f"  Href: {href} | Text: {text[:60]}")
        
    # Let's search for table or grid elements
    print("\nTable/Grid tags:")
    tables = soup.find_all("table")
    print(f"Found {len(tables)} tables.")
    for i, t in enumerate(tables):
        print(f"  Table {i} headers: {[th.get_text().strip() for th in t.find_all('th')]}")

if __name__ == "__main__":
    analyze_luatvietnam()
    analyze_phapluat()
