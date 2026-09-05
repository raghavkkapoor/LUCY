import ctypes
import argparse
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

# Extended Window Styles (GWL_EXSTYLE)
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
# Window Styles (GWL_STYLE)
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX   = 0x00010000

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


def make_process_window_click_through(process_pid: int, width_scale: float = 0.5, height_scale: float = 0.5):
    # Find the Chrome window handle by title
    # hwnd = user32.FindWindowW(None, window_title)
    hwnd = get_hwnd_from_pid(process_pid)
    if hwnd:
        # Get existing window styles
        current_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        # Apply click-through and layered styles
        user32.SetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
            current_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        )
        current_window_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(
            hwnd,
            GWL_STYLE,
            current_window_style & ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        )
        # Prevent the user from focusing or typing into the browser window.
        user32.EnableWindow(hwnd, False)

        # Fetch total screen dimensions
        screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
        screen_height = user32.GetSystemMetrics(SM_CYSCREEN)

        win_width = int(screen_width * width_scale)
        win_height = int(screen_height * height_scale)
        x_pos = int((screen_width - win_width) / 2)
        y_pos = int((screen_height - win_height) / 2)

        user32.SetWindowPos(
            hwnd,
            None,
            x_pos,
            y_pos,
            win_width,
            win_height,
            SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--width-scale", type=float, default=0.5)
    parser.add_argument("--height-scale", type=float, default=0.5)
    args = parser.parse_args()

    if not 0 < args.width_scale <= 1 or not 0 < args.height_scale <= 1:
        raise SystemExit("Window scales must be greater than 0 and no greater than 1.")

    make_process_window_click_through(args.pid, args.width_scale, args.height_scale)


if __name__ == "__main__":
    main()
