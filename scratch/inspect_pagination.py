from bs4 import BeautifulSoup

def main():
    with open("scratch/luatvietnam.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
        
    pag = soup.find(class_="pagination")
    if pag:
        print("Found pagination outer HTML:")
        print(pag.prettify()[:1500])

if __name__ == "__main__":
    main()
