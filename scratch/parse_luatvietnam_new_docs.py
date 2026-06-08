import requests
from bs4 import BeautifulSoup
import re

url = "https://luatvietnam.vn/van-ban-moi.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

resp = requests.get(url, headers=headers, timeout=15)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Let's search for document blocks.
    # Typically, documents are inside list divs.
    # Let's look for tags that contain "Nghị quyết", "Thông tư", "Quyết định", "Nghị định"
    # or have class containing "document", "list", "item", "title".
    
    # Print elements that might contain document title and metadata
    # Often there's a list with class "list-document" or similar
    classes = set()
    for el in soup.find_all(class_=True):
        for c in el['class']:
            classes.add(c)
            
    print("Found classes starting with 'doc' or 'list':")
    for c in sorted(classes):
        if 'doc' in c or 'list' in c or 'item' in c or 'van' in c:
            print(f" - {c}")
            
    # Let's find links inside the main area
    # Let's print links with text that looks like a legal document title
    print("\n--- Potential Legal Document Links ---")
    doc_patterns = ["nghị định", "thông tư", "quyết định", "luật", "pháp lệnh", "nghị quyết", "chỉ thị"]
    count = 0
    for link in soup.find_all('a', href=True):
        text = link.get_text(strip=True)
        href = link['href']
        # check if text looks like a legal document
        is_doc = any(pat in text.lower() for pat in doc_patterns)
        if is_doc and len(text) > 20:
            print(f"Text: {text}")
            print(f"Href: {href}")
            print("-" * 40)
            count += 1
            if count >= 20:
                break
else:
    print("Fetch failed")
