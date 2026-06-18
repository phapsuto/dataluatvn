from bs4 import BeautifulSoup

def find_surrounding_html(filename, text_to_find):
    print(f"\nSearching for '{text_to_find}' in {filename}...")
    with open(filename, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    elements = soup.find_all(string=lambda text: text and text_to_find in text)
    print(f"Found {len(elements)} occurrences:")
    for i, el in enumerate(elements):
        print(f"Occurrence {i+1}:")
        parent = el.parent
        print(f"  Parent tag: {parent.name} | classes: {parent.get('class')} | attrs: {list(parent.attrs.keys())}")
        # Print up to 3 levels of ancestors
        p = parent
        for level in range(3):
            p = p.parent
            if p:
                print(f"  Ancestor L{level+1}: {p.name} | classes: {p.get('class')} | attrs: {list(p.attrs.keys())}")
        print("-" * 40)

if __name__ == "__main__":
    find_surrounding_html("scratch/luatvietnam.html", "3414/CT-CHK")
    find_surrounding_html("scratch/phapluat.html", "16/2026/QĐ-UBND")
