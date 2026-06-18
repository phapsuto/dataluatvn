import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    url = "https://luatvietnam.vn/vi-pham-hanh-chinh/nghi-dinh-211-2026-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh-ve-chan-nuoi-437773-d1.html"
    print(f"Fetching detail page: {url}...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # Find the largest content div
            content_divs = []
            for d in soup.find_all("div", class_=True):
                classes = d.get('class')
                if any(c in ' '.join(classes) for c in ['content', 'fulltext', 'detail-content', 'noi-dung', 'article-detail']):
                    content_divs.append((d, len(d.get_text())))
            
            if not content_divs:
                print("No content divs found!")
                return
                
            # Get largest
            content_divs.sort(key=lambda x: x[1], reverse=True)
            largest_div, length = content_divs[0]
            print(f"Largest div class: {largest_div.get('class')} | length: {length}")
            
            text = largest_div.get_text()
            print("\nFirst 1000 chars of content:")
            print(text[:1000])
            
            # Let's search for "luatvietnam" or other watermarks in the text of the largest div
            import re
            print("\nSearching watermarks inside largest div:")
            keywords = ["luatvietnam", "bản quyền", "copy", "cấm sao chép"]
            for kw in keywords:
                matches = [m.start() for m in re.finditer(kw, text, re.IGNORECASE)]
                print(f"  Keyword '{kw}' matches: {len(matches)}")
                for m in matches[:5]:
                    start = max(0, m - 40)
                    end = min(len(text), m + len(kw) + 40)
                    print(f"    snippet: ...{text[start:end].strip().replace('\n', ' ')}...")
                    
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
