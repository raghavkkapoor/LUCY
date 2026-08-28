param(
    [Parameter(Mandatory=$true)]
    [string]$Title,

    [Parameter(Mandatory=$true)]
    [string]$Text,

    [int]$CdpPort = 9223
)

$ErrorActionPreference = "Stop"

$env:LUCY_DOC_TITLE = $Title
$env:LUCY_DOC_TEXT = $Text
$env:LUCY_CDP_PORT = "$CdpPort"

$py = @"
from playwright.sync_api import sync_playwright
import os

wanted_title = os.environ["LUCY_DOC_TITLE"]
text = os.environ["LUCY_DOC_TEXT"]
port = os.environ["LUCY_CDP_PORT"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    context = browser.contexts[0]

    docs = []
    for page in context.pages:
        try:
            if "docs.google.com/document/" in page.url and wanted_title.lower() in page.title().lower():
                docs.append(page)
        except Exception:
            pass

    if not docs:
        raise RuntimeError(f"Opened Google Doc not found: {wanted_title}")

    doc = docs[-1]
    doc.bring_to_front()

    editor = doc.locator(".kix-appview-editor")
    if editor.count() == 0:
        editor = doc.locator(".docs-editor")
    if editor.count() == 0:
        raise RuntimeError("Google Docs editor surface not found.")

    editor.first.click(position={"x":250,"y":180})
    doc.keyboard.press("Control+A")
    doc.keyboard.insert_text(text)
    doc.wait_for_timeout(1200)

    doc.keyboard.press("Control+A")
    doc.keyboard.press("Control+C")
    doc.wait_for_timeout(400)

    copied = doc.evaluate("navigator.clipboard.readText()")
    verified = " ".join(text.split()) in " ".join(copied.split())
    doc.keyboard.press("ArrowRight")

    if not verified:
        raise RuntimeError("Document text verification failed.")

    print("DOC_UPDATED=True")
    print("TEXT_VERIFIED=True")
    print("DOC_URL=" + doc.url)
"@

$tmp = Join-Path $env:TEMP "lucy-write-google-doc-reusable.py"
Set-Content $tmp $py -Encoding UTF8
python $tmp

if ($LASTEXITCODE -ne 0) {
    throw "Google Doc update failed."
}
