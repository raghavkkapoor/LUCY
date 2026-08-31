import ctypes
from ctypes import wintypes
from time import sleep
# Win32 Constants
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020  # Pass all mouse events through
WS_EX_LAYERED = 0x00080000      # Required for hit-testing passthrough
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_NOACTIVATE = 0x0010
# System Metrics Constants
SM_CXSCREEN = 0
SM_CYSCREEN = 1

user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

def get_hwnd_from_pid(pid: int) -> int | None:
    found_hwnd = None

    def enum_windows_callback(hwnd, lparam):
        nonlocal found_hwnd
        # Only check visible windows
        if user32.IsWindowVisible(hwnd):
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid:
                found_hwnd = hwnd
                return False  # Stop enumeration
        return True  # Continue enumeration

    # Give Chrome a brief moment to create the GUI window
    sleep(1)

    callback = WNDENUMPROC(enum_windows_callback)
    user32.EnumWindows(callback, 0)
    
    return found_hwnd


def make_process_window_click_through(process_pid: int):
    # Find the Chrome window handle by title
    # hwnd = user32.FindWindowW(None, window_title)
    hwnd = get_hwnd_from_pid(process_pid)
    if hwnd:
        # Get existing window styles
        current_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        # Apply click-through and layered styles
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current_style | WS_EX_TRANSPARENT | WS_EX_LAYERED)

        # Fetch total screen dimensions
        screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
        screen_height = user32.GetSystemMetrics(SM_CYSCREEN)

        # Example: 50% width, 60% height, centered on screen
        win_width = int(screen_width * 0.25)
        win_height = int(screen_height * 0.30)
        x_pos = int((screen_width - win_width) / 2 - 350)
        y_pos = int((screen_height - win_height) / 2 - 100)

        user32.SetWindowPos(
            hwnd,
            None,
            x_pos,
            y_pos,
            win_width,
            win_height,
            SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE
        )