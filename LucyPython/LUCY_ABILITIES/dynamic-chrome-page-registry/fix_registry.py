from pathlib import Path
import re

path = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\main.py")
text = path.read_text(encoding="utf-8-sig")

marker = "LUCY_DYNAMIC_BROWSER_REGISTRY_V2"

registry = r'''
# LUCY_DYNAMIC_BROWSER_REGISTRY_V2
_PAGE_REGISTRY = {}
_TRACKED_CONTEXT_IDS = set()
_PAGE_REGISTRY_LOCK = threading.Lock()
_BROWSER_CDP_SESSION = None


def _page_key(page):
    return id(page)


def _remove_page(key):
    with _PAGE_REGISTRY_LOCK:
        _PAGE_REGISTRY.pop(key, None)


def _register_page(page):
    key = _page_key(page)

    with _PAGE_REGISTRY_LOCK:
        _PAGE_REGISTRY[key] = page

    try:
        page.on("close", lambda: _remove_page(key))
    except Exception:
        pass

    return page


def _track_context(context):
    context_key = id(context)

    if context_key not in _TRACKED_CONTEXT_IDS:
        _TRACKED_CONTEXT_IDS.add(context_key)
        try:
            context.on("page", _register_page)
        except Exception:
            pass

    try:
        for existing_page in context.pages:
            _register_page(existing_page)
    except Exception:
        pass


def _ensure_browser_cdp_session(browser):
    global _BROWSER_CDP_SESSION

    if _BROWSER_CDP_SESSION is not None:
        return _BROWSER_CDP_SESSION

    _BROWSER_CDP_SESSION = browser.new_browser_cdp_session()

    try:
        _BROWSER_CDP_SESSION.send(
            "Target.setDiscoverTargets",
            {"discover": True}
        )
    except Exception:
        pass

    return _BROWSER_CDP_SESSION


def raw_browser_targets(browser):
    """
    Browser-process-wide target inventory.

    Unlike context.pages, Target.getTargets can see Chrome targets that
    exist at the browser level even if Playwright has not materialized
    them into Page objects yet.
    """
    session = _ensure_browser_cdp_session(browser)

    try:
        result = session.send("Target.getTargets")
    except Exception:
        return []

    targets = []

    for info in result.get("targetInfos", []):
        target_type = info.get("type", "")

        if target_type not in ("page", "webview"):
            continue

        targets.append({
            "target_id": info.get("targetId", ""),
            "type": target_type,
            "title": info.get("title", ""),
            "url": info.get("url", ""),
            "attached": bool(info.get("attached", False)),
            "browser_context_id": info.get("browserContextId", ""),
        })

    return targets


def refresh_page_registry(browser):
    active_keys = set()

    try:
        contexts = list(browser.contexts)
    except Exception:
        contexts = []

    for browser_context in contexts:
        _track_context(browser_context)

        try:
            pages = list(browser_context.pages)
        except Exception:
            pages = []

        for browser_page in pages:
            try:
                if browser_page.is_closed():
                    continue
            except Exception:
                continue

            key = _page_key(browser_page)
            active_keys.add(key)

            with _PAGE_REGISTRY_LOCK:
                _PAGE_REGISTRY[key] = browser_page

    with _PAGE_REGISTRY_LOCK:
        for key in list(_PAGE_REGISTRY):
            if key not in active_keys:
                _PAGE_REGISTRY.pop(key, None)

        return list(_PAGE_REGISTRY.values())


def all_pages(browser):
    """
    Live Playwright Page objects across every CDP-visible context.
    """
    return refresh_page_registry(browser)


def browser_target_snapshot(browser):
    """
    Complete browser-process-level inventory of tabs/windows.

    Combines Playwright pages with raw CDP targets and de-duplicates by
    URL/title where possible. Raw target_id remains available so Lucy can
    later address a target directly through CDP when needed.
    """
    snapshot = []
    seen = set()

    for index, browser_page in enumerate(all_pages(browser), start=1):
        try:
            if browser_page.is_closed():
                continue
        except Exception:
            continue

        try:
            title = browser_page.title()
        except Exception:
            title = ""

        try:
            url = browser_page.url
        except Exception:
            url = ""

        key = ("page", url, title)

        if key in seen:
            continue

        seen.add(key)

        snapshot.append({
            "source": "playwright",
            "index": index,
            "title": title,
            "url": url,
            "target_id": "",
            "page": browser_page,
        })

    for target in raw_browser_targets(browser):
        title = target.get("title", "")
        url = target.get("url", "")

        # If this target is already represented by a Playwright Page,
        # enrich the existing entry with its browser target id.
        matching = None
        for item in snapshot:
            if (
                item["source"] == "playwright"
                and item["url"] == url
                and item["title"] == title
            ):
                matching = item
                break

        if matching is not None:
            matching["target_id"] = target.get("target_id", "")
            continue

        snapshot.append({
            "source": "cdp",
            "index": len(snapshot) + 1,
            "title": title,
            "url": url,
            "target_id": target.get("target_id", ""),
            "page": None,
        })

    return snapshot


def browser_page_snapshot(browser):
    """
    Serializable view of every Chrome tab/window target Lucy can see.
    """
    result = []

    for item in browser_target_snapshot(browser):
        result.append({
            "source": item["source"],
            "index": item["index"],
            "title": item["title"],
            "url": item["url"],
            "target_id": item["target_id"],
        })

    return result


def find_lucy_page(browser):
    for browser_page in all_pages(browser):
        try:
            if browser_page.url.startswith(LUCY_URL):
                return browser_page
        except Exception:
            pass

    return None


def install_page_tracking(browser):
    for browser_context in list(browser.contexts):
        _track_context(browser_context)

    _ensure_browser_cdp_session(browser)
    pages = refresh_page_registry(browser)
    targets = raw_browser_targets(browser)

    print(
        f"{GREEN}LUCY_DYNAMIC_BROWSER_REGISTRY_READY=True "
        f"PAGES={len(pages)} TARGETS={len(targets)}{RESET}"
    )


'''

m = re.search(r'(?m)^def connect_to_lucy\(p\):\s*$', text)
if not m:
    raise RuntimeError("connect_to_lucy(p) not found")

text = text[:m.start()] + registry + "\n" + text[m.start():]

start = text.find("def connect_to_lucy(p):")
end_match = re.search(
    r'(?m)^def is_target_closed_error\(error\):\s*$',
    text[start:]
)

if not end_match:
    raise RuntimeError("Could not locate connect_to_lucy end")

end = start + end_match.start()
block = text[start:end]

pattern = re.compile(
    r'(\n[ \t]+if not browser\.contexts:\s*\n'
    r'[ \t]+raise RuntimeError\("No Chrome browser context found\."\)\s*\n)',
    re.M
)

block, n = pattern.subn(
    r'\1\n    install_page_tracking(browser)\n',
    block,
    count=1
)

if n != 1:
    raise RuntimeError("Could not insert install_page_tracking")

block, n = re.subn(
    r'for existing_page in context\.pages:',
    'for existing_page in all_pages(browser):',
    block,
    count=1
)

if n != 1:
    raise RuntimeError("Could not replace Lucy page enumeration")

text = text[:start] + block + text[end:]

required = [
    marker,
    "def raw_browser_targets(browser):",
    "def browser_target_snapshot(browser):",
    "def all_pages(browser):",
    'Target.getTargets',
    'Target.setDiscoverTargets',
    "install_page_tracking(browser)",
    "for existing_page in all_pages(browser):",
]

missing = [item for item in required if item not in text]

if missing:
    raise RuntimeError("Missing markers: " + ", ".join(missing))

path.write_text(text, encoding="utf-8")

print("V2_PATCH_WRITE_OK=True")
print("V2_PATCH_MARKERS_OK=True")
