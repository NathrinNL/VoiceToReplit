"""History of the last 50 sent prompts."""
import json
import logging
from datetime import datetime

from .paths import HISTORY_FILE, ensure_dirs

log = logging.getLogger(__name__)
MAX_ITEMS = 50


def load() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        log.exception("history.json unreadable")
        return []


def add(prompt: str, transcript: str = "") -> None:
    ensure_dirs()
    items = load()
    items.insert(0, {"timestamp": datetime.now().isoformat(timespec="seconds"),
                     "prompt": prompt, "transcript": transcript})
    HISTORY_FILE.write_text(json.dumps(items[:MAX_ITEMS], indent=2), encoding="utf-8")
