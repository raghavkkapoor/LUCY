"""Reusable Photopea Playwright helpers.

connect(cdp_port=9223):
    Connect to Lucy's existing Chromium browser.

find_photopea(context):
    Return the existing Photopea page.

enter_editor(page):
    Click a visible Start using Photopea button.

new_project(page):
    Open New Project and click the real Create button.

inspect(page):
    Return compact editor state.

rectangle_test(page, width=50, height=35):
    Select the rectangle tool and make a small test shape.

LLM usage:
    Compose these functions instead of dumping the DOM. Prefer semantic
    controls and compact verification to keep automation output small.
"""

def connect(cdp_port=9223):
    pw = __import__("playwright.sync_api", fromlist=["sync_playwright"])
    return pw.sync_playwright()

def find_photopea(context):
    return next(
        (p for p in context.pages if "photopea.com" in p.url.lower()),
        None
    )

def enter_editor(page):
    buttons = page.get_by_role(
        "button",
        name="Start using Photopea"
    )
    for i in range(buttons.count()):
        b = buttons.nth(i)
        try:
            box = b.bounding_box()
            if box and box["width"] > 0 and box["height"] > 0:
                b.click(timeout=5000)
                page.wait_for_timeout(2500)
                return True
        except Exception:
            pass
    return False

def new_project(page):
    page.get_by_role("button", name="Create").first.click(timeout=3000)
    page.wait_for_timeout(1000)
    return page.evaluate(
        "() => document.querySelectorAll('canvas').length > 0"
    )

def inspect(page):
    return page.evaluate("""() => ({
        url: location.href,
        canvas: document.querySelectorAll("canvas").length,
        sizes: [...document.querySelectorAll("canvas")]
            .map(c => [c.width, c.height])
    })""")

def rectangle_test(page, width=50, height=35):
    canvas = page.locator("canvas").first
    box = canvas.bounding_box()
    if not box:
        return False
    page.keyboard.press("U")
    page.mouse.move(box["x"] + 20, box["y"] + 20)
    page.mouse.down()
    page.mouse.move(
        box["x"] + 20 + width,
        box["y"] + 20 + height,
        steps=4
    )
    page.mouse.up()
    return True
