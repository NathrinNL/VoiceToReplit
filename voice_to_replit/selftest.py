"""--selftest: exercise each stage on its own and report which one fails."""
import logging
import os
import tempfile
import threading
import time
import traceback
import wave

import numpy as np

from . import audio, sender, winutil
from .llm import Ollama
from .settings import Settings
from .stt import Transcriber

log = logging.getLogger(__name__)

SAMPLE_SPEECH = "Make the login button blue and move it to the top right corner of the page."
SAMPLE_TRANSCRIPT = ("um so like I want the uh the login button to be, to be blue, and uh move it to the "
                     "top right, yeah top right corner, and also change the header text to say Welcome Back")

STAGES = ["mic", "whisper", "ollama", "rewrite", "window", "paste"]


class StageWarning(Exception):
    pass


def _synth_speech() -> np.ndarray:
    """Use Windows' built-in text-to-speech to make a known test clip (works offline)."""
    import win32com.client
    path = os.path.join(tempfile.gettempdir(), "vtr_selftest.wav")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
    fmt.Type = 18  # SAFT16kHz16BitMono
    stream.Format = fmt
    stream.Open(path, 3)
    voice = win32com.client.Dispatch("SAPI.SpVoice")
    voice.AudioOutputStream = stream
    voice.Speak(SAMPLE_SPEECH)
    stream.Close()
    with wave.open(path, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        rate = w.getframerate()
    os.remove(path)
    return audio._to_16k(data, rate)


class SelfTest:
    def __init__(self, settings: Settings, live_mic: bool):
        self.s = settings
        self.live_mic = live_mic
        self.transcriber = Transcriber()
        self.ollama = Ollama(settings["ollama_url"])

    def stage_mic(self):
        names = audio.list_input_devices()
        if not names:
            raise audio.AudioError("No microphone found.")
        mic = self.s["microphone"] or "system default"
        if self.live_mic:
            print("    >>> Speak now for 3 seconds...", flush=True)
            clip = audio.record_seconds(3, self.s["microphone"])
            audio.check_not_silent(clip)
            return f"{mic}: recorded 3 s, level {audio.rms(clip):.4f}"
        clip = audio.record_seconds(1, self.s["microphone"])
        return f"{mic}: opened OK, {len(clip) / 16000:.1f}s captured (use --mic to test with your voice)"

    def stage_whisper(self):
        t0 = time.time()
        self.transcriber.load(self.s["whisper_model"], self.s["whisper_device"])
        load = time.time() - t0
        clip = _synth_speech()
        t0 = time.time()
        text = self.transcriber.transcribe(clip, self.s["whisper_model"], self.s["whisper_device"])
        missing = [w for w in ("login", "button", "blue") if w not in text.lower()]
        if missing:
            raise RuntimeError(f"Transcript {text!r} is missing {missing}")
        return (f"{self.s['whisper_model']} on {self.transcriber.device}, load {load:.1f}s, "
                f"transcribe {time.time() - t0:.2f}s: {text!r}")

    def stage_ollama(self):
        self.ollama.ensure_running()
        if not self.ollama.has_model(self.s["ollama_model"]):
            raise RuntimeError(f"Model '{self.s['ollama_model']}' missing. Run: ollama pull {self.s['ollama_model']}")
        return f"running, model '{self.s['ollama_model']}' available"

    def stage_rewrite(self):
        t0 = time.time()
        out = self.ollama.rewrite(SAMPLE_TRANSCRIPT, self.s["ollama_model"], self.s["system_prompt"])
        low = out.lower()
        problems = []
        if not out.lstrip().startswith("1"):
            problems.append("not a numbered list")
        for w in ("login", "blue", "top right", "welcome back"):
            if w not in low:
                problems.append(f"dropped '{w}'")
        for filler in (" um ", " uh "):
            if filler in f" {low} ":
                problems.append(f"kept filler '{filler.strip()}'")
        detail = f"{time.time() - t0:.1f}s\n" + "\n".join("        " + l for l in out.splitlines())
        if problems:
            raise StageWarning(", ".join(problems) + "; " + detail)
        return detail

    def stage_window(self):
        wins = winutil.find_replit_windows()
        if not wins:
            raise StageWarning("No Replit window open (open your Replit project in a browser to test this)")
        lines = [w.label() for w in wins]
        calib = self.s["chat_position"]
        if calib:
            try:
                sender.check_calibration(wins[0], calib)
                lines.append("calibration matches the current window")
            except sender.NeedsCalibration as e:
                lines.append(f"calibration: {e}")
        else:
            lines.append("not calibrated yet")
        return "; ".join(lines)

    def stage_paste(self):
        """Run the real send() path against a throwaway window instead of Replit."""
        import tkinter as tk
        original = winutil.save_clipboard()
        try:
            winutil.set_clipboard_text("VTR-ORIGINAL-CLIPBOARD")
            root = tk.Tk()
            root.title("Voice to Replit self-test (paste target)")
            root.geometry("520x220+200+200")
            root.attributes("-topmost", True)
            txt = tk.Text(root)
            txt.pack(fill="both", expand=True)
            root.update()
            hwnd = winutil.user32.GetParent(root.winfo_id())
            l, t, r, b = winutil.window_rect(hwnd)
            target = winutil.WindowInfo(hwnd, root.title(), "python.exe")
            calib = sender.calibration_for(target, (l + r) // 2, (t + b) // 2)
            payload = "1. Self-test paste line one.\n2. Line two."
            err = []
            th = threading.Thread(target=lambda: _catch(err, sender.send, payload, target, calib, False))
            th.start()
            while th.is_alive():
                root.update()
                time.sleep(0.02)
            for _ in range(20):
                root.update()
                time.sleep(0.02)
            got = txt.get("1.0", "end").strip()
            root.destroy()
            if err:
                raise err[0]
            if got != payload:
                raise RuntimeError(f"Pasted text mismatch: {got!r}")
            if winutil.get_clipboard_text() != "VTR-ORIGINAL-CLIPBOARD":
                raise RuntimeError("Clipboard was not restored")
            return "focus, click, Ctrl+V paste and clipboard restore all OK"
        finally:
            winutil.restore_clipboard(original)

    def run(self, only: list[str] | None = None) -> int:
        stages = only or STAGES
        print(f"\nVoice to Replit self-test  (Whisper={self.s['whisper_model']}, Ollama={self.s['ollama_model']})\n")
        failed = []
        for name in stages:
            t0 = time.time()
            try:
                detail = getattr(self, f"stage_{name}")()
                status = "PASS"
            except StageWarning as e:
                status, detail = "WARN", str(e)
            except Exception as e:
                status, detail = "FAIL", f"{type(e).__name__}: {e}"
                log.error("selftest %s failed\n%s", name, traceback.format_exc())
                failed.append(name)
            print(f"  [{status}] {name:<8} ({time.time() - t0:.1f}s) {detail}", flush=True)
        print()
        if failed:
            print(f"FAILED at: {', '.join(failed)}  (details in the log file)")
            return 1
        print("All stages passed.")
        return 0


def _catch(err, fn, *args):
    try:
        fn(*args)
    except Exception as e:
        err.append(e)
