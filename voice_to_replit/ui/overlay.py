"""Small always-on-top status pill ("Recording", "Processing") that never steals focus."""
import ctypes
import tkinter as tk

from . import theme

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


class Overlay:
    def __init__(self, root: tk.Tk):
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.93)
        self.win.configure(bg=theme.PANEL)
        frame = tk.Frame(self.win, bg=theme.PANEL, padx=16, pady=8, highlightthickness=1,
                         highlightbackground=theme.BORDER)
        frame.pack()
        self.dot = tk.Label(frame, text="●", fg=theme.FAIL, bg=theme.PANEL, font=("Segoe UI", 14))
        self.dot.pack(side="left")
        self.label = tk.Label(frame, text="", fg=theme.FG, bg=theme.PANEL, font=theme.FONT_BOLD)
        self.label.pack(side="left", padx=(8, 0))
        self.meter = tk.Canvas(frame, width=60, height=8, bg=theme.FIELD, highlightthickness=0)
        self.meter.pack(side="left", padx=(12, 0))
        self._bar = self.meter.create_rectangle(0, 0, 0, 8, fill=theme.OK, width=0)
        self._styled = False
        self._blink = None

    def _no_activate(self):
        if self._styled:
            return
        self.win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                            style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        self._styled = True

    def show(self, text: str, mode: str = "recording") -> None:
        self.label.configure(text=text)
        color = {"recording": theme.FAIL, "busy": theme.WARN, "info": theme.OK}.get(mode, theme.FG)
        self.dot.configure(fg=color)
        if mode == "recording":
            self.meter.pack(side="left", padx=(12, 0))
        else:
            self.meter.pack_forget()
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        x = (self.win.winfo_screenwidth() - w) // 2
        self.win.geometry(f"+{x}+{int(self.win.winfo_fpixels('0.35i'))}")
        self._no_activate()
        self.win.deiconify()
        self.win.lift()

    def level(self, value: float) -> None:
        w = max(0, min(60, int(value * 600)))
        self.meter.coords(self._bar, 0, 0, w, 8)

    def hide(self) -> None:
        self.win.withdraw()
