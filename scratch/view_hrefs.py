from bs4 import BeautifulSoup

def view_luatvietnam_post_docs():
    with open("scratch/luatvietnam.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    posts = soup.find_all("div", class_="post-doc")
    print(f"Found {len(posts)} post-doc divs in LuatVietnam:")
    for i, p in enumerate(posts[:3]):
        print(f"\n--- Post {i+1} ---")
        title_a = p.find("h2", class_="doc-title").find("a")
        print(f"Title: {title_a.get_text().strip()}")
        print(f"Href: {title_a['href']}")
        print(f"Title attr: {title_a.get('title')}")
        
        # Meta tags (date, organ, etc.)
        meta_div = p.find("div", class_="doc-meta")
        if meta_div:
            print(f"Meta text: {meta_div.get_text().strip()}")
            
        # Let's see if we can find document metadata or links
        links = [a['href'] for a in p.find_all("a", href=True)]
        print(f"All links in this post: {links}")

def view_phapluat_docs():
    with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    # In phapluat.gov.vn, let's look for divs that represent document cards
    # We saw Ancestor L3: div | classes: ['flex', 'items-start', 'gap-3', 'sm:gap-4']
    # Let's find divs containing text "1/7/2026" or "16/6/2026"
    cards = []
    for d in soup.find_all("div"):
        text = d.get_text()
        if "16/6/2026" in text and len(text) < 1000:
            cards.append(d)
            
    print(f"\nFound {len(cards)} possible cards in phapluat:")
    for i, c in enumerate(cards[:2]):
        print(f"\n--- Card {i+1} ---")
        print(f"Classes: {c.get('class')}")
        # Print child structure or some texts
        print(f"Text content: {c.get_text().strip()[:200]}")
        # Find all elements inside with class or action
        for sub in c.find_all(["div", "span", "button", "a"]):
            if sub.get("class") or sub.name == "button" or sub.name == "a":
                print(f"  Sub: {sub.name} | Class: {sub.get('class')} | Text: {sub.get_text().strip()[:40]}")

if __name__ == "__main__":
    view_luatvietnam_post_docs()
    view_phapluat_docs()
