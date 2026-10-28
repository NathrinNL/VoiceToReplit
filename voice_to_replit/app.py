"""Tray application: push-to-talk -> Whisper -> Ollama -> review -> paste into Replit."""
import ctypes
import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import pystray
from pynput import keyboard

from . import APP_NAME, audio, hotkey, history, sender, training, winutil
from .llm import Ollama, OllamaError
from .settings import Settings
from .stt import Transcriber, TranscriptionError
from .ui import dialogs, icon, theme
from .ui.overlay import Overlay
from .ui.review import ReviewWindow
from .ui.settings_window import SettingsWindow

log = logging.getLogger(__name__)


class App:
    def __init__(self):
        self.settings = Settings.load()
        self.q: queue.Queue = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        theme.apply(self.root)
        self._icon_photo = None
        self._set_window_icon()
        self.overlay = Overlay(self.root)
        self.transcriber = Transcriber()
        self.ollama = Ollama(self.settings["ollama_url"])
        self.recorder = audio.Recorder(self.settings["microphone"])
        self.ptt = None
        self.hotkey_suspended = False
        self.busy = False
        self.review: ReviewWindow | None = None
        self.calibrating = None  # {"window", "listener", "after"} while calibrating
        self.tray = None
        self._status = "Starting..."

    # ------------------------------------------------------------ plumbing
    def post(self, fn, *args):
        """Run fn(*args) on the Tk thread (safe from any thread)."""
        self.q.put((fn, args))

    def _pump(self):
        try:
            while True:
                fn, args = self.q.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    log.exception("UI task failed")
        except queue.Empty:
            pass
        if self.recorder.recording:
            self.overlay.level(self.recorder.level)
        self.root.after(40, self._pump)

    def _set_window_icon(self):
        from PIL import ImageTk
        self._icon_photo = ImageTk.PhotoImage(icon.make("idle", 32))
        self.root.iconphoto(True, self._icon_photo)

    def notify(self, message: str, title: str = APP_NAME):
        log.info("notify: %s", message)
        try:
            if self.tray:
                self.tray.notify(message, title)
        except Exception:
            log.exception("notify failed")

    def error(self, message: str, title: str = APP_NAME):
        log.error(message)
        self.overlay.hide()
        self._dialog(messagebox.showerror, title, message)

    def _dialog(self, fn, title, message):
        holder = tk.Toplevel(self.root)
        holder.withdraw()
        holder.attributes("-topmost", True)
        try:
            return fn(title, message, parent=holder)
        finally:
            holder.destroy()

    def set_status(self, text: str, state: str = "idle"):
        self._status = text
        if self.tray:
            self.tray.icon = icon.make(state)
            self.tray.title = f"{APP_NAME} - {text}"
            self.tray.update_menu()

    # ------------------------------------------------------------ tray
    def _build_tray(self):
        def P(fn):
            def handler(icon_, item):
                log.info("Tray menu: %s", item.text)
                self.post(fn)
            return handler
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self._status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", P(self.open_settings), default=True),
            pystray.MenuItem("History", P(self.open_history)),
            pystray.MenuItem("Run System Check", P(self.open_syscheck)),
            pystray.MenuItem("Recalibrate", P(self.start_calibration)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", P(self.quit)),
        )
        self.tray = pystray.Icon("VoiceToReplit", icon.make("busy"), APP_NAME, menu)
        threading.Thread(target=self.tray.run, daemon=True, name="tray").start()

    # ------------------------------------------------------------ hotkey
    def _start_hotkey(self) -> bool:
        if self.ptt:
            self.ptt.stop()
            self.ptt = None
        hk = self.settings["hotkey"]
        try:
            conflict = hotkey.check_conflict(hk)
        except hotkey.HotkeyError as e:
            self.error(f"The hotkey '{hk}' is invalid: {e}\n\nPick another one in Settings.")
            self.open_settings()
            return False
        if conflict:
            if self._dialog(messagebox.askyesno, "Hotkey conflict",
                            f"{conflict}\n\nPick a different hotkey now? (No = keep using it)"):
                self.open_settings()
        self.ptt = hotkey.PushToTalk(hk, lambda: self.post(self.ptt_down), lambda: self.post(self.ptt_up))
        self.ptt.start()
        return True

    def suspend_hotkey(self, suspended: bool):
        self.hotkey_suspended = suspended

    # ------------------------------------------------------------ recording pipeline
    def ptt_down(self):
        log.info("Hotkey down (suspended=%s, calibrating=%s, busy=%s)",
                 self.hotkey_suspended, bool(self.calibrating), self.busy)
        if self.hotkey_suspended or self.calibrating:
            return
        if self.busy:
            self.overlay.show("Still processing the last recording...", "busy")
            return
        if self.review and self.review.alive:
            self.review.close()  # speaking again replaces the open review
            self._log_outcome(self.review, training.REPLACED)
            self.review = None
        try:
            self.recorder.device_name = self.settings["microphone"]
            self.recorder.start()
        except audio.AudioError as e:
            self.error(str(e))
            return
        self.overlay.show(f"Recording...  release {hotkey.pretty(self.settings['hotkey'])} to stop", "recording")
        self.set_status("Recording", "recording")

    def ptt_up(self):
        if not self.recorder.recording:
            return
        clip = self.recorder.stop()
        log.info("Hotkey up: recorded %.1fs, level %.4f", len(clip) / audio.TARGET_RATE, audio.rms(clip))
        self.busy = True
        self.overlay.show("Transcribing...", "busy")
        self.set_status("Processing", "busy")
        threading.Thread(target=self._process, args=(clip,), daemon=True).start()

    def _process(self, clip):
        s = self.settings
        record = None
        try:
            audio.check_not_silent(clip)
            if s["training_log"]:
                record = training.Record(len(clip) / audio.TARGET_RATE, s)
            if not self.transcriber.is_downloaded(s["whisper_model"]):
                self.post(self.overlay.show, f"Downloading Whisper '{s['whisper_model']}' (one time)...", "busy")
            transcript = self.transcriber.transcribe(clip, s["whisper_model"], s["whisper_device"])
            log.info("Transcript: %s", transcript)
            if record:
                record.transcript = transcript
            self.post(self.overlay.show, "Rewriting prompt...", "busy")
            prompt = self.ollama.rewrite(transcript, s["ollama_model"], s["system_prompt"])
            if record:
                record.add_rewrite(prompt)
            self.post(self._processed, transcript, prompt, None, record)
        except (audio.AudioError, TranscriptionError, OllamaError) as e:
            if record:
                record.finish(training.ERROR, error=str(e))
            self.post(self._processed, None, None, str(e), None)
        except Exception as e:
            log.exception("Processing failed")
            if record:
                record.finish(training.ERROR, error=str(e))
            self.post(self._processed, None, None, f"Something went wrong: {e}", None)

    def _processed(self, transcript, prompt, err, record):
        self.busy = False
        self.overlay.hide()
        self.set_status("Ready")
        if err:
            self.error(err)
            return
        self.open_review(transcript, prompt, record)

    # ------------------------------------------------------------ review
    def _log_outcome(self, rw: ReviewWindow | None, outcome: str, target: str | None = None):
        if rw and rw.record:
            rw.record.finish(outcome, final_prompt=rw.last_prompt, target=target)

    def open_review(self, transcript: str, prompt: str, record=None):
        if self.review and self.review.alive:
            self.review.close()
            self._log_outcome(self.review, training.REPLACED)
        log.info("Review window opened")
        self.review = ReviewWindow(self.root, transcript, prompt, on_send=self._send,
                                  on_rerecord=self._rerecord, on_regenerate=self._regenerate,
                                  on_cancel=self._review_cancelled, record=record)
        self.root.after(50, self._focus_review)

    def _focus_review(self):
        if self.review and self.review.alive:
            win = self.review.win
            win.update_idletasks()
            winutil.force_foreground(ctypes.windll.user32.GetParent(win.winfo_id()))
            win.focus_force()
            self.review.text.focus_set()

    def _review_cancelled(self):
        log.info("Review cancelled")
        self._log_outcome(self.review, training.CANCELLED)
        self.review = None

    def _rerecord(self):
        log.info("Re-record requested")
        self._log_outcome(self.review, training.RERECORDED)
        self.review = None
        self.overlay.show(f"Hold {hotkey.pretty(self.settings['hotkey'])} and speak again", "info")
        self.root.after(2500, self.overlay.hide)

    def _regenerate(self, rw: ReviewWindow):
        def work():
            try:
                p = self.ollama.rewrite(rw.transcript, self.settings["ollama_model"], self.settings["system_prompt"])
                if rw.record:
                    rw.record.add_rewrite(p)
                self.post(lambda: rw.alive and (rw.set_prompt(p), rw.set_busy(False)))
            except Exception as e:
                log.exception("Regenerate failed")
                self.post(lambda: rw.alive and rw.set_error(str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _pick_window(self):
        wins = winutil.find_replit_windows()
        if not wins:
            return None
        if len(wins) == 1:
            return wins[0]
        return dialogs.choose_window(self.root, wins)

    def _send(self, rw: ReviewWindow, prompt: str):
        log.info("Send clicked")
        window = self._pick_window()
        if window is None:
            winutil.set_clipboard_text(prompt)
            rw.close()
            self._log_outcome(rw, training.COPIED)
            self.review = None
            self.notify("No Replit window found. Your prompt is on the clipboard - paste it with Ctrl+V.")
            return
        rw.set_busy(True, "Sending to Replit...")
        rw.win.withdraw()
        calib = self.settings["chat_position"]

        def work():
            try:
                sender.send(prompt, window, calib, self.settings["auto_enter"])
                self.post(self._sent, rw, prompt, None, window.title)
            except sender.NeedsCalibration as e:
                self.post(self._sent, rw, prompt, e, None)
            except Exception as e:
                log.exception("Send failed")
                self.post(self._sent, rw, prompt, e, None)
        threading.Thread(target=work, daemon=True).start()

    def _sent(self, rw: ReviewWindow, prompt: str, err, target):
        if err is None:
            history.add(prompt, rw.transcript)
            rw.close()
            rw.last_prompt = prompt  # exactly what was pasted
            self._log_outcome(rw, training.SENT, target)
            self.review = None
            self.notify("Prompt sent to Replit.")
            return
        rw.win.deiconify()
        rw.set_busy(False)
        if isinstance(err, sender.NeedsCalibration):
            rw.set_error("Needs calibration - your prompt is on the clipboard.")
            if self._dialog(messagebox.askyesno, "Recalibrate", f"{err}\n\nRecalibrate now?"):
                self.start_calibration(after=lambda: rw.alive and (rw.win.deiconify(), rw.win.lift(),
                                                                  rw.status.configure(text="Calibrated - click Send again.")))
        else:
            rw.set_error(f"{err}  (The prompt is on your clipboard.)")
            self.notify(f"Could not send: {err}. The prompt is on your clipboard.")

    # ------------------------------------------------------------ calibration
    def start_calibration(self, after=None):
        if self.calibrating:
            return
        window = self._pick_window()
        if window is None:
            self.error("No Replit window is open.\n\nOpen your Replit project (with the Agent chat visible) "
                       "in Chrome, Edge, Firefox or the Replit app, then choose Recalibrate.")
            return
        log.info("Calibration started for %s", window.label())
        winutil.force_foreground(window.hwnd)

        def on_key(key):
            if key == keyboard.Key.f8:
                self.post(self._calib_capture)
            elif key == keyboard.Key.esc:
                self.post(self._calib_end, False)

        listener = keyboard.Listener(on_press=on_key)
        listener.daemon = True
        listener.start()
        self.calibrating = {"window": window, "listener": listener, "after": after}
        self.overlay.show("Hover over the Replit Agent chat box and press F8 to save (on laptops: Fn+F8)"
                          "  ·  Esc = cancel", "info")

    def _calib_capture(self):
        if not self.calibrating:
            return
        x, y = winutil.cursor_pos()
        root_hwnd = winutil.root_window_at(x, y)
        window = self.calibrating["window"]
        if root_hwnd != window.hwnd:
            match = [w for w in winutil.find_replit_windows() if w.hwnd == root_hwnd]
            if not match:
                log.info("F8 at (%d, %d) is over a non-Replit window, ignored", x, y)
                self.overlay.show("That's not the Replit window. Hover over the Agent chat box and press F8.", "recording")
                return
            window = match[0]
        self.settings["chat_position"] = sender.calibration_for(window, x, y)
        self.settings.save()
        log.info("Calibrated chat box at (%d, %d) in %s", x, y, window.label())
        self._calib_end(True)

    def _calib_end(self, saved: bool):
        c, self.calibrating = self.calibrating, None
        if not c:
            return
        c["listener"].stop()
        if not saved:
            log.info("Calibration cancelled")
        self.overlay.show("Chat box position saved ✓" if saved else "Calibration cancelled", "info")
        self.root.after(1500, self.overlay.hide)
        if saved and c["after"]:
            c["after"]()

    # ------------------------------------------------------------ windows
    def open_settings(self):
        SettingsWindow(self.root, self.settings, on_saved=self._settings_saved,
                       on_recalibrate=self.start_calibration, suspend_hotkey=self.suspend_hotkey,
                       ollama=self.ollama)

    def _settings_saved(self):
        self.ollama.url = self.settings["ollama_url"].rstrip("/")
        self._start_hotkey()
        self.notify(f"Settings saved. Hold {hotkey.pretty(self.settings['hotkey'])} to talk.")
        threading.Thread(target=self._preload, daemon=True).start()

    def open_history(self):
        dialogs.HistoryWindow(self.root, on_resend=lambda it: self.open_review(it.get("transcript", ""), it["prompt"]))

    def open_syscheck(self):
        def apply(whisper, model):
            self.settings["whisper_model"], self.settings["ollama_model"] = whisper, model
            self.settings.save()
            threading.Thread(target=self._preload, daemon=True).start()
        dialogs.SystemCheckWindow(self.root, self.settings, apply)

    # ------------------------------------------------------------ lifecycle
    def _preload(self):
        """Load Whisper and the Ollama model up front so the first request is fast."""
        s = self.settings
        self.post(self.set_status, "Loading models...", "busy")
        problems = []
        try:
            self.ollama.ensure_running()
            if not self.ollama.has_model(s["ollama_model"]):
                problems.append(f"Ollama model '{s['ollama_model']}' is missing. Run:  ollama pull {s['ollama_model']}")
            else:
                self.ollama.warm_up(s["ollama_model"])
        except Exception as e:
            problems.append(str(e))
        try:
            self.transcriber.load(s["whisper_model"], s["whisper_device"])
        except Exception as e:
            problems.append(str(e))
        if problems:
            self.post(self.set_status, "Problem - see notification", "recording")
            self.post(self.error, "\n\n".join(problems))
        else:
            dev = "GPU" if self.transcriber.device == "cuda" else "CPU"
            self.post(self.set_status, f"Ready ({dev}) - hold {hotkey.pretty(s['hotkey'])}")

    def quit(self):
        log.info("Quitting")
        if self.review and self.review.alive:
            self.review.close()
            self._log_outcome(self.review, training.APP_CLOSED)
        if self.ptt:
            self.ptt.stop()
        if self.recorder.recording:
            self.recorder.stop()
        threading.Thread(target=self.ollama.unload, args=(self.settings["ollama_model"],), daemon=True).start()
        if self.tray:
            self.tray.stop()
        self.root.after(300, self.root.destroy)

    def run(self):
        self._build_tray()
        threading.Thread(target=self._preload, daemon=True).start()
        self.root.after(40, self._pump)
        self.root.after(200, self._start_hotkey)  # may show a conflict dialog; runs inside the loop
        if not self.settings["chat_position"]:
            self.root.after(2500, lambda: self.notify(
                "Running in the tray. Open Replit, then choose Recalibrate from the tray menu to set the chat box position."))
        self.root.mainloop()
