#!/usr/bin/env python3
"""
Playwright script to navigate the dashboard, click Research → Contributing,
and capture screenshots. Run with: python scripts/browser_screenshot_research.py

Requires: pip install playwright && playwright install chromium
"""
import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Install Playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        try:
            # 1. Navigate
            print("Navigating to http://127.0.0.1:8000...")
            await page.goto("http://127.0.0.1:8000", wait_until="networkidle")
            await asyncio.sleep(10)
            print("Waited 10s for data to load.")

            # 2. Click Research tab
            research_btn = page.locator('button[data-tab="research"]')
            await research_btn.click()
            await asyncio.sleep(3)
            print("Clicked Research tab, waited 3s.")
            await page.screenshot(path="screenshot_research_tab.png")
            print("Saved screenshot_research_tab.png")

            # 3. Click Contributing subtab
            contributing_btn = page.locator('button[data-subtab="contributing"]')
            await contributing_btn.click()
            await asyncio.sleep(2)
            print("Clicked Contributing subtab, waited 2s.")
            await page.screenshot(path="screenshot_contributing_tab.png")
            print("Saved screenshot_contributing_tab.png")

        finally:
            await browser.close()

    print("\nDone. Check screenshot_research_tab.png and screenshot_contributing_tab.png")


if __name__ == "__main__":
    asyncio.run(main())
