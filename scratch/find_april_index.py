import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

for page in [30, 45, 55, 65, 75]:
    url = f"https://luatvietnam.vn/van-ban-moi.html?PageSize=20&PageIndex={page}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, 'html.parser')
        docs = soup.find_all(class_='post-doc')
        if docs:
            meta_div = docs[0].find(class_='post-meta-doc')
            if meta_div:
                dmy = meta_div.find(class_='doc-dmy')
                if dmy:
                    date_str = dmy.find(class_='w-doc-dmy2').get_text(strip=True)
                    print(f"Page {page} start date: {date_str}")
        else:
            print(f"Page {page}: No documents found")
    else:
        print(f"Failed to fetch page {page}")
