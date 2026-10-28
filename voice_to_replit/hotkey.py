"""Global push-to-talk hotkey using pynput (no admin rights needed)."""
import ctypes
import logging

from pynput import keyboard

log = logging.getLogger(__name__)

_MOD_ALIASES = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "shift_l": "shift", "shift_r": "shift", "shift": "shift", "cmd_l": "cmd", "cmd_r": "cmd",
}
_MOD_FLAGS = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "cmd": 0x8}

# Shortcuts Windows or common apps already use.
KNOWN_CONFLICTS = {
    frozenset({"ctrl", "alt", "delete"}): "Windows security screen",
    frozenset({"cmd", "space"}): "Windows input language switch",
    frozenset({"alt", "space"}): "Window system menu / PowerToys Run",
    frozenset({"ctrl", "space"}): "Code completion in many editors",
    frozenset({"alt", "tab"}): "Windows app switcher",
    frozenset({"ctrl", "shift", "esc"}): "Task Manager",
}


class HotkeyError(Exception):
    pass


def _vk_for_char(ch: str) -> int:
    fn = ctypes.windll.user32.VkKeyScanW
    fn.argtypes, fn.restype = [ctypes.c_wchar], ctypes.c_short
    res = fn(ch)
    if res == -1:
        raise HotkeyError(f"Unknown key: {ch!r}")
    return res & 0xFF


def parse(hotkey: str) -> frozenset:
    """'<ctrl>+<alt>+<space>' -> frozenset({'ctrl', 'alt', 'space'})."""
    ids = set()
    for part in hotkey.lower().split("+"):
        part = part.strip()
        if not part:
            raise HotkeyError(f"Invalid hotkey: {hotkey!r}")
        if part.startswith("<") and part.endswith(">"):
            name = part[1:-1]
            if name not in _MOD_FLAGS and not hasattr(keyboard.Key, name):
                raise HotkeyError(f"Unknown key: {part}")
            ids.add(_MOD_ALIASES.get(name, name))
        elif len(part) == 1:
            ids.add(f"vk{_vk_for_char(part)}")
        else:
            raise HotkeyError(f"Unknown key: {part} (use e.g. <f9> or a single character)")
    if len(ids) < 2 and not any(i.startswith("f") and i[1:].isdigit() for i in ids):
        raise HotkeyError("Use at least one modifier (Ctrl/Alt/Shift/Win) or a function key.")
    return frozenset(ids)


def key_id(key) -> str:
    if isinstance(key, keyboard.Key):
        return _MOD_ALIASES.get(key.name, key.name)
    if getattr(key, "vk", None) is not None:
        return f"vk{key.vk}"
    if getattr(key, "char", None):
        return f"vk{_vk_for_char(key.char)}"
    return str(key)


def _vk_for_id(i: str) -> int | None:
    if i.startswith("vk"):
        return int(i[2:])
    k = getattr(keyboard.Key, i, None)
    return k.value.vk if k is not None else None


def check_conflict(hotkey: str) -> str | None:
    """Return a description of a conflict, or None if the hotkey looks free."""
    ids = parse(hotkey)
    if ids in KNOWN_CONFLICTS:
        return f"{pretty(hotkey)} is already used by: {KNOWN_CONFLICTS[ids]}"
    mods = sum(_MOD_FLAGS[i] for i in ids if i in _MOD_FLAGS)
    keys = [i for i in ids if i not in _MOD_FLAGS]
    if len(keys) != 1:
        return None
    vk = _vk_for_id(keys[0])
    if vk is None:
        return None
    # If another app registered this combo, RegisterHotKey fails.
    user32 = ctypes.windll.user32
    test_id = 0xBEEF
    if not user32.RegisterHotKey(None, test_id, mods | 0x4000, vk):  # MOD_NOREPEAT
        return f"{pretty(hotkey)} is already registered by another application."
    user32.UnregisterHotKey(None, test_id)
    return None


def pretty(hotkey: str) -> str:
    return " + ".join(p.strip("<>").capitalize() for p in hotkey.split("+"))


class PushToTalk:
    """Calls on_press() when the full combo goes down and on_release() when any part comes up."""

    def __init__(self, hotkey: str, on_press, on_release):
        self.combo = parse(hotkey)
        self.on_press, self.on_release = on_press, on_release
        self._down: set[str] = set()
        self._active = False
        self._listener = None

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _press(self, key):
        try:
            self._down.add(key_id(key))
            if not self._active and self.combo <= self._down:
                self._active = True
                self.on_press()
        except Exception:
            log.exception("hotkey press handler")

    def _release(self, key):
        try:
            kid = key_id(key)
            self._down.discard(kid)
            if self._active and kid in self.combo:
                self._active = False
                self.on_release()
        except Exception:
            log.exception("hotkey release handler")
