import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/dau-tu/thong-tu-27-2026-tt-bxd-quy-dinh-phan-cap-tham-quyen-bo-truong-bo-xay-dung-436725-d1.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

print(f"Fetching {url}...")
resp = requests.get(url, headers=headers, timeout=15)
print(f"Status Code: {resp.status_code}")
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # 1. Print title
    h1 = soup.find('h1')
    print("H1 Title:", h1.get_text(strip=True) if h1 else "Not found")
    
    # 2. Check metadata
    # Often LuatVietNam has a metadata table or section.
    # Let's search for typical labels like "Cơ quan ban hành", "Số hiệu", "Ngày ban hành", "Hiệu lực"
    text = soup.get_text()
    for label in ["Cơ quan ban hành", "Số hiệu", "Ngày ban hành", "Tình trạng hiệu lực", "Lĩnh vực"]:
        match = soup.find(text=lambda t: t and label in t)
        if match:
            # Let's print its parent or surrounding text
            print(f"Label found: '{label}' -> Parent text: {match.parent.get_text(strip=True)[:100]}")
            
    # 3. Check fulltext content
    # Let's see if there is a div with class "content-html" or id "content-detail" or similar
    content_div = soup.find('div', id='content-detail') or soup.find(class_=lambda c: c and 'content' in c)
    if content_div:
        print(f"Content div found: {content_div.name} class={content_div.get('class')} id={content_div.get('id')}")
        print("Content text preview:", content_div.get_text(strip=True)[:200])
    else:
        # Let's search for any div containing "Điều 1" or similar
        print("No content-detail div found, trying to search for largest text block...")
        largest_div = None
        largest_len = 0
        for div in soup.find_all('div'):
            text_len = len(div.get_text())
            if text_len > largest_len:
                largest_len = text_len
                largest_div = div
        if largest_div:
            print(f"Largest div name={largest_div.name} class={largest_div.get('class')} id={largest_div.get('id')} len={largest_len}")
            print("Preview:", largest_div.get_text(strip=True)[:200])
else:
    print("Fetch failed")
