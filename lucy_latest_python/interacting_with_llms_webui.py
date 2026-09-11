# Standard imports
import sys
import time
import json
import queue
import threading
from datetime import datetime
from pathlib import Path
import subprocess
import re
import ast
import psutil

# Util imports
from utils.CloseLucyBrowser9223 import kill_cdp_browser
from utils.gemini_usage import get_gemini_usage
from playwright.sync_api import expect, sync_playwright, Error as PlaywrightError
from utils.ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from utils.lucy_logging import log, LogColors
import utils.Constants as Constants


def check_usage_and_warn(usage_page):
    if not get_gemini_usage:
        print("[Usage Monitor] gemini_usage module not available. Skipping check.")
        return
    try:
        print("[Usage Monitor] Checking Gemini usage metrics...")
        usage_data = get_gemini_usage(usage_page)
        current_usage_str = int(usage_data.get("daily_usage_remaining"))
        if current_usage_str:
            if current_usage_str > 80:
                print(f"\033[93m[WARNING] You are reaching the selected LLM's limits! Current usage is at {current_usage_str}%.\033[0m")
                print("[Usage Monitor] Exiting script execution due to high usage limits.")
                sys.exit(0)
            else:
                print(f"[Usage Monitor] Usage is safe ({current_usage_str}%). Proceeding...")
        else:
            print("[Usage Monitor] Could not parse numeric usage percentage. Proceeding...")
    except Exception as e:
        print(f"[Usage Monitor Error] Failed to retrieve usage metrics: {e}")


LLM_SELECTED = "gemini"  # "chatgpt" or "gemini"

def get_llm_selectors(llm):
    llm = llm.lower().strip()

    if llm == "chatgpt":
        return {
            "STOP_RESPONSE_BUTTON": lambda page: page.get_by_test_id(
                "stop-button"
            ).first,

            "COMPOSER": lambda page: page.get_by_role(
                "textbox",
                name="Chat with ChatGPT"
            ),

            "SEND_BUTTON": lambda page: page.locator(
                'button.send-button, '
                'button[aria-label*="Send"], '
                'button[aria-label*="Submit"]'
            ).first,

            "RESPONSE_TURNS": lambda page: page.locator(
                '[data-message-author-role="assistant"]'
            ),
            "LLM_URL": Constants.CHATGPT_URL,
        }

    elif llm == "gemini":
        return {
            "STOP_RESPONSE_BUTTON": lambda page: page.get_by_role(
                "button",
                name="Stop response"
            ).first,

            "COMPOSER": lambda page: page.locator(
                "rich-textarea .ql-editor"
            ).first,

            "SEND_BUTTON": lambda page: page.locator(
                'button.send-button, '
                'button[aria-label*="Send"], '
                'button[aria-label*="Submit"]'
            ).first,

            "RESPONSE_TURNS": lambda page: page.locator(
                'message-content, model-response, div.model-response, .response-container'
            ),
            "LLM_URL": Constants.GEMINI_GEM_URL,
        }

    raise ValueError(
        f"Unsupported LLM: {llm}. "
        'Use "chatgpt" or "gemini".'
    )


SELECTORS = get_llm_selectors(LLM_SELECTED)
STOP_RESPONSE_BUTTON = SELECTORS["STOP_RESPONSE_BUTTON"]
COMPOSER = SELECTORS["COMPOSER"]
SEND_BUTTON = SELECTORS["SEND_BUTTON"]
RESPONSE_TURNS = SELECTORS["RESPONSE_TURNS"]
PRIMARY_CODE_BLOCKS = lambda container: container.locator("pre code, code-block code")
FALLBACK_CODE_BLOCKS = lambda container: container.locator("code")
llm_url = SELECTORS["LLM_URL"]


MAX_PROMPTS_PER_CHAT = 10
ASYNC_LOG_FILE = Constants.PROJECT_DIR.joinpath("lucy_latest_python/gemini_llm_activity.jsonl")

class AsyncLLMLogger:
    """Writes LLM activity to disk from a dedicated background thread."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._worker,
            name="Lucy-LLM-Logger",
            daemon=True,
        )

    def start(self):
        self._thread.start()

    def log(self, event_type: str, **data):
        """Queues a timestamped event without waiting for disk I/O."""
        self._queue.put_nowait({
            "datetime": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event": event_type,
            **data,
        })

    def _worker(self):
        try:
            while not self._stop_event.is_set() or not self._queue.empty():
                try:
                    record = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                try:
                    Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(
                        self.file_path,
                        "a",
                        encoding="utf-8",
                        buffering=1,
                    ) as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception as e:
                    # Never allow logging failures to affect the LLM loop.
                    print(f"[Async Logger Error] {e}")
                finally:
                    self._queue.task_done()
        except Exception as e:
            print(f"[Async Logger Fatal Error] {e}")

    def stop(self):
        """Flushes queued records before the process exits."""
        self._stop_event.set()
        self._thread.join(timeout=5)


def build_rollover_request(original_request: str, latest_code: str, latest_output: str) -> str:
    """Builds the context sent to the first prompt in a fresh Gemini chat."""
    return (
        f"{Constants.PROMPT_PREFIX}{original_request}{Constants.PROMPT_SUFFIX}\n\n"
        "IMPORTANT: This is a continuation in a fresh chat because the previous "
        "chat reached its prompt limit.\n\n"
        "LATEST PYTHON CODE THAT WAS EXECUTED:\n"
        "```python\n"
        f"{latest_code}\n"
        "```\n\n"
        "OUTPUT FROM THAT CODE:\n"
        f"{latest_output}\n\n"
        "Continue working on the original task from this state. "
        "Do not restart the work from scratch."
    )


def open_fresh_llm_chat(state, logger, original_request, latest_code, latest_output):
    """
    Opens a new Gemini tab using the exact configured Gemini URL, waits for it
    to render, then sends the continuation context.
    """
    old_page = state["page"]

    logger.log(
        "chat_rollover",
        reason=f"Reached {MAX_PROMPTS_PER_CHAT} prompts",
        previous_url=old_page.url,
    )
    
    # reload the same page instead of opening new pages to preserve system resources
    new_page = old_page
    new_page.goto(llm_url, wait_until="domcontentloaded")
    new_page.wait_for_timeout(2000)

    # Wait for the actual composer rather than relying only on a fixed delay.
    COMPOSER(new_page).wait_for(state="visible", timeout=30000)

    rollover_request = build_rollover_request(
        original_request,
        latest_code,
        latest_output,
    )

    send_request(new_page, rollover_request)

    logger.log(
        "prompt_sent",
        prompt_number=1,
        rollover=True,
        prompt=rollover_request,
    )

    # The rollover context message is itself the first sent prompt in the
    # fresh chat, so the counter starts at 1.
    return new_page, 1


def run_python_code(script_content: str, max_runtime: float = 120.0) -> str:
    try:
        tree = ast.parse(script_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'input':
                return "taking input from the user is restricted in this sandbox environment"
    except SyntaxError:
        pass

    try:
        process = subprocess.Popen(
            [sys.executable, "-c", script_content],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=max_runtime)
        except subprocess.TimeoutExpired:
            try:
                parent = psutil.Process(process.pid)
                parent.kill()
                psutil.wait_procs([parent], timeout=5)
            except psutil.NoSuchProcess:
                pass
            return "Script timed out and took forever."

        if process.returncode != 0:
            line_match = re.search(r'line (\d+)', stderr)
            script_lines = script_content.splitlines()
            offending_line = "unknown"
            if line_match:
                line_idx = int(line_match.group(1)) - 1
                if 0 <= line_idx < len(script_lines):
                    offending_line = script_lines[line_idx].strip()
            
            stderr_lines = [l.strip() for l in stderr.strip().split('\n') if l.strip()]
            error_type = "Error"
            if stderr_lines:
                last_line = stderr_lines[-1]
                error_type = last_line.split(':')[0] if ':' in last_line else last_line
                
            return f"{error_type} at statement: '{offending_line}'"
            
        combined_output = f"{stdout}{stderr}".strip()
        return combined_output if combined_output else "Could you verify if that worked? I can't tell since there's no output."
        
    except Exception as e:
        return f"Error: {str(e)}"


def connect_to_LLM(p, endpoint_url):
    log(f"Connecting to ChatGPT at {endpoint_url}...", LogColors.YELLOW)

    try:
        browser = p.chromium.connect_over_cdp(
            endpoint_url,
            no_defaults=True
        )

    except Exception:
        chrome_state = launch_lucy_chrome(preferred_port=Constants.PORT)
        endpoint_url = chrome_state["url"]

        browser = p.chromium.connect_over_cdp(
            endpoint_url,
            no_defaults=True
        )

    context = browser.contexts[0]

    all_pages = context.pages

    chat_page = None

    for page in all_pages:
        if page.url.startswith(llm_url):
            chat_page = page
            break

    if chat_page is None:
        # no llm session found
        # open session in new page
        chat_page = context.new_page()
        chat_page.goto(llm_url, wait_until="domcontentloaded")
        chat_page.wait_for_timeout(2000) # give the page some time to load and render the UI elements

    chat_page.bring_to_front()

    log(f"Connected to {LLM_SELECTED}.", LogColors.GREEN)

    return {
        "browser": browser,
        "context": context,
        "page": chat_page,
        "endpoint_url": endpoint_url
    }


def reconnect(playwright_instance):
    log(f"LLM NOT FOUND:", LogColors.RED)
    state = None
    if not is_cdp_port_active(Constants.PORT):
        log("Browser not found. Attempting hard recovery...", LogColors.YELLOW)
        chrome_state = launch_lucy_chrome(
            preferred_port=Constants.PORT
        )

        endpoint_url = chrome_state["url"]

        state = connect_to_LLM(
            playwright_instance,
            endpoint_url
        )
    else:
        log("LLM context not found. Attempting soft recovery...", LogColors.YELLOW)
        endpoint_url = f"http://127.0.0.1:{Constants.PORT}"
        state = connect_to_LLM(
            playwright_instance,
            endpoint_url
        )

    if not state:
        log(
            f"Recovery failed. Please restart the application.",
            LogColors.RED
        )
        exit(1)

    return state


def is_generating(page):
    return STOP_RESPONSE_BUTTON(page).is_visible()


def wait_for_ready(page):
    while is_generating(page):
        time.sleep(0.8)


def send_request(page, request):
    """Sends one prompt and returns only after submission is confirmed."""
    page.bring_to_front()

    wait_for_ready(page)

    composer = COMPOSER(page)
    composer.wait_for(
        state="visible",
        timeout=30000
    )

    composer.focus()
    composer.fill(request)

    composer.evaluate("""el => {
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")

    button = SEND_BUTTON(page)
    button.wait_for(state="visible", timeout=30000)

    try:
        button.click(timeout=3000)
    except Exception:
        button.evaluate("btn => btn.click()")

    try:
        expect(composer).to_be_empty(timeout=5000)
    except AssertionError:
        composer.press("Enter")
        expect(composer).to_be_empty(
            timeout=5000,
            message="Failed to submit request via UI."
        )

    return True


def extracted_code(page):
    wait_for_ready(page)

    turns = RESPONSE_TURNS(page)
    if turns.count() == 0:
        raise RuntimeError("You forgot to respond.")
 
    newest = turns.nth(turns.count() - 1)

    blocks = PRIMARY_CODE_BLOCKS(newest)
    if blocks.count() == 0:
        blocks = FALLBACK_CODE_BLOCKS(newest)
        if blocks.count() == 0:
            if (Constants.MAGIC_STOP_WORD in newest.inner_html().lower()):
                return Constants.MAGIC_STOP_WORD
    
    if blocks.count() > 1:
        raise RuntimeError(
            "Just give me 1 code block."
        )

    return blocks.first.inner_text(
        timeout=30000
    ).strip()


def main():
    try:
        chrome_state = launch_lucy_chrome(
            preferred_port=Constants.PORT
        )

        endpoint_url = chrome_state["url"]

    except Exception as e:
        log(
            f"Failed to init Chrome: {e}",
            LogColors.RED
        )
        return

    if not is_cdp_port_active(Constants.PORT):
        log(
            f"Browser unreachable. Exiting.",
            LogColors.RED
        )
        return

    with sync_playwright() as p:
        state = connect_to_LLM(
            p,
            endpoint_url
        )

        # Open or reuse dedicated usage monitoring tab (prevent duplicates)
        usage_page = None
        for p_tab in state["context"].pages:
            if "gemini.google.com/usage" in p_tab.url:
                usage_page = p_tab
                break
        if not usage_page:
            usage_page = state["context"].new_page()
            usage_page.goto("https://gemini.google.com/usage", wait_until="domcontentloaded")
            usage_page.wait_for_timeout(2000)

        # bring main llm session page to front.
        state["page"].bring_to_front()

        # Check usage before initial request
        check_usage_and_warn(usage_page)

        initial_request_log = print(
            "Enter a task/goal to achieve: "
        )

        initial_request = sys.stdin.read().strip()

        if not initial_request:
            return

        request = f"{Constants.PROMPT_PREFIX}{initial_request}{Constants.PROMPT_SUFFIX}"

        # Counts every prompt actually sent to Gemini. Responses do not count.
        prompts_sent_in_current_chat = 0

        # Latest execution state is retained specifically for chat rollover.
        latest_code = ""
        latest_output = ""

        async_logger = AsyncLLMLogger(ASYNC_LOG_FILE)
        async_logger.start()

        while True:
            try:
                if not is_cdp_port_active(Constants.PORT):
                    state = reconnect(p)

                if not request.strip():
                    request = (
                        "No execution output was captured. "
                        "Try again."
                    )

                # Check usage before sending request in loop
                check_usage_and_warn(usage_page)

                send_request(
                    state["page"],
                    request
                )

                prompts_sent_in_current_chat += 1

                # This log operation only puts a small object into a queue.
                # Disk I/O happens on the dedicated logger thread.
                async_logger.log(
                    "prompt_sent",
                    prompt_number=prompts_sent_in_current_chat,
                    rollover=False,
                    prompt=request,
                )

                log(
                    f"Request sent ({prompts_sent_in_current_chat}/{MAX_PROMPTS_PER_CHAT}).",
                    LogColors.GREEN
                )

                response = extracted_code(
                    state["page"]
                )

                if Constants.MAGIC_STOP_WORD in response.lower().strip():
                    async_logger.log(
                        "completion",
                        prompt_number=prompts_sent_in_current_chat,
                        code=response,
                        output="Job finished.",
                    )

                    log(
                        f"Job Finished. Idling...",
                        LogColors.GRAY
                    )

                    check_for_next_request_log = print(
                        "Enter next task: "
                    )

                    check_for_next_request = sys.stdin.read().strip()

                    if not check_for_next_request:
                        async_logger.stop()
                        break

                    # New user task = new conversation state and fresh count.
                    initial_request = check_for_next_request
                    request = (
                        f"{Constants.PROMPT_PREFIX}"
                        f"{check_for_next_request}"
                        f"{Constants.PROMPT_SUFFIX}"
                    )
                    prompts_sent_in_current_chat = 0
                    latest_code = ""
                    latest_output = ""
                    continue

                # Preserve the exact code and exact compact execution output
                # for both logging and the next chat rollover.
                latest_code = response
                latest_output = run_python_code(response)

                async_logger.log(
                    "code_executed",
                    prompt_number=prompts_sent_in_current_chat,
                    code=latest_code,
                    output=latest_output,
                )

                log(
                    f"OUTPUT:\n{latest_output}",
                    LogColors.CYAN
                )

                # Once 20 prompts have been SENT, rollover before generating
                # the next normal request. The rollover context prompt is
                # sent into the fresh chat and counts as prompt #1 there.
                if prompts_sent_in_current_chat >= MAX_PROMPTS_PER_CHAT:
                    new_page, prompts_sent_in_current_chat = open_fresh_llm_chat(
                        state,
                        async_logger,
                        initial_request,
                        latest_code,
                        latest_output,
                    )

                    state["page"] = new_page

                    log(
                        "Started fresh Gemini chat and transferred latest state.",
                        LogColors.YELLOW
                    )

                    # The rollover prompt is now waiting for Gemini's response.
                    # Continue directly to extraction/execution below.
                    response = extracted_code(state["page"])

                    if Constants.MAGIC_STOP_WORD in response.lower().strip():
                        async_logger.log(
                            "completion",
                            prompt_number=prompts_sent_in_current_chat,
                            code=response,
                            output="Job finished.",
                        )

                        log(
                            "Job Finished. Idling...",
                            LogColors.GRAY
                        )

                        check_for_next_request = sys.stdin.read().strip()

                        if not check_for_next_request:
                            async_logger.stop()
                            break

                        initial_request = check_for_next_request
                        request = (
                            f"{Constants.PROMPT_PREFIX}"
                            f"{check_for_next_request}"
                            f"{Constants.PROMPT_SUFFIX}"
                        )
                        prompts_sent_in_current_chat = 0
                        latest_code = ""
                        latest_output = ""
                        continue

                    latest_code = response
                    latest_output = run_python_code(response)

                    async_logger.log(
                        "code_executed",
                        prompt_number=prompts_sent_in_current_chat,
                        code=latest_code,
                        output=latest_output,
                    )

                    log(
                        f"ROLLOVER OUTPUT:\n{latest_output}",
                        LogColors.CYAN
                    )

                # The next normal Gemini prompt is generated from the latest
                # Python execution result.
                request = latest_output

                time.sleep(4)  # throttle usage
                continue

            except PlaywrightError as e:

                if "closed" in str(e).lower():

                    try:
                        state = reconnect(p)
                        request = (
                            f"{Constants.PROMPT_PREFIX}"
                            f"{initial_request}"
                            f"{Constants.PROMPT_SUFFIX}"
                        )

                    except Exception as fatal:

                        log(
                            f"Recovery failed: {fatal}",
                            LogColors.RED
                        )
                else:

                    request = (
                        f"Playwright Engine Error: {e}"
                    )


            except KeyboardInterrupt:
                try:
                    async_logger.stop()
                except Exception:
                    pass

                log(
                    f"Interrupted by user.",
                    LogColors.RED
                )

                try:
                    if 'state' in locals() and 'page' in state and is_generating(state["page"]):
                        log("Stopping active Gemini generation...", LogColors.YELLOW)
                        STOP_RESPONSE_BUTTON(state["page"]).click(timeout=3000)
                except Exception as ex:
                    log(f"Could not stop generation on exit: {ex}", LogColors.YELLOW)

                try:
                    p.stop()
                except Exception:
                    pass

                kill_cdp_browser()

                sys.exit(0)

            except Exception as e:

                try:
                    async_logger.log(
                        "error",
                        error=str(e),
                        prompt_number=prompts_sent_in_current_chat,
                    )
                except Exception:
                    pass

                log(
                    f"Loop error caught: {e}",
                    LogColors.RED
                )

                request = (str(e))

                time.sleep(2)
                continue


if __name__ == "__main__":
    main()


# saving this shit for later
# number of user sent prompts (how many messages we sent)
# page.locator("user-query-content").count()