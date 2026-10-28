"""Local speech-to-text with faster-whisper. The model stays loaded after first use."""
import logging
import threading

import numpy as np

from .gpu import cuda_available, register_cuda_dlls
from .paths import MODELS_DIR

log = logging.getLogger(__name__)

WHISPER_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]


class TranscriptionError(Exception):
    pass


class Transcriber:
    def __init__(self):
        self._model = None
        self._key = None
        self._lock = threading.Lock()
        self.device = None

    def is_downloaded(self, size: str) -> bool:
        try:
            from faster_whisper.utils import download_model
            download_model(size, local_files_only=True, cache_dir=str(MODELS_DIR))
            return True
        except Exception:
            return False

    def download(self, size: str) -> str:
        """Download the model (prints tqdm progress to the console)."""
        from faster_whisper.utils import download_model
        return download_model(size, cache_dir=str(MODELS_DIR))

    def load(self, size: str, device: str = "auto"):
        with self._lock:
            key = (size, device)
            if self._model is not None and self._key == key:
                return self._model
            register_cuda_dlls()
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model
            try:
                # Use the local copy without touching the network (works offline).
                path = download_model(size, local_files_only=True, cache_dir=str(MODELS_DIR))
            except Exception:
                log.info("Downloading Whisper model %s ...", size)
                path = self.download(size)
            attempts = []
            if device in ("auto", "cuda") and cuda_available():
                attempts.append(("cuda", "int8_float16"))
            if device in ("auto", "cpu") or not attempts:
                attempts.append(("cpu", "int8"))
            last = None
            for dev, ctype in attempts:
                try:
                    model = WhisperModel(path, device=dev, compute_type=ctype)
                    # A tiny warm-up catches missing CUDA/cuDNN DLLs now rather than mid-request.
                    list(model.transcribe(np.zeros(16000, dtype=np.float32), language="en")[0])
                    self._model, self._key, self.device = model, key, dev
                    log.info("Whisper %s loaded on %s (%s)", size, dev, ctype)
                    return model
                except Exception as e:
                    last = e
                    log.warning("Whisper failed on %s: %s", dev, e)
            raise TranscriptionError(f"Could not load Whisper model '{size}': {last}")

    def transcribe(self, audio: np.ndarray, size: str, device: str = "auto") -> str:
        model = self.load(size, device)
        with self._lock:
            segments, _ = model.transcribe(
                audio, language="en", beam_size=5, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 700},
            )
            text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            raise TranscriptionError("No speech was recognised in the recording. Try speaking closer to the mic.")
        return text
