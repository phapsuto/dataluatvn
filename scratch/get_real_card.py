import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        print("Navigating...")
        await page.goto("https://vbpl.vn/van-ban/trung-uong", wait_until="domcontentloaded", timeout=30000)
        
        try:
            # wait for actual card (no skeleton)
            await page.wait_for_selector('[class*="documentCard"]:not(:has(.ant-skeleton)), [class*="DocumentCard"]:not(:has(.ant-skeleton))', timeout=15000)
        except Exception as e:
            print("Timeout waiting for real card")
            
        card_html = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll('[class*="documentCard"], [class*="DocumentCard"]');
            for(const c of cards) {
                if(!c.querySelector('.ant-skeleton')) return c.outerHTML;
            }
            return "No real card found";
        }
        """)
        with open("real_card.html", "w", encoding="utf-8") as f:
            f.write(card_html)
        print("Done")
        await browser.close()

asyncio.run(run())
