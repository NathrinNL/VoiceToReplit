"""Settings window."""
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .. import audio, autostart, hotkey
from ..paths import TRAINING_DIR
from ..settings import DEFAULT_SYSTEM_PROMPT
from ..stt import WHISPER_SIZES
from . import dialogs, theme


class SettingsWindow:
    def __init__(self, root, settings, *, on_saved, on_recalibrate, suspend_hotkey, ollama):
        self.root, self.s, self.on_saved, self.suspend_hotkey = root, settings, on_saved, suspend_hotkey
        win = self.win = tk.Toplevel(root)
        win.title("Voice to Replit - Settings")
        win.configure(bg=theme.BG)
        theme.center(win, 720, 720)
        theme.dark_titlebar(win)
        win.bind("<Escape>", lambda e: win.destroy())

        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Settings", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        r = 1

        def row(label):
            nonlocal r
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="nw", pady=6, padx=(0, 12))
            r += 1
            return r - 1

        # Hotkey
        self.hotkey = tk.StringVar(value=settings["hotkey"])
        i = row("Push-to-talk hotkey")
        ttk.Entry(body, textvariable=self.hotkey).grid(row=i, column=1, sticky="ew")
        ttk.Button(body, text="Change...", command=self._capture).grid(row=i, column=2, padx=(8, 0))

        # Whisper
        self.whisper = tk.StringVar(value=settings["whisper_model"])
        i = row("Whisper model")
        ttk.Combobox(body, textvariable=self.whisper, values=WHISPER_SIZES, state="readonly").grid(
            row=i, column=1, sticky="ew")
        self.device = tk.StringVar(value=settings["whisper_device"])
        ttk.Combobox(body, textvariable=self.device, values=["auto", "cuda", "cpu"], state="readonly",
                     width=7).grid(row=i, column=2, padx=(8, 0))

        # Ollama
        self.ollama_model = tk.StringVar(value=settings["ollama_model"])
        i = row("Ollama model")
        self.ollama_box = ttk.Combobox(body, textvariable=self.ollama_model,
                                       values=["llama3.2", "qwen2.5:3b", "qwen2.5:7b"])
        self.ollama_box.grid(row=i, column=1, sticky="ew")
        threading.Thread(target=self._load_models, args=(ollama,), daemon=True).start()

        # Microphone
        self.mic = tk.StringVar(value=settings["microphone"] or "System default")
        i = row("Microphone")
        try:
            mics = ["System default"] + audio.list_input_devices()
        except Exception:
            mics = ["System default"]
        ttk.Combobox(body, textvariable=self.mic, values=mics, state="readonly").grid(
            row=i, column=1, columnspan=2, sticky="ew")

        # Toggles
        self.auto_enter = tk.BooleanVar(value=settings["auto_enter"])
        self.autostart = tk.BooleanVar(value=autostart.is_enabled())
        self.training_log = tk.BooleanVar(value=settings["training_log"])
        i = row("Options")
        opts = ttk.Frame(body)
        opts.grid(row=i, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(opts, text="Press Enter after pasting", variable=self.auto_enter).pack(anchor="w")
        ttk.Checkbutton(opts, text="Start with Windows", variable=self.autostart).pack(anchor="w", pady=(4, 0))
        tl = ttk.Frame(opts)
        tl.pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(tl, text="Save training log (transcripts, rewrites, confirmed prompts)",
                        variable=self.training_log).pack(side="left")
        ttk.Button(tl, text="Open folder", command=self._open_training).pack(side="left", padx=(8, 0))

        # Chat box position
        i = row("Chat box position")
        cp = settings["chat_position"]
        pos = (f"x={cp['x']}, y={cp['y']} in a {cp['window_rect'][2] - cp['window_rect'][0]}x"
               f"{cp['window_rect'][3] - cp['window_rect'][1]} window") if cp else "Not calibrated"
        ttk.Label(body, text=pos, style="Muted.TLabel").grid(row=i, column=1, sticky="w")
        ttk.Button(body, text="Recalibrate", command=lambda: (win.destroy(), on_recalibrate())).grid(
            row=i, column=2, padx=(8, 0))

        # System prompt
        i = row("Rewriting prompt")
        body.rowconfigure(i, weight=1)
        self.prompt = theme.text_widget(body, height=10, mono=True)
        self.prompt.grid(row=i, column=1, columnspan=2, sticky="nsew")
        theme.set_text(self.prompt, settings["system_prompt"])
        ttk.Button(body, text="Reset prompt to default",
                   command=lambda: theme.set_text(self.prompt, DEFAULT_SYSTEM_PROMPT)).grid(
            row=r, column=1, sticky="w", pady=(6, 0))
        r += 1

        bar = ttk.Frame(body)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(bar, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="right", padx=8)

    def _load_models(self, ollama):
        try:
            names = ollama.models()
        except Exception:
            return
        merged = list(dict.fromkeys(n.removesuffix(":latest") for n in names))
        merged += [m for m in ("llama3.2", "qwen2.5:3b", "qwen2.5:7b") if m not in merged]
        self.win.after(0, lambda: self.ollama_box.configure(values=merged))

    def _open_training(self):
        TRAINING_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(TRAINING_DIR)

    def _capture(self):
        self.suspend_hotkey(True)
        try:
            hk = dialogs.capture_hotkey(self.win)
        finally:
            self.suspend_hotkey(False)
        if hk:
            self.hotkey.set(hk)

    def _save(self):
        hk = self.hotkey.get().strip()
        try:
            hotkey.parse(hk)
        except hotkey.HotkeyError as e:
            messagebox.showerror("Invalid hotkey", str(e), parent=self.win)
            return
        if hk != self.s["hotkey"]:
            conflict = hotkey.check_conflict(hk)
            if conflict and not messagebox.askyesno(
                    "Hotkey conflict", f"{conflict}\n\nUse it anyway? (Choose No to pick another.)", parent=self.win):
                return
        model = self.ollama_model.get().strip()
        if not model:
            messagebox.showerror("Ollama model", "Enter an Ollama model name.", parent=self.win)
            return
        s = self.s
        s["hotkey"] = hk
        s["whisper_model"] = self.whisper.get()
        s["whisper_device"] = self.device.get()
        s["ollama_model"] = model
        s["microphone"] = "" if self.mic.get() == "System default" else self.mic.get()
        s["auto_enter"] = self.auto_enter.get()
        s["system_prompt"] = self.prompt.get("1.0", "end").strip() or DEFAULT_SYSTEM_PROMPT
        s["start_with_windows"] = self.autostart.get()
        s["training_log"] = self.training_log.get()
        try:
            autostart.set_enabled(s["start_with_windows"])
        except OSError as e:
            messagebox.showwarning("Start with Windows", f"Could not update startup entry: {e}", parent=self.win)
        s.save()
        self.win.destroy()
        self.on_saved()
