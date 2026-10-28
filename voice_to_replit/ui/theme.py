"""Dark theme for tkinter/ttk."""
import tkinter as tk
from tkinter import ttk

BG = "#1e1f24"
PANEL = "#26282f"
FIELD = "#2f323a"
FG = "#e6e6e6"
MUTED = "#9aa0aa"
ACCENT = "#f26207"  # Replit orange
ACCENT_HOVER = "#ff7a26"
OK = "#3fb950"
WARN = "#d29922"
FAIL = "#f85149"
BORDER = "#3a3d46"
FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 13)
MONO = ("Cascadia Mono", 10)


def apply(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    root.option_add("*Font", FONT)
    style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=PANEL, font=FONT,
                    selectbackground=ACCENT, selectforeground="white", insertcolor=FG)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=FONT_TITLE)
    style.configure("Bold.TLabel", font=FONT_BOLD)
    style.configure("TButton", background=FIELD, foreground=FG, padding=(12, 6), borderwidth=1)
    style.map("TButton", background=[("active", BORDER), ("disabled", PANEL)],
              foreground=[("disabled", MUTED)])
    style.configure("Accent.TButton", background=ACCENT, foreground="white", font=FONT_BOLD)
    style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", PANEL)])
    style.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG, padding=4)
    style.configure("TSpinbox", fieldbackground=FIELD, foreground=FG, background=FIELD, arrowcolor=FG,
                    insertcolor=FG, padding=4)
    style.configure("TCombobox", fieldbackground=FIELD, foreground=FG, background=FIELD, arrowcolor=FG, padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    style.configure("TCheckbutton", background=BG, foreground=FG, indicatorbackground=FIELD,
                    indicatorforeground=FG)
    style.map("TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT)])
    style.configure("TRadiobutton", background=BG, foreground=FG, indicatorbackground=FIELD,
                    indicatorforeground=FG)
    style.map("TRadiobutton", background=[("active", BG)], indicatorbackground=[("selected", ACCENT)])
    style.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, rowheight=26,
                    borderwidth=0)
    style.map("Treeview", background=[("selected", ACCENT)])
    style.configure("Treeview.Heading", background=PANEL, foreground=FG, font=FONT_BOLD, relief="flat")
    style.configure("Vertical.TScrollbar", background=PANEL, arrowcolor=FG)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD)


def text_widget(parent, height=8, readonly=False, mono=False) -> tk.Text:
    t = tk.Text(parent, height=height, wrap="word", bg=FIELD, fg=FG, insertbackground=FG,
                selectbackground=ACCENT, relief="flat", padx=8, pady=6, undo=True,
                font=MONO if mono else FONT, highlightthickness=1, highlightbackground=BORDER,
                highlightcolor=ACCENT)
    if readonly:
        t.configure(state="disabled", fg=MUTED)
    return t


def set_text(widget: tk.Text, value: str) -> None:
    state = widget.cget("state")
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    widget.configure(state=state)


def center(win: tk.Toplevel, w: int, h: int) -> None:
    win.update_idletasks()
    scale = win.winfo_fpixels("1i") / 96.0
    w, h = int(w * scale), int(h * scale)
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 3
    win.geometry(f"{w}x{h}+{x}+{y}")


def dark_titlebar(win: tk.Toplevel) -> None:
    """Ask DWM for a dark title bar (Windows 10 2004+ / 11)."""
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass
