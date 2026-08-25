import os
import sys
import tempfile
import uuid
import time
import subprocess
import urllib.request
from playwright.sync_api import sync_playwright
import threading
import traceback
from pathlib import Path
from seleniumbase import sb_cdp


try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# Persistent PowerShell process tracking
_PS_PROCESS = None
_PS_LOCK = threading.Lock()

# saving this in case of targetclosed error
last_command_received = ""

BROWSER_LAUNCHER_SCRIPT_PATH = r"C:\Users\ragha\Downloads\LUCY\LucyPython\POWERSHELL_DEBUG_SCRIPTS\manageLucyChromeProfile.ps1"
BROWSER_CLOSER_SCRIPT_PATH = r"C:\Users\ragha\Downloads\LUCY\LucyPython\POWERSHELL_DEBUG_SCRIPTS\CloseLucyBrowser9223.ps1"
PORT = 9223
CDP_URL = f"http://127.0.0.1:{PORT}"

LUCY_URL = (
    "https://chatgpt.com/"
)

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"


def cdp_ready():
    try:
        with urllib.request.urlopen(
            f"{CDP_URL}/json/version",
            timeout=1000
        ) as response:
            return response.status == 200
    except Exception:
        return False

def read_clipboard():
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True,
            text=True
        )
        return result.stdout
    except Exception:
        return ""


def set_clipboard(text):
    try:
        subprocess.run(
            ["clip"],
            input=text,
            text=True
        )
    except Exception:
        pass


def focus_chrome(page):
    try:
        page.bring_to_front()
        time.sleep(0.25)
    except Exception:
        pass



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

    # Just create the session—DO NOT send Target.setDiscoverTargets
    _BROWSER_CDP_SESSION = browser.new_browser_cdp_session()
    return _BROWSER_CDP_SESSION


def raw_browser_targets(browser):
    session = _ensure_browser_cdp_session(browser)
    try:
        # Target.getTargets works perfectly fine WITHOUT setting discover: True first!
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



def connect_to_lucy(p):
    # close old instance
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                BROWSER_CLOSER_SCRIPT_PATH
            ],
            cwd=os.path.dirname(BROWSER_CLOSER_SCRIPT_PATH),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except Exception as error:
        raise RuntimeError(
            "Failed to shut down existing instance of Lucy's automated browser"
        )


    # launch new one
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                BROWSER_LAUNCHER_SCRIPT_PATH
            ],
            cwd=os.path.dirname(BROWSER_LAUNCHER_SCRIPT_PATH),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except Exception as error:
        raise RuntimeError(
            "Failed to launch Lucy's automated browser"
        )

    if not cdp_ready():
        raise RuntimeError(
            f"No Chrome instance detected at {CDP_URL} on port {PORT}."
        )

    print(
        f"{YELLOW}Connecting Playwright to CDP on port {PORT}...{RESET}"
    )

    browser = p.chromium.connect_over_cdp(
        CDP_URL,
        no_defaults=True
    )

    if not browser.contexts:
        raise RuntimeError("No Chrome browser context found.")


    install_page_tracking(browser)
    context = browser.contexts[0]
    page = None

    for existing_page in all_pages(browser):
        try:
            if existing_page.url.startswith(LUCY_URL):
                page = existing_page
                break
        except Exception:
            pass

    if page is None:
        page = context.new_page()
        page.goto(
            LUCY_URL,
            wait_until="domcontentloaded"
        )

    page.emulate_media(color_scheme="light")

    print(f"{GREEN}Connected to Lucy.{RESET}")
    return browser, context, page


def is_target_closed_error(error):
    message = str(error).lower()
    return any(
        text in message
        for text in (
            "target page, context or browser has been closed",
            "target closed",
            "page has been closed",
            "context has been closed",
            "browser has been closed",
            "browser closed",
        )
    )


def recover_lucy(p):
    print(f"{RED}Lucy page/context/browser was closed.{RESET}")
    print(f"{YELLOW}Reconnecting to existing Chrome...{RESET}")
    browser, context, page = connect_to_lucy(p)
    print(f"{GREEN}Lucy recovered successfully.{RESET}")
    return browser, context, page


def get_composer_icon_href(page):
    try:
        composer_icon_use = page.locator(
            'button.composer-submit-button-color svg use'
        ).first
        return composer_icon_use.get_attribute("href") or ""
    except Exception as error:
        if is_target_closed_error(error):
            raise
        return ""


def wait_until_not_responding(page):
    while True:
        href = get_composer_icon_href(page)
        if "#stop-filled-style-thin" not in href:
            return

        print(f"{YELLOW}LLM is already responding; waiting...{RESET}")
        page.wait_for_timeout(250)


def send_request_reliably(page, composer, request):
    composer.click(force=True)

    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(request)

    send_button = page.locator('button.composer-submit-button-color').first
    send_button.wait_for(state="visible", timeout=30000)

    for attempt in range(1, 4):
        print(f"{YELLOW}Send attempt {attempt}/3...{RESET}")
        send_button.click(force=True)
        page.wait_for_timeout(750)

        remaining_text = composer.inner_text().strip()
        if not remaining_text:
            print(f"{GREEN}Request actually submitted.{RESET}")
            return

        print(f"{YELLOW}Message still in composer. Retrying...{RESET}")
        composer.click(force=True)
        page.wait_for_timeout(250)

    print(f"{YELLOW}Send button failed 3 times. Falling back to Enter...{RESET}")
    composer.click(force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(750)

    remaining_text = composer.inner_text().strip()
    if remaining_text:
        raise RuntimeError("Could not submit request after 3 click attempts and Enter fallback.")

    print(f"{GREEN}Request submitted using Enter fallback.{RESET}")


def run_persistent_powershell(script_content, timeout=None):
    # Keep Lucy/Python itself UTF-8 safe.
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    token = uuid.uuid4().hex
    temp_dir = tempfile.gettempdir()

    command_file = os.path.join(temp_dir, "lucy_command_" + token + ".ps1")
    wrapper_file = os.path.join(temp_dir, "lucy_wrapper_" + token + ".ps1")
    output_file = os.path.join(temp_dir, "lucy_output_" + token + ".txt")

    with open(command_file, "w", encoding="utf-8-sig", newline="") as f:
        f.write(script_content)

    # IMPORTANT:
    # Do NOT use Tee-Object -FilePath here.
    # Windows PowerShell 5.1 writes that file as UTF-16LE by default,
    # which was the source of the NUL-byte garbage in Lucy's clipboard.
    wrapper = r"""$ErrorActionPreference = 'Continue'

$Host.UI.RawUI.WindowTitle = 'LUCY COMMAND'

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$outputPath = '__OUTPUT__'

[System.IO.File]::WriteAllText(
    $outputPath,
    '',
    $Utf8NoBom
)

Write-Host ''
Write-Host '============================================================'
Write-Host '                     LUCY COMMAND'
Write-Host '============================================================'
Write-Host ('Started: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host ''
Write-Host '--- LIVE OUTPUT ---'
Write-Host ''

$exitCode = 0

try {
    & '__COMMAND__' 2>&1 | ForEach-Object {
        $line = $_ | Out-String
        $line = $line.TrimEnd("`r","`n")

        # Show it live in the visible terminal.
        Write-Host $line

        # Independently append UTF-8 bytes to Lucy's capture file.
        [System.IO.File]::AppendAllText(
            $outputPath,
            $line + [Environment]::NewLine,
            $Utf8NoBom
        )
    }

    if ($LASTEXITCODE -ne $null) {
        $exitCode = [int]$LASTEXITCODE
    }
}
catch {
    $line = ($_ | Out-String).TrimEnd("`r","`n")

    Write-Host $line

    [System.IO.File]::AppendAllText(
        $outputPath,
        $line + [Environment]::NewLine,
        $Utf8NoBom
    )

    $exitCode = 1
}

Write-Host ''
Write-Host '--- COMMAND FINISHED ---'
Write-Host ('Exit code: ' + $exitCode)
Write-Host ('Finished: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host '============================================================'

exit $exitCode
"""

    wrapper = wrapper.replace(
        "__COMMAND__",
        command_file.replace("'", "''")
    ).replace(
        "__OUTPUT__",
        output_file.replace("'", "''")
    )

    with open(wrapper_file, "w", encoding="utf-8-sig", newline="") as f:
        f.write(wrapper)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    proc = subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            wrapper_file,
        ],
        creationflags=creationflags,
        env=env,
    )

    # No hard command timeout.
    return_code = proc.wait()

    output = ""

    if os.path.exists(output_file):
        raw = Path(output_file).read_bytes()

        # UTF-8 is the expected format.
        # Keep fallbacks so stale/foreign PowerShell output cannot break Lucy.
        if raw.startswith(b"\xff\xfe") or (
            len(raw) >= 4 and raw[1:2] == b"\x00"
        ):
            output = raw.decode("utf-16", errors="replace")
        else:
            output = raw.decode("utf-8", errors="replace")

        output = output.replace("\x00", "").strip()

    for file_path in (command_file, wrapper_file, output_file):
        try:
            os.remove(file_path)
        except OSError:
            pass

    if not output:
        output = "COMMAND_EXIT_CODE=" + str(return_code)

    return output



def main():
    with sync_playwright() as p:
        browser, context, page = connect_to_lucy(p)
        request = input("Enter a task/goal to achieve: ")

        while True:
            try:
                if not request.strip():
                    print(f"{RED}Clipboard result was empty.{RESET}")
                    request = "No output was captured from the script. Couldn't confirm success."

                focus_chrome(page)

                try:
                    composer_icon_use = page.locator(
                        'button.composer-submit-button-color svg use'
                    ).first

                    composer_icon_use.wait_for(state="attached", timeout=30000)
                    wait_until_not_responding(page)
                except Exception as error:
                    if is_target_closed_error(error):
                        raise
                    print(f"{RED}Could not determine ChatGPT response state:\n{error}{RESET}")
                    continue

                composer = page.locator(
                    '#prompt-textarea[contenteditable="true"]'
                ).first

                try:
                    focus_chrome(page)
                    composer.wait_for(state="visible", timeout=30000)
                except Exception as error:
                    if is_target_closed_error(error):
                        raise
                    print(f"{RED}Could not find ChatGPT prompt box.{RESET}")
                    continue


                send_request_reliably(page, composer, request)
                print(f"{GREEN}Request sent.{RESET}")

                print(f"{YELLOW}Waiting for LLM to start responding...{RESET}")
                try:
                    page.wait_for_function(
                        """
                        () => {
                            const use = document.querySelector(
                                'button.composer-submit-button-color svg use'
                            );
                            const href = use?.getAttribute('href') || '';
                            return href.includes('#stop-filled-style-thin');
                        }
                        """,
                        polling=100,
                        timeout=30000
                    )
                except Exception as error:
                    if is_target_closed_error(error):
                        raise
                    print(f"{RED}LLM response did not start:\n{error}{RESET}")
                    continue

                print(f"{GREEN}LLM is responding.{RESET}")

                print(f"{YELLOW}Waiting for LLM to finish responding...{RESET}")
                try:
                    page.wait_for_function(
                        """
                        () => {
                            const use = document.querySelector(
                                'button.composer-submit-button-color svg use'
                            );
                            const href = use?.getAttribute('href') || '';
                            return href.includes('#voice-regular-24');
                        }
                        """,
                        polling=100,
                        timeout=1000000
                    )
                except Exception as error:
                    if is_target_closed_error(error):
                        raise
                    print(f"{RED}Assistant response did not finish:\n{error}{RESET}")
                    continue

                print(f"{GREEN}Response finished.{RESET}")

                page.wait_for_timeout(300)

                # Scope copy extraction to the newest assistant response only.
                # Read code directly from the newest assistant DOM turn.
                # This avoids stale Copy-button/clipboard races entirely.
                assistant_turns = page.locator('[data-message-author-role="assistant"]')
                assistant_count = assistant_turns.count()

                if assistant_count == 0:
                    print(f"{YELLOW}No assistant response found.{RESET}")
                    request = "Return exactly one PowerShell code block."
                    continue

                newest_turn = assistant_turns.nth(assistant_count - 1)
                code_blocks = newest_turn.locator('pre code')
                code_count = code_blocks.count()

                if code_count == 0:
                    # Fallback for code renderers where <code> is not nested in <pre>.
                    code_blocks = newest_turn.locator('code')
                    code_count = code_blocks.count()

                if code_count == 0:
                    print(f"{YELLOW}Newest assistant response contained no code block.{RESET}")
                    request = "Return exactly one PowerShell code block and nothing else."
                    continue

                latest_code = code_blocks.nth(code_count - 1)
                try:
                    llm_output = latest_code.inner_text(timeout=10000).strip()
                except Exception as error:
                    if is_target_closed_error(error):
                        raise
                    print(f"{RED}Could not read newest code block directly:\n{error}{RESET}")
                    continue
                if not llm_output:
                    print(f"{RED}Copied code was empty.{RESET}")
                    request = (
                        "U missed the code block. Only spit out code blocks with commands."
                    )
                    continue

                if llm_output.lower() == "stop":
                    print(f"{RED}STOP CODE DETECTED! STOPPING LUCY LEARNING SERVICE.{RESET}")
                    # continue to allow persistent state instead of shutting down loop
                    request = input("Enter a task/goal to achieve: ")
                    continue


                if not llm_output:
                    last_command_received = ""
                else:
                    last_command_received = llm_output

                print(f"{YELLOW}Running command via persistent PowerShell session...{RESET}")
                try:
                    set_clipboard("")
                    result_output = run_persistent_powershell(llm_output.rstrip())
                    set_clipboard(result_output)
                    request = result_output
                    print(f"{CYAN}OUTPUT BEING SENT BACK: {request}\n{RESET}")
                except Exception as error:
                    print(f"{RED}Could not run command script:\n{error}{RESET}")
                    continue
            except Exception as error:
                if is_target_closed_error(error):
                    browser = None
                    context = None
                    page = None
                    browser, context, page = recover_lucy(p)
                    # handling the case of an incomplete context due to a crash or freeze
                    incomplete_context = read_clipboard().strip()
                    temp_request = request
                    request = f"This is a continuation of a previous goal/request by the user. User's original request was: {temp_request} and here's the latest output from Lucy trying to solve it: {incomplete_context}.\n"
                    continue
                raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"{RED}\nLUCY CRASHED CRITICAL ERROR: MAIN LOOP INTERRUPTED.{RESET}")
    except Exception as error:
        crash_text = (
            "\n=== LUCY FATAL CRASH ===\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Error type: {type(error).__name__}\n"
            f"Error: {error}\n\n"
            + traceback.format_exc()
            + "\n"
        )

        try:
            crash_log = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "LUCY_ABILITIES",
                "main-crash-diagnostics",
                "main-crash.log"
            )
            os.makedirs(os.path.dirname(crash_log), exist_ok=True)
            with open(crash_log, "a", encoding="utf-8") as f:
                f.write(crash_text)
                f.flush()
        except Exception:
            pass

        print(f"{RED}{crash_text}{RESET}")
        sys.exit(1)



# TODO LATER: OPTIMIZATIONS




# REWRITE LUCY MAIN SCRIPT AND WEB PAGE CRASH LOGIC. IT SHOULD PRESERVE ALL PREVIOUS CONTEXT
# TEST PROMPT: Close all browser tabs and email to me




# ADD ANDROID PHONE 'EXTEND UNLOCK' NEAR LUCY'S HOME/DEFAULT LOCATION
# ENABLE WIRELESS DEBUGGING IN ANDROID TO ALLOW LUCY TO CONTROL THE PHONE

# OPTIMIZE SYSTEM PROMPT TO LIMIT OUTPUT FROM COMMANDS BY RESTRICTING/FILTERING COMMANDS THAST WOULD PRODUCE MASSIVE OUTPUTS

# RUN A LOCAL DATABASE FULL OF PERSONAL INFO FOR FASTER RESULTS.
# check discord feedback