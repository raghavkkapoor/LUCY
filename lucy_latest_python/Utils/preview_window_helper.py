from playwright.sync_api import sync_playwright
import ctypes
from ctypes import wintypes
import tkinter as tk

# --- Win32 Structures & Constants ---
DWM_TTN_RECTDESTINATION = 0x00000001
DWM_TTN_VISIBLE = 0x00000008
DWM_TTN_OPACITY = 0x00000004
GA_ROOT = 2

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcDestination", RECT),
        ("rcSource", RECT),
        ("opacity", ctypes.c_byte),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL)
    ]

# Load DLLs
dwmapi = ctypes.WinDLL("dwmapi")
user32 = ctypes.WinDLL("user32")

def move_window_offscreen():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://localhost:9223")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to browser on port 9223: {e}")

        if not browser.contexts or not browser.contexts[0].pages:
            raise RuntimeError("No browser pages found on debugging port 9223.")

        context = browser.contexts[0]
        target_page = None

        # 1. Look for matching URL
        for page in context.pages:
            url = page.url
            if "gemini.google.com/app" in url or "gemini.google.com/usage" in url:
                target_page = page
                print("FOUND TARGET PAGE BY URL")
                break

        # 2. Fallback to first page if URL match wasn't found
        if target_page is None:
            target_page = context.pages[0]
            print(f"URL match not found. Defaulting to first available page: {target_page.url}")

        # 3. Create CDP Session and move window
        client = context.new_cdp_session(target_page)
        window_info = client.send("Browser.getWindowForTarget")
        window_id = window_info["windowId"]

        client.send("Browser.setWindowBounds", {
            "windowId": window_id,
            "bounds": {
                "left": -32000,
                "top": -32000
            }
        })
        print("Preview window successfully repositioned offscreen to (-32000, -32000).")

        return target_page.title()

def get_hwnd_by_title(title_substring):
    """Finds a window handle (HWND) containing title_substring."""
    hwnd_found = None
    
    def enum_windows_callback(hwnd, extra):
        nonlocal hwnd_found
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                # Ignore empty or irrelevant titles
                if title_substring.lower() in buff.value.lower():
                    hwnd_found = hwnd
                    return False  # Stop searching
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
    return hwnd_found


class DwmPreviewApp:
    def __init__(self, root, target_title, x, y, width, height):
        self.root = root
        self.root.title("DWM Thumbnail Preview")
        self.root.geometry("800x600")
        
        # Force Tkinter to initialize graphics & create the native Win32 HWND
        self.root.update_idletasks()
        self.root.update()

        self.h_thumbnail = ctypes.c_void_p()

        # Get top-level HWND of our Tkinter window
        self.dest_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        
        # Get HWND of target process window
        self.src_hwnd = get_hwnd_by_title(target_title)

        if not self.src_hwnd:
            print(f"Error: Could not find open window matching title '{target_title}'")
            return

        # Avoid linking a window to itself
        if self.dest_hwnd == self.src_hwnd:
            print("Error: Target window is the same as the destination window.")
            return

        # Register thumbnail link
        res = dwmapi.DwmRegisterThumbnail(
            wintypes.HWND(self.dest_hwnd),
            wintypes.HWND(self.src_hwnd),
            ctypes.byref(self.h_thumbnail)
        )

        if res == 0:
            self.update_preview_rect(x, y, width, height)
            # print("DWM Thumbnail registered successfully!")
            print("Rendering process preview...")
        else:
            # Mask HRESULT to unsigned 32-bit hex format
            hresult_hex = hex(res & 0xFFFFFFFF)
            print(f"DwmRegisterThumbnail failed with HRESULT: {hresult_hex}")

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def update_preview_rect(self, x, y, width, height):
        """Sets destination position and bounds inside the host window."""
        props = DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = DWM_TTN_RECTDESTINATION | DWM_TTN_VISIBLE | DWM_TTN_OPACITY
        props.fVisible = True
        props.opacity = 255  # 0 to 255
        
        props.rcDestination = RECT(
            left=x,
            top=y,
            right=x + width,
            bottom=y + height
        )

        dwmapi.DwmUpdateThumbnailProperties(
            self.h_thumbnail,
            ctypes.byref(props)
        )

    def on_close(self):
        if self.h_thumbnail:
            dwmapi.DwmUnregisterThumbnail(self.h_thumbnail)
        self.root.destroy()



def render_window_preview(process_window_name = None):
    if not process_window_name:
        return

    root = tk.Tk()
    app = DwmPreviewApp(
        root=root,
        target_title=process_window_name,
        x=50,
        y=50,
        width=500,
        height=350
    )

    root.mainloop()

if __name__ == "__main__":
    name = move_window_offscreen()
    render_window_preview(name)