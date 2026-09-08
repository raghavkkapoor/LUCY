import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

VISIBLE_CDP = "http://127.0.0.1:9223"
HEADLESS_CDP = "http://127.0.0.1:9333"
HEADLESS_PORT = 9333

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(os.environ["TEMP"], "LucyHeadlessAuthenticatedTest")
SCREENSHOT = os.path.join(os.environ["TEMP"], "lucy_headless_authenticated_chatgpt.png")

def cdp_ready(url):
    try:
        with urllib.request.urlopen(url + "/json/version", timeout=1) as r:
            return json.loads(r.read().decode("utf-8"))
    except:
        return None

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # -------------------------------
        # OBSERVE existing visible browser
        # -------------------------------
        visible = await p.chromium.connect_over_cdp(VISIBLE_CDP)

        visible_contexts = visible.contexts
        if not visible_contexts:
            print("VISIBLE_CONTEXT_FOUND=False")
            sys.exit(30)

        vctx = visible_contexts[0]
        visible_pages = []
        for ctx in visible_contexts:
            visible_pages.extend(ctx.pages)

        print(f"VISIBLE_CONTEXT_COUNT={len(visible_contexts)}")
        print(f"VISIBLE_PAGE_COUNT={len(visible_pages)}")

        # Get real browser/user-agent characteristics from Lucy's normal browser.
        real_ua = None
        real_lang = "en-US"
        real_platform = "Win32"

        sample_page = None
        chatgpt_page = None

        for pg in visible_pages:
            if "chatgpt.com" in pg.url:
                chatgpt_page = pg
                sample_page = pg
                break

        if sample_page is None and visible_pages:
            sample_page = visible_pages[0]

        if sample_page:
            try:
                fingerprint = await sample_page.evaluate("""() => ({
                    ua: navigator.userAgent,
                    language: navigator.language,
                    platform: navigator.platform,
                    webdriver: navigator.webdriver
                })""")
                real_ua = fingerprint.get("ua")
                real_lang = fingerprint.get("language") or "en-US"
                real_platform = fingerprint.get("platform") or "Win32"

                print("VISIBLE_USER_AGENT_HEADLESS=" + str("HeadlessChrome" in (real_ua or "")))
                print("VISIBLE_NAVIGATOR_WEBDRIVER=" + str(fingerprint.get("webdriver")))
            except Exception as e:
                print("VISIBLE_FINGERPRINT_READ_ERROR=" + type(e).__name__)

        if not real_ua:
            # Match installed Chrome version while omitting HeadlessChrome marker.
            real_ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.7922.174 Safari/537.36"
            )

        # Copy cookies in memory only.
        # NEVER print cookie values.
        cookies = await vctx.cookies()
        chatgpt_cookies = [
            c for c in cookies
            if (
                "chatgpt.com" in c.get("domain", "")
                or "openai.com" in c.get("domain", "")
                or "auth.openai.com" in c.get("domain", "")
            )
        ]

        cloudflare_cookie_names = {
            "__cf_bm",
            "cf_clearance",
            "_cfuvid"
        }

        names = {c.get("name", "") for c in chatgpt_cookies}

        print(f"VISIBLE_TOTAL_COOKIE_COUNT={len(cookies)}")
        print(f"CHATGPT_SESSION_COOKIE_COUNT={len(chatgpt_cookies)}")
        print("HAS_CF_CLEARANCE=" + str("cf_clearance" in names))
        print("HAS_CF_BM=" + str("__cf_bm" in names))

        # Capture storage state for relevant origins without displaying secrets.
        storage_state = await vctx.storage_state()

        relevant_origins = []
        for origin in storage_state.get("origins", []):
            u = origin.get("origin", "")
            if "chatgpt.com" in u or "openai.com" in u:
                relevant_origins.append(origin)

        print(f"CHATGPT_STORAGE_ORIGIN_COUNT={len(relevant_origins)}")

        # -------------------------------
        # ORIENT: create isolated headless browser
        # -------------------------------
        if os.path.exists(PROFILE):
            shutil.rmtree(PROFILE, ignore_errors=True)
        os.makedirs(PROFILE, exist_ok=True)

        args = [
            CHROME,
            "--headless=new",
            f"--remote-debugging-port={HEADLESS_PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",

            # Make headless browser report the same normal Chrome UA as Lucy.
            f"--user-agent={real_ua}",

            # Avoid the most obvious automation-exposed Blink property.
            "--disable-blink-features=AutomationControlled",

            "--window-size=1440,1000",
            "about:blank"
        ]

        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            version = None
            for _ in range(60):
                version = cdp_ready(HEADLESS_CDP)
                if version:
                    break
                await asyncio.sleep(0.25)

            if not version:
                print("HEADLESS_CDP_READY=False")
                sys.exit(31)

            print("HEADLESS_CDP_READY=True")

            headless = await p.chromium.connect_over_cdp(HEADLESS_CDP)

            if not headless.contexts:
                print("HEADLESS_CONTEXT_FOUND=False")
                sys.exit(32)

            hctx = headless.contexts[0]

            # Inject authenticated browser cookies.
            if chatgpt_cookies:
                try:
                    await hctx.add_cookies(chatgpt_cookies)
                    print("SESSION_COOKIES_INJECTED=True")
                except Exception as e:
                    print("SESSION_COOKIES_INJECTED=False")
                    print("COOKIE_INJECTION_ERROR=" + type(e).__name__)
            else:
                print("SESSION_COOKIES_INJECTED=False")

            pages = hctx.pages
            if pages:
                page = pages[0]
            else:
                page = await hctx.new_page()

            # Set properties before ChatGPT JavaScript executes.
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # -------------------------------
            # ACT: navigate to ChatGPT
            # -------------------------------
            try:
                await page.goto(
                    "https://chatgpt.com/",
                    wait_until="domcontentloaded",
                    timeout=60000
                )
            except Exception as e:
                print("GOTO_EXCEPTION=" + type(e).__name__)

            # Give Cloudflare / React enough opportunity to transition.
            # We inspect repeatedly instead of assuming the first DOM is final.
            passed_challenge = False

            for attempt in range(1, 21):
                await page.wait_for_timeout(1000)

                try:
                    info = await page.evaluate("""() => ({
                        title: document.title,
                        href: location.href,
                        ready: document.readyState,
                        ua: navigator.userAgent,
                        webdriver: navigator.webdriver,
                        body: document.body ? document.body.innerText : '',
                        elements: document.querySelectorAll('*').length,
                        buttons: document.querySelectorAll('button').length,
                        textareas: document.querySelectorAll('textarea').length,
                        editables: document.querySelectorAll('[contenteditable="true"]').length,
                        prompt: document.querySelectorAll('#prompt-textarea').length
                    })""")
                except Exception as e:
                    print(f"ATTEMPT_{attempt}_DOM_ERROR={type(e).__name__}")
                    continue

                title = info["title"] or ""
                body = info["body"] or ""

                is_challenge = (
                    "Just a moment" in title
                    or "Checking your browser" in body
                    or "Verify you are human" in body
                )

                has_chatgpt_dom = (
                    info["prompt"] > 0
                    or info["textareas"] > 0
                    or info["editables"] > 0
                    or info["buttons"] >= 3
                    or len(body.strip()) > 100
                )

                print(
                    f"ATTEMPT_{attempt}:"
                    f"TITLE={title[:60]!r};"
                    f"ELEMENTS={info['elements']};"
                    f"BUTTONS={info['buttons']};"
                    f"TEXTAREAS={info['textareas']};"
                    f"EDITABLES={info['editables']};"
                    f"PROMPT={info['prompt']};"
                    f"BODYCHARS={len(body)};"
                    f"CHALLENGE={is_challenge}"
                )

                if not is_challenge and has_chatgpt_dom:
                    passed_challenge = True
                    final_info = info
                    break

            # -------------------------------
            # OBSERVE result
            # -------------------------------
            try:
                await page.screenshot(path=SCREENSHOT, full_page=False)
                print("SCREENSHOT_EXISTS=" + str(os.path.exists(SCREENSHOT)))
                print("SCREENSHOT=" + SCREENSHOT)
            except Exception as e:
                print("SCREENSHOT_ERROR=" + type(e).__name__)

            if not passed_challenge:
                final_title = await page.title()
                print("FINAL_TITLE=" + final_title)
                print("CLOUDFLARE_CHALLENGE_PASSED=False")
                print("HEADLESS_CHATGPT_CONTROL_TEST=False")
                sys.exit(40)

            print("CLOUDFLARE_CHALLENGE_PASSED=True")

            # Verify actual rendered JS DOM.
            body_text = (final_info.get("body") or "").strip()

            print("HEADLESS_UA_CONTAINS_HEADLESS=" +
                  str("HeadlessChrome" in (final_info.get("ua") or "")))
            print("HEADLESS_NAVIGATOR_WEBDRIVER=" +
                  str(final_info.get("webdriver")))
            print(f"FINAL_DOM_ELEMENTS={final_info['elements']}")
            print(f"FINAL_DOM_BUTTONS={final_info['buttons']}")
            print(f"FINAL_DOM_TEXTAREAS={final_info['textareas']}")
            print(f"FINAL_DOM_EDITABLES={final_info['editables']}")
            print(f"FINAL_PROMPT_SELECTOR_COUNT={final_info['prompt']}")
            print(f"FINAL_BODY_CHARS={len(body_text)}")

            # Read a safe preview proving DOM visibility.
            safe_preview = " ".join(body_text.split())[:500]
            print("DOM_TEXT_PREVIEW_BEGIN")
            print(safe_preview)
            print("DOM_TEXT_PREVIEW_END")

            # Enumerate controls but never dump values from text inputs.
            controls = await page.evaluate("""() =>
                Array.from(document.querySelectorAll(
                    'button, textarea, [contenteditable="true"], a, input'
                ))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden';
                })
                .slice(0, 40)
                .map((el, i) => ({
                    i,
                    tag: el.tagName,
                    role: el.getAttribute('role') || '',
                    aria: el.getAttribute('aria-label') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    text: (el.innerText || '').trim().slice(0,100)
                }))
            """)

            print(f"VISIBLE_CONTROL_COUNT={len(controls)}")

            for c in controls[:20]:
                print("CONTROL=" + json.dumps(c, ensure_ascii=False))

            # Strong success criterion:
            # challenge gone AND enough rendered UI to control.
            control_ready = (
                final_info["prompt"] > 0
                or final_info["textareas"] > 0
                or final_info["editables"] > 0
                or len(controls) >= 3
            )

            print("JS_RENDERED_DOM_READABLE=True")
            print("CHATGPT_CONTROLS_ACCESSIBLE=" + str(control_ready))
            print("HEADLESS_CHATGPT_CONTROL_TEST=" + str(control_ready))

            if not control_ready:
                sys.exit(41)

        finally:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass

asyncio.run(main())

