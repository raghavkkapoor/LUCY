from pathlib import Path
import re
import sys

path = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython\main.py")
text = path.read_text(encoding="utf-8-sig")

MARKER = "LUCY_DYNAMIC_PAGE_REGISTRY_V1"

registry = r'''
# LUCY_DYNAMIC_PAGE_REGISTRY_V1
_PAGE_REGISTRY = {}
_TRACKED_CONTEXT_IDS = set()
_PAGE_REGISTRY_LOCK = threading.Lock()


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
        stale_keys = [
            key for key in list(_PAGE_REGISTRY)
            if key not in active_keys
        ]

        for key in stale_keys:
            _PAGE_REGISTRY.pop(key, None)

        return list(_PAGE_REGISTRY.values())


def all_pages(browser):
    """Return all currently-live tabs/pages in every CDP-visible context."""
    return refresh_page_registry(browser)


def browser_page_snapshot(browser):
    snapshot = []

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

        snapshot.append({
            "index": index,
            "title": title,
            "url": url,
        })

    return snapshot


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

    pages = refresh_page_registry(browser)

    print(
        f"{GREEN}LUCY_DYNAMIC_PAGE_REGISTRY_READY=True "
        f"PAGES={len(pages)}{RESET}"
    )


'''

if MARKER not in text:
    match = re.search(r'(?m)^def connect_to_lucy\(p\):\s*$', text)
    if not match:
        raise RuntimeError("connect_to_lucy(p) function was not found")

    text = text[:match.start()] + registry + "\n" + text[match.start():]

# Replace only connect_to_lucy's old single-context discovery section.
start = text.find("def connect_to_lucy(p):")
if start < 0:
    raise RuntimeError("connect_to_lucy(p) disappeared")

end_match = re.search(r'(?m)^def is_target_closed_error\(error\):\s*$', text[start:])
if not end_match:
    raise RuntimeError("Could not locate end of connect_to_lucy")

end = start + end_match.start()
block = text[start:end]

# Install tracking immediately after browser context validation.
if "install_page_tracking(browser)" not in block:
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
        raise RuntimeError(
            "Could not locate browser.contexts validation block. "
            "No changes written."
        )

# Make Lucy-page lookup dynamic across every tracked context/page.
block = re.sub(
    r'for existing_page in context\.pages:',
    'for existing_page in all_pages(browser):',
    block,
    count=1
)

# If the source still has the old lookup and replacement didn't happen,
# fail rather than write a half-patch.
if "for existing_page in context.pages:" in block:
    raise RuntimeError("Old context.pages Lucy lookup remains")

text = text[:start] + block + text[end:]

required = [
    "LUCY_DYNAMIC_PAGE_REGISTRY_V1",
    "def all_pages(browser):",
    'context.on("page", _register_page)',
    "install_page_tracking(browser)",
    "for existing_page in all_pages(browser):",
]

missing = [x for x in required if x not in text]
if missing:
    raise RuntimeError("Missing patch markers: " + ", ".join(missing))

path.write_text(text, encoding="utf-8")

print("PATCH_WRITE_OK=True")
print("PATCH_MARKERS_OK=True")
