from bs4 import BeautifulSoup

def inspect_content_paragraphs():
    with open("scratch/luatvietnam.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find(class_="tab-noi-dung")
    if not content_div:
        print("No class='tab-noi-dung' found!")
        return
        
    paragraphs = content_div.find_all(["p", "div", "table"])
    print(f"Total elements inside tab-noi-dung: {len(paragraphs)}")
    
    # Print the first 10 paragraphs/elements
    print("\nFirst 10 elements:")
    count = 0
    for el in paragraphs:
        text = el.get_text().strip()
        if text:
            print(f"  [{count+1}] <{el.name}>: {text[:150]}")
            count += 1
            if count >= 10:
                break
                
    # Search for watermark strings in the paragraph texts
    watermark_patterns = [
        r"luatvietnam", r"LuatVietnam", r"bản quyền", r"cấm sao chép", r"1900\s*\d+"
    ]
    import re
    print("\nChecking paragraphs for watermarks:")
    for i, el in enumerate(paragraphs):
        text = el.get_text()
        for pat in watermark_patterns:
            if re.search(pat, text, re.IGNORECASE):
                # Print the paragraph and where it is
                print(f"  Element {i} (<{el.name}>) contains watermark matching '{pat}':")
                print(f"    Text: {text.strip()[:200]}")
                print("-" * 50)

if __name__ == "__main__":
    inspect_content_paragraphs()
