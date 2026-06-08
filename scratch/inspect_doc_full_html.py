import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/van-ban-moi.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, yGecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    item = soup.find(class_='post-type-doc')
    if item:
        print(item.prettify())
    else:
        print("post-type-doc not found")
else:
    print("Fetch failed")
