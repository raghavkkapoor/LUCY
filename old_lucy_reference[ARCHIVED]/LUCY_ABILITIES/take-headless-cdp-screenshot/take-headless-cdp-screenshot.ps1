$ErrorActionPreference = "Stop"

$port = 9333
$screenshot = Join-Path $env:TEMP "lucy_headless_9333_current_page.png"
$pyPath = Join-Path $env:TEMP "lucy_take_headless_screenshot.py"

Invoke-RestMethod "http://127.0.0.1:$port/json/version" -TimeoutSec 3 | Out-Null

@"
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9333")
        pages = [page for context in browser.contexts for page in context.pages]

        if not pages:
            raise RuntimeError("No page exists.")

        page = pages[-1]
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass

        await page.screenshot(
            path=r"$screenshot",
            full_page=False
        )

        print("PAGE_URL=" + page.url)
        print("PAGE_TITLE=" + await page.title())
        print("SCREENSHOT=" + r"$screenshot")

asyncio.run(main())
"@ | Set-Content $pyPath -Encoding UTF8

& python $pyPath
if ($LASTEXITCODE -ne 0) { throw "Screenshot failed." }

if (-not (Test-Path $screenshot)) { throw "Screenshot missing." }

Start-Process $screenshot
Write-Output "SCREENSHOT_EXISTS=True"
Write-Output "SCREENSHOT=$screenshot"
