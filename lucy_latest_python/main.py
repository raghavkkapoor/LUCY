
from utils.lucy_logging import log, LogColors
from utils.lucy_command_search import process_input
from utils.find_anything import process_multi_search
from utils.CloseLucyBrowser9223 import kill_cdp_browser
from utils.ChromeCdpManager import launch_lucy_chrome
import ctypes
import customtkinter as ctk
import sys
import keyboard
import signal


APP_BG_COLOR = "#04082D"

def load_local_font(font_path):
    """Dynamically loads a .ttf font into the Windows session memory."""
    FR_PRIVATE = 0x10
    ctypes.windll.gdi32.AddFontResourceExW(font_path, FR_PRIVATE, 0)

try:
    load_local_font(
        r"Lucy-fonts\GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf"
    )
except Exception as e:
    log(f"[WARNING] Could not load font: {e}", LogColors.YELLOW)

# ctk.set_appearance_mode("Dark")

app = ctk.CTk()
app.title("LUCY")
app.overrideredirect(True)
app.configure(fg_color=APP_BG_COLOR)

screen_w = app.winfo_screenwidth()
screen_h = app.winfo_screenheight()

min_w_pct, min_h_pct = 0.20, 0.15
max_w_px, max_h_px = 500, 400

min_w = int(screen_w * min_w_pct)
min_h = int(screen_h * min_h_pct)

app_window_width = min(max(screen_w, min_w), max_w_px)
base_window_height = 220
app_window_height = min(max(screen_h, min_h), base_window_height)

pos_x = int(screen_w / 2 - (app_window_width / 2))
pos_y = 150

app.geometry(f"{app_window_width}x{app_window_height}+{pos_x}+{pos_y}")

def handle_cleanup():
    log("Cleaning up...", LogColors.GREEN)
    try:
        kill_cdp_browser()
        log("Closed CDP browser instance...", LogColors.GREEN) 
    except Exception as e:
        log(f"Cleanup browser error: {e}", LogColors.RED)

    app.destroy()

    sys.exit(0)

# 1. Define what happens when Ctrl+C is pressed in the terminal
signal.signal(signal.SIGINT, lambda sig, frame: handle_cleanup())

# 2. Keep-alive timer to allow Python to intercept terminal signals
def allow_signals():
    app.after(500, allow_signals)

app.after(500, allow_signals)

# ---------------------------------------------------------
# VISIBILITY & HOTKEY LOGIC
# ---------------------------------------------------------
is_visible = True

def toggle_window(app_handle, input_entry):
    global is_visible
    if is_visible:
        app_handle.withdraw()
        is_visible = False
    else:
        app_handle.deiconify()
        app_handle.lift()
        app_handle.focus_force()
        input_entry.focus()
        is_visible = True

# ---------------------------------------------------------
# DYNAMIC RESIZING & LOGGING
# ---------------------------------------------------------
BASE_INPUT_HEIGHT = 45
# THIS COMMANDS DIRECTORY WILL BE A SERVER INSTEAD OF LOCALLY STORED SCRIPTS
COMMANDS_ROOT_DIR = r"C:\Users\ragha\OneDrive\Desktop\LUCY\lucy_latest_python\POWERSHELL_DEBUG_SCRIPTS"
MAX_SEARCH_RESULTS = 200

def on_input_change(event=None):
    content = repr(textbox.get("1.0", "end-1c"))

    if (len(content.strip("'").strip(r"\n")) == 0):
        return


    # process_input(content, COMMANDS_ROOT_DIR, limit=MAX_SEARCH_RESULTS)
    process_multi_search(content, limit=MAX_SEARCH_RESULTS)


    num_lines = content.count("\n") + 1
    chars_per_line = 38
    wrapped_lines = sum(
        max(1, len(line) // chars_per_line) for line in content.split("\n")
    )
    effective_lines = max(num_lines, wrapped_lines)

    new_input_h = BASE_INPUT_HEIGHT + (effective_lines - 1) * 22
    target_window_h = base_window_height + (new_input_h - BASE_INPUT_HEIGHT)
    final_window_h = min(max(target_window_h, base_window_height), max_h_px)

    textbox.configure(
        height=final_window_h - (base_window_height - BASE_INPUT_HEIGHT)
    )
    app.geometry(f"{app_window_width}x{final_window_h}")

# ---------------------------------------------------------
# CONDITIONAL DRAGGABLE WINDOW LOGIC
# ---------------------------------------------------------
_drag_start_x = 0
_drag_start_y = 0
is_textbox_focused = False

def set_textbox_focused(focused):
    global is_textbox_focused
    is_textbox_focused = focused

def is_event_inside_textbox(event_widget):
    """Checks if the mouse event originated from the textbox or any of its sub-widgets."""
    widget = event_widget
    while widget is not None:
        if widget == textbox:
            return True
        widget = getattr(widget, "master", None)
    return False

def start_drag(event):
    global _drag_start_x, _drag_start_y
    # Do not initiate drag if focused or clicking inside textbox/scrollbar
    if is_textbox_focused or is_event_inside_textbox(event.widget):
        return
    _drag_start_x = event.x
    _drag_start_y = event.y

def execute_drag(event):
    # Ignore motion events if focused or clicking inside textbox/scrollbar
    if is_textbox_focused or is_event_inside_textbox(event.widget):
        return
    x = app.winfo_x() - _drag_start_x + event.x
    y = app.winfo_y() - _drag_start_y + event.y
    app.geometry(f"+{x}+{y}")

app.bind("<Button-1>", start_drag)
app.bind("<B1-Motion>", execute_drag)

# ---------------------------------------------------------
# UI LAYOUT
# ---------------------------------------------------------
container = ctk.CTkFrame(app, fg_color="transparent")
container.pack(expand=True, fill="both", padx=20, pady=15)

container.bind("<Button-1>", start_drag)
container.bind("<B1-Motion>", execute_drag)

label_title = ctk.CTkLabel(
    container,
    text="LUCY [beta]",
    font=("Google Sans Flex", 24, "bold"),
    text_color="#CDD6F4",
)
label_title.pack(pady=(0, 2))

label_subtitle = ctk.CTkLabel(
    container,
    text="What would you like to do?",
    font=("Google Sans Flex", 18),
    text_color="#89B4FA",
)
label_subtitle.pack(pady=(0, 10))

textbox = ctk.CTkTextbox(
    container,
    height=BASE_INPUT_HEIGHT,
    font=("Google Sans Flex", 15),
    wrap="word",
    fg_color="#313244",
    border_color="#45475A",
    border_width=1,
    text_color="#CDD6F4",
    activate_scrollbars=True,
)
textbox.pack(fill="x", padx=5)
textbox.focus()

# Track focus states to explicitly block window dragging
textbox.bind("<FocusIn>", lambda e: set_textbox_focused(True))
textbox.bind("<FocusOut>", lambda e: set_textbox_focused(False))

# Clicking background outside the textbox clears focus from the textbox
def clear_focus_on_bg(event):
    if not is_event_inside_textbox(event.widget):
        app.focus_set()

app.bind("<Button-1>", clear_focus_on_bg, add="+")
container.bind("<Button-1>", clear_focus_on_bg, add="+")

textbox.bind("<KeyRelease>", on_input_change)

app.bind("<Escape>", lambda event: toggle_window(app_handle=app, input_entry=textbox))

keyboard.add_hotkey(
    "win+space", lambda: app.after(0, toggle_window, app, textbox)
)


chrome = launch_lucy_chrome()
endpoint_url = chrome["url"]

# MAIN GUI CALL
app.mainloop()





# Type of requests:

# FIRST: NAVIGATE MYBCIT AND LEARNING HUB.

# 1. Send and receive email.
# 2. Summerized web search about a topic.
# 3. Detailed web search about a topic.
# 5. Create alarms and reminders.
# 6. Playing any song/playlist (handling basic playback).
# 7. Get every calendar event and ready to retrieve on demand. Automatically remind the user if an event is coming up without asking to "remind" them.
# 8. Pull up any image(s) about something from the web.
# 9. Open any website.
# 10. Open any app.
# 11. Know my youtube search history to pull relative past info on demand

# TODO: PERFORM INTENT CLASSIFICATION ON THE UTILS DIRECTORY USING: Zero-Shot Text Classification