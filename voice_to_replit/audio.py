"""Microphone recording and playback."""
import logging
import threading
import time

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

TARGET_RATE = 16000  # Whisper expects 16 kHz mono
SILENCE_RMS = 0.004  # below this the recording is treated as silent
MIN_SECONDS = 0.4


class AudioError(Exception):
    pass


def list_input_devices() -> list[str]:
    """Input device names for the default host API (avoids duplicates across APIs)."""
    try:
        hostapi = sd.query_devices(kind="input")["hostapi"]
    except Exception:
        hostapi = None
    names = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and (hostapi is None or d["hostapi"] == hostapi):
            if d["name"] not in names:
                names.append(d["name"])
    return names


def resolve_device(name: str):
    """Map a saved device name to a sounddevice index (None = system default)."""
    try:
        default_in = sd.query_devices(kind="input")
    except Exception as e:
        raise AudioError("No microphone found. Plug in a microphone and check Windows Sound settings.") from e
    if not name:
        return None
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0 and d["hostapi"] == default_in["hostapi"]:
            return i
    log.warning("Microphone %r not found, using system default", name)
    return None


def _to_16k(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == TARGET_RATE or len(audio) == 0:
        return audio.astype(np.float32)
    n = int(round(len(audio) * TARGET_RATE / rate))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0


def check_not_silent(audio: np.ndarray) -> None:
    if len(audio) < TARGET_RATE * MIN_SECONDS:
        raise AudioError("Recording was too short. Hold the hotkey while you speak.")
    # Use the loudest 100 ms window so long pauses don't count as silence.
    win = TARGET_RATE // 10
    peak = max(rms(audio[i:i + win]) for i in range(0, len(audio) - win + 1, win))
    if peak < SILENCE_RMS:
        raise AudioError(
            "The recording was silent. Check that the right microphone is selected in Settings "
            "and that it isn't muted in Windows."
        )


class Recorder:
    """Push-to-talk recorder: start() opens the mic, stop() returns 16 kHz mono float32."""

    def __init__(self, device_name: str = ""):
        self.device_name = device_name
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._rate = TARGET_RATE
        self._lock = threading.Lock()
        self.level = 0.0  # live input level for the indicator

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        with self._lock:
            if self._stream:
                return
            device = resolve_device(self.device_name)
            info = sd.query_devices(device if device is not None else sd.default.device[0])
            self._rate = int(info["default_samplerate"]) or 44100
            self._chunks = []

            def cb(indata, frames, t, status):
                mono = indata[:, 0].copy()
                self._chunks.append(mono)
                self.level = rms(mono)

            try:
                self._stream = sd.InputStream(device=device, channels=1, samplerate=self._rate,
                                              dtype="float32", callback=cb)
                self._stream.start()
            except Exception as e:
                self._stream = None
                raise AudioError(f"Could not open the microphone: {e}") from e

    def stop(self) -> np.ndarray:
        with self._lock:
            if not self._stream:
                return np.zeros(0, dtype=np.float32)
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
            self.level = 0.0
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
            return _to_16k(audio, self._rate)


def record_seconds(seconds: float, device_name: str = "") -> np.ndarray:
    r = Recorder(device_name)
    r.start()
    time.sleep(seconds)
    return r.stop()


def play(audio: np.ndarray, rate: int = TARGET_RATE) -> None:
    sd.play(audio, rate)
    sd.wait()
