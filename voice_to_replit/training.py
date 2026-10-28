"""Training log: each voice session's transcript, model rewrites and the prompt the user confirmed.

Text only - no audio is kept. Layout in %APPDATA%\\VoiceToReplit\\training\\:
    log.jsonl              one JSON object per session (see README for the fields)
    prompts\\<hash>.txt     each distinct rewriting system prompt, referenced by system_prompt_id
"""
import hashlib
import json
import logging
import threading
from datetime import datetime

from . import __version__
from .paths import TRAINING_DIR

log = logging.getLogger(__name__)
LOG_FILE = TRAINING_DIR / "log.jsonl"
_lock = threading.Lock()

# Outcomes
SENT = "sent"                  # pasted into Replit
COPIED = "copied"              # no Replit window; left on the clipboard
CANCELLED = "cancelled"        # Cancel / Esc / window closed
RERECORDED = "rerecorded"      # Re-record button
REPLACED = "replaced"          # user started a new recording while the review was open
APP_CLOSED = "app_closed"      # app quit with the review still open
ERROR = "error"                # transcription or rewriting failed


def _prompt_id(system_prompt: str) -> str:
    pid = hashlib.sha1(system_prompt.encode("utf-8")).hexdigest()[:10]
    path = TRAINING_DIR / "prompts" / f"{pid}.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(system_prompt, encoding="utf-8")
    return pid


class Record:
    def __init__(self, audio_seconds: float, settings):
        now = datetime.now()
        self.id = now.strftime("%Y%m%d-%H%M%S-%f")[:-3]
        self.timestamp = now.isoformat(timespec="seconds")
        self.audio_seconds = round(audio_seconds, 2)
        self.whisper_model = settings["whisper_model"]
        self.ollama_model = settings.active_model
        self.llm_mode = settings["llm_mode"]
        self.system_prompt = settings["system_prompt"]
        self.transcript = ""
        self.rewrites: list[str] = []
        self.done = False

    def add_rewrite(self, text: str) -> None:
        self.rewrites.append(text)

    def finish(self, outcome: str, final_prompt: str | None = None, target: str | None = None,
               error: str | None = None) -> None:
        """Append the session to log.jsonl once; later calls are ignored."""
        with _lock:
            if self.done:
                return
            self.done = True
            try:
                self._write(outcome, final_prompt, target, error)
            except Exception:
                log.exception("Could not write training record")

    def _write(self, outcome, final_prompt, target, error):
        TRAINING_DIR.mkdir(parents=True, exist_ok=True)
        model_prompt = self.rewrites[-1] if self.rewrites else None
        entry = {
            "id": self.id,
            "timestamp": self.timestamp,
            "outcome": outcome,
            "audio_seconds": self.audio_seconds,
            "whisper_model": self.whisper_model,
            "transcript": self.transcript,
            "ollama_model": self.ollama_model,
            "llm_mode": self.llm_mode,
            "system_prompt_id": _prompt_id(self.system_prompt),
            "rewrites": self.rewrites,
            "model_prompt": model_prompt,
            "final_prompt": final_prompt,
            "edited_by_user": bool(final_prompt is not None and model_prompt is not None
                                   and final_prompt.strip() != model_prompt.strip()),
            "target_window": target,
            "error": error,
            "app_version": __version__,
        }
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log.info("Training record %s saved (%s)", self.id, outcome)
