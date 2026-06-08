import requests
from bs4 import BeautifulSoup

url = "https://luatvietnam.vn/dau-tu/thong-tu-27-2026-tt-bxd-quy-dinh-phan-cap-tham-quyen-bo-truong-bo-xay-dung-436725-d1.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Let's find all table cells that contain labels
    print("--- Meta Table Elements ---")
    for td in soup.find_all('td'):
        td_text = td.get_text(strip=True)
        if td_text and any(label in td_text for label in ["Cơ quan ban hành", "Số hiệu", "Ngày ban hành", "Hiệu lực", "Lĩnh vực", "Người ký", "Ngày hết hiệu lực"]):
            # print this td and next sibling tds
            siblings = [td.get_text(strip=True)]
            curr = td.next_sibling
            while curr:
                if curr.name in ['td', 'th']:
                    siblings.append(curr.get_text(strip=True))
                curr = curr.next_sibling
            print("Row:", " | ".join(siblings))
            
    # If no td, check list elements (li) or divs
    print("--- List/Div Elements ---")
    for item in soup.find_all(['li', 'div']):
        text = item.get_text(strip=True)
        if text and any(label + ":" in text for label in ["Cơ quan ban hành", "Số hiệu", "Ngày ban hành", "Hiệu lực", "Lĩnh vực", "Người ký", "Ngày hết hiệu lực"]):
            print("Item:", text[:150])

    # Let's search for full text container
    # Full text is usually in a div like class="the-content", class="content-doc", id="doc-content", class="box-content-doc", id="full-text"
    print("\n--- Potential Content Containers ---")
    candidates = []
    for div in soup.find_all('div'):
        div_class = div.get('class', [])
        div_id = div.get('id', '')
        
        # Check if class or id contains keywords
        is_candidate = False
        if isinstance(div_class, list):
            class_str = " ".join(div_class)
        else:
            class_str = str(div_class)
            
        for kw in ["doc-content", "content-doc", "the-content", "body-doc", "fulltext", "full-text", "noi-dung-doc", "box-content"]:
            if kw in class_str or kw in div_id:
                is_candidate = True
                break
        
        if is_candidate:
            candidates.append((div.name, div_class, div_id, len(div.get_text())))
            
    for cand in candidates:
        print(f"Cand: tag={cand[0]} class={cand[1]} id={cand[2]} len={cand[3]}")
        
    # Let's search specifically for the div that contains the string "Bộ trưởng Bộ Xây dựng" and "phân cấp" and has length > 1000
    print("\n--- Searching by content ---")
    for div in soup.find_all('div'):
        txt = div.get_text()
        if "Bộ trưởng Bộ Xây dựng" in txt and "tài sản công" in txt and len(txt) > 2000:
            # check if it has children
            # we want the deepest child that still has length > 2000
            print(f"Div found: class={div.get('class')} id={div.get('id')} len={len(txt)}")
            # print first 300 chars
            print(txt.strip()[:300])
            print("...")
            break
