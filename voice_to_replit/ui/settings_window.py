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
        theme.center(win, 760, 800)
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

        # Ollama: lists the models actually installed (queried from Ollama at runtime)
        self.ollama = ollama
        self.installed: list[str] | None = None  # None = not loaded yet / Ollama offline
        self.ollama_model = tk.StringVar(value=settings["ollama_model"])
        i = row("Ollama model")
        self.ollama_box = ttk.Combobox(body, textvariable=self.ollama_model, values=[])
        self.ollama_box.grid(row=i, column=1, sticky="ew")
        ttk.Button(body, text="Refresh", command=self._refresh_models).grid(row=i, column=2, padx=(8, 0))
        self.model_status = tk.Label(body, text="Checking installed models...", bg=theme.BG, fg=theme.MUTED,
                                     font=theme.FONT, anchor="w", justify="left")
        self.model_status.grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        self.ollama_model.trace_add("write", lambda *_: self._show_model_status())

        # Temperature
        self.temperature = tk.DoubleVar(value=settings["temperature"])
        i = row("Temperature")
        tf = ttk.Frame(body)
        tf.grid(row=i, column=1, columnspan=2, sticky="w")
        ttk.Spinbox(tf, textvariable=self.temperature, from_=0.0, to=1.0, increment=0.05, width=6,
                    format="%.2f").pack(side="left")
        ttk.Label(tf, text="0 = most literal (recommended 0.2), higher = more varied wording",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self._refresh_models()

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

    def _refresh_models(self):
        self.model_status.configure(text="Checking installed models...", fg=theme.MUTED)
        result = {}

        def work():  # network call off the UI thread; never touches Tk
            try:
                result["names"] = [n.removesuffix(":latest") for n in self.ollama.models()]
            except Exception:
                result["names"] = None

        def poll():
            if not self.win.winfo_exists():
                return
            if "names" not in result:
                self.win.after(100, poll)
                return
            self.installed = result["names"]
            self.ollama_box.configure(values=sorted(self.installed) if self.installed else [])
            self._show_model_status()

        threading.Thread(target=work, daemon=True).start()
        self.win.after(100, poll)

    def _model_problem(self) -> str | None:
        """None if the chosen model is installed, else a message saying how to fix it."""
        name = self.ollama_model.get().strip()
        if self.installed is None:
            return "Ollama isn't running, so installed models can't be listed. Start the Ollama app, then press Refresh."
        if not name:
            return "Choose a model from the list."
        if name.removesuffix(":latest") not in self.installed:
            return f"'{name}' isn't installed. Run in a terminal:  ollama pull {name}   then press Refresh."
        return None

    def _show_model_status(self):
        problem = self._model_problem()
        if problem:
            self.model_status.configure(text=problem, fg=theme.WARN if self.installed is None else theme.FAIL)
        else:
            n = len(self.installed)
            self.model_status.configure(text=f"✓ Installed  ({n} model{'s' if n != 1 else ''} available locally)",
                                        fg=theme.OK)

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
            messagebox.showerror("Ollama model", "Choose an Ollama model.", parent=self.win)
            return
        problem = self._model_problem()
        if problem and not messagebox.askyesno("Ollama model", f"{problem}\n\nSave anyway?", parent=self.win):
            return
        try:
            temperature = round(min(1.0, max(0.0, float(self.temperature.get()))), 2)
        except (tk.TclError, ValueError):
            messagebox.showerror("Temperature", "Temperature must be a number from 0 to 1.", parent=self.win)
            return
        s = self.s
        s["hotkey"] = hk
        s["whisper_model"] = self.whisper.get()
        s["whisper_device"] = self.device.get()
        s["ollama_model"] = model
        s["temperature"] = temperature
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
