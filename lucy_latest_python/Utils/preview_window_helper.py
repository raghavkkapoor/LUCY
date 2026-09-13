import ctypes
from ctypes import wintypes
import tkinter as tk
import sys




# --- Win32 Structures & Constants ---
DWM_TTN_RECTDESTINATION = 0x00000001
DWM_TNM_RECTSOURCE = 0x00000002
DWM_TTN_VISIBLE = 0x00000008
DWM_TTN_OPACITY = 0x00000004
GA_ROOT = 2

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

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

# Load Win32 DLLs
dwmapi = ctypes.WinDLL("dwmapi")
user32 = ctypes.WinDLL("user32")


GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080

# Configure SetWindowLongPtr for 32-bit and 64-bit Python compatibility
if ctypes.sizeof(ctypes.c_void_p) == 8:
    SetWindowLong = user32.SetWindowLongPtrW
    GetWindowLong = user32.GetWindowLongPtrW
else:
    SetWindowLong = user32.SetWindowLongW
    GetWindowLong = user32.GetWindowLongW

SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
SetWindowLong.restype = ctypes.c_ssize_t
GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
GetWindowLong.restype = ctypes.c_ssize_t


def get_hwnd_by_pid(target_pid: int):
    """Enumerates open windows to find the main visible HWND for any given OS PID."""
    hwnd_found = None
    
    def enum_windows_callback(hwnd, extra):
        nonlocal hwnd_found
        if user32.IsWindowVisible(hwnd):
            lpdw_process_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lpdw_process_id))
            
            if lpdw_process_id.value == target_pid:
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    hwnd_found = hwnd
                    return False  # Stop enumeration
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
    return hwnd_found

def set_taskbar_visibility(hwnd: int, visible: bool):
    """Shows or hides an HWND icon from the Windows Taskbar."""
    style = GetWindowLong(hwnd, GWL_EXSTYLE)
    
    if visible:
        style &= ~WS_EX_TOOLWINDOW   # Remove tool window style
        style |= WS_EX_APPWINDOW    # Add main app window style
    else:
        style &= ~WS_EX_APPWINDOW   # Remove main app window style
        style |= WS_EX_TOOLWINDOW   # Add tool window style
        
    SetWindowLong(hwnd, GWL_EXSTYLE, style)
    
    # Force Windows Taskbar/DWM to immediately reflect the style change
    user32.ShowWindow(hwnd, 0)  # SW_HIDE
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE


class DwmPreviewApp:
    def __init__(self, root, target_pid: int):
        self.root = root
        self.target_pid = target_pid
        self.root.title(f"DWM Preview - PID {target_pid}")
        self.root.geometry("800x650")
        
        self.h_thumbnail = ctypes.c_void_p()
        self.is_hidden = False
        self.original_rect = RECT()

        # Canvas for preview rendering
        self.preview_x = 50
        self.preview_y = 70
        self.preview_width = 700
        self.preview_height = 480

        # UI Control Frame
        self.btn_toggle = tk.Button(
            self.root, 
            text="Hide Window & Enable Preview", 
            command=self.toggle_window_state,
            font=("Arial", 11, "bold"),
            bg="#2b8cbe",
            fg="white",
            pady=8
        )
        self.btn_toggle.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # Initialize native Win32 HWND references
        self.root.update_idletasks()
        self.root.update()

        self.dest_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        self.src_hwnd = get_hwnd_by_pid(self.target_pid)

        if not self.src_hwnd:
            print(f"Error: Could not locate open window for PID {self.target_pid}")
            return

        # Save the original window position before modifying it
        user32.GetWindowRect(self.src_hwnd, ctypes.byref(self.original_rect))

        # Start hidden with live preview by default
        self.hide_and_start_preview()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def register_dwm_preview(self):
        """Registers and updates the DWM thumbnail relationship."""
        if self.h_thumbnail.value:
            return

        res = dwmapi.DwmRegisterThumbnail(
            wintypes.HWND(self.dest_hwnd),
            wintypes.HWND(self.src_hwnd),
            ctypes.byref(self.h_thumbnail)
        )

        if res == 0:
            client_rect = RECT()
            user32.GetClientRect(self.src_hwnd, ctypes.byref(client_rect))

            props = DWM_THUMBNAIL_PROPERTIES()
            props.dwFlags = (
                DWM_TTN_RECTDESTINATION | 
                DWM_TNM_RECTSOURCE | 
                DWM_TTN_VISIBLE | 
                DWM_TTN_OPACITY
            )
            props.fVisible = True
            props.opacity = 255
            props.fSourceClientAreaOnly = True

            props.rcDestination = RECT(
                left=self.preview_x,
                top=self.preview_y,
                right=self.preview_x + self.preview_width,
                bottom=self.preview_y + self.preview_height
            )

            props.rcSource = RECT(
                left=0,
                top=0,
                right=client_rect.right,
                bottom=client_rect.bottom
            )

            dwmapi.DwmUpdateThumbnailProperties(
                self.h_thumbnail,
                ctypes.byref(props)
            )
        else:
            print(f"DwmRegisterThumbnail failed: {hex(res & 0xFFFFFFFF)}")

    def unregister_dwm_preview(self):
        """Unregisters the DWM thumbnail link."""
        if self.h_thumbnail.value:
            dwmapi.DwmUnregisterThumbnail(self.h_thumbnail)
            self.h_thumbnail = ctypes.c_void_p()

    def hide_and_start_preview(self):
        """Moves window offscreen and enables the DWM preview."""
        set_taskbar_visibility(self.src_hwnd, visible=False)  # remove taskbar icon

        user32.SetWindowPos(
            self.src_hwnd, 
            0, 
            -32000, 
            -32000, 
            0, 
            0, 
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        )
        self.register_dwm_preview()
        self.is_hidden = True
        self.btn_toggle.config(
            text="Restore Window to Screen (Stop Preview)", 
            bg="#e41a1c"
        )

    def restore_window(self):
        """Restores window back to its original screen coordinates and unregisters preview."""
        self.unregister_dwm_preview()
        user32.SetWindowPos(
            self.src_hwnd, 
            0, 
            0, 
            0, 
            0, 
            0, 
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        )

        set_taskbar_visibility(self.src_hwnd, visible=True)  # Restore taskbar icon

        self.is_hidden = False
        self.btn_toggle.config(
            text="Hide Window Offscreen (Start Preview)", 
            bg="#2b8cbe"
        )

    def toggle_window_state(self):
        """Toggles between hidden preview mode and restored mode."""
        if self.is_hidden:
            self.restore_window()
        else:
            # Refresh coordinates before hiding again in case the user moved it
            user32.GetWindowRect(self.src_hwnd, ctypes.byref(self.original_rect))
            self.hide_and_start_preview()

    def on_close(self):
        """Restores target window position on app exit and cleans up."""
        if self.is_hidden and self.src_hwnd:
            self.restore_window()
        self.root.destroy()


def show_browser_preview(pid):
    root = tk.Tk()
    app = DwmPreviewApp(root=root, target_pid=pid)
    root.mainloop()



if __name__ == "__main__":
    if len(sys.argv) > 1:
        pid = int(sys.argv[1])
        show_browser_preview(pid)
    else:
        print("Usage: python script.py <TARGET_PID>")