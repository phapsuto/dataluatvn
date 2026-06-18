import asyncio
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def parse_detail():
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
            
            # Save screenshot
            screenshot_path = "/Users/tonguyen/.gemini/antigravity-ide/brain/4dd346af-f3c4-4d23-b284-13cea384cf66/luatvn_detail_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"Saved screenshot to {screenshot_path}")
            
            # Extract HTML
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # Let's see if we can find full text content or metadata table
            # On luatvietnam.vn, metadata table is usually in a table or a list
            tables = soup.find_all("table")
            print(f"Found {len(tables)} tables on detail page.")
            for i, t in enumerate(tables):
                text = t.get_text()
                if "Cơ quan ban hành" in text or "Số hiệu" in text or "Ngày ban hành" in text:
                    print(f"  Table {i} is likely the metadata table:")
                    for tr in t.find_all("tr"):
                        print(f"    {tr.get_text().strip().replace('\n', ' ')}")
            
            # Let's find the main full text div
            # Often it's a div with class containing "content", "fulltext", "detail", "van-ban"
            print("\nPossible content divs:")
            content_divs = []
            for d in soup.find_all("div", class_=True):
                classes = d.get('class')
                if any(c in ' '.join(classes) for c in ['content', 'fulltext', 'detail-content', 'noi-dung', 'article-detail']):
                    content_divs.append((classes, len(d.get_text())))
            for cls, length in sorted(content_divs, key=lambda x: x[1], reverse=True)[:10]:
                print(f"  Class: {cls} | Text length: {length}")
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(parse_detail())
