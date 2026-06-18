from bs4 import BeautifulSoup
import re

with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

# Let's search for elements containing page numbers or next page icons like ">" or "Sau"
# Find all elements with classes containing "page", "pag", "pagination", "next"
classes = set()
for el in soup.find_all(class_=True):
    for c in el['class']:
        if any(k in c.lower() for k in ['page', 'pag', 'next', 'prev']):
            classes.add(c)
print("Page-related class names in phapluat.html:")
print(list(classes))

# Search for elements containing page numbers
for d in soup.find_all(["button", "a", "li", "span"]):
    txt = d.get_text().strip()
    if txt == "2" or txt == "Sau" or txt == "Next" or "Trang" in txt:
        print(f"  Element: <{d.name}> | class: {d.get('class')} | text: {txt}")
