"""Filesystem locations and logging setup."""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from . import APP_ID


def _env_dir(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or (Path.home() / fallback))


# Settings, history and logs live in %APPDATA%\VoiceToReplit (roaming).
DATA_DIR = _env_dir("APPDATA", "AppData/Roaming") / APP_ID
# Large model files live in %LOCALAPPDATA% so they don't roam with the profile.
MODELS_DIR = _env_dir("LOCALAPPDATA", "AppData/Local") / APP_ID / "models"

SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE = DATA_DIR / "history.json"
LOG_FILE = DATA_DIR / "voice_to_replit.log"
REPORT_FILE = DATA_DIR / "system_check_report.txt"
TRAINING_DIR = DATA_DIR / "training"

FROZEN = getattr(sys, "frozen", False)
# Folder containing the app (repo root, or the folder holding the .exe).
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent.parent


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(console: bool = False) -> None:
    ensure_dirs()
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console and sys.stderr:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
