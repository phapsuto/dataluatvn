import asyncio
import re
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
            
            # Find detail content div
            content_div = soup.find(class_="tab-noi-dung") or soup.find(class_="tab-content")
            if not content_div:
                print("Could not find content div!")
                return
                
            text = content_div.get_text()
            print(f"Content length: {len(text)}")
            
            # Search for watermarks/copyright lines in the content
            lines = text.split("\n")
            watermark_lines = []
            for i, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue
                # Watermark patterns
                if any(kw in line_str.lower() for kw in ["luatvietnam", "bản quyền", "copy", "tất cả các quyền", "tổng đài 1900"]):
                    watermark_lines.append((i, line_str))
                    
            print(f"\nFound {len(watermark_lines)} lines containing watermark keywords:")
            for idx, line in watermark_lines[:15]:
                print(f"  Line {idx}: {line[:120]}")
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
