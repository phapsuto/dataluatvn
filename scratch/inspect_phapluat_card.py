from bs4 import BeautifulSoup

def inspect_phapluat_card():
    with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    # Find the element containing '16/2026/QĐ-UBND'
    target = soup.find(string=lambda t: t and '16/2026/QĐ-UBND' in t)
    if not target:
        print("Target text not found in phapluat.html!")
        return
        
    print("Found target text. Let's trace ancestors:")
    curr = target
    for i in range(5):
        curr = curr.parent
        if not curr:
            break
        print(f"  Level {i+1}: <{curr.name}> | class: {curr.get('class')} | id: {curr.get('id')} | attrs: {list(curr.attrs.keys())}")
        
    print("\nLet's print the outer HTML of the card container (Level 4):")
    print(curr.prettify()[:2000])

if __name__ == "__main__":
    inspect_phapluat_card()
