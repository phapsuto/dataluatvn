from bs4 import BeautifulSoup

def search_watermark():
    with open("scratch/luatvietnam.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    soup = BeautifulSoup(html, "html.parser")
    content_div = soup.find(class_="tab-noi-dung")
    if not content_div:
        # Let's search in the entire html
        content_div = soup
        
    text = content_div.get_text()
    
    # Common watermark keywords in Vietnamese law sites
    keywords = [
        "luatvietnam", "LuatVietnam", "vietnamlaw", "cấm sao chép", "bản quyền", 
        "trực tuyến", "tổng đài", "1900", "tiện ích", "đăng ký", "đăng nhập",
        "tài khoản", "tiêu chuẩn", "nâng cao", "vui lòng", "xem chi tiết"
    ]
    
    print("Searching for watermarks/prompts in content text...")
    for kw in keywords:
        matches = [m.start() for m in re.finditer(kw, text, re.IGNORECASE)] if 're' in globals() else []
        # fallback if re not imported
        import re
        matches = [m.start() for m in re.finditer(kw, text, re.IGNORECASE)]
        if matches:
            print(f"Keyword '{kw}' found {len(matches)} times:")
            for m in matches[:5]:
                start = max(0, m - 50)
                end = min(len(text), m + len(kw) + 50)
                snippet = text[start:end].replace('\n', ' ')
                print(f"  Snippet: ...{snippet}...")

if __name__ == "__main__":
    search_watermark()
