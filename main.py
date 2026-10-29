# Standard imports
import sys
import time
import subprocess
import os
import ast
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event, get_ident

IS_DEBUG_MODE = True

# colors
BACKGROUND = "#222222"
FORE = "#bb9ca4"
BLUE = "#00E0FF"

def run_python_worker():
    import traceback

    try:
        code = sys.stdin.read()
        namespace = {"__name__": "__main__"}
        exec(compile(code, "<lucy-generated>", "exec"), namespace)
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1


if "--python-worker" in sys.argv:
    sys.exit(run_python_worker())


# Auto-install Playwright browser drivers if missing
try:
    import playwright
except ImportError:
    pass

# Run browser asset installation silently inside the compiled app
if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    subprocess.run(
        ["playwright", "install", "chromium"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

from playwright.sync_api import expect, sync_playwright, Error as PlaywrightError
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import TextArea, OptionList, Static, RichLog

# Util imports
from helpers.lucy_logging import LogColors
from helpers.CloseLucyBrowser9223 import kill_cdp_browser
from helpers.ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from helpers.Constants import *

# dont change to another llm otherwise everything will break.
LLM_SELECTED = "gemini"

SHUTDOWN = False
ACTIVE_PROCESS = None
TASK_QUEUE = Queue()
STOP_REQUESTED = Event()
GUI_APP = None



# ============================================================
# GUI LOGGING
# ============================================================

def _gui_log(message, color=None, debug=False):
    """Write diagnostic logs only in debug mode."""
    if not IS_DEBUG_MODE:
        return

    app = GUI_APP
    text = str(message)

    if app is not None:
        app.write_log(text, debug=debug, color=color)
    else:
        print(text, flush=True)


def log(message, color=None):
    _gui_log(message, color=color)


def debug_log(message):
    _gui_log(message, debug=True)


def user_log(message):
    """Always show user prompts; prefix them only in debug mode."""
    text = str(message)
    if IS_DEBUG_MODE:
        text = f"USER PROMPT: {text}"

    app = GUI_APP
    if app is not None:
        app.write_log(text, color="white")
    else:
        print(text, flush=True)


# ============================================================
# CLEANUP
# ============================================================

def cleanup(page_state=None, playwright=None):
    """Perform best-effort, idempotent shutdown of Lucy's resources."""
    global SHUTDOWN, ACTIVE_PROCESS

    if SHUTDOWN:
        raise SystemExit(0)

    SHUTDOWN = True
    debug_log("Shutting down...\n")

    process = ACTIVE_PROCESS

    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=2)
            except Exception:
                pass
        except Exception as exc:
            print(f"[LUCY] Child-process cleanup warning: {exc}", flush=True)

    if page_state is not None:
        try:
            page = page_state.get("page")
            if page is not None and not page.is_closed() and is_generating(page):
                STOP_RESPONSE_BUTTON(page).click(timeout=1000)
        except Exception:
            pass

    if playwright is not None:
        try:
            playwright.stop()
        except Exception:
            pass

    try:
        kill_cdp_browser()
    except Exception as exc:
        print(f"[LUCY] Browser cleanup warning: {exc}", flush=True)

    print("[LUCY] Goodbye :)", flush=True)
    raise SystemExit(0)


def read_task(prompt_text="Enter a computer task"):
    """Wait for a task submitted through the GUI."""
    while not STOP_REQUESTED.is_set():
        try:
            task = TASK_QUEUE.get(timeout=0.25)
            return task or ""
        except Empty:
            continue

    return ""


# ============================================================
# PYTHON EXECUTION
# ============================================================
def get_python_command():
    """Use the project's interpreter or Lucy's bundled runtime."""
    if not getattr(sys, "frozen", False):
        return [sys.executable]

    return [sys.executable, "--python-worker"]

# ============================================================
# LLM SELECTORS
# ============================================================

def get_llm_selectors(llm):
    llm = llm.lower().strip()

    if llm == "chatgpt":
        return {
            "STOP_RESPONSE_BUTTON": lambda page: page.get_by_test_id(
                "stop-button"
            ).first,

            "COMPOSER": lambda page: page.get_by_role(
                "textbox",
                name="Chat with ChatGPT",
            ),

            "SEND_BUTTON": lambda page: page.locator(
                'button.send-button, '
                'button[aria-label*="Send"], '
                'button[aria-label*="Submit"]'
            ).first,

            "RESPONSE_TURNS": lambda page: page.locator(
                '[data-message-author-role="assistant"]'
            ),

            "LLM_URL": CHATGPT_URL,
        }

    if llm == "gemini":
        return {
            "STOP_RESPONSE_BUTTON": lambda page: page.get_by_role(
                "button",
                name="Stop response",
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
                'message-content, model-response, '
                'div.model-response, .response-container'
            ),

            "LLM_URL": GEMINI_GEM_URL,
        }

    raise ValueError(
        f'Unsupported LLM: {llm}. Use "chatgpt" or "gemini".'
    )


SELECTORS = get_llm_selectors(LLM_SELECTED)

STOP_RESPONSE_BUTTON = SELECTORS["STOP_RESPONSE_BUTTON"]
COMPOSER = SELECTORS["COMPOSER"]
SEND_BUTTON = SELECTORS["SEND_BUTTON"]
RESPONSE_TURNS = SELECTORS["RESPONSE_TURNS"]

PRIMARY_CODE_BLOCKS = lambda container: container.locator(
    "pre code, code-block code"
)
FALLBACK_CODE_BLOCKS = lambda container: container.locator("code")

llm_url = SELECTORS["LLM_URL"]


def build_rollover_request(original_request, latest_code, latest_output):
    """Build continuation context for a fresh LLM chat session."""
    return FORM_CONTEXT_PROMPT(
        original_request,
        latest_code,
        latest_output,
    )


def open_fresh_llm_chat(state, original_request, latest_code, latest_output):
    """Open a fresh chat and send continuation context."""
    new_page = state["page"]

    new_page.goto(llm_url, wait_until="domcontentloaded")
    new_page.wait_for_timeout(2000)

    COMPOSER(new_page).wait_for(state="visible", timeout=30000)

    rollover_request = build_rollover_request(
        original_request,
        latest_code,
        latest_output,
    )

    send_request(new_page, rollover_request)

    return new_page, 1


# ============================================================
# GENERATED CODE EXECUTION
# ============================================================

def run_python_code(scripts: list, max_runtime: float = 120.0) -> str:
    """Execute generated code using the project or bundled Python runtime."""
    global ACTIVE_PROCESS

    if not scripts:
        return "No Python scripts were provided."

    for script_content in scripts:
        try:
            tree = ast.parse(script_content)

            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "input"
                ):
                    return (
                        "Execution blocked: input() is not allowed "
                        "in generated code."
                    )
        except SyntaxError:
            # Let Python report the syntax error during execution.
            pass

        process = None

        try:
            frozen = getattr(sys, "frozen", False)
            command = get_python_command()

            if frozen:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(Path(__file__).resolve().parent),
                )
                ACTIVE_PROCESS = process
                stdout, stderr = process.communicate(
                    input=script_content,
                    timeout=max_runtime,
                )
            else:
                command.extend(["-u", "-c", script_content])
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(Path(__file__).resolve().parent),
                )
                ACTIVE_PROCESS = process
                stdout, stderr = process.communicate(timeout=max_runtime)

            combined = "\\n".join(
                part for part in (stdout, stderr) if part
            ).strip()

            if process.returncode != 0:
                return (
                    f"Python exited with code {process.returncode}.\\n"
                    f"Full output/traceback:\\n"
                    f"{combined or '(no output)'}"
                )

            return combined or "Execution completed."

        except subprocess.TimeoutExpired:
            if process is not None:
                process.kill()
                stdout, stderr = process.communicate()
            else:
                stdout, stderr = "", ""

            return (
                f"Execution timed out after {max_runtime} seconds.\\n"
                f"STDOUT:\\n{stdout or ''}\\n"
                f"STDERR:\\n{stderr or ''}"
            )

        except KeyboardInterrupt:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
            raise

        except Exception as exc:
            return (
                f"Execution infrastructure error: "
                f"{type(exc).__name__}: {exc}"
            )

        finally:
            ACTIVE_PROCESS = None

    return "No Python scripts were provided."


# ============================================================
# BROWSER CONNECTION AND RECOVERY
# ============================================================

def connect_to_LLM(p, endpoint_url):
    try:
        browser = p.chromium.connect_over_cdp(
            endpoint_url,
            no_defaults=True,
        )

    except Exception:
        chrome_state = launch_lucy_chrome(
            preferred_port=PORT
        )

        endpoint_url = chrome_state["url"]

        browser = p.chromium.connect_over_cdp(
            endpoint_url,
            no_defaults=True,
        )

    context = browser.contexts[0]
    all_pages = context.pages
    chat_page = None

    for page in all_pages:
        if page.url.startswith(llm_url):
            chat_page = page
            break

    if chat_page is None:
        chat_page = context.new_page()
        chat_page.goto(llm_url, wait_until="domcontentloaded")
        chat_page.wait_for_timeout(2000)

    debug_log(f"✓ Connected to LLM at {endpoint_url}.\n")


    return {
        "browser": browser,
        "context": context,
        "page": chat_page,
        "endpoint_url": endpoint_url,
    }


def reconnect(playwright_instance):
    if not is_cdp_port_active(PORT):
        debug_log("Browser context not found. Attempting hard recovery...\n")

        chrome_state = launch_lucy_chrome(
            preferred_port=PORT
        )

        endpoint_url = chrome_state["url"]

    else:
        debug_log("LLM context not found. Attempting soft recovery...\n")
        endpoint_url = f"http://127.0.0.1:{PORT}"

    state = connect_to_LLM(playwright_instance, endpoint_url)

    if not state:
        debug_log("ERROR: Recovery failed. Please restart the application.\n")
        raise RuntimeError("Browser recovery failed.")

    return state


def is_generating(page):
    return STOP_RESPONSE_BUTTON(page).is_visible()


def wait_for_ready(page):
    while is_generating(page):
        if STOP_REQUESTED.is_set():
            raise InterruptedError("Lucy is shutting down.")
        time.sleep(0.8)


def send_request(page, request):
    """Send one prompt and return after submission is confirmed."""
    wait_for_ready(page)

    composer = COMPOSER(page)
    composer.wait_for(state="visible", timeout=30000)

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

    page.wait_for_timeout(500)

    not_now = page.get_by_role("button", name="Not now")

    if not_now.is_visible():
        not_now.click(timeout=3000)

    try:
        expect(composer).to_be_empty(timeout=5000)
    except AssertionError:
        composer.press("Enter")
        expect(composer).to_be_empty(
            timeout=5000,
            message="Failed to submit request via UI.",
        )

    return True


def extracted_code(page):
    wait_for_ready(page)

    turns = RESPONSE_TURNS(page)

    if turns.count() == 0:
        raise RuntimeError("No response was found.")

    newest = turns.nth(turns.count() - 1)
    blocks = PRIMARY_CODE_BLOCKS(newest)

    if blocks.count() == 0:
        fallback_blocks = FALLBACK_CODE_BLOCKS(newest)

        if fallback_blocks.count() == 0:
            if MAGIC_STOP_WORD in newest.inner_html().lower():
                return MAGIC_STOP_WORD

            raise RuntimeError(
                "Expected executable Python code blocks or "
                f"{MAGIC_STOP_WORD} without a code block."
            )

        blocks = fallback_blocks

    return [
        code.inner_text(timeout=30000).strip()
        for code in blocks.all()
    ]


# ============================================================
# MAIN AGENT LOOP
# ============================================================

def main():
    try:
        chrome_state = launch_lucy_chrome(
            preferred_port=PORT
        )
        endpoint_url = chrome_state["url"]

    except Exception as exc:
        debug_log(f"ERROR: Failed to initialize Chrome: {exc}\n")
        return

    if not is_cdp_port_active(PORT):
        debug_log("ERROR: Browser unreachable. Exiting.\n")
        return

    state = None
    p = None

    try:
        with sync_playwright() as p:
            state = connect_to_LLM(p, endpoint_url)

            initial_request = read_task()

            if not initial_request or STOP_REQUESTED.is_set():
                return

            request = (
                f"{PROMPT_PREFIX}"
                f"{initial_request}"
                f"{PROMPT_SUFFIX}"
            )

            prompts_sent_in_current_chat = 0
            latest_code = ""
            latest_output = ""

            debug_log(f"> Working on request: {initial_request}...\n")

            while not STOP_REQUESTED.is_set():
                try:
                    if not is_cdp_port_active(PORT):
                        state = reconnect(p)

                    if not request.strip():
                        request = (
                            "No execution output was captured. Try again."
                        )

                    send_request(state["page"], request)
                    prompts_sent_in_current_chat += 1

                    debug_log(
                        "Request sent "
                        f"({prompts_sent_in_current_chat}/"
                        f"{MAX_PROMPTS_PER_CHAT}).\n"
                    )

                    response = extracted_code(state["page"])

                    if not isinstance(response, list):
                        if (
                            MAGIC_STOP_WORD
                            in response.lower().strip()
                        ):
                            debug_log("✓ Finished working on task.\n")

                            next_request = read_task(
                                "Enter the next computer task"
                            )

                            if not next_request or STOP_REQUESTED.is_set():
                                break

                            initial_request = next_request
                            request = (
                                f"{PROMPT_PREFIX}"
                                f"{next_request}"
                                f"{PROMPT_SUFFIX}"
                            )

                            prompts_sent_in_current_chat = 0
                            latest_code = ""
                            latest_output = ""
                            continue

                    else:
                        latest_code = response
                        debug_log(f"> Running Command:\n {latest_code}\n")
                        latest_output = run_python_code(response)
                        debug_log(f"> Output:\n {latest_output}\n")

                        
                    # debug_log(
                    #     "OUTPUT BEING SENT BACK TO LLM:\n"
                    #     f"{latest_output}"
                    # )

                    if (
                        prompts_sent_in_current_chat
                        >= MAX_PROMPTS_PER_CHAT
                    ):
                        new_page, prompts_sent_in_current_chat = (
                            open_fresh_llm_chat(
                                state,
                                initial_request,
                                latest_code,
                                latest_output,
                            )
                        )

                        state["page"] = new_page

                        debug_log(
                            "Transferred session state to maintain context.\n"
                        )

                        response = extracted_code(state["page"])

                        if not isinstance(response, list):
                            if (
                                MAGIC_STOP_WORD
                                in response.lower().strip()
                            ):
                                debug_log("✓ Finished working on task.\n")
                                next_request = read_task(
                                    "Enter the next computer task"
                                )

                                if (
                                    not next_request
                                    or STOP_REQUESTED.is_set()
                                ):
                                    break

                                initial_request = next_request
                                request = (
                                    f"{PROMPT_PREFIX}"
                                    f"{next_request}"
                                    f"{PROMPT_SUFFIX}"
                                )

                                prompts_sent_in_current_chat = 0
                                latest_code = ""
                                latest_output = ""
                                continue

                        else:
                            latest_code = response
                            debug_log(f"> Running Command:\n {latest_code}\n")
                            latest_output = run_python_code(response)
                            # not needed here
                            # debug_log(latest_output)
                        debug_log(f"> Rollover Output:\n{latest_output}\n")

                    request = latest_output
                    continue

                except InterruptedError:
                    if STOP_REQUESTED.is_set():
                        break
                    raise

                except PlaywrightError as exc:
                    if "closed" in str(exc).lower():
                        try:
                            state = reconnect(p)

                            request = build_rollover_request(
                                initial_request,
                                latest_code,
                                latest_output,
                            )

                        except Exception as fatal:
                            debug_log(f"ERROR: Recovery failed: {fatal}\n")

                    else:
                        request = f"Playwright Engine Error: {exc}"

                except KeyboardInterrupt:
                    cleanup(state, p)

                except Exception as exc:
                    if STOP_REQUESTED.is_set():
                        break

                    debug_log(f"Loop error caught: {exc}\n")
                    request = str(exc)

    except KeyboardInterrupt:
        cleanup(state, p)


# ============================================================
# MULTILINE INPUT
# ============================================================

class TaskTextArea(TextArea):
    """
    Enter submits the current task.
    Shift+Enter inserts a newline.
    Other editing keys retain TextArea's default behavior.
    """

    BINDINGS = [
        Binding(
            "enter",
            "submit_task",
            "Submit task",
            priority=True,
        ),
        Binding(
            "shift+enter",
            "insert_newline",
            "Insert newline",
            priority=True,
        ),
    ]

    def action_submit_task(self):
        self.app.submit_task(self.text)

    def action_insert_newline(self):
        self.insert("\n")


# ============================================================
# TEXTUAL GUI
# ============================================================

class TheLucyProgram(App):
    """Textual interface for Lucy's agent loop."""

    CSS = """
    Screen {
        background: #222222;
        color: #FFFFFF;
        align: center middle;
    }

    /* Outer container or main application wrapper if needed, 
       or individual components centered via margin */

    #title {
        width: 100%;
        background: #222222;
        color: #b0b0b0;
        content-align: center middle;
        text-style: bold;
        border-bottom: solid #d6a7b3;
        margin-bottom: 1;
    }

    #main-area {
        height: 1fr;
        width: 95%;
        padding: 1 0;
    }

    .label {
        height: 1;
        width: 100%;
        color: #b0b0b0;
        text-style: bold;
    }

    .note-label {
        height: 1;
        width: 100%;
        color: #b0b0b0;
        text-style: none;
    }

    #cmd-input {
        dock: bottom;
        height: 6;
        width: 95vw; /* Or match 95% width with auto margins */
        background: #222222;
        color: #FFFFFF;
        border: solid #d6a7b3;
    }

    #cmd-input:focus {
        border: solid #d6a7b3;
    }

    #suggestions {
        height: 1;
        width: 100%;
        background: #222222;
        border: solid #bb9ca4;
        display: none;
        margin-bottom: 1;

    }

    #log-view {
        height: 1fr;
        width: 100%;
        background: #222222;
        border: solid #d6a7b3;
        color: #00E0FF;
        margin-bottom: 1;
    }
"""

    def compose(self) -> ComposeResult:
        with Vertical(id="main-area"):
            yield Static("LUCY - Free Computer Use Agent", id="title")

            yield Static("Session History", classes="label")

            yield RichLog(
                id="log-view",
                highlight=False,
                markup=False,
                wrap=True,
                auto_scroll=True,
            )
            # removed for now
            # yield OptionList(id="suggestions")
            yield Static(
                "> Shift + Enter to add new line",
                classes="note-label",
            )
            yield Static(
                "> 'exit' or 'quit' to close lucy",
                classes="note-label",
            )

            yield TaskTextArea(
                "",
                id="cmd-input",
                soft_wrap=True,
                tab_behavior="indent",
                placeholder="Enter a computer task here..."
            )

    def on_mount(self):
        global GUI_APP

        GUI_APP = self
        self._ui_thread_id = get_ident()
        self.query_one("#cmd-input", TaskTextArea).focus()

        # start the loop
        Thread(
            target=self._run_agent,
            daemon=True,
            name="LucyAgentLoop",
        ).start()

    def _run_agent(self):
        try:
            main()

        except SystemExit:
            pass

        except Exception as exc:
            debug_log(
                f"Fatal agent error: {type(exc).__name__}: {exc}\n",
                color=LogColors.RED,
            )

        finally:
            if not STOP_REQUESTED.is_set():
                debug_log("Agent loop stopped.\n")

    def write_log(self, message, debug=False, color=None):
        """Thread-safe activity panel writer with optional text coloring."""
        text = str(message).rstrip("\n")

        if not text:
            return

 
        try:
            if get_ident() == getattr(self, "_ui_thread_id", None):
                self._write_log_ui( text, color)
            else:
                self.call_from_thread(self._write_log_ui, text, color)
        except RuntimeError:
            pass

    def _write_log_ui(self, text, color=None):
        try:
            log_view = self.query_one("#log-view", RichLog)
            if color:
                log_view.write(text, style=str(color))
            else:
                log_view.write(text)
        except Exception:
            pass

    def on_text_area_changed(self, event: TextArea.Changed):
        return
        if event.text_area.id != "cmd-input":
            return

        query = event.text_area.text.strip().lower()
        suggestions = self.query_one("#suggestions", OptionList)

        if not query or query != "exit" and query != "quit":
            suggestions.clear_options()
            suggestions.styles.display = "none"
            return

        suggestions.clear_options()
        suggestions.add_option("exit or quit - exits the application")
        suggestions.styles.display = "block"

    def on_option_list_option_selected(
        self,
        event: OptionList.OptionSelected,
    ):
        editor = self.query_one("#cmd-input", TaskTextArea)

        editor.text = "exit"

        self.query_one("#suggestions", OptionList).styles.display = "none"
        editor.focus()

    def submit_task(self, raw_value):
        value = raw_value.strip()

        # suggestions = self.query_one("#suggestions", OptionList)
        # suggestions.styles.display = "none"

        if not value:
            return

        if value.lower() == "quit" or value.lower() == "exit":
            print("> Exiting The Lucy Program...\n")

            STOP_REQUESTED.set()
            TASK_QUEUE.put("")

            Thread(
                target=self._shutdown_lucy,
                daemon=True,
                name="LucyShutdown",
            ).start()

            self.exit()
            return

        if STOP_REQUESTED.is_set():
            return

        user_log(value)

        # Submit the entire multiline string as one task.
        TASK_QUEUE.put(value)

        editor = self.query_one("#cmd-input", TaskTextArea)
        editor.text = ""
        editor.focus()

    def _shutdown_lucy(self):
        """Shut down Lucy without overriding Textual's internal _shutdown."""
        global ACTIVE_PROCESS

        process = ACTIVE_PROCESS

        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)

            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        try:
            kill_cdp_browser()
        except Exception as exc:
            debug_log(f"> Shutdown warning: {exc}\n")




if __name__ == "__main__":
    TheLucyProgram().run()