import importlib.util
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

MAIN = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\main.py")
CDP = "http://127.0.0.1:9223"

spec = importlib.util.spec_from_file_location("lucy_v2_test", MAIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP, no_defaults=True)

    if not browser.contexts:
        raise RuntimeError("No browser contexts")

    mod.install_page_tracking(browser)

    before = mod.browser_page_snapshot(browser)
    context = browser.contexts[0]

    # ----------------------------------------------------------
    # TEST A: ordinary new tab -> must become Playwright Page.
    # ----------------------------------------------------------
    tab = context.new_page()
    tab.goto(
        "data:text/html,<title>LUCY_V2_TAB_TEST</title><h1>tab</h1>",
        wait_until="domcontentloaded",
    )

    time.sleep(0.5)

    tab_snapshot = mod.browser_page_snapshot(browser)

    tab_seen = any(
        item["title"] == "LUCY_V2_TAB_TEST"
        for item in tab_snapshot
    )

    tab_as_playwright = any(
        item["title"] == "LUCY_V2_TAB_TEST"
        and item["source"] == "playwright"
        for item in tab_snapshot
    )

    # ----------------------------------------------------------
    # TEST B: true Chrome-level separate window.
    # This is the exact scenario that failed before.
    # ----------------------------------------------------------
    session = browser.new_browser_cdp_session()

    created = session.send(
        "Target.createTarget",
        {
            "url": "data:text/html,<title>LUCY_V2_WINDOW_TEST</title><h1>window</h1>",
            "newWindow": True,
        },
    )

    target_id = created["targetId"]

    window_seen = False
    window_source = ""
    window_item = None

    deadline = time.time() + 5.0

    while time.time() < deadline:
        snapshot = mod.browser_page_snapshot(browser)

        for item in snapshot:
            if (
                item["target_id"] == target_id
                or item["title"] == "LUCY_V2_WINDOW_TEST"
                or "LUCY_V2_WINDOW_TEST" in item["url"]
            ):
                window_seen = True
                window_source = item["source"]
                window_item = item
                break

        if window_seen:
            break

        time.sleep(0.2)

    # We do NOT require Playwright to materialize it.
    # Raw browser-level CDP awareness is sufficient to prove Lucy sees it.
    chatgpt_seen = any(
        "chatgpt.com" in item["url"]
        for item in mod.browser_page_snapshot(browser)
    )

    raw_target_seen = any(
        target["target_id"] == target_id
        for target in mod.raw_browser_targets(browser)
    )

    print(f"INITIAL_TARGET_COUNT={len(before)}")
    print(f"NEW_TAB_DISCOVERED={tab_seen}")
    print(f"NEW_TAB_IS_PLAYWRIGHT_PAGE={tab_as_playwright}")
    print(f"NEW_WINDOW_DISCOVERED={window_seen}")
    print(f"NEW_WINDOW_SOURCE={window_source}")
    print(f"RAW_CDP_WINDOW_TARGET_DISCOVERED={raw_target_seen}")
    print(f"EXISTING_CHATGPT_PRESERVED={chatgpt_seen}")
    print(f"NEW_WINDOW_TARGET_ID={target_id}")

    # Cleanup.
    try:
        tab.close()
    except Exception:
        pass

    try:
        session.send(
            "Target.closeTarget",
            {"targetId": target_id}
        )
    except Exception:
        pass

    time.sleep(0.5)

    cleaned = mod.browser_page_snapshot(browser)

    test_targets_left = [
        item for item in cleaned
        if (
            item["title"] in ("LUCY_V2_TAB_TEST", "LUCY_V2_WINDOW_TEST")
            or "LUCY_V2_TAB_TEST" in item["url"]
            or "LUCY_V2_WINDOW_TEST" in item["url"]
        )
    ]

    cleanup_ok = len(test_targets_left) == 0

    print(f"CLOSED_TEST_TARGETS_REMOVED={cleanup_ok}")

    if not tab_seen:
        raise RuntimeError("Normal new tab not discovered")

    if not tab_as_playwright:
        raise RuntimeError("Normal new tab was not represented as Page")

    if not window_seen:
        raise RuntimeError("Separate Chrome window not discovered")

    if not raw_target_seen:
        raise RuntimeError("Separate window missing from raw CDP target inventory")

    if not chatgpt_seen:
        raise RuntimeError("Lucy ChatGPT target disappeared")

    if not cleanup_ok:
        raise RuntimeError("Closed test targets remained visible")

    print("DYNAMIC_MULTIWINDOW_TEST_PASSED=True")
