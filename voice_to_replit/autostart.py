"""'Start with Windows' via the per-user Run registry key (no admin needed)."""
import sys
import winreg

from . import APP_ID
from .paths import APP_DIR, FROZEN

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if FROZEN:
        return f'"{sys.executable}"'
    pythonw = APP_DIR / ".venv" / "Scripts" / "pythonw.exe"
    return f'"{pythonw}" "{APP_DIR / "VoiceToReplit.pyw"}"'


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, APP_ID)
            except FileNotFoundError:
                pass


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_ID)
            return True
    except FileNotFoundError:
        return False
