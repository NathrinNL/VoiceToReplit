"""Review window: nothing is sent to Replit until the user clicks Send."""
import tkinter as tk
from tkinter import ttk

from . import theme


class ReviewWindow:
    def __init__(self, root, transcript: str, prompt: str, *, on_send, on_rerecord, on_regenerate, on_cancel,
                 record=None):
        self.on_send, self.on_rerecord, self.on_regenerate, self.on_cancel = on_send, on_rerecord, on_regenerate, on_cancel
        self.transcript = transcript
        self.record = record  # training.Record for this session, or None
        self.last_prompt = prompt
        w = self.win = tk.Toplevel(root)
        w.title("Voice to Replit - Review prompt")
        w.configure(bg=theme.BG)
        w.minsize(520, 380)
        theme.center(w, 720, 560)
        theme.dark_titlebar(w)
        w.protocol("WM_DELETE_WINDOW", self.cancel)

        body = ttk.Frame(w, padding=16)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Review your prompt before sending", style="Title.TLabel").pack(anchor="w")

        # Collapsible raw transcript
        self._show_raw = tk.BooleanVar(value=False)
        self.raw_toggle = ttk.Button(body, text="▸ Raw transcript", command=self._toggle_raw)
        self.raw_toggle.pack(anchor="w", pady=(10, 4))
        self.raw = theme.text_widget(body, height=5, readonly=True)
        theme.set_text(self.raw, transcript or "(no transcript)")

        self.prompt_label = ttk.Label(body, text="Prompt for the Replit Agent (editable)", style="Bold.TLabel")
        self.prompt_label.pack(anchor="w", pady=(8, 4))
        self.text = theme.text_widget(body, height=12)
        self.text.pack(fill="both", expand=True)
        theme.set_text(self.text, prompt)

        self.status = ttk.Label(body, text="Ctrl+Enter = Send   ·   Esc = Cancel", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(8, 0))

        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=(12, 0))
        self.btn_send = ttk.Button(bar, text="Send to Replit", style="Accent.TButton", command=self.send)
        self.btn_send.pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.cancel).pack(side="right", padx=(0, 8))
        self.btn_regen = ttk.Button(bar, text="Regenerate", command=self.regenerate)
        self.btn_regen.pack(side="left")
        ttk.Button(bar, text="Re-record", command=self.rerecord).pack(side="left", padx=(8, 0))
        if not transcript:
            self.btn_regen.state(["disabled"])

        w.bind("<Control-Return>", lambda e: (self.send(), "break")[1])
        w.bind("<Escape>", lambda e: self.cancel())
        self.text.focus_set()
        self.text.mark_set("insert", "end")

    def _toggle_raw(self):
        if self._show_raw.get():
            self.raw.pack_forget()
            self.raw_toggle.configure(text="▸ Raw transcript")
        else:
            self.raw.pack(fill="x", after=self.raw_toggle)
            self.raw_toggle.configure(text="▾ Raw transcript")
        self._show_raw.set(not self._show_raw.get())

    def get_prompt(self) -> str:
        return self.text.get("1.0", "end").strip()

    def set_prompt(self, prompt: str):
        theme.set_text(self.text, prompt)

    def set_busy(self, busy: bool, message: str = ""):
        for b in (self.btn_send, self.btn_regen):
            b.state(["disabled"] if busy else ["!disabled"])
        if not self.transcript:
            self.btn_regen.state(["disabled"])
        self.status.configure(text=message or "Ctrl+Enter = Send   ·   Esc = Cancel")

    def set_error(self, message: str):
        self.set_busy(False)
        self.status.configure(text=message, foreground=theme.FAIL)

    def send(self):
        prompt = self.get_prompt()
        if not prompt:
            self.set_error("The prompt is empty.")
            return
        if "disabled" in self.btn_send.state():
            return
        self.on_send(self, prompt)

    def regenerate(self):
        self.set_busy(True, "Rewriting...")
        self.on_regenerate(self)

    def rerecord(self):
        self.close()
        self.on_rerecord()

    def cancel(self):
        self.close()
        self.on_cancel()

    def close(self):
        try:
            if self.alive:
                self.last_prompt = self.get_prompt()  # keep the final text for the training log
            self.win.destroy()
        except tk.TclError:
            pass

    @property
    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False
