"""Settings window."""
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .. import audio, autostart, hotkey
from ..llm import OllamaError, is_cloud_model, is_local_url, start_signin
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
        theme.center(win, 780, 880)
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

        # Rewriting model: Local / Cloud toggle, then the models installed in Ollama (queried at runtime)
        self.ollama = ollama
        self.installed: list[str] | None = None  # every model Ollama lists; None = not loaded yet / offline
        self.mode = tk.StringVar(value=settings["llm_mode"])
        self.choice = {"local": settings["ollama_model"], "cloud": settings["ollama_cloud_model"]}
        self.signed_in: bool | None = None  # None = unknown / not checked (never checked in Local mode)
        self._signin_job = 0
        i = row("Rewriting runs")
        mf = ttk.Frame(body)
        mf.grid(row=i, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(mf, text="Local (on this computer)", value="local", variable=self.mode,
                        command=self._mode_changed).pack(side="left")
        ttk.Radiobutton(mf, text="Cloud (Ollama cloud models)", value="cloud", variable=self.mode,
                        command=self._mode_changed).pack(side="left", padx=(16, 0))

        self.ollama_model = tk.StringVar(value=self.choice[self.mode.get()])
        i = row("Ollama model")
        self.ollama_box = ttk.Combobox(body, textvariable=self.ollama_model, values=[])
        self.ollama_box.grid(row=i, column=1, sticky="ew")
        ttk.Button(body, text="Refresh", command=self._refresh_models).grid(row=i, column=2, padx=(8, 0))
        self.model_status = tk.Label(body, text="Checking installed models...", bg=theme.BG, fg=theme.MUTED,
                                     font=theme.FONT, anchor="w", justify="left", wraplength=560)
        self.model_status.grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        self.ollama_model.trace_add("write", lambda *_: self._show_model_status())

        # Cloud-only: privacy warning and Ollama sign-in
        self.cloud_warning = tk.Label(
            body, bg=theme.BG, fg=theme.WARN, font=theme.FONT_BOLD, anchor="w", justify="left", wraplength=560,
            text="⚠ Cloud models send your transcripts to external servers, may require an Ollama account "
                 "sign-in, and may be subject to usage limits or costs. Your data leaves this computer.")
        self.cloud_warning.grid(row=r, column=1, columnspan=2, sticky="w", pady=(4, 0))
        self._cloud_rows = [self.cloud_warning]
        r += 1
        self.signin_frame = ttk.Frame(body)
        self.signin_frame.grid(row=r, column=1, columnspan=2, sticky="w", pady=(4, 0))
        self._cloud_rows.append(self.signin_frame)
        r += 1
        self.signin_label = tk.Label(self.signin_frame, text="", bg=theme.BG, fg=theme.MUTED, font=theme.FONT,
                                     anchor="w", justify="left", wraplength=440)
        self.signin_label.pack(side="left")
        self.signin_btn = ttk.Button(self.signin_frame, text="Sign in", command=self._sign_in)

        # Temperature
        self.temperature = tk.DoubleVar(value=settings["temperature"])
        i = row("Temperature")
        tf = ttk.Frame(body)
        tf.grid(row=i, column=1, columnspan=2, sticky="w")
        ttk.Spinbox(tf, textvariable=self.temperature, from_=0.0, to=1.0, increment=0.05, width=6,
                    format="%.2f").pack(side="left")
        ttk.Label(tf, text="0 = most literal (recommended 0.2), higher = more varied wording",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0))
        self._apply_mode()
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

    # ---------------------------------------------------------------- Local / Cloud
    @property
    def cloud(self) -> bool:
        return self.mode.get() == "cloud"

    def _run_async(self, work, done):
        """Run work() on a thread and done(result) on the Tk thread, without touching Tk from the thread."""
        box = {}
        threading.Thread(target=lambda: box.setdefault("r", work()), daemon=True).start()

        def poll():
            if not self.win.winfo_exists():
                return
            if "r" in box:
                done(box["r"])
            else:
                self.win.after(100, poll)
        self.win.after(100, poll)

    def _mode_changed(self):
        other = "local" if self.cloud else "cloud"
        self.choice[other] = self.ollama_model.get().strip()  # remember the pick for the mode we left
        self._apply_mode()
        self.ollama_model.set(self.choice[self.mode.get()])

    def _apply_mode(self):
        for w in self._cloud_rows:
            if self.cloud:
                w.grid()
            else:
                w.grid_remove()
        self._fill_dropdown()
        if self.cloud:
            self._check_signin()

    def _fill_dropdown(self):
        names = [n for n in (self.installed or []) if is_cloud_model(n) == self.cloud]
        self.ollama_box.configure(values=sorted(names))
        self._show_model_status()

    def _refresh_models(self):
        if not self.cloud and not is_local_url(self.ollama.url):
            # Local mode never talks to anything but Ollama on this computer.
            self.installed = None
            self.model_status.configure(text=f"Local mode only talks to Ollama on this computer, but the Ollama "
                                             f"address is {self.ollama.url}.", fg=theme.FAIL)
            return
        self.model_status.configure(text="Checking installed models...", fg=theme.MUTED)

        def work():
            try:
                return [n.removesuffix(":latest") for n in self.ollama.models()]
            except Exception:
                return None

        def done(names):
            self.installed = names
            self._fill_dropdown()

        self._run_async(work, done)
        if self.cloud:
            self._check_signin()

    def _model_problem(self) -> str | None:
        """None if the chosen model can be used in the current mode, else a message saying how to fix it."""
        name = self.ollama_model.get().strip()
        if self.installed is None:
            return "Ollama isn't running, so installed models can't be listed. Start the Ollama app, then press Refresh."
        if self.cloud and not any(is_cloud_model(n) for n in self.installed) and not name:
            return ("No cloud models added yet. Add one in a terminal, e.g.:  ollama pull glm-5.3-flash:cloud   "
                    "then press Refresh.")
        if not name:
            return "Choose a model from the list."
        if not self.cloud and is_cloud_model(name):
            return f"'{name}' is a cloud model. Switch to Cloud to use it, or pick a local model."
        if self.cloud and not is_cloud_model(name):
            return f"'{name}' is a local model. Switch to Local to use it, or pick a :cloud model."
        if name.removesuffix(":latest") not in self.installed:
            return f"'{name}' isn't installed. Run in a terminal:  ollama pull {name}   then press Refresh."
        return None

    def _show_model_status(self):
        if self.installed is None and not self.cloud and not is_local_url(self.ollama.url):
            return  # keep the "local only" message
        problem = self._model_problem()
        if problem:
            self.model_status.configure(text=problem, fg=theme.WARN if self.installed is None else theme.FAIL)
        else:
            n = len(self.ollama_box.cget("values"))
            kind = "cloud" if self.cloud else "local"
            self.model_status.configure(text=f"✓ Installed  ({n} {kind} model{'s' if n != 1 else ''} available)",
                                        fg=theme.OK)

    def _check_signin(self):
        """Ask the local Ollama whether it's signed in to ollama.com. Cloud mode only."""
        if not self.cloud:
            return
        self._signin_job += 1
        job = self._signin_job
        self.signin_label.configure(text="Checking your Ollama sign-in...", fg=theme.MUTED)
        self.signin_btn.pack_forget()

        def done(result):
            if job != self._signin_job or not self.cloud:
                return
            ok, who = result
            self.signed_in = ok
            if ok:
                self.signin_label.configure(text=f"✓ Signed in to Ollama{' as ' + who if who else ''}.", fg=theme.OK)
                self.signin_btn.pack_forget()
            else:
                self.signin_label.configure(
                    text="Cloud models need a free Ollama account. You're not signed in.", fg=theme.WARN)
                self.signin_btn.pack(side="left", padx=(10, 0))

        self._run_async(self.ollama.signed_in, done)

    def _sign_in(self):
        try:
            start_signin()
        except OllamaError as e:
            messagebox.showerror("Sign in", str(e), parent=self.win)
            return
        self.signin_label.configure(text="Follow the steps in the 'ollama signin' window (it shows a link to open "
                                         "in your browser). Waiting for you to finish...", fg=theme.MUTED)
        self.signin_btn.pack_forget()
        self._wait_for_signin(deadline=time.time() + 300)

    def _wait_for_signin(self, deadline):
        def done(result):
            if not self.cloud or not self.win.winfo_exists():
                return
            if result[0]:
                self._check_signin()
            elif time.time() < deadline:
                self.win.after(3000, lambda: self._wait_for_signin(deadline))
            else:
                self._check_signin()
        self._run_async(self.ollama.signed_in, done)

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
        if self.cloud != is_cloud_model(model):
            messagebox.showerror("Ollama model", self._model_problem(), parent=self.win)
            return
        problem = self._model_problem()
        if problem and not messagebox.askyesno("Ollama model", f"{problem}\n\nSave anyway?", parent=self.win):
            return
        if self.cloud and self.signed_in is False and not messagebox.askyesno(
                "Ollama sign-in", "You're not signed in to Ollama, so cloud models won't work yet.\n\nSave anyway?",
                parent=self.win):
            return
        self.choice[self.mode.get()] = model
        try:
            temperature = round(min(1.0, max(0.0, float(self.temperature.get()))), 2)
        except (tk.TclError, ValueError):
            messagebox.showerror("Temperature", "Temperature must be a number from 0 to 1.", parent=self.win)
            return
        s = self.s
        s["hotkey"] = hk
        s["whisper_model"] = self.whisper.get()
        s["whisper_device"] = self.device.get()
        s["llm_mode"] = self.mode.get()
        s["ollama_model"] = self.choice["local"]
        s["ollama_cloud_model"] = self.choice["cloud"]
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
