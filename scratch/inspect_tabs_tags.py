import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/dau-tu/thong-tu-27-2026-tt-bxd-quy-dinh-phan-cap-tham-quyen-bo-truong-bo-xay-dung-436725-d1.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Print all tags that have text containing "Nội dung" (case-insensitive)
    print("--- Elements containing 'Nội dung' ---")
    for el in soup.find_all(lambda tag: tag.name in ['a', 'span', 'li', 'div', 'button'] and tag.string and "Nội dung" in tag.string):
        print(f"Tag: {el.name} class={el.get('class')} id={el.get('id')} parent={el.parent.name} text='{el.string}'")
        
    print("\n--- Let's find all links with text containing 'nội' or 'dung' ---")
    for a in soup.find_all('a'):
        txt = a.get_text(strip=True)
        if "nội" in txt.lower() or "dung" in txt.lower() or "gốc" in txt.lower() or "lực" in txt.lower() or "lược" in txt.lower() or "quan" in txt.lower():
            print(f"Link text: '{txt}' -> href: '{a.get('href')}' class: {a.get('class')}")
            
    # Print the outer HTML of the tab navigation area
    # Let's search for any ul or div with class containing 'nav', 'tab', 'menu'
    print("\n--- Search navigation containers ---")
    for tag in soup.find_all(['ul', 'div'], class_=True):
        class_str = " ".join(tag['class'])
        if any(w in class_str for w in ['tab', 'nav', 'menu-doc', 'doc-menu']):
            print(f"Container: {tag.name} class={tag['class']} id={tag.get('id')} len={len(tag.get_text())}")
            # print children text
            children = [c.get_text(strip=True) for c in tag.children if c.name]
            print("Children text:", children[:10])
            print("-" * 40)
else:
    print("Fetch failed")
