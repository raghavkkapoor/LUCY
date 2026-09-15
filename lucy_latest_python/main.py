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
import signal
import traceback

from utils.gui import LucyGUI

# Playwright & LLM Automation Imports
from playwright.sync_api import expect, sync_playwright, Error as PlaywrightError
from utils.CloseLucyBrowser9223 import kill_cdp_browser
from utils.gemini_usage import get_gemini_usage
from utils.ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from utils.lucy_logging import log, LogColors
import utils.Constants as Constants

# ---------------------------------------------------------
# LLM AUTOMATION UTILITIES & SELECTORS
# ---------------------------------------------------------
LLM_SELECTED = "gemini"

def check_usage_and_warn(usage_page):
    if not get_gemini_usage:
        log("[Usage Monitor] gemini_usage module not available. Skipping check.", LogColors.YELLOW)
        return
    try:
        usage_data = get_gemini_usage(usage_page)
        current_usage_str = int(usage_data.get("daily_usage_remaining"))
        if current_usage_str >= 0:
            if current_usage_str > 80:
                log(f"[Usage Monitor Error] Lucy has reached high usage limits. Current usage is at {current_usage_str}%.", LogColors.RED)
                sys.exit(1)
        else:
            log("[Usage Monitor] Could not parse numeric usage percentage.", LogColors.YELLOW)
    except Exception as e:
        log(f"[Usage Monitor Error] Failed to retrieve usage metrics: {e}", LogColors.YELLOW)

def get_llm_selectors(llm):
    llm = llm.lower().strip()
    if llm == "chatgpt":
        return {
            "STOP_RESPONSE_BUTTON": lambda page: page.get_by_test_id("stop-button").first,
            "COMPOSER": lambda page: page.get_by_role("textbox", name="Chat with ChatGPT"),
            "SEND_BUTTON": lambda page: page.locator('button.send-button, button[aria-label*="Send"], button[aria-label*="Submit"]').first,
            "RESPONSE_TURNS": lambda page: page.locator('[data-message-author-role="assistant"]'),
            "LLM_URL": Constants.CHATGPT_URL,
        }
    elif llm == "gemini":
        return {
            "STOP_RESPONSE_BUTTON": lambda page: page.get_by_role("button", name="Stop response").first,
            "COMPOSER": lambda page: page.locator("rich-textarea .ql-editor").first,
            "SEND_BUTTON": lambda page: page.locator('button.send-button, button[aria-label*="Send"], button[aria-label*="Submit"]').first,
            "RESPONSE_TURNS": lambda page: page.locator('message-content, model-response, div.model-response, .response-container'),
            "LLM_URL": Constants.GEMINI_GEM_URL,
        }
    raise ValueError(f"Unsupported LLM: {llm}.")

SELECTORS = get_llm_selectors(LLM_SELECTED)
STOP_RESPONSE_BUTTON = SELECTORS["STOP_RESPONSE_BUTTON"]
COMPOSER = SELECTORS["COMPOSER"]
SEND_BUTTON = SELECTORS["SEND_BUTTON"]
RESPONSE_TURNS = SELECTORS["RESPONSE_TURNS"]
PRIMARY_CODE_BLOCKS = lambda container: container.locator("pre code, code-block code")
FALLBACK_CODE_BLOCKS = lambda container: container.locator("code")
llm_url = SELECTORS["LLM_URL"]

MAX_PROMPTS_PER_CHAT = 10
# TODO: Write a new file for each days worth of interactions instead of stuffing it all in one file.
ASYNC_LOG_FILE = Constants.PROJECT_DIR.joinpath("interactions.jsonl")

class AsyncLLMLogger:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, name="Lucy-LLM-Logger", daemon=True)

    def start(self):
        self._thread.start()

    def log(self, event_type: str, **data):
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
                    with open(self.file_path, "a", encoding="utf-8", buffering=1) as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"[Async Logger Error] {e}")
                finally:
                    self._queue.task_done()
        except Exception as e:
            print(f"[Async Logger Fatal Error] {e}")

    def stop(self):
        self._stop_event.set()
        self._thread.join(timeout=5)

def build_rollover_request(original_request: str, latest_code: str, latest_output: str) -> str:
    return (
        f"{Constants.PROMPT_PREFIX}{original_request}{Constants.PROMPT_SUFFIX}\n\n"
        "IMPORTANT: This is a continuation in a fresh chat because the previous chat reached its prompt limit.\n\n"
        "LATEST PYTHON CODE THAT WAS EXECUTED:\n"
        "```python\n"
        f"{latest_code}\n"
        "```\n\n"
        "OUTPUT FROM THAT CODE:\n"
        f"{latest_output}\n\n"
        "Continue working on the original task from this state. Do not restart the work from scratch."
    )

def open_fresh_llm_chat(state, logger, original_request, latest_code, latest_output):
    old_page = state["page"]
    logger.log("chat_rollover", reason=f"Reached {MAX_PROMPTS_PER_CHAT} prompts", previous_url=old_page.url)
    new_page = old_page
    new_page.goto(llm_url, wait_until="domcontentloaded")
    new_page.wait_for_timeout(2000)
    COMPOSER(new_page).wait_for(state="visible", timeout=30000)

    rollover_request = build_rollover_request(original_request, latest_code, latest_output)
    send_request(new_page, rollover_request)
    logger.log("prompt_sent", prompt_number=1, rollover=True, prompt=rollover_request)
    return new_page, 1
def run_python_code(script_content: str, max_runtime: float = 120.0) -> str:
    try:
        tree = ast.parse(script_content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'input':
                return "taking input from the user is restricted in this sandbox environment"
    except SyntaxError as e:
        return f"SyntaxError: {e}"

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
            return "Error: Script timed out."

        if process.returncode != 0:
            return stderr.strip() if stderr.strip() else f"Process failed with return code {process.returncode}"

        combined_output = f"{stdout}{stderr}".strip()
        return combined_output if combined_output else "Could you verify if that worked? I can't tell since there's no output."
    except Exception as e:
        return f"Error: {str(e)}"

def connect_to_LLM(p, endpoint_url):
    log(f"Connecting to Gemini at {endpoint_url}...", LogColors.YELLOW)
    try:
        browser = p.chromium.connect_over_cdp(endpoint_url, no_defaults=True)
    except Exception:
        chrome_state = launch_lucy_chrome(preferred_port=Constants.PORT)
        endpoint_url = chrome_state["url"]
        browser = p.chromium.connect_over_cdp(endpoint_url, no_defaults=True)

    context = browser.contexts[0]
    chat_page = None
    for page in context.pages:
        if page.url.startswith(llm_url):
            chat_page = page
            break

    if chat_page is None:
        chat_page = context.new_page()
        chat_page.goto(llm_url, wait_until="domcontentloaded")
        chat_page.wait_for_timeout(2000)

    log(f"Connected to {LLM_SELECTED}.", LogColors.GREEN)
    return {"browser": browser, "context": context, "page": chat_page, "endpoint_url": endpoint_url}

def reconnect(playwright_instance):
    log("LLM NOT FOUND:", LogColors.RED)
    if not is_cdp_port_active(Constants.PORT):
        log("Browser not found. Attempting hard recovery...", LogColors.YELLOW)
        chrome_state = launch_lucy_chrome(preferred_port=Constants.PORT)
        state = connect_to_LLM(playwright_instance, chrome_state["url"])
    else:
        log("LLM context not found. Attempting soft recovery...", LogColors.YELLOW)
        state = connect_to_LLM(playwright_instance, f"http://127.0.0.1:{Constants.PORT}")

    if not state:
        log("Recovery failed. Please restart the application.", LogColors.RED)
        sys.exit(1)
    return state

def is_generating(page):
    return STOP_RESPONSE_BUTTON(page).is_visible()

def wait_for_ready(page):
    while is_generating(page):
        time.sleep(0.8)



def send_request(page, request):
    wait_for_ready(page)
    composer = COMPOSER(page)
    composer.wait_for(state="visible", timeout=30000)
    composer.focus()

    # Force set text via evaluate if normal fill fails or leaves text
    composer.evaluate(f"""el => {{
        el.focus();
        if (el.isContentEditable) {{
            el.innerHTML = '<p>' + {json.dumps(request)} + '</p>';
        }} else {{
            el.value = {json.dumps(request)};
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }}""")

    button = SEND_BUTTON(page)
    button.wait_for(state="visible", timeout=30000)
    try:
        button.click(timeout=3000)
    except Exception:
        button.evaluate("btn => btn.click()")

    # Force clear/submit via Enter instead of hard failing on to_be_empty
    try:
        expect(composer, "Failed to submit request via UI.").to_be_empty(timeout=3000)
    except AssertionError:
        composer.press("Enter")
        # Force clear via JS if it's still stubborn so the next prompt loop won't break
        composer.evaluate("""el => {
            if (el.isContentEditable) {
                el.innerHTML = '<p><br></p>';
            } else {
                el.value = '';
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }""")
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
            if Constants.MAGIC_STOP_WORD in newest.inner_html().lower():
                return Constants.MAGIC_STOP_WORD

    if blocks.count() > 1:
        raise RuntimeError("Just give me 1 code block.")

    return blocks.first.inner_text(timeout=30000).strip()

task_queue = queue.Queue()


# ---------------------------------------------------------
# BACKGROUND WORKER LOOP (MERGED ENGINE)
# ---------------------------------------------------------
def llm_worker_loop(gui):
    try:
        chrome_state = launch_lucy_chrome(preferred_port=Constants.PORT)

        endpoint_url = chrome_state["url"]

    except Exception as e:
        log(f"Failed to init Chrome: {e}", LogColors.RED)
        gui.post("startup_failed", str(e))
        return

    if not is_cdp_port_active(Constants.PORT):
        log("Browser unreachable. Exiting worker thread.", LogColors.RED)
        gui.post("startup_failed", "Chrome is unreachable.")
        return

    with sync_playwright() as p:
        state = connect_to_LLM(p, endpoint_url)
        usage_page = state["context"].new_page()

        check_usage_and_warn(usage_page)

        async_logger = AsyncLLMLogger(ASYNC_LOG_FILE)
        async_logger.start()
        gui.post("ready")

        while True:
            # Wait for user input from UI queue
            initial_request = task_queue.get()
            if initial_request is None:
                async_logger.stop()
                break

            # Mark state as busy and disable UI elements
            gui.post("set_busy", True)

            request = f"{Constants.PROMPT_PREFIX}{initial_request}{Constants.PROMPT_SUFFIX}"
            prompts_sent_in_current_chat = 0
            latest_code = ""
            latest_output = ""

            task_id = object()
            title_summary = initial_request[:30] + "..." if len(initial_request) > 30 else initial_request
            gui.post("show_notification", task_id, title_summary, "Incoming...")
            completed = False

            try:
                while True:
                    try:
                        if not is_cdp_port_active(Constants.PORT):
                            state = reconnect(p)

                        if not request.strip():
                            request = "No execution output was captured. Try again."

                        check_usage_and_warn(usage_page)

                        # ---------------------------------------------------------
                        # 1. ROLLOVER CHECK BEFORE SENDING
                        # ---------------------------------------------------------
                        if prompts_sent_in_current_chat >= MAX_PROMPTS_PER_CHAT:
                            new_page, prompts_sent_in_current_chat = open_fresh_llm_chat(
                                state,
                                async_logger,
                                initial_request,
                                latest_code,
                                latest_output,
                            )
                            state["page"] = new_page
                            log("Started fresh Gemini chat and transferred latest state.", LogColors.YELLOW)
                            # open_fresh_llm_chat sends the rollover prompt
                        else:
                            # Normal prompt dispatch
                            send_request(state["page"], request)
                            prompts_sent_in_current_chat += 1
                            async_logger.log(
                                "prompt_sent",
                                prompt_number=prompts_sent_in_current_chat,
                                rollover=False,
                                prompt=request,
                            )
                            log(f"Attempt ({prompts_sent_in_current_chat}/{MAX_PROMPTS_PER_CHAT}).", LogColors.GREEN)

                        # ---------------------------------------------------------
                        # 2. SINGLE UNIFIED EXTRACTION & EXECUTION
                        # ---------------------------------------------------------
                        # wait for the page to process the request before extracting the latest code since its causing a race condition by pre fetching the last response and ignoring THIS prompt.
                        state["page"].wait_for_timeout(2000)

                        response = extracted_code(state["page"])

                        # Keep the last code visible when the final reply is only the stop marker.
                        if response.lower().strip() != Constants.MAGIC_STOP_WORD.lower().strip():
                            gui.post("update_notification", task_id, response)


                        # Execute code
                        latest_code = response
                        latest_output = run_python_code(response)

                        async_logger.log(
                            "code_executed",
                            prompt_number=prompts_sent_in_current_chat,
                            code=latest_code,
                            output=latest_output,
                        )


                        # Check for completion condition
                        if Constants.MAGIC_STOP_WORD in response.lower().strip():
                            async_logger.log(
                                "completion",
                                prompt_number=prompts_sent_in_current_chat,
                                code=response,
                                output="Job finished.",
                            )
                            log("Job Finished. Idling...", LogColors.GRAY)
                            completed = True
                            break

                        # Set output as next prompt request
                        request = latest_output
                        time.sleep(4)
                        continue

                    except PlaywrightError as e:
                        if "closed" in str(e).lower():
                            try:
                                state = reconnect(p)
                                request = f"{Constants.PROMPT_PREFIX}{initial_request}{Constants.PROMPT_SUFFIX}"
                            except Exception as fatal:
                                log(f"Recovery failed: {fatal}", LogColors.RED)
                        else:
                            request = f"Playwright Engine Error: {e}"
                    except Exception as e:
                        try:
                            async_logger.log("error", error=str(e), prompt_number=prompts_sent_in_current_chat)
                        except Exception:
                            pass
                        log(f"Loop error caught: {e}", LogColors.RED)
                        request = str(e)
                        time.sleep(1)
            finally:
                # Re-enable state and inputs when job finishes or terminates
                gui.post("finish_notification", task_id, "Completed" if completed else "Failed")
                gui.post("set_busy", False)


def main():
    def cleanup():
        log("Cleaning up and shutting down browser instance...", LogColors.YELLOW)
        task_queue.put(None)
        try:
            kill_cdp_browser()
        except Exception as exc:
            log(f"Cleanup failed: {exc}", LogColors.YELLOW)


    gui = LucyGUI(on_submit=task_queue.put, on_close=cleanup)

    def report_fatal(exc_type, exc_value, exc_tb):
        error = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log(f"[FATAL ERROR]\n{error}", LogColors.RED)
        gui.post("startup_failed", error)

    sys.excepthook = report_fatal

    def run_worker():
        try:
            llm_worker_loop(gui)
        except BaseException:
            report_fatal(*sys.exc_info())

    signal.signal(signal.SIGINT, lambda sig, frame: gui.post("close"))
    worker_thread = threading.Thread(target=run_worker, name="Lucy-Worker", daemon=True)
    worker_thread.start()
    gui.run()


if __name__ == "__main__":
    main()
