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
            
            # Find all divs containing tab-content or tab-noi-dung
            for d in soup.find_all("div"):
                classes = d.get('class')
                if classes and any(c in ' '.join(classes) for c in ['tab-content', 'tab-noi-dung']):
                    print(f"Found div | classes: {classes} | text length: {len(d.get_text())}")
                    if len(d.get_text()) > 1000:
                        print("  Text preview:")
                        print(d.get_text()[:300].strip())
                        print("-" * 50)
                        
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
