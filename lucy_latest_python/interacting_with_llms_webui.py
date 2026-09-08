import time
from playwright.sync_api import expect, sync_playwright, Error as PlaywrightError
from utils.ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from utils.lucy_logging import log, LogColors
import utils.Constants as Constants
import subprocess
import sys
import re
import ast





# -----------------------------------------------------------------------------
# DOM locators
# Keep the complete Playwright locator expressions centralized here so each
# target can be replaced in one place if LLM / Chrome UI markup changes.
# -----------------------------------------------------------------------------
PRIMARY_CODE_BLOCKS = lambda container: container.locator("pre code, code-block code")
FALLBACK_CODE_BLOCKS = lambda container: container.locator("code")

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
llm_url = SELECTORS["LLM_URL"]


user_prompt_prefix = "I'm trying to test something can you give me python code that helps me with "

user_prompt_suffix = " - ignore all this if the output helped me with my request and just say 'idle'"

import ast
import subprocess
import sys
import re
import psutil

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

    if not context.pages:
        page = context.wait_for_event("page")
    else:
        page = context.pages[0]

    if not page.url.startswith(llm_url):
        page.goto(llm_url, wait_until="domcontentloaded")


    page.wait_for_timeout(2000) # give the page some time to load and render the UI elements

    log(f"Connected to {LLM_SELECTED}.", LogColors.GREEN)

    return {
        "browser": browser,
        "context": context,
        "page": page,
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
    
    # 3. Force click via DOM if standard click fails in background
    try:
        button.click(timeout=3000)
    except Exception:
        button.evaluate("btn => btn.click()")

    # 4. Fallback verification
    try:
        expect(composer).to_be_empty(timeout=5000)
    except AssertionError:
        composer.press("Enter")
        expect(composer).to_be_empty(
            timeout=5000, 
            message="Failed to submit request via UI."
        )


def extract_code(page):
    wait_for_ready(page)

    turns = RESPONSE_TURNS(page)
    if turns.count() == 0:
        raise RuntimeError("No model response found.")
            
    newest = turns.nth(turns.count() - 1)
    blocks = PRIMARY_CODE_BLOCKS(newest)
        
    if blocks.count() == 0:
        blocks = FALLBACK_CODE_BLOCKS(newest)
            
    if blocks.count() == 0:
        
        raise RuntimeError(
            "Put 'idle' in a code block please if we are done."
        )

    if blocks.count() > 1:
        raise RuntimeError(
            "Just give me 1 code block please."
        )

    return blocks.first.inner_text(
        timeout=30000
    ).strip()


def main():

#     out = run_python_code("""name = input("Enter your name: ")
# print(f"Hi, {name}! Your Python test was successful.")""")
#     print(out)
#     exit(0)


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


        initial_request = input(
            "Enter a task/goal to achieve: "
        ).strip()

        if not initial_request:
            return

        request =  f"{user_prompt_prefix}{initial_request}{user_prompt_suffix}"

        while True:
            try:
                if not is_cdp_port_active(Constants.PORT):
                   state = reconnect(p)

                if not request.strip():
                    request = (
                        "No execution output was captured. "
                        "Try again."
                    )

                send_request(
                    state["page"],
                    request
                )

                log(
                    f"Request sent.",
                    LogColors.GREEN
                )


                code = extract_code(
                    state["page"]
                )


                if code.lower().strip() == "idle":

                    log(
                        f"Job Finished. Idling...",
                        LogColors.GRAY
                    )

                    check_for_next_request = input(
                        "Enter next task: "
                    ).strip()

                    if not check_for_next_request:
                        break

                    request = f"{user_prompt_prefix}{check_for_next_request}{user_prompt_suffix}"

                    continue


                request = run_python_code(code)

                log(
                    f"OUTPUT:\n{request}",
                    LogColors.CYAN
                )
                time.sleep(2)
                continue


            except PlaywrightError as e:

                if "closed" in str(e).lower():

                    try:
                        state = reconnect(p)
                        request = initial_request

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

                log(
                    f"Interrupted by user.",
                    LogColors.RED
                )

                p.stop()
                break

            except Exception as e:

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

