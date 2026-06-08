import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

for page in range(1, 11): # Let's check 10 pages!
    url = f"https://luatvietnam.vn/van-ban-moi.html?PageSize=20&PageIndex={page}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, 'html.parser')
        docs = soup.find_all(class_='post-doc')
        dates = []
        for doc in docs:
            meta_div = doc.find(class_='post-meta-doc')
            if meta_div:
                dmy = meta_div.find(class_='doc-dmy')
                if dmy:
                    dates.append(dmy.find(class_='w-doc-dmy2').get_text(strip=True))
        if dates:
            print(f"Page {page}: {len(docs)} documents. Date range: {dates[0]} to {dates[-1]}")
        else:
            print(f"Page {page}: {len(docs)} documents. No dates found.")
    else:
        print(f"Failed to fetch page {page}")
