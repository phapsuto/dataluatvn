"""
discover_api5.py — Test xem slug có cần chính xác không, 
và extract HTML content từ trang văn bản
"""
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Test 1: Slug chính xác
        print("=" * 70)
        print("TEST 1: Slug chính xác + ItemID 96122")
        url1 = "https://vbpl.vn/van-ban/chi-tiet/bo-luat-hinh-su-so-100-2015-qh13--96122"
        await page.goto(url1, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        title1 = await page.title()
        print(f"  Title: {title1}")
        has_content1 = "Văn bản không tồn tại" not in await page.inner_text("body")
        print(f"  Has content: {has_content1}")

        # Test 2: Slug giả + ItemID 96122
        print("\nTEST 2: Slug giả 'doc' + ItemID 96122")
        url2 = "https://vbpl.vn/van-ban/chi-tiet/doc--96122"
        await page.goto(url2, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        title2 = await page.title()
        print(f"  Title: {title2}")
        has_content2 = "Văn bản không tồn tại" not in await page.inner_text("body")
        print(f"  Has content: {has_content2}")

        # Test 3: Chỉ ItemID, không slug
        print("\nTEST 3: Chỉ ItemID, không slug")
        url3 = "https://vbpl.vn/van-ban/chi-tiet/96122"
        await page.goto(url3, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        title3 = await page.title()
        print(f"  Title: {title3}")
        has_content3 = "Văn bản không tồn tại" not in await page.inner_text("body")
        print(f"  Has content: {has_content3}")

        # Test 4: Test với 1 document thiếu content (ID nhỏ, thường là văn bản cũ)
        print("\nTEST 4: Test với ID 1720 (thiếu content)")
        url4 = "https://vbpl.vn/van-ban/chi-tiet/doc--1720"
        await page.goto(url4, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        title4 = await page.title()
        print(f"  Title: {title4}")
        body4 = await page.inner_text("body")
        has_content4 = "Văn bản không tồn tại" not in body4
        print(f"  Has content: {has_content4}")
        if has_content4:
            print(f"  Body preview: {body4[:300]}")

        # Nếu test thành công, thử extract HTML content 
        working_url = None
        if has_content1:
            working_url = url1
        elif has_content2:
            working_url = url2
        elif has_content3:
            working_url = url3

        if working_url:
            print(f"\n{'=' * 70}")
            print(f"✅ URL pattern works! Navigating to: {working_url}")
            print(f"{'=' * 70}")
            await page.goto(working_url, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # Tìm tab "Toàn văn" và click
            tabs = await page.locator("[role='tab'], [class*='tab'], button").all()
            for tab in tabs:
                text = await tab.inner_text()
                if "toàn văn" in text.lower() or "nội dung" in text.lower() or "full" in text.lower():
                    print(f"  Found tab: {text}")
                    await tab.click()
                    await page.wait_for_timeout(3000)
                    break

            # Extract content
            # Try various selectors for the content area
            content_html = None
            for selector in [
                "[class*='ContentTab']", "[class*='content-tab']",
                "[class*='fullText']", "[class*='full-text']", 
                "[class*='toanvan']", "[class*='toan-van']",
                ".content-html", "article", 
                "[class*='DetailContent']", "[class*='detail-content']",
                "main",
            ]:
                el = page.locator(selector).first
                if await el.count() > 0:
                    content_html = await el.inner_html()
                    if len(content_html) > 100:
                        print(f"\n📝 Content found via '{selector}' ({len(content_html)} chars)")
                        print(f"   Preview: {content_html[:300]}...")
                        break
                    content_html = None

            if not content_html:
                # Fallback: get the whole page content
                content_html = await page.inner_html("body")
                print(f"\n📝 Fallback: got body HTML ({len(content_html)} chars)")
            
            # Save content for inspection
            with open("sample_content.html", "w", encoding="utf-8") as f:
                f.write(content_html)
            print(f"\n💾 Content saved to sample_content.html")

        await browser.close()

asyncio.run(main())
