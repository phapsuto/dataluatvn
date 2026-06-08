import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/van-ban-moi.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Find all links ending with -d1.html or -d2.html
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.endswith('-d1.html') or href.endswith('-d2.html'):
            # Find its parent list-item or container
            parent = link.find_parent(class_='post-list-item') or link.find_parent('div')
            print(f"Found document link: {href}")
            print(f"Parent element {parent.name} class={parent.get('class')} id={parent.get('id')}:")
            print(parent.prettify()[:1500])
            print("=" * 60)
            break
else:
    print("Fetch failed")
