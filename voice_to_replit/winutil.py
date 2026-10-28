"""Win32 helpers: DPI awareness, Replit window discovery, focus, clipboard and input."""
import ctypes
import logging
import os
import time
from dataclasses import dataclass

import psutil
import win32api
import win32clipboard
import win32con
import win32gui
import win32process

log = logging.getLogger(__name__)
user32 = ctypes.windll.user32

KNOWN_APPS = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "replit.exe": "Replit desktop app", "brave.exe": "Brave", "opera.exe": "Opera",
}


def make_dpi_aware() -> None:
    """Per-monitor DPI awareness so screen coordinates are physical pixels everywhere."""
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            user32.SetProcessDPIAware()


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    exe: str

    @property
    def app(self) -> str:
        return KNOWN_APPS.get(self.exe.lower(), self.exe)

    def label(self) -> str:
        return f"{self.title}  [{self.app}]"


def _exe_for(hwnd: int) -> str:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name()
    except Exception:
        return "?"


def find_replit_windows() -> list[WindowInfo]:
    own_pid = os.getpid()
    found = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if "replit" not in title.lower():
            return True
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == own_pid:
            return True
        exe = _exe_for(hwnd)
        if exe.lower() in ("explorer.exe",):
            return True
        found.append(WindowInfo(hwnd, title, exe))
        return True

    win32gui.EnumWindows(cb, None)
    # Prefer known browsers / the Replit app first.
    found.sort(key=lambda w: w.exe.lower() not in KNOWN_APPS)
    return found


def window_rect(hwnd: int) -> list[int]:
    return list(win32gui.GetWindowRect(hwnd))


def root_window_at(x: int, y: int) -> int:
    hwnd = win32gui.WindowFromPoint((x, y))
    return user32.GetAncestor(hwnd, 2) if hwnd else 0  # GA_ROOT


def cursor_pos() -> tuple[int, int]:
    return win32api.GetCursorPos()


def force_foreground(hwnd: int) -> bool:
    """Bring a window to the front, working around Windows' foreground lock."""
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.3)
    fg = win32gui.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur_thread = win32api.GetCurrentThreadId()
    fg_thread = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
    attached = False
    try:
        if fg_thread and fg_thread != cur_thread:
            attached = bool(user32.AttachThreadInput(fg_thread, cur_thread, True))
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # A lone ALT tap releases the foreground lock.
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            win32gui.SetForegroundWindow(hwnd)
    except Exception as e:
        log.warning("SetForegroundWindow failed: %s", e)
    finally:
        if attached:
            user32.AttachThreadInput(fg_thread, cur_thread, False)
    time.sleep(0.25)
    return win32gui.GetForegroundWindow() == hwnd


# ---------------------------------------------------------------- clipboard

def _open_clipboard(retries: int = 20) -> None:
    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard(0)
            return
        except Exception:
            time.sleep(0.05)
    win32clipboard.OpenClipboard(0)


def save_clipboard() -> list[tuple[int, bytes]]:
    """Snapshot every clipboard format that can be copied as raw data."""
    saved = []
    _open_clipboard()
    try:
        fmt = win32clipboard.EnumClipboardFormats(0)
        while fmt:
            try:
                saved.append((fmt, win32clipboard.GetClipboardData(fmt)))
            except Exception:
                pass  # handle-based formats (bitmaps, etc.) can't be copied this way
            fmt = win32clipboard.EnumClipboardFormats(fmt)
    finally:
        win32clipboard.CloseClipboard()
    return saved


def restore_clipboard(saved: list[tuple[int, bytes]]) -> None:
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        for fmt, data in saved:
            try:
                if fmt == win32con.CF_UNICODETEXT:
                    win32clipboard.SetClipboardText(data, fmt)
                elif fmt in (win32con.CF_TEXT, win32con.CF_OEMTEXT, win32con.CF_LOCALE):
                    continue  # Windows synthesises these from CF_UNICODETEXT
                else:
                    win32clipboard.SetClipboardData(fmt, data)
            except Exception:
                pass
    finally:
        win32clipboard.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def get_clipboard_text() -> str:
    _open_clipboard()
    try:
        return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    except Exception:
        return ""
    finally:
        win32clipboard.CloseClipboard()


# ---------------------------------------------------------------- input

MODIFIERS = (win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_SHIFT, win32con.VK_LWIN, win32con.VK_RWIN)


def wait_modifiers_released(timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(win32api.GetAsyncKeyState(vk) & 0x8000 for vk in MODIFIERS):
            return
        time.sleep(0.03)


def key_tap(vk: int, modifiers: tuple = ()) -> None:
    for m in modifiers:
        win32api.keybd_event(m, 0, 0, 0)
    win32api.keybd_event(vk, 0, 0, 0)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    for m in reversed(modifiers):
        win32api.keybd_event(m, 0, win32con.KEYEVENTF_KEYUP, 0)


def click_at(x: int, y: int, restore_cursor: bool = True) -> None:
    old = win32api.GetCursorPos()
    win32api.SetCursorPos((x, y))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.05)
    if restore_cursor:
        win32api.SetCursorPos(old)


def paste() -> None:
    key_tap(ord("V"), (win32con.VK_CONTROL,))


def press_enter() -> None:
    key_tap(win32con.VK_RETURN)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
