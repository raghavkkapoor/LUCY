import ctypes
from ctypes import wintypes
import customtkinter as ctk
import sys

# --- Win32 Structures & Constants ---
DWM_TTN_RECTDESTINATION = 0x00000001
DWM_TNM_RECTSOURCE = 0x00000002
DWM_TTN_VISIBLE = 0x00000008
DWM_TTN_OPACITY = 0x00000004
GA_ROOT = 2

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
    
    user32.ShowWindow(hwnd, 0)  # SW_HIDE
    user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE

class DwmPreviewApp:
    def __init__(self, root, target_pid: int):
        self.root = root
        self.target_pid = target_pid
        
        # Remove native Windows title bar frame completely
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # Apply CustomTkinter theme settings with zero margin background
        ctk.set_appearance_mode("Dark")
        self.dark_bg = "#121212"
        self.root.configure(fg_color=self.dark_bg)

        self.h_thumbnail = ctypes.c_void_p()
        self.is_hidden = False
        self.original_rect = RECT()
        self._resize_job = None

        # UI Control Button at the top spanning full width with zero side padding
        self.btn_toggle = ctk.CTkButton(
            master=self.root,
            text="Hide Window & Enable Preview",
            command=self.toggle_window_state,
            font=("Google Sans Flex", 12, "bold"),
            fg_color="#1f4e79",
            hover_color="#16385d",
            text_color="white",
            corner_radius=0,
            height=34
        )
        self.btn_toggle.pack(side=ctk.TOP, fill=ctk.X, padx=0, pady=0)

        # Enable window dragging from the toggle button since title bar is removed
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.on_motion)

        # Preview Area Container Frame filling remaining space completely with zero borders or padding
        self.preview_frame = ctk.CTkFrame(
            master=self.root,
            fg_color="#121212",
            corner_radius=0,
            border_width=0
        )
        self.preview_frame.pack(side=ctk.TOP, fill="both", expand=True, padx=0, pady=0)

        # Initialize native Win32 HWND references early to compute automatic dimensions
        self.root.update_idletasks()
        self.root.update()

        self.dest_hwnd = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        self.src_hwnd = get_hwnd_by_pid(self.target_pid)

        if not self.src_hwnd:
            print(f"Error: Could not locate open window for PID {self.target_pid}")
            return

        user32.GetWindowRect(self.src_hwnd, ctypes.byref(self.original_rect))

        # Automatically compute initial geometry based on target source aspect ratio + button height
        client_rect = RECT()
        user32.GetClientRect(self.src_hwnd, ctypes.byref(client_rect))
        src_w = client_rect.right if client_rect.right > 0 else 1920
        src_h = client_rect.bottom if client_rect.bottom > 0 else 1080
        
        init_w = 500
        button_h = 34
        init_h = int(init_w * (src_h / src_w)) + button_h
        
        self.root.geometry(f"{init_w}x{init_h}")
        self.root.minsize(350, int(350 * (src_h / src_w)) + button_h)

        # Bind window resizing to dynamically lock aspect ratio and update the preview
        self.root.bind("<Configure>", self.on_window_configure)

        # Start hidden with live preview by default
        self.hide_and_start_preview()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def start_move(self, event):
        self._x = event.x
        self._y = event.y

    def on_motion(self, event):
        x = self.root.winfo_x() + (event.x - self._x)
        y = self.root.winfo_y() + (event.y - self._y)
        self.root.geometry(f"+{x}+{y}")

    def register_dwm_preview(self):
        """Registers and updates the DWM thumbnail relationship with aspect ratio preservation."""
        if self.h_thumbnail.value:
            self.update_dwm_preview_geometry()
            return

        res = dwmapi.DwmRegisterThumbnail(
            wintypes.HWND(self.dest_hwnd),
            wintypes.HWND(self.src_hwnd),
            ctypes.byref(self.h_thumbnail)
        )

        if res == 0:
            self.update_dwm_preview_geometry()
        else:
            print(f"DwmRegisterThumbnail failed: {hex(res & 0xFFFFFFFF)}")

    def update_dwm_preview_geometry(self):
        """Dynamically calculates scaling factors and letterboxes to preserve the source aspect ratio."""
        if not self.h_thumbnail.value or not self.src_hwnd:
            return

        self.preview_frame.update_idletasks()
        
        container_width = self.preview_frame.winfo_width()
        container_height = self.preview_frame.winfo_height()

        if container_width <= 10 or container_height <= 10:
            return

        container_x = self.preview_frame.winfo_rootx() - self.root.winfo_rootx()
        container_y = self.preview_frame.winfo_rooty() - self.root.winfo_rooty()

        client_rect = RECT()
        user32.GetClientRect(self.src_hwnd, ctypes.byref(client_rect))
        src_w = client_rect.right
        src_h = client_rect.bottom

        if src_w <= 0 or src_h <= 0:
            return

        scale = min(container_width / src_w, container_height / src_h)
        
        target_w = int(src_w * scale)
        target_h = int(src_h * scale)

        offset_x = container_x + (container_width - target_w) // 2
        offset_y = container_y + (container_height - target_h) // 2

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
            left=offset_x,
            top=offset_y,
            right=offset_x + target_w,
            bottom=offset_y + target_h
        )

        props.rcSource = RECT(
            left=0,
            top=0,
            right=src_w,
            bottom=src_h
        )

        dwmapi.DwmUpdateThumbnailProperties(
            self.h_thumbnail,
            ctypes.byref(props)
        )

    def on_window_configure(self, event):
        """Debounces window resize events, locks aspect ratio, and updates preview geometry smoothly."""
        if event.widget == self.root:
            if self._resize_job is not None:
                self.root.after_cancel(self._resize_job)
            self._resize_job = self.root.after(10, self.adjust_geometry_and_preview)

    def adjust_geometry_and_preview(self):
        """Enforces the source window aspect ratio on the Tkinter window automatically."""
        if not self.src_hwnd:
            return

        client_rect = RECT()
        user32.GetClientRect(self.src_hwnd, ctypes.byref(client_rect))
        src_w = client_rect.right
        src_h = client_rect.bottom
        if src_w <= 0 or src_h <= 0:
            src_w, src_h = 1920, 1080

        current_width = self.root.winfo_width()
        button_height = self.btn_toggle.winfo_height()
        if button_height <= 1:
            button_height = 34

        target_container_height = int(current_width * (src_h / src_w))
        target_total_height = target_container_height + button_height

        current_height = self.root.winfo_height()
        if abs(current_height - target_total_height) > 2:
            self.root.geometry(f"{current_width}x{target_total_height}")
            return

        self.update_dwm_preview_geometry()

    def unregister_dwm_preview(self):
        """Unregisters the DWM thumbnail link."""
        if self.h_thumbnail.value:
            dwmapi.DwmUnregisterThumbnail(self.h_thumbnail)
            self.h_thumbnail = ctypes.c_void_p()

    def hide_and_start_preview(self):
        """Moves window offscreen, enforces a consistent source resolution (1920x1080), and enables preview."""
        set_taskbar_visibility(self.src_hwnd, visible=False)

        user32.SetWindowPos(
            self.src_hwnd, 
            0, 
            -32000, 
            -32000, 
            1920, 
            1080, 
            SWP_NOZORDER | SWP_NOACTIVATE
        )
        self.register_dwm_preview()
        self.is_hidden = True
        self.btn_toggle.configure(
            text="Restore Window to Screen (Stop Preview)", 
            fg_color="#1f4e79",
            hover_color="#16385d"
        )

    def restore_window(self):
        """Restores window back to its original screen coordinates and size, then unregisters preview."""
        self.unregister_dwm_preview()
        
        orig_w = self.original_rect.right - self.original_rect.left
        orig_h = self.original_rect.bottom - self.original_rect.top
        
        user32.SetWindowPos(
            self.src_hwnd, 
            0, 
            0, 
            0, 
            orig_w, 
            orig_h, 
            SWP_NOZORDER | SWP_NOACTIVATE
        )

        set_taskbar_visibility(self.src_hwnd, visible=True)

        self.is_hidden = False
        self.btn_toggle.configure(
            text="Hide Window Offscreen (Start Preview)", 
            fg_color="#1f4e79",
            hover_color="#16385d"
        )

    def toggle_window_state(self):
        """Toggles between hidden preview mode and restored mode."""
        if self.is_hidden:
            self.restore_window()
        else:
            user32.GetWindowRect(self.src_hwnd, ctypes.byref(self.original_rect))
            self.hide_and_start_preview()

    def on_close(self):
        """Restores target window position on app exit and cleans up."""
        if self.is_hidden and self.src_hwnd:
            self.restore_window()
        self.root.destroy()

def show_browser_preview(pid):
    root = ctk.CTk()
    app = DwmPreviewApp(root=root, target_pid=pid)
    root.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        pid = int(sys.argv[1])
        show_browser_preview(pid)
    else:
        print("Usage: python script.py <TARGET_PID>")