import os
import sys
import tempfile
import uuid
import time
import subprocess
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


PORT = 9223
CDP_URL = f"http://127.0.0.1:{PORT}"
# GEMINI_URL = "https://gemini.google.com/"
GEMINI_GEM_URL = "https://gemini.google.com/gem/9cbc7f7cf497"


SCRIPT_DIR = Path(__file__).resolve().parent
SYS_PROMPT_PATH = SCRIPT_DIR / "sys_prompt.txt"


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
            timeout=3
        ) as response:
            return response.status == 200
    except Exception:
        return False


def require_cdp():
    if cdp_ready():
        return True

    print(
        f"{RED}ERROR: No browser CDP instance is running on port "
        f"{PORT}. Expected {CDP_URL}.{RESET}"
    )
    return False


def load_sys_prompt():
    if not SYS_PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Could not find system prompt file: {SYS_PROMPT_PATH}"
        )

    content = SYS_PROMPT_PATH.read_text(
        encoding="utf-8",
        errors="replace"
    ).strip()

    if not content:
        raise RuntimeError(
            f"System prompt file is empty: {SYS_PROMPT_PATH}"
        )

    return content


def focus_chrome(page):
    try:
        page.bring_to_front()
        time.sleep(0.25)
    except Exception:
        pass


def connect_to_gemini(p):
    if not require_cdp():
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

    context = browser.contexts[0]
    page = None

    # Reuse an already-open Gemini tab if one exists.
    for existing_page in context.pages:
        try:
            if existing_page.url.startswith("https://gemini.google.com"):
                page = existing_page
                break
        except Exception:
            pass

    # Only open a new tab if no existing Gemini tab was found.
    if page is None:
        page = context.new_page()
        page.goto(
            GEMINI_GEM_URL,
            wait_until="domcontentloaded"
        )

    page.emulate_media(color_scheme="light")

    print(f"{GREEN}Connected to Gemini.{RESET}")

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


def recover_gemini(p):
    print(f"{RED}Gemini page/context/browser was closed.{RESET}")
    print(f"{YELLOW}Checking browser on port {PORT}...{RESET}")

    if not require_cdp():
        raise RuntimeError(
            f"Browser recovery failed because port {PORT} is unavailable."
        )

    print(f"{YELLOW}Reconnecting to existing Chrome...{RESET}")

    browser, context, page = connect_to_gemini(p)

    print(f"{GREEN}Gemini recovered successfully.{RESET}")

    return browser, context, page


def is_gemini_generating(page):
    try:
        # Gemini displays a stop button while streaming responses.
        stop_btn = page.locator(
            'button[aria-label="Stop response"], button.stop-generating-button'
        ).first
        return stop_btn.is_visible()
    except Exception as error:
        if is_target_closed_error(error):
            raise
        return False


def wait_until_not_responding(page):
    while is_gemini_generating(page):
        print(
            f"{YELLOW}Gemini is currently generating a response; waiting...{RESET}"
        )
        page.wait_for_timeout(500)


def get_composer(page):
    # Select the rich-text Quill editor container used by Gemini.
    composer = page.locator(
        'div.new-input-ui.ql-editor, div.ql-editor[contenteditable="true"]'
    ).first

    composer.wait_for(
        state="visible",
        timeout=30000
    )

    return composer


def send_request_reliably(page, composer, request):
    composer.click(force=True)

    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    
    # Use insert_text to inject user prompt into Quill safely without triggering TrustedHTML violations
    page.keyboard.insert_text(request)

    # Locate Gemini's send button
    send_button = page.locator(
        'button.send-button, button[aria-label*="Send"], button[aria-label*="Submit"]'
    ).first

    send_button.wait_for(
        state="visible",
        timeout=30000
    )

    for attempt in range(1, 4):
        print(
            f"{YELLOW}Send attempt {attempt}/3...{RESET}"
        )

        send_button.click(force=True)
        page.wait_for_timeout(750)

        remaining_text = composer.inner_text().strip()

        if not remaining_text:
            print(
                f"{GREEN}Request actually submitted.{RESET}"
            )
            return

        print(
            f"{YELLOW}Message still in composer. Retrying...{RESET}"
        )

        composer.click(force=True)
        page.wait_for_timeout(250)

    print(
        f"{YELLOW}Send button failed 3 times. "
        f"Falling back to Enter...{RESET}"
    )

    composer.click(force=True)
    page.keyboard.press("Enter")

    page.wait_for_timeout(750)

    remaining_text = composer.inner_text().strip()

    if remaining_text:
        raise RuntimeError(
            "Could not submit request after 3 click attempts "
            "and Enter fallback."
        )

    print(
        f"{GREEN}Request submitted using Enter fallback.{RESET}"
    )


def wait_for_response(page):
    print(
        f"{YELLOW}Waiting for Gemini to finish generating...{RESET}"
    )

    # Give Gemini a short window to initiate generation
    page.wait_for_timeout(1000)

    try:
        # Poll until the stop generation button disappears
        while is_gemini_generating(page):
            page.wait_for_timeout(300)

    except Exception as error:
        if is_target_closed_error(error):
            raise

        raise RuntimeError(
            f"Assistant response did not finish: {error}"
        )

    print(f"{GREEN}Response finished.{RESET}")

    page.wait_for_timeout(500)


def extract_latest_code(page):
    # Read directly from the newest assistant turn in Gemini's DOM.
    response_containers = page.locator(
        'message-content, model-response, div.model-response, .response-container'
    )

    response_count = response_containers.count()

    if response_count == 0:
        raise RuntimeError(
            "No model response found in the DOM."
        )

    newest_turn = response_containers.nth(
        response_count - 1
    )

    # Search for code blocks inside the newest response
    code_blocks = newest_turn.locator("pre code, code-block code")
    code_count = code_blocks.count()

    if code_count == 0:
        # Fallback for inline code tags if standard pre/code-block aren't present
        code_blocks = newest_turn.locator("code")
        code_count = code_blocks.count()

    if code_count == 0:
        return None

    if code_count > 1:
        raise RuntimeError(
            "Gemini returned more than one code block."
        )

    try:
        return code_blocks.first.inner_text(
            timeout=30000
        ).strip()

    except Exception as error:
        if is_target_closed_error(error):
            raise

        raise RuntimeError(
            f"Could not read newest code block: {error}"
        )


def run_python(script_content):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(
                encoding="utf-8",
                errors="replace"
            )

        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(
                encoding="utf-8",
                errors="replace"
            )

    except Exception:
        pass

    token = uuid.uuid4().hex

    command_file = os.path.join(
        tempfile.gettempdir(),
        f"gemini_command_{token}.py"
    )

    try:
        with open(command_file, "w", encoding="utf-8") as f:
            f.write(script_content)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        print(
            f"{YELLOW}Running latest command...{RESET}"
        )

        MAX_COMMAND_RUNTIME = 300          # Hard limit: 5 minutes
        STATUS_CHECK_INTERVAL = 5          # Check every 5 seconds
        NO_OUTPUT_WARNING_AFTER = 30       # Warn after 30 sec with no output

        proc = subprocess.Popen(
            ["python", command_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8"
        )

        start_time = time.monotonic()
        last_status_check = start_time

        try:
            while True:
                return_code = proc.poll()

                if return_code is not None:
                    break

                now = time.monotonic()
                elapsed = now - start_time

                if elapsed >= MAX_COMMAND_RUNTIME:
                    print(
                        f"{RED}COMMAND TIMEOUT: Python has been "
                        f"running for {elapsed:.0f} seconds. "
                        f"Terminating it...{RESET}"
                    )

                    try:
                        subprocess.run(
                            [
                                "taskkill",
                                "/F",
                                "/T",
                                "/PID",
                                str(proc.pid),
                            ],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=10,
                        )
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass

                    proc.wait(timeout=10)

                    raise TimeoutError(
                        f"COMMAND_TIMEOUT=True\n"
                        f"COMMAND_RUNTIME_SECONDS={elapsed:.1f}\n"
                        f"COMMAND_PID={proc.pid}\n"
                        f"The Python command exceeded the maximum "
                        f"runtime of {MAX_COMMAND_RUNTIME} seconds and "
                        f"was terminated."
                    )

                if now - last_status_check >= STATUS_CHECK_INTERVAL:
                    print(
                        f"{YELLOW}COMMAND STILL RUNNING | "
                        f"PID={proc.pid} | "
                        f"ELAPSED={elapsed:.0f}s{RESET}"
                    )

                    if elapsed >= NO_OUTPUT_WARNING_AFTER:
                        print(
                            f"{YELLOW}WARNING: Command has been running "
                            f"for {elapsed:.0f}s. It may be waiting for "
                            f"input, blocked, performing a long operation, "
                            f"or frozen.{RESET}"
                        )

                    last_status_check = now

                time.sleep(0.25)

            raw_output = proc.communicate()[0] or ""

        except Exception:
            if proc.poll() is None:
                try:
                    subprocess.run(
                        [
                            "taskkill",
                            "/F",
                            "/T",
                            "/PID",
                            str(proc.pid),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                    )
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            raise

        if isinstance(raw_output, bytes):
            output = raw_output.decode(
                "utf-8",
                errors="replace"
            )
        else:
            output = str(raw_output)

        output = output.replace(
            "\x00",
            ""
        ).strip()

        if not output:
            output = (
                "COMMAND_EXIT_CODE="
                + str(proc.returncode)
            )
        else:
            output = (
                "COMMAND_EXIT_CODE="
                + str(proc.returncode)
                + "\n"
                + output
            )

        return output

    finally:
        try:
            if os.path.exists(command_file):
                os.remove(command_file)
        except OSError:
            pass


def build_initial_message(sys_prompt, user_request):
    return (
        sys_prompt
        + "\n\n"
        + "USER'S ORIGINAL REQUEST:\n"
        + user_request
    )


def safe_loop_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except KeyboardInterrupt:
        raise
    except Exception as error:
        return (
            "RECOVERABLE_ERROR: "
            + type(error).__name__
            + ": "
            + str(error)[:300]
        )


def main():
    if not require_cdp():
        return

    try:
        sys_prompt = load_sys_prompt()

    except Exception as error:
        print(
            f"{RED}ERROR: Could not load sys_prompt.txt: "
            f"{error}{RESET}"
        )
        return

    request = input(
        "Enter a task/goal to achieve: "
    ).strip()

    if not request:
        print(
            f"{RED}No task/goal was provided. Exiting.{RESET}"
        )
        return

    original_request = request

    with sync_playwright() as p:
        try:
            browser, context, page = connect_to_gemini(p)

        except Exception as error:
            print(
                f"{RED}ERROR: Could not connect to Gemini: "
                f"{error}{RESET}"
            )
            return

        needs_bootstrap = True
        request = None

        while True:
            try:
                if not require_cdp():
                    print(
                        f"{RED}Browser on port {PORT} is no longer "
                        f"available. Exiting gracefully.{RESET}"
                    )
                    return

                if needs_bootstrap:
                    # request = build_initial_message(
                    #     sys_prompt,
                    #     original_request
                    # )

                    # print(
                    #     f"{YELLOW}Sending system prompt and original "
                    #     f"user request...{RESET}"
                    # )

                    # debugging for custom gems but if those are no longer available use the above commented code to attach a short intruction set at the beginning of chats to preserve context.
                    request = original_request

                    needs_bootstrap = False

                if not request or not request.strip():
                    request = "No execution output was captured. The previous result could not confirm success. Try again."

                focus_chrome(page)

                try:
                    wait_until_not_responding(page)

                except Exception as error:
                    if is_target_closed_error(error):
                        raise
                    print(
                        f"{RED}Could not determine Gemini response "
                        f"state: {error}{RESET}"
                    )
                    continue

                try:
                    focus_chrome(page)
                    composer = get_composer(page)

                except Exception as error:
                    if is_target_closed_error(error):
                        raise

                    print(
                        f"{RED}Could not find Gemini prompt box: "
                        f"{error}{RESET}"
                    )

                    continue

                send_request_reliably(
                    page,
                    composer,
                    request
                )

                print(f"{GREEN}Request sent.{RESET}")

                wait_for_response(page)

                llm_output = extract_latest_code(page)

                print(f"checking: {llm_output}")

                if llm_output == "" or not llm_output:
                    print(
                        f"{YELLOW}Latest response contained 0 "
                        f"code blocks.{RESET}"
                    )

                    request = "Return exactly one Python code block and nothing else."
                    continue

                if llm_output.lower().strip().strip('"').strip("'") == "idle":
                    print(
                        f"{GRAY}Goal completed. Idling...{RESET}"
                    )

                    next_goal = input(
                        "Enter a task/goal to achieve: "
                    ).strip()

                    if not next_goal:
                        print(
                            f"{GREEN}No new task provided. "
                            f"Exiting gracefully.{RESET}"
                        )
                        return

                    needs_bootstrap = False
                    request = next_goal
                    continue

                result_output = run_python(
                    llm_output.rstrip()
                )

                request = result_output

                print(
                    f"{CYAN}OUTPUT BEING SENT BACK:\n"
                    f"{request}\n{RESET}"
                )

            except Exception as error:
                if is_target_closed_error(error):
                    print(
                        f"{YELLOW}Gemini browser target closed. "
                        f"Attempting recovery...{RESET}"
                    )

                    browser = None
                    context = None
                    page = None

                    browser, context, page = recover_gemini(p)

                    needs_bootstrap = True
                    request = None

                    continue

                print(
                    f"{RED}MAIN LOOP ERROR: {error}{RESET}"
                )

                request = (
                    "The execution engine encountered this error:\n"
                    + str(error)
                )

                continue

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            f"{RED}\nMAIN LOOP INTERRUPTED "
            f"BY KEYBOARD INTERRUPT.{RESET}"
        )

    except Exception as error:
        print(
            f"{RED}FATAL ERROR: {error}{RESET}"
        )
        sys.exit(1)