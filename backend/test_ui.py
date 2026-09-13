import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Testing Signup Page")
        await page.goto("http://localhost:5173/signup")
        await asyncio.sleep(1)
        await page.fill('input[type="email"]', 'testuser4@example.com')
        await page.fill('input[type="password"]', 'testpass')
        await page.click('button[type="submit"]')
        await asyncio.sleep(2)
        print("Signup Output:", await page.evaluate("document.body.innerText"))
        
        pages = [
            "/app",
            "/app/markets",
            "/app/portfolio",
            "/app/signals",
            "/app/positions",
            "/app/trades",
            "/app/performance",
            "/app/risk",
            "/app/settings",
            "/app/research",
        ]
        
        for path in pages:
            print(f"\n--- {path} ---")
            await page.goto(f"http://localhost:5173{path}")
            await asyncio.sleep(2)
            content = await page.evaluate("document.body.innerText")
            print(content[:500] if len(content) > 500 else content)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
