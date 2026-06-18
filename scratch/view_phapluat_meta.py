from bs4 import BeautifulSoup

def main():
    with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    # Search for all elements containing "Áp dụng" or "Ban hành" inside card items
    # Let's print all parents of elements with text containing "Ban hành:"
    els = soup.find_all(string=lambda t: t and "Ban hành:" in t)
    print(f"Found {len(els)} elements with 'Ban hành:':")
    for i, el in enumerate(els):
        parent = el.parent
        print(f"\n[{i+1}] Parent tag: <{parent.name}> | class: {parent.get('class')}")
        print(f"  Parent text: {parent.get_text().strip()}")
        # Let's see the siblings or parent's parent
        p2 = parent.parent
        print(f"  P2 class: {p2.get('class') if p2 else 'None'}")
        print(f"  P2 text: {p2.get_text().strip() if p2 else 'None'}")
        p3 = p2.parent if p2 else None
        print(f"  P3 class: {p3.get('class') if p3 else 'None'}")

if __name__ == "__main__":
    main()
