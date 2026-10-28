"""Smaller dialogs: window chooser, hotkey capture, history, system check."""
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .. import history
from . import theme


def _toplevel(root, title, w, h, modal=False):
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=theme.BG)
    theme.center(win, w, h)
    theme.dark_titlebar(win)
    if modal:
        win.attributes("-topmost", True)
        win.grab_set()
    win.bind("<Escape>", lambda e: win.destroy())
    return win


def choose_window(root, windows):
    """Let the user pick one of several Replit windows. Returns the WindowInfo or None."""
    win = _toplevel(root, "Choose the Replit window", 560, 300, modal=True)
    body = ttk.Frame(win, padding=16)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="More than one Replit window is open. Which one?", style="Bold.TLabel").pack(anchor="w")
    lb = tk.Listbox(body, bg=theme.FIELD, fg=theme.FG, selectbackground=theme.ACCENT, relief="flat",
                    highlightthickness=0, activestyle="none")
    for wi in windows:
        lb.insert("end", wi.label())
    lb.selection_set(0)
    lb.pack(fill="both", expand=True, pady=10)
    result = {}

    def ok(*_):
        sel = lb.curselection()
        if sel:
            result["w"] = windows[sel[0]]
        win.destroy()

    bar = ttk.Frame(body)
    bar.pack(fill="x")
    ttk.Button(bar, text="Use this window", style="Accent.TButton", command=ok).pack(side="right")
    ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right", padx=8)
    lb.bind("<Double-Button-1>", ok)
    win.bind("<Return>", ok)
    win.focus_force()
    root.wait_window(win)
    return result.get("w")


_KEYSYM_MAP = {"space": "<space>", "Return": "<enter>", "Tab": "<tab>", "Insert": "<insert>",
               "Home": "<home>", "End": "<end>", "Prior": "<page_up>", "Next": "<page_down>",
               "Pause": "<pause>", "Scroll_Lock": "<scroll_lock>"}
_MODIFIER_KEYSYMS = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R", "Win_L", "Win_R"}


def capture_hotkey(root):
    """Modal 'press your new hotkey' dialog. Returns a pynput-style string or None."""
    win = _toplevel(root, "Set hotkey", 420, 170, modal=True)
    body = ttk.Frame(win, padding=20)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="Press the new key combination...", style="Bold.TLabel").pack()
    shown = ttk.Label(body, text="", style="Title.TLabel")
    shown.pack(pady=10)
    ttk.Label(body, text="Esc to cancel", style="Muted.TLabel").pack()
    result = {}

    def on_key(e):
        if e.keysym == "Escape":
            win.destroy()
            return "break"
        if e.keysym in _MODIFIER_KEYSYMS:
            return "break"
        parts = []
        if e.state & 0x4:
            parts.append("<ctrl>")
        if e.state & 0x20000:
            parts.append("<alt>")
        if e.state & 0x1:
            parts.append("<shift>")
        ks = e.keysym
        if ks in _KEYSYM_MAP:
            key = _KEYSYM_MAP[ks]
        elif ks.startswith("F") and ks[1:].isdigit():
            key = f"<{ks.lower()}>"
        elif len(ks) == 1 and ks.isalnum():
            key = ks.lower()
        else:
            shown.configure(text=f"'{ks}' is not supported")
            return "break"
        result["hk"] = "+".join(parts + [key])
        shown.configure(text=result["hk"])
        win.after(500, win.destroy)
        return "break"

    win.bind("<KeyPress>", on_key)
    win.focus_force()
    root.wait_window(win)
    return result.get("hk")


class HistoryWindow:
    def __init__(self, root, on_resend):
        self.items = history.load()
        win = self.win = _toplevel(root, "Voice to Replit - History", 760, 520)
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Last {len(self.items)} sent prompts", style="Title.TLabel").pack(anchor="w")
        tree = self.tree = ttk.Treeview(body, columns=("time", "prompt"), show="headings", height=8)
        tree.heading("time", text="Sent")
        tree.heading("prompt", text="Prompt")
        tree.column("time", width=150, stretch=False)
        tree.column("prompt", width=520)
        for i, it in enumerate(self.items):
            ts = datetime.fromisoformat(it["timestamp"]).strftime("%Y-%m-%d %H:%M")
            first = it["prompt"].strip().splitlines()[0] if it["prompt"].strip() else ""
            tree.insert("", "end", iid=str(i), values=(ts, first))
        tree.pack(fill="both", expand=True, pady=(10, 8))
        self.preview = theme.text_widget(body, height=8, readonly=True)
        self.preview.pack(fill="both", expand=True)
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
        self.btn = ttk.Button(bar, text="Resend...", style="Accent.TButton",
                              command=lambda: self._resend(on_resend))
        self.btn.pack(side="right", padx=8)
        tree.bind("<<TreeviewSelect>>", self._select)
        tree.bind("<Double-Button-1>", lambda e: self._resend(on_resend))
        if self.items:
            tree.selection_set("0")
        else:
            theme.set_text(self.preview, "Nothing sent yet.")
            self.btn.state(["disabled"])

    def _current(self):
        sel = self.tree.selection()
        return self.items[int(sel[0])] if sel else None

    def _select(self, _=None):
        it = self._current()
        if it:
            theme.set_text(self.preview, it["prompt"])

    def _resend(self, on_resend):
        it = self._current()
        if it:
            self.win.destroy()
            on_resend(it)


class SystemCheckWindow:
    def __init__(self, root, settings, on_apply):
        from .. import syscheck
        self.syscheck, self.settings, self.on_apply = syscheck, settings, on_apply
        win = self.win = _toplevel(root, "Voice to Replit - System Check", 780, 600)
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="System compatibility check", style="Title.TLabel").pack(anchor="w")
        self.rows = ttk.Frame(body)
        self.rows.pack(fill="both", expand=True, pady=10)
        ttk.Label(self.rows, text="Checking...", style="Muted.TLabel").pack(anchor="w")

        rec = ttk.Frame(body)
        rec.pack(fill="x", pady=(4, 0))
        ttk.Label(rec, text="Recommended models (you can change them):", style="Bold.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        from ..stt import WHISPER_SIZES
        self.whisper = tk.StringVar(value=settings["whisper_model"])
        self.ollama = tk.StringVar(value=settings["ollama_model"])
        ttk.Label(rec, text="Whisper").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(rec, textvariable=self.whisper, values=WHISPER_SIZES, width=18, state="readonly").grid(
            row=1, column=1, padx=8)
        ttk.Label(rec, text="Ollama").grid(row=1, column=2, sticky="w")
        ttk.Combobox(rec, textvariable=self.ollama, width=18,
                     values=["llama3.2", "qwen2.5:3b", "qwen2.5:7b", "llama3.2:1b"]).grid(row=1, column=3, padx=8)
        self.btn_apply = ttk.Button(rec, text="Accept models", style="Accent.TButton", command=self._apply)
        self.btn_apply.grid(row=1, column=4, padx=8)

        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(12, 0))
        self.btn_mic = ttk.Button(bar, text="Test microphone (3 s)", command=self._mic)
        self.btn_mic.pack(side="left")
        self.mic_status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.mic_status.pack(side="left", padx=10)
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Open report", command=self._open_report).pack(side="right", padx=8)
        self.report = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        from ..llm import is_local_url
        url = self.settings["ollama_url"]
        if not self.settings.cloud and not is_local_url(url):
            url = "http://127.0.0.1:11434"  # Local mode only ever checks Ollama on this computer
        rep = self.syscheck.run_checks(url, self.settings["ollama_model"])
        self.syscheck.save_report(rep)
        self.win.after(0, self._show, rep)

    def _show(self, rep):
        self.report = rep
        for c in self.rows.winfo_children():
            c.destroy()
        colors = {"PASS": theme.OK, "WARN": theme.WARN, "FAIL": theme.FAIL, "INFO": theme.MUTED}
        for i, c in enumerate(rep.checks):
            tk.Label(self.rows, text=c.status, fg=colors[c.status], bg=theme.BG, font=theme.FONT_BOLD,
                     width=6, anchor="w").grid(row=i, column=0, sticky="nw")
            ttk.Label(self.rows, text=c.name, style="Bold.TLabel").grid(row=i, column=1, sticky="nw", padx=(0, 12))
            ttk.Label(self.rows, text=c.detail, wraplength=520).grid(row=i, column=2, sticky="nw", pady=1)
        tk.Label(self.rows, text=f"Recommended: Whisper {rep.recommended_whisper}, Ollama {rep.recommended_ollama}",
                 fg=theme.ACCENT, bg=theme.BG, font=theme.FONT_BOLD).grid(
            row=len(rep.checks), column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.whisper.set(rep.recommended_whisper)
        self.ollama.set(rep.recommended_ollama)

    def _apply(self):
        self.on_apply(self.whisper.get(), self.ollama.get().strip())
        self.btn_apply.configure(text="Saved ✓")

    def _mic(self):
        self.btn_mic.state(["disabled"])
        self.mic_status.configure(text="Recording - speak now for 3 seconds...")

        def work():
            c = self.syscheck.mic_test(self.settings["microphone"])
            self.win.after(0, done, c)

        def done(c):
            self.btn_mic.state(["!disabled"])
            self.mic_status.configure(text=f"{c.status}: {c.detail}")
            if self.report:
                self.report.checks.append(c)
                self.syscheck.save_report(self.report)

        threading.Thread(target=work, daemon=True).start()

    def _open_report(self):
        from ..paths import REPORT_FILE
        if REPORT_FILE.exists():
            os.startfile(REPORT_FILE)
