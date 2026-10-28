"""Create the desktop shortcut (python -m voice_to_replit.shortcut)."""
import os

import win32com.client
from win32com.shell import shell, shellcon

from . import APP_NAME
from .paths import APP_DIR, FROZEN
from .ui.icon import save_ico


def create_desktop_shortcut() -> str:
    ico = APP_DIR / "icon.ico"
    save_ico(ico)
    desktop = shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0)  # follows OneDrive redirection
    path = os.path.join(desktop, f"{APP_NAME}.lnk")
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(path)
    if FROZEN:
        import sys
        sc.TargetPath = sys.executable
    else:
        sc.TargetPath = str(APP_DIR / ".venv" / "Scripts" / "pythonw.exe")
        sc.Arguments = f'"{APP_DIR / "VoiceToReplit.pyw"}"'
    sc.WorkingDirectory = str(APP_DIR)
    sc.IconLocation = str(ico)
    sc.Description = APP_NAME
    sc.Save()
    return path


if __name__ == "__main__":
    print(f"Desktop shortcut created: {create_desktop_shortcut()}")
