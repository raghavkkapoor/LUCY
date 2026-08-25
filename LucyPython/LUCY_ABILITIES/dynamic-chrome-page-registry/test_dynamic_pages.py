import importlib.util
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

MAIN = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\main.py")
CDP = "http://127.0.0.1:9223"

spec = importlib.util.spec_from_file_location("lucy_dynamic_test", MAIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP, no_defaults=True)

    if not browser.contexts:
        raise RuntimeError("No browser contexts visible over CDP")

    mod.install_page_tracking(browser)

    before = mod.browser_page_snapshot(browser)
    context = browser.contexts[0]

    # New tab test.
    tab = context.new_page()
    tab.goto(
        "data:text/html,<title>LUCY_DYNAMIC_TAB_TEST</title><h1>Lucy tab test</h1>",
        wait_until="domcontentloaded",
    )

    time.sleep(0.5)

    tab_snapshot = mod.browser_page_snapshot(browser)
    tab_seen = any(
        item["title"] == "LUCY_DYNAMIC_TAB_TEST"
        for item in tab_snapshot
    )

    # Genuine separate browser window test through Chrome Target domain.
    session = browser.new_browser_cdp_session()
    result = session.send(
        "Target.createTarget",
        {
            "url": "data:text/html,<title>LUCY_DYNAMIC_WINDOW_TEST</title><h1>Lucy window test</h1>",
            "newWindow": True,
        },
    )

    target_id = result["targetId"]
    time.sleep(1.0)

    window_snapshot = mod.browser_page_snapshot(browser)
    window_seen = any(
        item["title"] == "LUCY_DYNAMIC_WINDOW_TEST"
        or "LUCY_DYNAMIC_WINDOW_TEST" in item["url"]
        for item in window_snapshot
    )

    chatgpt_seen = any(
        "chatgpt.com" in item["url"]
        for item in window_snapshot
    )

    # Verify registry heals dynamically rather than requiring restart.
    count_before_cleanup = len(window_snapshot)

    try:
        tab.close()
    except Exception:
        pass

    try:
        session.send("Target.closeTarget", {"targetId": target_id})
    except Exception:
        pass

    time.sleep(0.5)

    cleaned = mod.browser_page_snapshot(browser)
    cleanup_ok = not any(
        item["title"] in (
            "LUCY_DYNAMIC_TAB_TEST",
            "LUCY_DYNAMIC_WINDOW_TEST",
        )
        for item in cleaned
    )

    print(f"INITIAL_PAGE_COUNT={len(before)}")
    print(f"NEW_TAB_DISCOVERED={tab_seen}")
    print(f"NEW_WINDOW_DISCOVERED={window_seen}")
    print(f"EXISTING_CHATGPT_PRESERVED={chatgpt_seen}")
    print(f"TEST_PAGE_COUNT={count_before_cleanup}")
    print(f"CLOSED_TEST_PAGES_REMOVED={cleanup_ok}")

    if not tab_seen:
        raise RuntimeError("New tab was not dynamically discovered")

    if not window_seen:
        raise RuntimeError("New Chrome window was not dynamically discovered")

    if not chatgpt_seen:
        raise RuntimeError("Existing ChatGPT page was not preserved")

    if not cleanup_ok:
        raise RuntimeError("Closed test pages remained in dynamic registry")

    print("DYNAMIC_BROWSER_TEST_PASSED=True")
