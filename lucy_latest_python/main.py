import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from lucy_logging import log, LogColors
from concurrent.futures import ProcessPoolExecutor, TimeoutError
import task_runner  # Pre-loads imports on process initialization


# Configuration
PORT = 9223
GEMINI_GEM_URL = "https://gemini.google.com/gem/9cbc7f7cf497"
SCRIPT_DIR = Path(__file__).resolve().parent

CYAN, GREEN, YELLOW, RED, GRAY, RESET = (
    "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"
)





class ProcessPoolPythonExecutor:
    """Handles isolated Python script execution via ProcessPoolExecutor."""

    @staticmethod
    def run(script_content: str, max_runtime: float = 300.0) -> str:
        with ProcessPoolExecutor(max_workers=1) as executor:
            future = executor.submit(task_runner.execute_code, script_content)
            try:
                return future.result(timeout=max_runtime)
            except TimeoutError:
                return (
                    f"EXECUTION_STATUS=FAILED\n"
                    f"COMMAND_EXIT_CODE=124\n"
                    f"ERROR_TYPE=TimeoutError\n"
                    f"ERROR_LINE=Unknown\n"
                    f"FULL_TRACEBACK:\nCommand exceeded max runtime of {max_runtime}s."
                )







class GeminiController:
    """Manages Playwright interaction with the Gemini web interface."""
    
    def __init__(self, p, endpoint_url):
        self.p = p
        self.endpoint_url = endpoint_url
        self.browser = None
        self.context = None
        self.page = None
        self.connect()

    def connect(self):
        print(f"{YELLOW}Connecting to CDP...{RESET}")
        self.browser = self.p.chromium.connect_over_cdp(self.endpoint_url, no_defaults=True)
        self.context = self.browser.contexts[0]
        
        # 1. Fallback to waiting for existing targets if pages list is initially empty
        if not self.context.pages:
            self.context.wait_for_event("page")

        # 2. Grab the primary page (the existing window instance)
        self.page = self.context.pages[0]


        # 3. Navigate if it isn't already at the target URL
        if not self.page.url.startswith(GEMINI_GEM_URL):
            self.page.goto(GEMINI_GEM_URL, wait_until="domcontentloaded")
            
        self.page.emulate_media(color_scheme="light")
        print(f"{GREEN}Connected to Gemini.{RESET}")

        #TODO ADJUST PAGE ZOOM FOR THE COMPRESSED PREVIEW WINDOW WHEN LUCY IS PERFORMING WEB RELATED TASKS
        
        zoom = self.page.evaluate("""() => {
            document.body.style.zoom = 0.3
            const rawZoom = window.getComputedStyle(document.body).zoom;
            return rawZoom ? parseFloat(rawZoom) : 1.0;
        }""")

        print(f"Current page zoom: {zoom}")


    def reconnect(self):
        print(f"{RED}Target closed. Attempting recovery...{RESET}")
        if not is_cdp_port_active(PORT):
            raise RuntimeError(f"Port {PORT} unavailable.")
        self.connect()

    def _is_generating(self):
        try:
            return self.page.locator('button[aria-label="Stop response"], button.stop-generating-button').first.is_visible()
        except PlaywrightError:
            raise

    def wait_for_ready(self):
        while self._is_generating():
            time.sleep(0.5)

    def send_request(self, request):
        self.page.bring_to_front()
        self.wait_for_ready()
        
        composer = self.page.locator('div.new-input-ui.ql-editor, div.ql-editor[contenteditable="true"]').first
        composer.wait_for(state="visible", timeout=30000)
        
        composer.click(force=True)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.page.keyboard.insert_text(request)

        btn = self.page.locator('button.send-button, button[aria-label*="Send"], button[aria-label*="Submit"]').first
        btn.wait_for(state="visible", timeout=30000)

        for _ in range(3):
            btn.click(force=True)
            self.page.wait_for_timeout(750)
            if not composer.inner_text().strip():
                return
            composer.click(force=True)
            self.page.wait_for_timeout(250)

        composer.click(force=True)
        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(750)
        if composer.inner_text().strip():
            raise RuntimeError("Failed to submit request via UI.")

    def extract_code(self):
        self.wait_for_ready()
        self.page.wait_for_timeout(1000)
        
        turns = self.page.locator('message-content, model-response, div.model-response, .response-container')
        if turns.count() == 0:
            raise RuntimeError("No model response found.")
            
        newest = turns.nth(turns.count() - 1)
        blocks = newest.locator("pre code, code-block code")
        
        if blocks.count() == 0:
            blocks = newest.locator("code")
            
        if blocks.count() == 0:
            return None
        if blocks.count() > 1:
            raise RuntimeError("Returned multiple code blocks.")
            
        return blocks.first.inner_text(timeout=30000).strip()


def main():
    try:
        chrome_state = launch_lucy_chrome(preferred_port=PORT)
        endpoint_url = chrome_state["url"]
    except Exception as e:
        log(f"Failed to init Chrome: {e}", LogColors.RED)
        return

    if not is_cdp_port_active(PORT):
        print(f"{RED}Browser unreachable. Exiting.{RESET}")
        return

    initial_request = input("Enter a task/goal to achieve: ").strip()
    if not initial_request:
        return

    with sync_playwright() as p:
        try:
            gemini = GeminiController(p, endpoint_url)
        except Exception as e:
            print(f"{RED}Connection error: {e}{RESET}")
            return

        request = initial_request

        while True:
            try:
                if not is_cdp_port_active(PORT):
                    print(f"{RED}Browser died. Exiting.{RESET}")
                    break

                if not request or not request.strip():
                    request = "No execution output was captured. Try again."

                gemini.send_request(request)
                print(f"{GREEN}Request sent.{RESET}")

                code = gemini.extract_code()
                
                if not code:
                    print(f"{YELLOW}No code found.{RESET}")
                    request = "Return exactly one Python code block and nothing else."
                    continue

                if code.lower().strip().strip('"').strip("'") == "idle":
                    print(f"{GRAY}Goal completed. Idling...{RESET}")
                    request = input("Enter next task: ").strip()
                    if not request:
                        break
                    continue

                request = ProcessPoolPythonExecutor.run(code)

                print(f"{CYAN}OUTPUT:\n{request}\n{RESET}")

            except PlaywrightError as e:
                if "closed" in str(e).lower():
                    try:
                        gemini.reconnect()
                        request = initial_request # Reset to baseline or handle context reload
                    except Exception as fatal:
                        print(f"{RED}Recovery failed: {fatal}{RESET}")
                        time.sleep(2)
                else:
                    request = f"Playwright Engine Error: {e}"
            
            except KeyboardInterrupt:
                print(f"{RED}\nInterrupted by user.{RESET}")
                break
                
            except Exception as e:
                print(f"{RED}Loop error caught: {e}{RESET}")
                request = f"The execution engine encountered this error:\n{str(e)}"

if __name__ == "__main__":
    main()