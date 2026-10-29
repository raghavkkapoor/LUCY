from playwright.sync_api import sync_playwright
import ctypes
from ctypes import wintypes
import tkinter as tk


# ============================================================
# CONFIGURATION
# ============================================================

CDP_URL = "http://localhost:9223"

OFFSET_X = 10
OFFSET_Y = 50

PREVIEW_WIDTH = 300
PREVIEW_HEIGHT = 180

# good resolution for a large preview
EXPANDED_WIDTH = 1280
EXPANDED_HEIGHT = 720

HEADER_HEIGHT = 30

ANIMATION_DURATION = 120
ANIMATION_DELAY = 5

BUTTON_SIZE = 40

BG = "#202020"
BUTTON_HOVER_BG = "#3E3E3E"
FG = "#FFFFFF"


# ============================================================
# WINDOWS API
# ============================================================

user32 = ctypes.WinDLL("user32")
dwmapi = ctypes.WinDLL("dwmapi")

GA_ROOT = 2

SM_CXSCREEN = 0
SM_CYSCREEN = 1

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

DWM_TTN_RECTDESTINATION = 0x00000001
DWM_TTN_VISIBLE = 0x00000008
DWM_TTN_OPACITY = 0x00000004


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcDestination", RECT),
        ("rcSource", RECT),
        ("opacity", ctypes.c_byte),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL),
    ]


user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

user32.GetAncestor.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
]
user32.GetAncestor.restype = wintypes.HWND

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
]
user32.GetWindowTextW.restype = ctypes.c_int

dwmapi.DwmRegisterThumbnail.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.POINTER(ctypes.c_void_p),
]
dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long

dwmapi.DwmUpdateThumbnailProperties.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(DWM_THUMBNAIL_PROPERTIES),
]
dwmapi.DwmUpdateThumbnailProperties.restype = ctypes.c_long

dwmapi.DwmUnregisterThumbnail.argtypes = [ctypes.c_void_p]
dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long


def apply_rounded_corners(hwnd):
    """Request native Windows rounded corners."""
    preference = ctypes.c_int(DWMWCP_ROUND)
    try:
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
    except Exception:
        pass


# ============================================================
# CHROME POSITIONING
# ============================================================

def move_window_offscreen():
    """
    Move the actual Chrome window offscreen.
    The Tkinter preview is positioned independently.
    """
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Chrome on port 9223: {e}"
            ) from e

        if not browser.contexts or not browser.contexts[0].pages:
            raise RuntimeError("No browser pages found on port 9223.")

        context = browser.contexts[0]
        target_page = None

        for page in context.pages:
            if (
                "gemini.google.com/app" in page.url
                or "gemini.google.com/usage" in page.url
            ):
                target_page = page
                break

        if target_page is None:
            target_page = context.pages[0]

        client = context.new_cdp_session(target_page)

        try:
            info = client.send("Browser.getWindowForTarget")

            client.send(
                "Browser.setWindowBounds",
                {
                    "windowId": info["windowId"],
                    "bounds": {
                        "left": -32000,
                        "top": -32000,
                        "width": EXPANDED_WIDTH,
                        "height": EXPANDED_HEIGHT,
                    },
                },
            )

            print("Chrome moved to (-32000, -32000).")
            return target_page.title()

        finally:
            client.detach()


# ============================================================
# FIND SOURCE WINDOW
# ============================================================

def get_hwnd_by_title(title_substring):
    found = None

    CALLBACK = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    def callback(hwnd, extra):
        nonlocal found

        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(
            hwnd,
            buffer,
            length + 1,
        )

        if title_substring.lower() in buffer.value.lower():
            found = hwnd
            return False

        return True

    user32.EnumWindows(CALLBACK(callback), 0)
    return found


# ============================================================
# PREVIEW APPLICATION
# ============================================================

class DwmPreviewApp:

    def __init__(self, root, target_title):
        self.root = root
        self.target_title = target_title

        self.screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
        self.screen_height = user32.GetSystemMetrics(SM_CYSCREEN)

        self.normal_width = min(
            PREVIEW_WIDTH,
            self.screen_width,
        )

        self.normal_height = min(
            PREVIEW_HEIGHT + HEADER_HEIGHT,
            self.screen_height,
        )

        self.expanded_width = min(
            EXPANDED_WIDTH,
            self.screen_width,
        )

        self.expanded_height = min(
            EXPANDED_HEIGHT,
            self.screen_height,
        )

        self.collapsed_height = HEADER_HEIGHT

        # States: normal, expanded, collapsed.
        self.mode = "normal"
        self.animating = False
        self.closing = False
        self.hovered = False
        self.overlay_visible = False

        self.current_width = self.normal_width
        self.current_height = self.normal_height

        self.current_x = max(
            0,
            self.screen_width - self.normal_width - OFFSET_X,
        )

        self.current_y = max(0, OFFSET_Y)

        self.h_thumbnail = ctypes.c_void_p()

        # ----------------------------------------------------
        # ROOT WINDOW
        # ----------------------------------------------------

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        self.root.configure(bg=BG)

        self.set_geometry()

        self.root.update_idletasks()
        self.root.update()

        self.dest_hwnd = user32.GetAncestor(
            self.root.winfo_id(),
            GA_ROOT,
        )

        apply_rounded_corners(self.dest_hwnd)
        self.bind_source_window()

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        self.header = tk.Frame(
            self.root,
            bg=BG,
            height=HEADER_HEIGHT,
        )

        self.header.place(
            x=0,
            y=0,
            relwidth=1,
            height=HEADER_HEIGHT,
        )

        self.title_label = tk.Label(
            self.header,
            text="Lucy Background Preview [BETA]",
            bg=BG,
            fg=FG,
            font=("Segoe UI", 10),
        )

        self.title_label.pack(
            side="left",
            padx=8,
        )

        self.minimize_button = tk.Button(
            self.root,
            text="−",
            anchor="center",
            command=self.minimize_action,
            bg=BG,
            fg=FG,
            activebackground=BUTTON_HOVER_BG,
            activeforeground=FG,
            bd=0,
            relief="flat",
            font=("Segoe UI", 20),
            cursor="hand2",
            takefocus=False,
        )

        self.minimize_button.bind("<Enter>", lambda e: self.minimize_button.config(bg=BUTTON_HOVER_BG, fg=FG))
        self.minimize_button.bind("<Leave>", lambda e: self.minimize_button.config(bg=BG, fg=FG))

        # ----------------------------------------------------
        # SEPARATE OVERLAY WINDOWS
        # ----------------------------------------------------

        self.overlay = tk.Toplevel(self.root, cursor="hand2")
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="black")
        self.overlay.attributes("-alpha", 0.38)
        self.overlay.withdraw()
        self.overlay.bind("<Button-1>", self.on_preview_click)

        # ----------------------------------------------------
        # TRANSPARENT EXPAND BUTTON WINDOW
        # ----------------------------------------------------

        self.expand_window = tk.Toplevel(self.root)
        self.expand_window.overrideredirect(True)
        self.expand_window.attributes("-topmost", True)

        self.transparent_key = "#010203"

        try:
            self.expand_window.attributes(
                "-transparentcolor",
                self.transparent_key,
            )
        except tk.TclError:
            pass

        self.expand_window.withdraw()

        self.expand_button = tk.Button(
            self.expand_window,
            text="⤢",
            font=("Segoe UI", 16, "bold"),
            bg=self.transparent_key,
            fg="#FFFFFF",
            activebackground=self.transparent_key,
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            command=self.expand_action,
            takefocus=False,
        )

        self.expand_button.pack(fill="both", expand=True)

        for widget in (
            self.root,
            self.header,
            self.title_label,
            self.overlay,
            self.expand_window,
            self.expand_button,
        ):
            widget.bind("<Enter>", self.on_enter)
            widget.bind("<Leave>", self.on_leave)

        self.root.bind("<Button-1>", self.on_root_click)

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close,
        )

        # Start background watchdog to check if Chrome/source window died or restarted
        self.root.after(2000, self.watchdog_check)

    def bind_source_window(self):
        """Finds the source window and registers the DWM thumbnail."""
        self.src_hwnd = get_hwnd_by_title(self.target_title)

        if not self.src_hwnd:
            return False

        if self.dest_hwnd == self.src_hwnd:
            return False

        # Unregister previous if any exists
        if self.h_thumbnail:
            try:
                dwmapi.DwmUnregisterThumbnail(self.h_thumbnail)
            except Exception:
                pass
            self.h_thumbnail = ctypes.c_void_p()

        result = dwmapi.DwmRegisterThumbnail(
            self.dest_hwnd,
            self.src_hwnd,
            ctypes.byref(self.h_thumbnail),
        )

        if result == 0:
            self.update_thumbnail()
            return True
        
        return False

    def watchdog_check(self):
        """Periodically ensures the source window handle is still alive and re-links if necessary."""
        if self.closing:
            return

        is_alive = self.src_hwnd and user32.IsWindow(self.src_hwnd) and user32.IsWindowVisible(self.src_hwnd)

        if not is_alive:
            try:
                new_title = move_window_offscreen()
                if new_title:
                    self.target_title = new_title
            except Exception:
                pass

            success = self.bind_source_window()
            if success:
                print("Successfully re-linked preview to new source window.")

        self.root.after(2000, self.watchdog_check)

    # ========================================================
    # GEOMETRY
    # ========================================================

    def set_geometry(self):
        self.root.geometry(
            f"{self.current_width}x{self.current_height}"
            f"+{self.current_x}+{self.current_y}"
        )

    def center_expand_button(self):
        if not self.overlay_visible:
            return

        button_size = BUTTON_SIZE
        preview_height = max(
            1,
            self.current_height - HEADER_HEIGHT,
        )

        x = (
            self.current_x
            + (self.current_width - button_size) // 2
        )

        y = (
            self.current_y
            + HEADER_HEIGHT
            + (preview_height - button_size) // 2
        )

        self.expand_window.geometry(
            f"{button_size}x{button_size}+{x}+{y}"
        )

        self.expand_window.deiconify()
        self.expand_window.lift()

    def position_overlay(self):
        if not self.overlay_visible:
            return

        overlay_height = max(
            1,
            self.current_height - HEADER_HEIGHT,
        )

        self.overlay.geometry(
            f"{self.current_width}x{overlay_height}"
            f"+{self.current_x}+{self.current_y + HEADER_HEIGHT}"
        )

        self.overlay.deiconify()
        self.overlay.lift()
        self.center_expand_button()

    # ========================================================
    # DWM THUMBNAIL
    # ========================================================

    def update_thumbnail(self):
        if not self.h_thumbnail:
            return

        props = DWM_THUMBNAIL_PROPERTIES()

        props.dwFlags = (
            DWM_TTN_RECTDESTINATION
            | DWM_TTN_VISIBLE
            | DWM_TTN_OPACITY
        )

        props.fVisible = self.mode != "collapsed"
        props.opacity = 255

        props.rcDestination = RECT(
            left=0,
            top=HEADER_HEIGHT,
            right=self.current_width,
            bottom=self.current_height,
        )

        dwmapi.DwmUpdateThumbnailProperties(
            self.h_thumbnail,
            ctypes.byref(props),
        )

    # ========================================================
    # HOVER HANDLING
    # ========================================================

    def on_enter(self, event=None):
        if self.closing:
            return

        self.hovered = True

        self.minimize_button.place(
            x=self.current_width - HEADER_HEIGHT,
            y=0,
            width=HEADER_HEIGHT + 10,
            height=HEADER_HEIGHT,
        )

        self.minimize_button.lift()

        if self.mode != "collapsed":
            self.show_overlay()

    def on_leave(self, event=None):
        if self.closing:
            return

        self.root.after(
            70,
            self.check_pointer,
        )

    def on_preview_click(self, event=None):
        self.expand_action()
        return "break"

    def on_root_click(self, event=None):
        if event is not None and event.y >= HEADER_HEIGHT:
            self.expand_action()
            return "break"

    def check_pointer(self):
        if self.closing:
            return

        px = self.root.winfo_pointerx()
        py = self.root.winfo_pointery()

        left = self.current_x
        top = self.current_y

        inside_root = (
            left <= px < left + self.current_width
            and top <= py < top + self.current_height
        )

        inside_overlay = (
            self.overlay_visible
            and left <= px < left + self.current_width
            and top + HEADER_HEIGHT <= py < top + self.current_height
        )

        self.hovered = inside_root or inside_overlay

        if not self.hovered:
            self.minimize_button.place_forget()
            self.hide_overlay()

    # ========================================================
    # OVERLAY
    # ========================================================

    def show_overlay(self):
        if self.closing or self.mode in ("collapsed", "expanded"):
            return

        self.overlay_visible = True
        self.position_overlay()

        self.overlay.lift()
        self.expand_window.lift()
        self.root.lift()
        self.minimize_button.lift()

    def hide_overlay(self):
        self.overlay_visible = False
        self.overlay.withdraw()
        self.expand_window.withdraw()

    # ========================================================
    # MINIMIZE / RESTORE
    # ========================================================

    def minimize_action(self):
        if self.animating or self.closing:
            return

        if self.mode == "expanded":
            self.hide_overlay()
            self.animate_to(
                width=self.normal_width,
                height=self.normal_height,
                x=max(
                    0,
                    self.screen_width
                    - self.normal_width
                    - OFFSET_X,
                ),
                y=max(0, OFFSET_Y),
                new_mode="normal",
            )

        elif self.mode == "normal":
            self.hide_overlay()
            self.animate_to(
                width=self.normal_width,
                height=self.collapsed_height,
                x=self.current_x,
                y=self.current_y,
                new_mode="collapsed",
            )

        elif self.mode == "collapsed":
            self.animate_to(
                width=self.normal_width,
                height=self.normal_height,
                x=max(
                    0,
                    self.screen_width
                    - self.normal_width
                    - OFFSET_X,
                ),
                y=max(0, OFFSET_Y),
                new_mode="normal",
            )

    # ========================================================
    # EXPAND
    # ========================================================

    def expand_action(self):
        if self.animating or self.closing:
            return

        if self.mode != "normal":
            return

        self.hide_overlay()

        target_x = (
            self.screen_width - self.expanded_width
        ) // 2

        target_y = (
            self.screen_height - self.expanded_height
        ) // 2

        self.animate_to(
            width=self.expanded_width,
            height=self.expanded_height,
            x=max(0, target_x),
            y=max(0, target_y),
            new_mode="expanded",
        )

    # ========================================================
    # ANIMATION
    # ========================================================

    def animate_to(
        self,
        width,
        height,
        x,
        y,
        new_mode,
    ):
        if self.animating or self.closing:
            return

        self.animating = True

        self.target_width = width
        self.target_height = height
        self.target_x = x
        self.target_y = y
        self.target_mode = new_mode

        self.animation_start = (
            self.current_width,
            self.current_height,
            self.current_x,
            self.current_y,
        )

        self.animation_started_at = self.root.tk.call(
            "clock",
            "milliseconds",
        )

        self.animate_step()

    def animate_step(self):
        if self.closing:
            return

        now = self.root.tk.call(
            "clock",
            "milliseconds",
        )

        elapsed = now - self.animation_started_at

        progress = min(
            1.0,
            elapsed / ANIMATION_DURATION,
        )

        eased = 1.0 - (1.0 - progress) ** 3

        starts = self.animation_start

        targets = (
            self.target_width,
            self.target_height,
            self.target_x,
            self.target_y,
        )

        values = [
            round(start + (target - start) * eased)
            for start, target in zip(starts, targets)
        ]

        if progress >= 1.0:
            values = list(targets)

        (
            self.current_width,
            self.current_height,
            self.current_x,
            self.current_y,
        ) = values

        self.set_geometry()
        self.update_thumbnail()

        if self.overlay_visible:
            self.position_overlay()

        if self.hovered:
            self.minimize_button.place_configure(
                x=self.current_width - HEADER_HEIGHT,
                y=0,
            )

        if progress >= 1.0:
            self.mode = self.target_mode
            self.animating = False

            self.update_thumbnail()

            if self.mode == "collapsed":
                self.hide_overlay()
                self.minimize_button.configure(text="+")
            else:
                self.minimize_button.configure(text="−")

                if self.hovered:
                    self.show_overlay()

            apply_rounded_corners(self.dest_hwnd)
            return

        self.root.after(
            ANIMATION_DELAY,
            self.animate_step,
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    def close(self):
        if self.closing:
            return

        self.closing = True

        if self.h_thumbnail:
            dwmapi.DwmUnregisterThumbnail(
                self.h_thumbnail,
            )
            self.h_thumbnail = ctypes.c_void_p()

        try:
            self.overlay.destroy()
            self.expand_window.destroy()
        except tk.TclError:
            pass

        self.root.destroy()


# ============================================================
# ENTRY POINT
# ============================================================

def render_window_preview(process_window_name):
    root = tk.Tk()

    DwmPreviewApp(
        root=root,
        target_title=process_window_name,
    )

    root.mainloop()


if __name__ == "__main__":
    title = move_window_offscreen()
    render_window_preview(title)