$ErrorActionPreference = "Stop"

$work = Join-Path $env:TEMP "lucy_hawken_mechs"
New-Item -ItemType Directory -Path $work -Force | Out-Null
$env:LUCY_HAWKEN_OUT = $work

$py = @"
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import os, time, glob

OUT = os.environ["LUCY_HAWKEN_OUT"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    context = browser.contexts[0]

    search = context.new_page()
    search.goto(
        "https://www.google.com/search?tbm=isch&q=Hawken+game+mechs",
        wait_until="domcontentloaded",
        timeout=30000
    )
    time.sleep(4)

    saved = []
    imgs = search.locator("img")

    for i in range(imgs.count()):
        if len(saved) >= 5:
            break
        try:
            img = imgs.nth(i)
            box = img.bounding_box()
            src = img.get_attribute("src") or ""
            if not box or box["width"] < 140 or box["height"] < 100 or not src:
                continue

            path = os.path.join(OUT, f"hawken_mech_{len(saved)+1}.png")
            img.screenshot(path=path)

            if os.path.getsize(path) > 5000:
                saved.append(path)
            else:
                os.remove(path)
        except:
            pass

    if len(saved) < 3:
        raise RuntimeError("Could not capture enough Hawken mech images.")

    gmail = None
    for pg in context.pages:
        if "mail.google.com" in pg.url:
            gmail = pg
            break

    if gmail is None:
        gmail = context.new_page()
        try:
            gmail.goto(
                "https://mail.google.com/mail/u/0/#inbox",
                wait_until="commit",
                timeout=15000
            )
        except PlaywrightTimeout:
            pass

    gmail.wait_for_selector('div[role="main"], div[gh="cm"]', timeout=30000)

    compose = gmail.locator('div[gh="cm"]')
    if compose.count() == 0:
        compose = gmail.get_by_text("Compose", exact=True)

    compose.first.click()
    gmail.wait_for_selector('input[name="subjectbox"]', timeout=15000)

    to = gmail.locator(
        'input[aria-label="To recipients"], input[role="combobox"][aria-autocomplete="list"]'
    ).last

    to.fill("raghavkkapoor7@gmail.com")
    to.press("Enter")

    gmail.locator('input[name="subjectbox"]').last.fill("Hawken mech pictures")
    gmail.locator('div[aria-label="Message Body"]').last.fill(
        "Here are some pictures of mechs from HAWKEN."
    )

    gmail.locator('input[type="file"]').last.set_input_files(saved)
    time.sleep(4)

    send = gmail.locator(
        'div[role="button"][data-tooltip^="Send"], div[role="button"][aria-label^="Send"]'
    ).last

    send.wait_for(state="visible", timeout=15000)
    send.click()

    confirmed = False
    for _ in range(30):
        time.sleep(0.5)
        if gmail.get_by_text("Message sent", exact=False).count() > 0:
            confirmed = True
            break

    search.close()

    if not confirmed:
        raise RuntimeError("Gmail did not confirm Message sent.")

    print("MESSAGE_SENT=True")
"@

$tmp = Join-Path $work "run.py"
Set-Content $tmp $py -Encoding UTF8

python $tmp

if ($LASTEXITCODE -ne 0) {
    throw "Hawken email workflow failed."
}
