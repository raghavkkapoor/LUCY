import time
from playwright.sync_api import expect, sync_playwright, Error as PlaywrightError
from ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from Utils.lucy_logging import log, LogColors
from concurrent.futures import ProcessPoolExecutor, TimeoutError
import task_runner
import Utils.Constants as Constants
from better_sys_prompt import system_instruction, user_prompt_prefix

def run_python_code(script_content: str, max_runtime: float = 300.0) -> str:
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
                f"FULL_TRACEBACK:\n"
                f"Command exceeded max runtime of {max_runtime}s."
            )


def connect_to_gemini(p, endpoint_url):
    log(f"Connecting to Gemini at {endpoint_url}...", LogColors.YELLOW)

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
        context.wait_for_event("page")

    page = context.pages[0]

    if not page.url.startswith(Constants.GEMINI_GEM_URL):
        page.goto(
            Constants.GEMINI_GEM_URL,
            wait_until="domcontentloaded"
        )

    page.wait_for_timeout(5000) # give the page some time to load and render the UI elements

    log(f"Connected to LLM.", LogColors.GREEN)

    system_prompt_exists = (page.get_by_text("Your goal for this convo is simple: plan, build, and test Python scripts to complete the user's goal.").count() > 0)

    if not system_prompt_exists:
        send_request(
            page,
            f"{system_instruction}"
        )

        page.wait_for_timeout(5000)

        log(f"Preloaded system instructions.", LogColors.GREEN)
    else:
        log(f"Skipped preloading system instructions. They already exist in context.", LogColors.CYAN)

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

        state = connect_to_gemini(
            playwright_instance,
            endpoint_url
        )
    else:
        log("LLM context not found. Attempting soft recovery...", LogColors.YELLOW)
        endpoint_url = f"http://127.0.0.1:{Constants.PORT}"
        state = connect_to_gemini(
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
    return page.get_by_role("button", name="Stop response").first.is_visible()


def wait_for_ready(page):
    while is_generating(page):
        time.sleep(0.8)


def send_request(page, request):

    wait_for_ready(page)

    composer = page.locator("rich-textarea .ql-editor").first
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

    button = page.locator(
        'button.send-button, '
        'button[aria-label*="Send"], '
        'button[aria-label*="Submit"]'
    ).first


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

    turns = page.locator('message-content, model-response, div.model-response, .response-container')
    if turns.count() == 0:
        raise RuntimeError("No model response found.")
            
    newest = turns.nth(turns.count() - 1)
    blocks = newest.locator("pre code, code-block code")
        
    if blocks.count() == 0:
        blocks = newest.locator("code")
            
    if blocks.count() == 0:
        raise RuntimeError(
            "No code block found."
        )

    if blocks.count() > 1:
        raise RuntimeError(
            "Returned multiple code blocks. Only 1 is supported."
        )

    return blocks.first.inner_text(
        timeout=30000
    ).strip()


def handle_result(code):
    if code.lower().strip().strip('"').strip("'") == "idle":
        return None

    return run_python_code(code)


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
        state = connect_to_gemini(
            p,
            endpoint_url
        )


        initial_request = input(
            "Enter a task/goal to achieve: "
        ).strip()

        if not initial_request:
            return

        request =  f"{user_prompt_prefix}{initial_request}"

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

                    request = f"{user_prompt_prefix}{check_for_next_request}"

                    continue


                request = run_python_code(code)

                log(
                    f"OUTPUT:\n{request}",
                    LogColors.CYAN
                )
                time.sleep(2)


            except PlaywrightError as e:

                if "closed" in str(e).lower():

                    try:
                        state = reconnect(
                            p,
                            state
                        )

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

                request = (
                    "The execution engine encountered this error:\n"
                    f"{str(e)}"
                )

                time.sleep(2)
                continue


if __name__ == "__main__":
    main()


# saving this shit for later
# number of user sent prompts (how many messages we sent)
# page.locator("user-query-content").count()


