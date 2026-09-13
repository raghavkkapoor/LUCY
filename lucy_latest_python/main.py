import sys
import os

if getattr(sys, 'frozen', False):
    # Executing inside PyInstaller bundle
    BASE_DIR = sys._MEIPASS
else:
    # Executing as standard script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


import ctypes
import signal
import customtkinter as ctk
import keyboard
from PIL import Image
from utils.lucy_logging import LogColors, log
import threading
import pystray
from pystray import MenuItem as item
import traceback

def show_fatal_error(exc_type, exc_value, exc_tb):
    """Catches unhandled exceptions and displays a native Windows error dialog."""
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    err_text = "".join(tb_lines)

    try:
        log(f"[FATAL ERROR]\n{err_text}", LogColors.RED)
    except Exception:
        pass

    ctypes.windll.user32.MessageBoxW(
        0, 
        err_text, 
        "LUCY - Unhandled Fatal Exception", 
        0x10
    )
    sys.exit(1)

sys.excepthook = show_fatal_error

icon_path = os.path.join(BASE_DIR, "Lucy-fonts", "microphone-solid-gray.png")
font_path = os.path.join(BASE_DIR, "Lucy-fonts", "GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf")

# Safe image fallback handling for test environments
try:
    pil_img = Image.open(icon_path)
    mic_icon = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(20, 20))
except Exception:
    pil_img = Image.new('RGBA', (20, 20), (128, 128, 128, 255))
    mic_icon = None


def load_local_font():
    """Dynamically loads a .ttf font into the Windows session memory."""
    FR_PRIVATE = 0x10
    ctypes.windll.gdi32.AddFontResourceExW(font_path, FR_PRIVATE, 0)


try:
    load_local_font()
except Exception as e:
    log(f"[WARNING] Could not load font: {e}", LogColors.YELLOW)

ctk.set_appearance_mode("Dark")

# ---------------------------------------------------------
# MAIN APPLICATION WINDOW
# ---------------------------------------------------------
app = ctk.CTk()
app.title("LUCY")
app.overrideredirect(True)

# Chroma key transparent color for rounded edges
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

# Global registry to manage open notification windows
active_notifications = []

def reposition_all_notifications():
    """Adjusts position of all open notification windows beneath main window."""
    gap = 8
    accumulated_y = pos_y + current_app_h + gap

    for notif_win in list(active_notifications):
        if notif_win.winfo_exists():
            h = notif_win._win_height
            notif_win.geometry(f"{app_window_width}x{h}+{pos_x}+{accumulated_y}")
            accumulated_y += h + gap
        else:
            active_notifications.remove(notif_win)


# ---------------------------------------------------------
# SYSTEM TRAY SETUP
# ---------------------------------------------------------
tray_icon = None
def on_tray_toggle(icon, item):
    """Safely toggles window visibility from system tray menu."""
    app.after(0, lambda: toggle_window(app_handle=app, input_entry=textbox))

def on_tray_exit(icon, item):
    """Clean exit triggered from system tray context menu."""
    icon.stop()
    app.after(0, handle_cleanup)

def setup_system_tray():
    global tray_icon
    
    menu = pystray.Menu(
        item("Show/Hide LUCY", on_tray_toggle, default=True),
        pystray.Menu.SEPARATOR,
        item("Exit", on_tray_exit)
    )
    
    tray_icon = pystray.Icon("LUCY", pil_img, "LUCY Assistant", menu)
    tray_icon.run()

tray_thread = threading.Thread(target=setup_system_tray, daemon=True)
tray_thread.start()

def handle_cleanup():
    global tray_icon
    try:
        log("Cleaning up...", LogColors.GREEN)
        if tray_icon is not None:
            tray_icon.stop()
        app.destroy()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, lambda sig, frame: handle_cleanup())


def allow_signals():
    app.after(500, allow_signals)


app.after(500, allow_signals)

# ---------------------------------------------------------
# VISIBILITY & HOTKEY LOGIC
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# DYNAMIC RESIZING & LOGGING
# ---------------------------------------------------------
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
            total_effective_lines += max(
                1, (len(line) + chars_per_line - 1) // chars_per_line
            )

        calculated_height = base_window_height + (total_effective_lines - 1) * 22
        current_app_h = min(max(calculated_height, base_window_height), max_h_px)

    app.geometry(f"{app_window_width}x{current_app_h}+{pos_x}+{pos_y}")
    reposition_all_notifications()


# ---------------------------------------------------------
# FOCUS LOGIC
# ---------------------------------------------------------
def on_focus_in(event):
    if is_initializing:
        return
    if textbox.get("1.0", "end-1c") == PLACEHOLDER:
        textbox.delete("1.0", "end")
        textbox.configure(text_color=COLOR_TEXT)


def on_focus_out(event):
    if is_initializing:
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


# ---------------------------------------------------------
# UI LAYOUT - MAIN WINDOW
# ---------------------------------------------------------
main_container = ctk.CTkFrame(
    master=app,
    fg_color=TRANSPARENT_COLOR,
    border_width=0,
)
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
    if is_initializing:
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


# ---------------------------------------------------------
# INITIALIZATION LOCK & RIPPLE ANIMATION
# ---------------------------------------------------------
def initialize_lucy(seconds=4):
    """Blocks UI input for `seconds`, playing a border ripple & loading dots animation."""
    global is_initializing
    is_initializing = True

    # Lock interaction controls
    btn_mic.configure(state="disabled")
    textbox.configure(state="normal")
    textbox.delete("1.0", "end")
    textbox.insert("1.0", "Initializing Lucy...")
    textbox.configure(text_color=COLOR_PLACEHOLDER, state="disabled")

    ripple_colors = ["#7E88B1", "#8EA0E3", "#9BB5FF", "#8EA0E3"]
    total_steps = int(seconds * 10)  # 10 frames per second
    step = 0

    def animate():
        nonlocal step
        if step < total_steps:
            # Animate text dots
            dot_count = (step % 4)
            dots = ">" * dot_count
            textbox.configure(state="normal")
            textbox.delete("1.0", "end")
            textbox.insert("1.0", f"Initializing Lucy{dots}")
            textbox.configure(state="disabled")

            # Animate border ripple
            color = ripple_colors[step % len(ripple_colors)]
            input_container.configure(border_color=color)
            input_container.configure(border_color=color)
            textbox.configure(text_color=color)
            

            step += 1
            app.after(150, animate)
        else:
            # Restore state after initialization finishes
            finish_initialization()

    def finish_initialization():
        global is_initializing
        is_initializing = False

        # Reset container border & restore textbox
        input_container.configure(border_color=DEFAULT_BORDER_COLOR)
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", PLACEHOLDER)
        textbox.configure(text_color=COLOR_PLACEHOLDER)

        # Re-enable mic button
        btn_mic.configure(state="normal")

    animate()


# ---------------------------------------------------------
# DYNAMIC NOTIFICATION WINDOW CREATOR
# ---------------------------------------------------------
def show_notification_window(title: str, text: str, notif_h: int = 150):
    """Creates a standalone top-level notification popup positioned under the main window."""
    notif_win = ctk.CTkToplevel(app)
    notif_win.title("LUCY Notification")
    notif_win.overrideredirect(True)
    notif_win.configure(fg_color=TRANSPARENT_COLOR)
    notif_win.wm_attributes("-transparentcolor", TRANSPARENT_COLOR)
    notif_win.attributes("-topmost", True)
    notif_win._win_height = notif_h

    # Container setup
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

    # Title Bar Header with Close Button
    header_frame = ctk.CTkFrame(notif_box, fg_color="transparent")
    header_frame.pack(fill="x", padx=12, pady=(8, 2))

    title_label = ctk.CTkLabel(
        header_frame,
        text=title,
        font=("Google Sans Flex", 14, "bold"),
        text_color="#808080",
        anchor="w"
    )
    title_label.pack(side="left", fill="x", expand=True)

    def close_popup():
        if notif_win in active_notifications:
            active_notifications.remove(notif_win)
        notif_win.destroy()
        reposition_all_notifications()

    btn_close = ctk.CTkButton(
        header_frame,
        text="✕",
        width=18,
        height=18,
        corner_radius=9,
        fg_color="transparent",
        hover_color="#333333",
        text_color="#808080",
        font=("Arial", 11, "bold"),
        command=close_popup
    )
    btn_close.pack(side="right")

    # Divider
    divider = ctk.CTkFrame(notif_box, height=1, fg_color="#7E88B1", border_width=0)
    divider.pack(fill="x", padx=10, pady=(0, 4))

    # Text content
    notif_textbox = ctk.CTkTextbox(
        notif_box,
        font=("Google Sans Flex", 13),
        wrap="word",
        fg_color="transparent",
        border_width=0,
        text_color="#d1d1d1",
        activate_scrollbars=True,
        scrollbar_button_color="#d1d1d1",
        scrollbar_button_hover_color="#b5b5b5",
    )
    notif_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 6))
    notif_textbox.insert("1.0", text)

    # Register and position
    active_notifications.append(notif_win)
    reposition_all_notifications()

    if not is_visible:
        notif_win.withdraw()

    return notif_win


def clear_focus_on_bg(event):
    if not is_event_inside_textbox(event.widget) and not is_initializing:
        app.focus_set()


app.bind("<Button-1>", clear_focus_on_bg, add="+")
main_container.bind("<Button-1>", clear_focus_on_bg, add="+")
app.bind(
    "<Escape>",
    lambda event: toggle_window(app_handle=app, input_entry=input_container),
)

keyboard.add_hotkey("ctrl+space", lambda: toggle_window(app_handle=app, input_entry=textbox))

# Schedule initialization overlay to execute right after main window renders (default 4 seconds)
app.after(100, lambda: initialize_lucy(seconds=2))

app.mainloop()