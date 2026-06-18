import asyncio
import os
from playwright.async_api import async_playwright

async def dump_luatvietnam():
    url = "https://luatvietnam.vn/van-ban-moi.html"
    print(f"Fetching {url}...")
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
            screenshot_path = "/Users/tonguyen/.gemini/antigravity-ide/brain/4dd346af-f3c4-4d23-b284-13cea384cf66/luatvietnam_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"Saved screenshot to {screenshot_path}")
            
            # Get some HTML snippets
            html = await page.content()
            with open("scratch/luatvietnam.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved HTML to scratch/luatvietnam.html")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

async def dump_phapluat():
    url = "https://phapluat.gov.vn/he-thong-van-ban-phap-luat"
    print(f"Fetching {url}...")
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
            screenshot_path = "/Users/tonguyen/.gemini/antigravity-ide/brain/4dd346af-f3c4-4d23-b284-13cea384cf66/phapluat_screenshot.png"
            await page.screenshot(path=screenshot_path)
            print(f"Saved screenshot to {screenshot_path}")
            
            # Get HTML
            html = await page.content()
            with open("scratch/phapluat.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved HTML to scratch/phapluat.html")
            
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

async def main():
    await dump_luatvietnam()
    await dump_phapluat()

if __name__ == "__main__":
    asyncio.run(main())
