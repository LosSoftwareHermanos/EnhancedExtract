"""Windows without the Windows title bar and frame, used by the main window and pop-ups.

The window stays a normal window (taskbar, Alt+Tab, keyboard focus, Alt+F4). Tk's own
overrideredirect would remove the bar too, but Windows then never gives the window
keyboard focus.

After the bar is removed, Tk still counts its height and would shrink the window
whenever Tk itself moves or sizes it. So moving and resizing here go straight through
Windows, never through Tk's geometry().
"""
import ctypes
import os
from ctypes import wintypes
import tkinter as tk

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_EX_EDGES = 0x00000001 | 0x00000100 | 0x00000200 | 0x00020000   # dialog, window, client, static edges
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20

try:
    user32 = ctypes.windll.user32
except AttributeError:  # not Windows
    user32 = None


ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")


def set_app_icon(root):
    """App icon on the window, every pop-up and the taskbar. Without its own app ID,
    Windows groups the app under python.exe and shows Python's icon on the taskbar."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EnhancedExtract")
    except (AttributeError, OSError):
        pass
    try:
        root.iconbitmap(default=ICON)   # default= also covers pop-ups opened later
    except tk.TclError:
        pass


def hwnd_of(win):
    return user32.GetParent(win.winfo_id())


def window_rect(win):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd_of(win), ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def hide_title_bar(win, keep_system_menu=False):
    """Strip the title bar and frame. keep_system_menu keeps what the taskbar and Alt+F4
    need (minimize/restore from the taskbar, close) for a main window."""
    try:
        hwnd = hwnd_of(win)
        remove = WS_CAPTION | WS_THICKFRAME | (0 if keep_system_menu else WS_SYSMENU)
        user32.SetWindowLongW(hwnd, GWL_STYLE, user32.GetWindowLongW(hwnd, GWL_STYLE) & ~remove)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & ~WS_EX_EDGES)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)
        user32.SetForegroundWindow(hwnd)
        return True
    except (OSError, AttributeError):
        return False


def move(win, x, y):
    user32.SetWindowPos(hwnd_of(win), 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)


def place(win, x, y, w, h):
    user32.SetWindowPos(hwnd_of(win), 0, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE)


def make_draggable(win, handle):
    """Dragging `handle` moves `win`."""
    start = {}

    def press(e):
        x, y, _, _ = window_rect(win)
        start.update(mx=e.x_root, my=e.y_root, x=x, y=y)

    def motion(e):
        if start:
            move(win, start["x"] + e.x_root - start["mx"], start["y"] + e.y_root - start["my"])

    handle.bind("<ButtonPress-1>", press, add="+")
    handle.bind("<B1-Motion>", motion, add="+")


class ResizeGrip(tk.Canvas):
    """Drag handle in a window's bottom-right corner, standing in for the removed frame."""

    SIZE = 16

    def __init__(self, win, min_w, min_h, bg, fg):
        super().__init__(win, width=self.SIZE, height=self.SIZE, bg=bg, highlightthickness=0, bd=0,
                         cursor="size_nw_se")
        for i in (4, 8, 12):
            self.create_line(self.SIZE - 2, i, i, self.SIZE - 2, fill=fg)
        self.win, self.min_w, self.min_h = win, min_w, min_h
        self._start = None
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_start", None))
        self.place(relx=1, rely=1, anchor="se")

    def _press(self, e):
        self._start = (e.x_root, e.y_root, window_rect(self.win))

    def _motion(self, e):
        if not self._start:
            return
        mx, my, (x, y, w, h) = self._start
        place(self.win, x, y, max(self.min_w, w + e.x_root - mx), max(self.min_h, h + e.y_root - my))
        tk.Misc.lift(self)    # keep it above the page content (Canvas.lift means something else)
