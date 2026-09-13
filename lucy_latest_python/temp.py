import sys
import os
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
import ctypes
import traceback
import math
import customtkinter as ctk
import keyboard
from PIL import Image
import pystray
from pystray import MenuItem as item

# Playwright & LLM Automation Imports
from playwright.sync_api import expect, sync_playwright, Error as PlaywrightError
from utils.CloseLucyBrowser9223 import kill_cdp_browser
from utils.gemini_usage import get_gemini_usage
from utils.ChromeCdpManager import launch_lucy_chrome, is_cdp_port_active
from utils.lucy_logging import log, LogColors
import utils.Constants as Constants

# ---------------------------------------------------------
# GLOBAL SETUP & PATHS
# ---------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

icon_path = os.path.join(BASE_DIR, "Lucy-fonts", "microphone-solid-gray.png")
font_path = os.path.join(BASE_DIR, "Lucy-fonts", "GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf")

try:
    pil_img = Image.open(icon_path)
    mic_icon = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(20, 20))
except Exception:
    pil_img = Image.new('RGBA', (20, 20), (128, 128, 128, 255))
    mic_icon = None

def load_local_font():
    FR_PRIVATE = 0x10
    ctypes.windll.gdi32.AddFontResourceExW(font_path, FR_PRIVATE, 0)

try:
    load_local_font()
except Exception as e:
    log(f"[WARNING] Could not load font: {e}", LogColors.YELLOW)

def show_fatal_error(exc_type, exc_value, exc_tb):
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    err_text = "".join(tb_lines)
    try:
        log(f"[FATAL ERROR]\n{err_text}", LogColors.RED)
    except Exception:
        pass
    ctypes.windll.user32.MessageBoxW(0, err_text, "LUCY - Unhandled Fatal Exception", 0x10)
    sys.exit(1)

sys.excepthook = show_fatal_error

ctk.set_appearance_mode("Dark")

# ---------------------------------------------------------
# GLOBAL STATE TRACKING
# ---------------------------------------------------------
is_busy = False

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
ASYNC_LOG_FILE = Constants.PROJECT_DIR.joinpath("lucy_latest_python/gemini_llm_activity.jsonl")

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
        expect(composer).to_be_empty(timeout=5000, message="Failed to submit request via UI.")
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

# ---------------------------------------------------------
# GUI APPLICATION SETUP
# ---------------------------------------------------------
app = ctk.CTk()
app.title("LUCY")
app.overrideredirect(True)

TRANSPARENT_COLOR = "#000001"
DARK_BG_COLOR = "#1e1e1e"
DEFAULT_BORDER_COLOR = "#7E88B1"

app.configure(fg_color=TRANSPARENT_COLOR)
app.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)
app.attributes("-topmost", True)

screen_w = app.winfo_screenwidth()
screen_h = app.winfo_screenheight()

min_w_pct, min_h_pct = 0.20, 0.15
max_w_px, max_h_px = 500, 400

min_w = int(screen_w * min_w_pct)
min_h = int(screen_h * min_h_pct)

app_window_width = min(max(screen_w, min_w), max_w_px)
base_window_height = 50
current_app_h = base_window_height

pos_x = int(screen_w - app_window_width - 20)
pos_y = 40

app.geometry(f"{app_window_width}x{base_window_height}+{pos_x}+{pos_y}")

active_notifications = []

def reposition_all_notifications():
    gap = 8
    accumulated_y = pos_y + current_app_h + gap
    for notif_win in list(active_notifications):
        if notif_win.winfo_exists():
            h = notif_win._win_height
            notif_win.geometry(f"{app_window_width}x{h}+{pos_x}+{accumulated_y}")
            accumulated_y += h + gap
        else:
            active_notifications.remove(notif_win)

def clear_all_notifications():
    for notif_win in list(active_notifications):
        if notif_win.winfo_exists():
            notif_win.destroy()
    active_notifications.clear()

tray_icon = None
def on_tray_toggle(icon, item):
    app.after(0, lambda: toggle_window(app_handle=app, input_entry=textbox))

def on_tray_exit(icon, item):
    icon.stop()
    app.after(0, handle_cleanup)

def setup_system_tray():
    global tray_icon
    menu = pystray.Menu(
        item("Show/Hide LUCY", on_tray_toggle, default=True),
        pystray.Menu.SEPARATOR,
        item("Exit", on_tray_exit)
    )
    tray_icon = pystray.Icon("LUCY", pil_img, "LUCY", menu)
    tray_icon.run()

tray_thread = threading.Thread(target=setup_system_tray, daemon=True)
tray_thread.start()

def handle_cleanup():
    global tray_icon
    try:
        log("Cleaning up...", LogColors.GREEN)
        if tray_icon is not None:
            tray_icon.stop()
        kill_cdp_browser()
        app.destroy()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, lambda sig, frame: handle_cleanup())
def allow_signals():
    app.after(500, allow_signals)
app.after(500, allow_signals)

is_visible = True
is_initializing = False

def toggle_window(app_handle, input_entry):
    global is_visible
    if is_initializing:
        return

    if is_visible:
        app_handle.withdraw()
        for win in active_notifications:
            if win.winfo_exists():
                win.withdraw()
        is_visible = False
    else:
        app_handle.deiconify()
        app_handle.lift()
        app_handle.focus_force()
        for win in active_notifications:
            if win.winfo_exists():
                win.deiconify()
                win.lift()
        input_entry.focus()
        is_visible = True

BASE_INPUT_HEIGHT = 45
PLACEHOLDER = "Ask Lucy..."
COLOR_PLACEHOLDER = ("#808080", "#a0a0a0")
COLOR_TEXT = ("#1a1a1a", "#ffffff")

def on_input_change(event=None):
    global current_app_h
    raw_text = textbox.get("1.0", "end-1c")

    if not raw_text.strip() or raw_text == PLACEHOLDER or is_initializing:
        current_app_h = base_window_height
    else:
        lines = raw_text.split("\n")
        chars_per_line = 34
        total_effective_lines = 0
        for line in lines:
            total_effective_lines += max(1, (len(line) + chars_per_line - 1) // chars_per_line)

        calculated_height = base_window_height + (total_effective_lines - 1) * 22
        current_app_h = min(max(calculated_height, base_window_height), max_h_px)

    app.geometry(f"{app_window_width}x{current_app_h}+{pos_x}+{pos_y}")
    reposition_all_notifications()

def on_focus_in(event):
    if is_initializing or is_busy:
        return
    if textbox.get("1.0", "end-1c") == PLACEHOLDER:
        textbox.delete("1.0", "end")
        textbox.configure(text_color=COLOR_TEXT)

def on_focus_out(event):
    if is_initializing or is_busy:
        return
    if not textbox.get("1.0", "end-1c").strip():
        textbox.insert("1.0", PLACEHOLDER)
        textbox.configure(text_color=COLOR_PLACEHOLDER)
        on_input_change()

def is_event_inside_textbox(event_widget):
    widget = event_widget
    while widget is not None:
        if widget in (textbox, input_container):
            return True
        widget = getattr(widget, "master", None)
    return False

main_container = ctk.CTkFrame(master=app, fg_color=TRANSPARENT_COLOR, border_width=0)
main_container.pack(fill="both", expand=True)

input_container = ctk.CTkFrame(
    main_container,
    corner_radius=16,
    fg_color=DARK_BG_COLOR,
    border_width=2,
    border_color=DEFAULT_BORDER_COLOR
)
input_container.pack(fill="both", expand=True, padx=0, pady=0)

input_container.grid_columnconfigure(0, weight=1)
input_container.grid_columnconfigure(1, weight=0)
input_container.grid_rowconfigure(0, weight=1)

textbox = ctk.CTkTextbox(
    input_container,
    font=("Google Sans Flex", 16),
    wrap="word",
    fg_color="transparent",
    border_width=0,
    activate_scrollbars=True,
    scrollbar_button_color="#d1d1d1",
    scrollbar_button_hover_color="#b5b5b5",
)
textbox.grid(row=0, column=0, sticky="nsew", padx=(10, 2), pady=4)

textbox.insert("1.0", PLACEHOLDER)
textbox.configure(text_color=COLOR_PLACEHOLDER)

textbox.bind("<FocusIn>", on_focus_in)
textbox.bind("<FocusOut>", on_focus_out)
textbox.bind(
    "<<Modified>>",
    lambda e: (
        textbox.edit_modified(False),
        app.after_idle(on_input_change),
    )[-1],
)

def trigger_mic_action():
    if is_initializing or is_busy:
        return
    log("Microphone clicked...", LogColors.GREEN)

btn_mic = ctk.CTkButton(
    input_container,
    text="",
    image=mic_icon,
    width=0,
    height=0,
    hover=False,
    fg_color="transparent",
    command=trigger_mic_action,
    border_spacing=8,
)
btn_mic.grid(row=0, column=1, sticky="ne", padx=(2, 6), pady=6)


def set_notif_text(tb_widget, text: str):
    if tb_widget and tb_widget.winfo_exists():
        # Get the top-level window containing this textbox
        notif_win = tb_widget.winfo_toplevel()
        
        # Use the existing geometry function to calculate and apply height
        update_notification_text(notif_win, tb_widget, text)
        
        # Force scroll position back to top
        tb_widget.yview_moveto(0.0)


# Configuration Constants
HEADER_HEIGHT = 38
DIVIDER_HEIGHT = 3  # Frame height + padding space (~9px total vertical footprint)
PADDING_Y = 14      # Combined internal padding of frames and textbox



def get_required_text_height(textbox: ctk.CTkTextbox) -> int:
    """Calculates exact height needed based on line count, capped at 7 lines."""
    textbox.update_idletasks()
    last_index = textbox._textbox.index("end-1c")
    line_count = int(last_index.split(".")[0])
    
    # Clamp line count to a maximum of 7 lines
    effective_lines = min(line_count, 7)
    
    # Approximate pixel height per line (adjust based on your font size, e.g., 18-20px)
    LINE_PIXEL_HEIGHT = 18 
    return effective_lines * LINE_PIXEL_HEIGHT



def update_notification_text(notif_win: ctk.CTkToplevel, textbox: ctk.CTkTextbox, new_text: str):
    """Updates textbox content and resizes notification window dynamically."""
    textbox.configure(state="normal")
    textbox.delete("1.0", "end")
    
    if new_text:
        textbox.insert("1.0", new_text)
        text_height = get_required_text_height(textbox)
    else:
        text_height = 0

    textbox.configure(state="disabled")

    # Target total height = Header + Divider/Paddings + Text Content
    total_h = HEADER_HEIGHT + DIVIDER_HEIGHT + PADDING_Y + text_height
    
    notif_win._win_height = total_h
    
    # Re-apply geometry immediately to the current window before shifting others
    if notif_win in active_notifications:
        idx = active_notifications.index(notif_win)
        # Calculate its correct vertical stack position based on index
        gap = 8
        accumulated_y = pos_y + current_app_h + gap
        for i in range(idx):
            w = active_notifications[i]
            if w.winfo_exists():
                accumulated_y += w._win_height + gap
        notif_win.geometry(f"{app_window_width}x{total_h}+{pos_x}+{accumulated_y}")
    
    reposition_all_notifications()

def show_notification_window(title: str, text: str = ""):
    notif_win = ctk.CTkToplevel(app)
    notif_win.title("LUCY Notification")
    notif_win.overrideredirect(True)
    notif_win.configure(fg_color=TRANSPARENT_COLOR)
    notif_win.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)
    notif_win.attributes("-topmost", True)

    # Base container layout
    notif_main = ctk.CTkFrame(master=notif_win, fg_color=TRANSPARENT_COLOR, border_width=0)
    notif_main.pack(fill="both", expand=True)

    notif_box = ctk.CTkFrame(
        notif_main,
        corner_radius=16,
        fg_color=DARK_BG_COLOR,
        border_width=1,
        border_color="#7E88B1"
    )
    notif_box.pack(fill="both", expand=True, padx=0, pady=0)

    # Fixed Header Bar
    header_frame = ctk.CTkFrame(notif_box, fg_color="transparent", height=HEADER_HEIGHT)
    header_frame.pack_propagate(False)
    header_frame.pack(fill="x", padx=12, pady=(4, 0))

    title_label = ctk.CTkLabel(
        header_frame,
        text=title,
        font=("Google Sans Flex", 14, "normal"),
        text_color="#808080",
        anchor="w"
    )
    title_label.pack(side="left", fill="both", expand=True)

    def close_popup():
        if notif_win in active_notifications:
            active_notifications.remove(notif_win)
        notif_win.destroy()
        reposition_all_notifications()

    # btn_close = ctk.CTkButton(
    #     header_frame,
    #     text="✕",
    #     width=18,
    #     height=18,
    #     corner_radius=9,
    #     fg_color="transparent",
    #     hover_color="#333333",
    #     text_color="#808080",
    #     font=("Arial", 11, "bold"),
    #     command=close_popup
    # )
    # btn_close.pack(side="right", pady=4)

    # Animated Divider Bar
    divider = ctk.CTkFrame(notif_box, height=2, fg_color="#7E88B1", border_width=0)
    divider.pack(fill="x", padx=10, pady=(2, 4))

    ripple_colors = ["#7E88B1", "#8EA0E3", "#9BB5FF", "#8EA0E3"]
    RIPPLE_SPEED = 4
    start_time = time.time()

    def animate_divider():
        if notif_win.winfo_exists():
            elapsed = time.time() - start_time
            color_index = int(elapsed * RIPPLE_SPEED * len(ripple_colors)) % len(ripple_colors)
            divider.configure(fg_color=ripple_colors[color_index])
            notif_win.after(50, animate_divider)

    animate_divider()

    # Content Textbox
    notif_textbox = ctk.CTkTextbox(
        notif_box,
        font=("Google Sans Flex", 13),
        wrap="word",
        fg_color="transparent",
        border_width=0,
        text_color="#d1d1d1",
        activate_scrollbars=False
    )
    notif_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 4))

    # ADD TO LIST ONCE (Removed duplicate append call)
    active_notifications.append(notif_win)

    # Apply initial content and size window dynamically
    update_notification_text(notif_win, notif_textbox, text)

    if not is_visible:
        notif_win.withdraw()

    return notif_textbox
# ---------------------------------------------------------
# QUEUE & THREAD CONTROL FOR ORCHESTRATION
# ---------------------------------------------------------
task_queue = queue.Queue()


def initialize_lucy(seconds=4, on_complete_callback=None):
    global is_initializing
    is_initializing = True

    btn_mic.configure(state="disabled")
    textbox.configure(state="normal")
    textbox.delete("1.0", "end")
    textbox.insert("1.0", "Initializing Lucy...")
    textbox.configure(text_color=COLOR_PLACEHOLDER, state="disabled")

    ripple_colors = ["#7E88B1", "#8EA0E3", "#9BB5FF", "#8EA0E3"]
    total_steps = int(seconds * 10)
    step = 0

    def animate():
        nonlocal step
        if step < total_steps:
            dot_count = (step % 4)
            dots = ">" * dot_count
            textbox.configure(state="normal")
            textbox.delete("1.0", "end")
            textbox.insert("1.0", f"Initializing Lucy{dots}")
            textbox.configure(state="disabled")

            color = ripple_colors[step % len(ripple_colors)]
            input_container.configure(border_color=color)
            textbox.configure(text_color=color)

            step += 1
            app.after(150, animate)
        else:
            finish_initialization()

    def finish_initialization():
        global is_initializing
        is_initializing = False

        input_container.configure(border_color=DEFAULT_BORDER_COLOR)
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.configure(text_color=COLOR_PLACEHOLDER)
        on_input_change()

        if on_complete_callback:
            on_complete_callback()

    animate()


def on_enter_pressed(event):
    if is_initializing or is_busy:
        return "break"
    
    if event.state & 0x0001:  # Shift key pressed -> new line
        return

    user_text = textbox.get("1.0", "end-1c").strip()
    if user_text and user_text != PLACEHOLDER:
        textbox.delete("1.0", "end")
        on_input_change()
        task_queue.put(user_text)
    return "break"

textbox.bind("<Return>", on_enter_pressed)

# ---------------------------------------------------------
# BACKGROUND WORKER LOOP (MERGED ENGINE)
# ---------------------------------------------------------
def llm_worker_loop():
    global is_busy
    try:
        chrome_state = launch_lucy_chrome(preferred_port=Constants.PORT)

        endpoint_url = chrome_state["url"]
        
    except Exception as e:
        log(f"Failed to init Chrome: {e}", LogColors.RED)
        return

    if not is_cdp_port_active(Constants.PORT):
        log("Browser unreachable. Exiting worker thread.", LogColors.RED)
        return

    with sync_playwright() as p:
        state = connect_to_LLM(p, endpoint_url)
        usage_page = state["context"].new_page()

        check_usage_and_warn(usage_page)

        async_logger = AsyncLLMLogger(ASYNC_LOG_FILE)
        async_logger.start()

        while True:
            # Wait for user input from UI queue
            initial_request = task_queue.get()
            if initial_request is None:
                async_logger.stop()
                break

            # Mark state as busy and disable UI elements
            is_busy = True
            app.after(0, lambda: textbox.configure(state="disabled"))
            app.after(0, lambda: btn_mic.configure(state="disabled"))

            request = f"{Constants.PROMPT_PREFIX}{initial_request}{Constants.PROMPT_SUFFIX}"
            prompts_sent_in_current_chat = 0
            latest_code = ""
            latest_output = ""

            notif_created = False
            active_textbox = None

            try:
                while True:
                    try:
                        if not is_cdp_port_active(Constants.PORT):
                            state = reconnect(p)

                        if not request.strip():
                            request = "No execution output was captured. Try again."

                        check_usage_and_warn(usage_page)

                        # create or update task notification

                        if not notif_created:
                            # First iteration: Spawn the window and save reference
                            title_summary = initial_request[:30] + "..." if len(initial_request) > 30 else initial_request

                            def create_notif(req=title_summary, out=""):
                                nonlocal active_textbox
                                active_textbox = show_notification_window(
                                    title=f"Working on: {req}",
                                    text=out
                                )

                            app.after(0, create_notif)

                            app.after(0, lambda out="Incoming...": set_notif_text(active_textbox, out))

                            notif_created = True


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
                        response = extracted_code(state["page"])

                        # Subsequent iterations: Dynamically update existing textbox
                        if notif_created:
                            app.after(0, lambda out=response: set_notif_text(active_textbox, out))


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

                            app.after(0, clear_all_notifications)
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
                is_busy = False
                app.after(0, lambda: textbox.configure(state="normal"))
                app.after(0, lambda: btn_mic.configure(state="normal"))

def clear_focus_on_bg(event):
    if not is_event_inside_textbox(event.widget) and not is_initializing and not is_busy:
        app.focus_set()

app.bind("<Button-1>", clear_focus_on_bg, add="+")
main_container.bind("<Button-1>", clear_focus_on_bg, add="+")
app.bind("<Escape>", lambda event: toggle_window(app_handle=app, input_entry=input_container))

keyboard.add_hotkey("ctrl+space", lambda: toggle_window(app_handle=app, input_entry=textbox))

# Run initialize_lucy dynamic loading while thread sets up Playwright/Chrome
app.after(100, lambda: initialize_lucy(seconds=5))

worker_thread = threading.Thread(target=llm_worker_loop, daemon=True)
worker_thread.start()
app.mainloop()