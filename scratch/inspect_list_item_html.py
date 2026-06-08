import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/van-ban-moi.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    item = soup.find(class_='post-list-item')
    if item:
        print("Found post-list-item HTML:")
        print(item.prettify()[:1500])
    else:
        print("post-list-item class not found. Printing some body snippet:")
        print(soup.body.get_text()[:500])
else:
    print("Fetch failed")
