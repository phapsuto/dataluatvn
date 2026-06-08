import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/van-ban-moi.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    # Let's find all pagination links. They are typically inside a div with class containing 'pagination' or 'pager' or similar
    print("--- Pagination Container links ---")
    pag_container = soup.find(class_=lambda c: c and ('pagination' in c or 'page' in c or 'pager' in c))
    if pag_container:
        print(f"Container: class={pag_container.get('class')}")
        for link in pag_container.find_all('a', href=True):
            print(f"Text: {link.get_text(strip=True)} -> {link['href']}")
    else:
        # Just print any link that contains "page-" or "p=" or looks like a page link
        print("No pagination container found. Printing all links that might be pages:")
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'p=' in href or 'page' in href or '-p' in href:
                print(f"Link: {link.get_text(strip=True)} -> {href}")
else:
    print("Fetch failed")
