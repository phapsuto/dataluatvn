import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    url = "https://phapluat.gov.vn/he-thong-van-ban-phap-luat"
    print(f"Navigating to {url}...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print("Page loaded. Waiting for cards...")
            await page.wait_for_timeout(6000)
            
            # Click on the first document card title or "Nội dung" button
            # Let's print the buttons on the page first
            buttons = await page.evaluate("""
            () => {
                const btns = [];
                document.querySelectorAll('button, div[class*="cursor-pointer"], a').forEach(el => {
                    const txt = el.textContent.trim();
                    if (txt.length > 5) {
                        btns.push({ tag: el.tagName, class: el.className, text: txt.substring(0, 50) });
                    }
                });
                return btns;
            }
            """)
            print(f"Found {len(buttons)} clickable elements. First 20:")
            for b in buttons[:20]:
                print(f"  {b['tag']} | class: {b['class']} | text: {b['text']}")
                
            # Click the first div containing "Quyết định" or "Nghị định" which is the title
            print("\nClicking on the first document title...")
            await page.evaluate("""
            () => {
                const els = document.querySelectorAll('div[class*="cursor-pointer"]');
                for (const el of els) {
                    const text = el.textContent.trim();
                    if (text.includes('Quyết định') || text.includes('Nghị định') || text.includes('Thông tư')) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
            """)
            
            # Wait for detail page
            print("Clicked! Waiting 8 seconds for detail page to load...")
            await page.wait_for_timeout(8000)
            
            print(f"Current URL after click: {page.url}")
            
            # Save screenshot of detail page
            screenshot_path = "/Users/tonguyen/.gemini/antigravity-ide/brain/4dd346af-f3c4-4d23-b284-13cea384cf66/phapluat_detail_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"Saved detail screenshot to {screenshot_path}")
            
            # Dump HTML of detail page
            html = await page.content()
            with open("scratch/phapluat_detail.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved detail HTML to scratch/phapluat_detail.html")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
