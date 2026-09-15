"""Lucy presentation layer. Worker threads communicate through LucyGUI.post()."""
import ctypes
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk

import customtkinter as ctk
import keyboard
from PIL import Image
import pystray

from utils.lucy_logging import log, LogColors

BG = "#1e1e1e"
BORDER = "#7E88B1"
TRANSPARENT = "#000001"
PLACEHOLDER = "What do you want to do one this computer?"
DEFAULT_SETTINGS = {"minimum_lines": 7, "notification_seconds": 30}


def load_settings(path):
    settings = DEFAULT_SETTINGS.copy()
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        for key, lower, upper in (("minimum_lines", 1, 20), ("notification_seconds", 0, 86400)):
            value = saved.get(key)
            if type(value) is int and lower <= value <= upper:
                settings[key] = value
    except (OSError, ValueError, AttributeError):
        pass
    return settings


class Notification:
    def __init__(self, gui, task_id, title, text):
        self.gui = gui
        self.task_id = task_id
        self.title = title
        self.text = ""
        self.finished_at = None
        self.expiry_job = None
        self.expanded = None
        self.window = ctk.CTkToplevel(gui.app)
        self.window.withdraw()
        self.window.title("LUCY Notification")
        self.window.overrideredirect(True)
        self.window.configure(fg_color=TRANSPARENT)
        self.window.wm_attributes("-transparentcolor", TRANSPARENT)
        self.window.attributes("-topmost", True)
        box = ctk.CTkFrame(self.window, corner_radius=16, fg_color=BG,
                           border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True)
        header = ctk.CTkFrame(box, fg_color="transparent", height=38)
        header.pack(fill="x", padx=12, pady=(4, 0))
        header.pack_propagate(False)
        for label, command in (("×", self.close), ("Expand", self.expand)):
            ctk.CTkButton(header, text=label, width=26 if label == "×" else 62,
                          height=26, fg_color="transparent", hover_color="#333333",
                          command=command).pack(side="right", padx=(4, 0), pady=4)
        self.label = ctk.CTkLabel(header, text=f"Working on: {title}", anchor="w",
                                  font=("Google Sans Flex", 14), text_color="#a0a0a0")
        self.label.pack(side="left", fill="both", expand=True)
        ctk.CTkFrame(box, height=2, fg_color=BORDER).pack(fill="x", padx=10, pady=(2, 4))
        self.textbox = ctk.CTkTextbox(box, font=("Consolas", 13), wrap="word",
                                      fg_color="transparent", text_color="#d1d1d1",
                                      activate_scrollbars=True)
        self.textbox.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.update(text)

    @staticmethod
    def replace_text(textbox, text):
        position = textbox.yview()[0]
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")
        textbox.yview_moveto(position)

    def update(self, text):
        self.text = text
        self.replace_text(self.textbox, text)
        if self.expanded is not None and self.expanded.winfo_exists():
            self.replace_text(self.expanded_text, text)
        self.resize()

    def resize(self):
        minimum = self.gui.settings["minimum_lines"]
        lines = max(minimum, min(max(1, len(self.text.splitlines())), max(7, minimum)))
        self.height = 62 + lines * 20
        self.gui.reposition_notifications()

    def expand(self):
        if self.expanded is not None and self.expanded.winfo_exists():
            self.expanded.deiconify()
            self.expanded.lift()
            return
        self.expanded = self.gui.create_centered_window(f"LUCY — {self.title}", 900, 650)
        self.expanded_text = ctk.CTkTextbox(self.expanded, font=("Consolas", 14),
                                            wrap="none", activate_scrollbars=True)
        self.expanded_text.pack(fill="both", expand=True, padx=12, pady=12)
        self.replace_text(self.expanded_text, self.text)
        # This independent viewer stays readable even when its small card expires.

    def finish(self, status="Completed"):
        self.label.configure(text=f"{status}: {self.title}")
        self.finished_at = time.monotonic()
        self.schedule_expiry()

    def schedule_expiry(self):
        if self.expiry_job is not None:
            self.gui.app.after_cancel(self.expiry_job)
            self.expiry_job = None
        seconds = self.gui.settings["notification_seconds"]
        if self.finished_at is not None and seconds:
            remaining = seconds - (time.monotonic() - self.finished_at)
            self.expiry_job = self.gui.app.after(max(0, int(remaining * 1000)), self.close)

    def close(self):
        if self.expiry_job is not None:
            self.gui.app.after_cancel(self.expiry_job)
            self.expiry_job = None
        self.gui.notifications.pop(self.task_id, None)
        self.window.destroy()
        self.gui.reposition_notifications()


class LucyGUI:
    def __init__(self, on_submit, on_close=None, settings_path=None, enable_integrations=True):
        self.on_submit = on_submit
        self.on_close = on_close
        self.events = queue.Queue()
        self.notifications = {}
        self.initializing = True
        self.busy = False
        self.visible = True
        self.closed = False
        self.settings_window = None
        self.tray_icon = None
        self.hotkey = None
        settings_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Lucy"
        self.settings_path = Path(settings_path) if settings_path else settings_dir / "gui_settings.json"
        self.settings = load_settings(self.settings_path)
        asset_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "fonts"
        try:
            ctypes.windll.gdi32.AddFontResourceExW(
                str(asset_dir / "GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf"), 0x10, 0)
        except (AttributeError, OSError):
            pass
        ctk.set_appearance_mode("Dark")
        self.app = ctk.CTk()
        self.app.title("LUCY")
        self.app.overrideredirect(True)
        self.app.configure(fg_color=TRANSPARENT)
        self.app.wm_attributes("-transparentcolor", TRANSPARENT)
        self.app.attributes("-topmost", True)
        self.width = min(500, self.app.winfo_screenwidth() - 40)
        self.height = 50
        self.x = self.app.winfo_screenwidth() - self.width - 20
        self.y = 40
        self.input_container = ctk.CTkFrame(self.app, corner_radius=16, fg_color=BG,
                                             border_width=2, border_color=BORDER)
        self.input_container.pack(fill="both", expand=True)
        self.input_container.grid_columnconfigure(0, weight=1)
        self.input_container.grid_rowconfigure(0, weight=1)
        self.textbox = ctk.CTkTextbox(self.input_container, font=("Google Sans Flex", 16),
                                       wrap="word", fg_color="transparent", border_width=0,
                                       activate_scrollbars=True)
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=(10, 2), pady=4)
        try:
            self.tray_image = Image.open(asset_dir / "microphone-solid-gray.png")
            self.mic_image = ctk.CTkImage(self.tray_image, self.tray_image, size=(20, 20))
        except OSError:
            self.tray_image = Image.new("RGBA", (20, 20), (128, 128, 128, 255))
            self.mic_image = None
        self.mic_button = ctk.CTkButton(self.input_container, text="" if self.mic_image else "Mic",
                                         image=self.mic_image, width=34, height=34,
                                         fg_color="transparent", command=self.trigger_mic)
        self.mic_button.grid(row=0, column=1, sticky="ne", pady=8)
        self.settings_button = ctk.CTkButton(self.input_container, text="⚙", width=34, height=34,
                                              font=("Segoe UI Symbol", 22), fg_color="transparent",
                                              command=self.open_settings)
        self.settings_button.grid(row=0, column=2, sticky="ne", padx=(0, 8), pady=8)
        self.textbox.bind("<FocusIn>", self.focus_in)
        self.textbox.bind("<FocusOut>", self.focus_out)
        self.textbox.bind("<Return>", self.submit)
        self.textbox.bind("<<Modified>>", self.input_modified)
        # A disabled Tk Text still permits selection. Block its class bindings too.
        self.input_guard = f"LucyInputGuard{id(self)}"
        native = self.textbox._textbox
        native.bindtags((self.input_guard,) + native.bindtags())
        for sequence in ("<ButtonPress>", "<ButtonRelease>", "<Motion>", "<MouseWheel>",
                         "<KeyPress>", "<KeyRelease>", "<<Paste>>", "<<Cut>>", "<<SelectAll>>"):
            native.bind_class(self.input_guard, sequence, self.guard_input)
        self.app.bind("<Escape>", lambda event: self.toggle_window())
        self.app.bind("<Button-1>", self.clear_focus, add="+")
        self.app.protocol("WM_DELETE_WINDOW", self.close)
        self.apply_input_state()
        self.resize_input()
        self.animate_startup()
        self.app.after(30, self.drain_events)
        if enable_integrations:
            self.start_integrations()

    def post(self, method, *args):
        """Thread-safe handoff; all Tk operations run in the main event loop."""
        if not self.closed:
            self.events.put((method, args))

    def drain_events(self):
        for _ in range(100):
            try:
                method, args = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                getattr(self, method)(*args)
            except Exception:
                self.app.report_callback_exception(*sys.exc_info())
            if self.closed:
                return
        self.app.after(30, self.drain_events)

    def guard_input(self, event):
        if self.initializing or self.busy:
            return "break"

    def apply_input_state(self):
        locked = self.initializing or self.busy
        self.textbox.configure(state="disabled" if locked else "normal")
        self.textbox._textbox.configure(cursor="arrow" if locked else "xterm", takefocus=not locked)
        if locked:
            self.textbox._textbox.tag_remove("sel", "1.0", "end")
            self.app.focus_set()
        self.mic_button.configure(state="disabled" if locked else "normal")

    def set_input_text(self, text, color="#a0a0a0"):
        self.textbox.configure(state="normal", text_color=color)
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self.apply_input_state()

    def animate_startup(self, step=0):
        if self.closed or not self.initializing:
            return
        self.set_input_text("Initializing Lucy" + "." * (step % 4))
        colors = (BORDER, "#8EA0E3", "#9BB5FF", "#8EA0E3")
        self.input_container.configure(border_color=colors[step % 4])
        self.app.after(150, self.animate_startup, step + 1)

    def ready(self):
        self.initializing = False
        self.input_container.configure(border_color=BORDER)
        self.set_input_text(PLACEHOLDER)

    def startup_failed(self, message):
        self.initializing = False
        self.busy = True
        self.input_container.configure(border_color="#dc7777")
        self.set_input_text("Startup failed — restart Lucy", "#dc7777")
        self.show_notification("startup-error", "Startup failed", message)
        self.finish_notification("startup-error", "Failed")

    def set_busy(self, busy):
        self.busy = busy
        self.apply_input_state()
        if not busy:
            self.focus_out()

    def focus_in(self, event=None):
        if not self.initializing and not self.busy and self.textbox.get("1.0", "end-1c") == PLACEHOLDER:
            self.set_input_text("", "#ffffff")

    def focus_out(self, event=None):
        if not self.initializing and not self.busy and not self.textbox.get("1.0", "end-1c").strip():
            self.set_input_text(PLACEHOLDER)

    def clear_focus(self, event):
        if event.widget not in (self.textbox, self.textbox._textbox):
            self.app.focus_set()

    def input_modified(self, event=None):
        if self.textbox.edit_modified():
            self.textbox.edit_modified(False)
            self.resize_input()

    def resize_input(self):
        text = self.textbox.get("1.0", "end-1c")
        lines = 1 if self.initializing or text == PLACEHOLDER else sum(
            max(1, (len(line) + 31) // 32) for line in text.split("\n"))
        self.height = min(400, 50 + (lines - 1) * 22)
        self.app.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
        self.reposition_notifications()

    def submit(self, event):
        if self.initializing or self.busy:
            return "break"
        if event.state & 0x0001:
            return
        text = self.textbox.get("1.0", "end-1c").strip()
        if text and text != PLACEHOLDER:
            self.set_input_text("", "#ffffff")
            self.set_busy(True)
            self.on_submit(text)
        return "break"

    def trigger_mic(self):
        if not self.initializing and not self.busy:
            log("Microphone clicked...", LogColors.GREEN)

    def show_notification(self, task_id, title, text=""):
        if task_id in self.notifications:
            self.update_notification(task_id, text)
            return
        self.notifications[task_id] = Notification(self, task_id, title, text)
        self.reposition_notifications()
        if self.visible:
            self.notifications[task_id].window.deiconify()

    def update_notification(self, task_id, text):
        notification = self.notifications.get(task_id)
        if notification is not None:
            notification.update(text)

    def finish_notification(self, task_id, status="Completed"):
        notification = self.notifications.get(task_id)
        if notification is not None:
            notification.finish(status)

    def reposition_notifications(self):
        y = self.y + self.height + 8
        for notification in self.notifications.values():
            notification.window.geometry(f"{self.width}x{notification.height}+{self.x}+{y}")
            y += notification.height + 8

    def toggle_window(self):
        self.visible = not self.visible
        for window in [self.app] + [n.window for n in self.notifications.values()]:
            window.deiconify() if self.visible else window.withdraw()
        if self.visible and not self.initializing and not self.busy:
            self.app.lift()
            self.textbox.focus_set()

    def create_centered_window(self, title, width, height):
        window = ctk.CTkToplevel(self.app)
        window.title(title)
        window.configure(fg_color=BG)
        screen_w, screen_h = self.app.winfo_screenwidth(), self.app.winfo_screenheight()
        width, height = min(width, screen_w - 80), min(height, screen_h - 100)
        window.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 2}")
        window.minsize(min(440, width), min(280, height))
        window.resizable(True, True)
        window.lift()
        return window

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        self.settings_window = self.create_centered_window("LUCY Settings", 520, 340)
        panel = ctk.CTkFrame(self.settings_window, fg_color="transparent")
        panel.pack(fill="both", expand=True, padx=24, pady=20)
        ctk.CTkLabel(panel, text="Notifications", font=("Google Sans Flex", 22, "bold")).pack(anchor="w")
        self.settings_vars = {}
        for label, key, lower, upper in (("Minimum preview lines", "minimum_lines", 1, 20),
                                          ("Clear after completion (seconds)", "notification_seconds", 0, 86400)):
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.pack(fill="x", pady=(18, 0))
            ctk.CTkLabel(row, text=label).pack(side="left")
            variable = tk.StringVar(value=str(self.settings[key]))
            self.settings_vars[key] = variable
            tk.Spinbox(row, from_=lower, to=upper, textvariable=variable, width=7,
                       font=("Segoe UI", 12), bg="#303030", fg="white",
                       insertbackground="white", buttonbackground="#404040",
                       relief="flat").pack(side="right")
        ctk.CTkLabel(panel, text="Each finished notification gets its own timer.\n0 seconds keeps notifications until you close them.",
                     justify="left", text_color="#a0a0a0").pack(anchor="w", pady=(14, 0))
        self.settings_error = ctk.CTkLabel(panel, text="", text_color="#ff9999")
        self.settings_error.pack(anchor="w")
        ctk.CTkButton(panel, text="Save", command=self.save_settings).pack(anchor="e")

    def save_settings(self):
        try:
            values = {key: int(variable.get()) for key, variable in self.settings_vars.items()}
            if not 1 <= values["minimum_lines"] <= 20 or not 0 <= values["notification_seconds"] <= 86400:
                raise ValueError
        except ValueError:
            self.settings_error.configure(text="Use 1–20 lines and 0–86400 whole seconds.")
            return
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.settings_path)
        except OSError as exc:
            self.settings_error.configure(text=f"Could not save settings: {exc}")
            return
        self.settings = values
        for notification in list(self.notifications.values()):
            notification.resize()
            notification.schedule_expiry()
        self.settings_window.destroy()
        self.settings_window = None

    def start_integrations(self):
        try:
            self.hotkey = keyboard.add_hotkey("ctrl+space", lambda: self.post("toggle_window"))
            menu = pystray.Menu(
                pystray.MenuItem("Show/Hide LUCY", lambda icon, item: self.post("toggle_window"), default=True),
                pystray.MenuItem("Settings", lambda icon, item: self.post("open_settings")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda icon, item: self.post("close")))
            self.tray_icon = pystray.Icon("LUCY", self.tray_image, "LUCY", menu)
            threading.Thread(target=self.tray_icon.run, name="Lucy-Tray", daemon=True).start()
        except Exception as exc:
            log(f"[GUI] Could not enable tray or hotkey: {exc}", LogColors.YELLOW)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.hotkey is not None:
            keyboard.remove_hotkey(self.hotkey)
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.app.destroy()
        if self.on_close:
            self.on_close()

    def run(self):
        self.app.mainloop()
