param(
    [Parameter(Mandatory=$true)]
    [string]$Title,

    [int]$CdpPort = 9223
)

$ErrorActionPreference = "Stop"

$env:LUCY_DOC_TITLE = $Title
$env:LUCY_CDP_PORT = "$CdpPort"

$py = @"
from playwright.sync_api import sync_playwright
import os, time

title_text = os.environ["LUCY_DOC_TITLE"]
port = os.environ["LUCY_CDP_PORT"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    context = browser.contexts[0]
    cdp = browser.new_browser_cdp_session()

    result = cdp.send("Target.createTarget", {
        "url": "https://docs.new",
        "newWindow": True
    })

    target_id = result["targetId"]
    doc = None

    for _ in range(80):
        for page in context.pages:
            try:
                if "docs.google.com" not in page.url:
                    continue

                info = cdp.send(
                    "Target.getTargetInfo",
                    {"targetId": target_id}
                )["targetInfo"]

                if info.get("targetId") == target_id:
                    doc = page
                    break
            except Exception:
                pass

        if doc:
            break

        time.sleep(0.25)

    if doc is None:
        docs_pages = [p for p in context.pages if "docs.google.com" in p.url]
        if docs_pages:
            doc = docs_pages[-1]

    if doc is None:
        raise RuntimeError("Could not locate new Google Docs window.")

    doc.wait_for_timeout(3000)

    selectors = [
        ".docs-title-input",
        'input[aria-label="Rename"]',
        'input[aria-label*="document name" i]'
    ]

    title = None

    for selector in selectors:
        loc = doc.locator(selector)
        if loc.count() > 0:
            title = loc.first
            break

    if title is None:
        raise RuntimeError("Google Docs title field was not found.")

    title.wait_for(state="visible", timeout=30000)
    title.click()
    title.fill(title_text)
    title.press("Enter")
    doc.wait_for_timeout(1500)

    actual = title.input_value().strip()

    if actual != title_text:
        raise RuntimeError(
            f"Title verification failed: expected {title_text!r}, got {actual!r}"
        )

    print("DOC_CREATED=True")
    print("DOC_TITLE=" + actual)
    print("DOC_URL=" + doc.url)
"@

$tmp = Join-Path $env:TEMP "lucy-create-google-doc.py"
Set-Content -Path $tmp -Value $py -Encoding UTF8

python $tmp

if ($LASTEXITCODE -ne 0) {
    throw "Google Doc creation failed."
}
