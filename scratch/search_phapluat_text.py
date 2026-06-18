from bs4 import BeautifulSoup
import re

with open("scratch/phapluat.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

matches = soup.find_all(string=re.compile("Ban hành", re.IGNORECASE))
print(f"Found {len(matches)} matches for 'Ban hành':")
for i, m in enumerate(matches[:10]):
    print(f"  [{i+1}] parent: <{m.parent.name}> class: {m.parent.get('class')} | text: {m.strip()[:100]}")
