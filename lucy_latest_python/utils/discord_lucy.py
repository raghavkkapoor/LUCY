import asyncio
from playwright.async_api import async_playwright

async def _send_message_async(recipient: str, message: str):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9223")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to browser on port 9223: {e}")

        target_page = None
        
        for context in browser.contexts:
            for page in context.pages:
                url = page.url
                if "gemini/app" in url or "/usage" in url:
                    continue
                if "discord.com" in url:
                    target_page = page
                    break
            if target_page:
                break

        if not target_page:
            if browser.contexts:
                context = browser.contexts[0]
                target_page = await context.new_page()
                await target_page.goto("https://discord.com/channels/@me")
            else:
                raise RuntimeError("No browser contexts found.")

        await target_page.bring_to_front()
        
        try:
            await target_page.wait_for_selector("div[class*='app']", timeout=5000)
        except Exception:
            current_url = target_page.url
            if "login" in current_url or "register" in current_url:
                raise RuntimeError("Discord is not logged in. Please log into Discord in the browser first.")
            await target_page.goto("https://discord.com/channels/@me")
            try:
                await target_page.wait_for_selector("div[class*='app']", timeout=10000)
            except Exception:
                raise RuntimeError("Discord login check failed. App container not found.")

        try:
            await target_page.keyboard.press("Control+KeyK")
        except Exception:
            await target_page.keyboard.press("Meta+KeyK")

        search_input = target_page.locator("input[placeholder*='Where would you like to go']")
        await search_input.wait_for(state="visible", timeout=5000)
        
        await search_input.fill(recipient)
        await target_page.wait_for_timeout(1000)
        
        await search_input.press("Enter")
        await target_page.wait_for_timeout(1500)

        chat_input = target_page.locator("div[role='textbox'][aria-label*='Message']")
        await chat_input.wait_for(state="visible", timeout=5000)
        
        await chat_input.click()
        await target_page.keyboard.type(message, delay=50)
        await target_page.keyboard.press("Enter")

def send_discord_message(recipient: str, message: str) -> None:
    """Connects to the existing Playwright instance on port 9223, verifies Discord login,
    skips restricted tabs, and sends a message to the specified recipient.
    Enforces a strict 2-minute physical timeout.
    """
    asyncio.run(asyncio.wait_for(_send_message_async(recipient, message), timeout=120.0))
