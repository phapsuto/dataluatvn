import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/van-ban-moi.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    item = soup.find(class_='post-doc')
    if item:
        print(f"post-doc element:")
        for idx, child in enumerate(item.children):
            if child.name:
                print(f"Child {idx}: name={child.name} class={child.get('class')} text_preview='{child.get_text(strip=True)[:100]}'")
    else:
        print("post-doc not found")
else:
    print("Fetch failed")
