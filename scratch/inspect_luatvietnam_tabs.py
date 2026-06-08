import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/dau-tu/thong-tu-27-2026-tt-bxd-quy-dinh-phan-cap-tham-quyen-bo-truong-bo-xay-dung-436725-d1.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Search for any link that contains "nội dung" or has class/id related to tabs
    print("--- Tab links ---")
    for link in soup.find_all('a', href=True):
        text = link.get_text(strip=True)
        if any(t in text.lower() for t in ["tổng quan", "nội dung", "vb gốc", "hiệu lực", "liên quan", "lược đồ"]):
            print(f"Tab: {text} -> {link['href']}")
            
    # Let's search for the div that holds the full content of the document
    # Maybe the content is in the page but hidden/shown with CSS or is it inside a div with class "content-full" or "content-doc"
    # Let's print all div classes and ids that have text containing "Điều 1." or "Điều 1 "
    print("\n--- Search divs containing 'Điều 1' ---")
    for div in soup.find_all('div'):
        txt = div.get_text(strip=True)
        if len(txt) > 200 and "Điều 1." in txt:
            print(f"Tag: {div.name} class={div.get('class')} id={div.get('id')} len={len(txt)}")
            print("Preview:", txt[:150])
            print("-" * 30)
else:
    print("Fetch failed")
