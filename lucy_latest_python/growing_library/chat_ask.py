import asyncio
import subprocess
import sys
import urllib.request
from playwright.async_api import async_playwright


endpoint_url = None

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

CDP_HOST = "127.0.0.1"
CDP_PORT = 9223
GEMINI_URL = "https://gemini.google.com/"


def test_cdp_port():
    url = f"http://{CDP_HOST}:{CDP_PORT}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except Exception:
        return False


async def stop_gemini_generation(page):
    js_stop = """
    async () => {
        const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
        let stopBtn = document.querySelector("button[aria-label*='Stop response']");
        if (visible(stopBtn)) {
            try { stopBtn.click(); } catch { stopBtn.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
            return true;
        }
        return false;
    }
    """
    try:
        stopped = await page.evaluate(js_stop)
        if stopped:
            print("\n[Interrupted] Stop response clicked in Gemini UI.")
    except Exception:
        pass


async def speak_in_process(text):
    """Spawns lucy_tts.py in a separate process with full text passed safely."""
    proc = subprocess.Popen(
        [sys.executable, r"lucy_latest_python\utils\lucy_tts.py", text],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8"
    )

    try:
        while proc.poll() is None:
            await asyncio.sleep(0.05)
            
        _, stderr = proc.communicate()
        if proc.returncode != 0 and stderr:
            print(f"[TTS Error] Subprocess stderr: {stderr}")

    except (KeyboardInterrupt, asyncio.CancelledError):
        proc.kill()
        proc.wait()
        raise


async def query_gemini(user_input):
    request_prompt = f"{user_input.strip()} - Respond with only ONE sentence and summerize if necessary."

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(endpoint_url)
        
        # Scan across all open browser contexts for the active Gemini page
        page = None
        for context in browser.contexts:
            for p_tab in context.pages:
                if "gemini.google.com" in p_tab.url:
                    page = p_tab
                    break
            if page:
                break

        # Throw error instead of opening a new tab window if app mode is not running
        if not page:
            raise RuntimeError(
                "Gemini app instance not found. Please launch Chrome in App Mode first with:\n"
                f"chrome.exe --remote-debugging-port={CDP_PORT} --app={GEMINI_URL}"
            )

        print("Attached to existing Gemini app instance.")

        js_interactor = """
        async (request) => {
            const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
            const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
            const responseText = () => {
                const turns = [...document.querySelectorAll("message-content, model-response, div.model-response, .response-container")].filter(visible);
                const texts = turns.map(turn => (turn.innerText || "").trim()).filter(text => text && text !== request.trim());
                return texts.length ? texts[texts.length - 1] : "";
            };

            try {
                let composer = document.querySelector("rich-textarea .ql-editor");
                for (let i = 0; i < 120 && !visible(composer); i++) {
                    await sleep(250);
                    composer = document.querySelector("rich-textarea .ql-editor");
                }
                if (!visible(composer)) return { success: false, error: "Gemini composer not found." };

                composer.focus();
                document.execCommand("selectAll", false, null);
                document.execCommand("insertText", false, request);
                composer.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: request }));
                composer.dispatchEvent(new Event("change", { bubbles: true }));

                let button = document.querySelector("button.send-button, button[aria-label*='Send'], button[aria-label*='Submit']");
                for (let i = 0; i < 120 && !visible(button); i++) {
                    await sleep(250);
                    button = document.querySelector("button.send-button, button[aria-label*='Send'], button[aria-label*='Submit']");
                }
                if (!visible(button)) return { success: false, error: "Gemini send button not found." };

                const before = responseText();
                let sawGeneration = false;
                try { button.click(); } catch { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); }

                for (let i = 0; i < 240; i++) {
                    const stop = document.querySelector("button[aria-label*='Stop response']");
                    const text = responseText();
                    if (stop) sawGeneration = true;
                    if (!stop && text && (sawGeneration || text !== before)) return { success: true, text: text };
                    await sleep(100);
                }

                const text = responseText();
                return text && (sawGeneration || text !== before)
                    ? { success: true, text: text }
                    : { success: false, error: "Gemini response timed out." };
            } catch (err) {
                return { success: false, error: err?.message || String(err) };
            }
        }
        """

        try:
            print("Sending request to Gemini... (Press Ctrl+C to stop)")
            data = await page.evaluate(js_interactor, request_prompt)

            if not data or not data.get("success"):
                raise RuntimeError(data.get("error") if data else "Failed execution.")

            print("\nGemini response:\n")
            print(data["text"])

            await speak_in_process(data["text"])

        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[Ctrl+C Detected] Terminating TTS process and stopping Gemini generation...")
            subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq lucy_tts*"], capture_output=True)
            await stop_gemini_generation(page)


def main():
    if not test_cdp_port():
        raise RuntimeError(
            f"Unable to connect to Chrome on CDP port {CDP_PORT}. Run Chrome with `--remote-debugging-port=9223`."
        )

    user_input = input("Enter your request: ").strip()
    if not user_input:
        print("No request entered.")
        sys.exit(0)

    try:
        asyncio.run(query_gemini(user_input))
    except KeyboardInterrupt:
        print("Exited cleanly.")


if __name__ == "__main__":
    main()