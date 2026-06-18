from bs4 import BeautifulSoup
import re

with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

ban_hanh_span = soup.find("span", string="Ban hành")
if ban_hanh_span:
    print("Found 'Ban hành' span:")
    # Print the parent div and all its children
    parent_div = ban_hanh_span.parent
    print(f"  Parent: <{parent_div.name}> class: {parent_div.get('class')}")
    print(f"  Parent outer HTML:\n{parent_div.prettify()}")
    
    # Print the siblings of parent
    print("\nSiblings of parent:")
    for sib in parent_div.next_siblings:
        if sib.name:
            print(f"  <{sib.name}> class: {sib.get('class')} | text: {sib.get_text().strip()}")
            
    # Print the grand-parent (the metadata grid block)
    p2 = parent_div.parent
    print(f"\nGrand-parent: <{p2.name}> class: {p2.get('class')}")
    print(f"Grand-parent outer HTML:\n{p2.prettify()[:1000]}")
