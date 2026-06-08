import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/dau-tu/thong-tu-27-2026-tt-bxd-quy-dinh-phan-cap-tham-quyen-bo-truong-bo-xay-dung-436725-d1.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Let's find table or list containing metadata
    meta_table = soup.find('table', class_='overview-meta-table') or soup.find('table')
    if meta_table:
        print("Found table HTML:")
        print(meta_table.prettify()[:2000])
    else:
        # If no table, let's find divs containing "Số hiệu:"
        print("No table found. Finding div containing 'Số hiệu:'")
        div = soup.find(lambda tag: tag.name == 'div' and tag.get_text() and "Số hiệu:" in tag.get_text())
        if div:
            print(div.prettify()[:1000])
else:
    print("Fetch failed")
