from bs4 import BeautifulSoup
import re

with open("scratch/luatvietnam.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

posts = soup.find_all("div", class_="post-doc")
print(f"Total posts: {len(posts)}")
for i, p in enumerate(posts):
    # Find h2.doc-title or similar
    h2 = p.find("h2", class_="doc-title")
    if not h2:
        # Try finding any a tag inside that could be title
        title_a = p.find("a")
    else:
        title_a = h2.find("a")
        
    if title_a:
        title = title_a.get_text().strip()
        href = title_a['href']
        # Let's find the publish date
        meta = p.find("div", class_="doc-meta")
        meta_text = meta.get_text().strip().replace('\n', ' ') if meta else ""
        print(f"[{i+1}] Title: {title[:60]}... | Date: {meta_text} | Href: {href}")
