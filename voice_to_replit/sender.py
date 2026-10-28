"""Paste a confirmed prompt into the Replit Agent chat box."""
import logging
import time

from . import winutil

log = logging.getLogger(__name__)

RECT_TOLERANCE = 4  # pixels


class SendError(Exception):
    pass


class NeedsCalibration(SendError):
    pass


class WindowNotFound(SendError):
    pass


def calibration_for(window: winutil.WindowInfo, x: int, y: int) -> dict:
    return {"x": x, "y": y, "window_rect": winutil.window_rect(window.hwnd), "window_title": window.title}


def check_calibration(window: winutil.WindowInfo, calib: dict | None) -> None:
    if not calib:
        raise NeedsCalibration("The Replit chat box position hasn't been calibrated yet.")
    rect = winutil.window_rect(window.hwnd)
    saved = calib["window_rect"]
    if any(abs(a - b) > RECT_TOLERANCE for a, b in zip(rect, saved)):
        raise NeedsCalibration(
            "The Replit window has moved or been resized since calibration "
            f"(was {saved}, now {rect}). Please recalibrate so I don't click in the wrong place."
        )
    l, t, r, b = rect
    if not (l <= calib["x"] < r and t <= calib["y"] < b):
        raise NeedsCalibration("The saved chat box position is outside the Replit window. Please recalibrate.")


def send(text: str, window: winutil.WindowInfo, calib: dict | None, auto_enter: bool = True) -> None:
    """Copy, focus Replit, click the chat box, paste, optionally press Enter, restore clipboard.

    On failure the prompt is left on the clipboard so it isn't lost.
    """
    winutil.wait_modifiers_released()
    saved = winutil.save_clipboard()
    winutil.set_clipboard_text(text)
    if not winutil.force_foreground(window.hwnd):
        raise SendError("Couldn't bring the Replit window to the front. The prompt is on your clipboard - paste it with Ctrl+V.")
    try:
        check_calibration(window, calib)  # after restoring a minimised window, its rect is real
    except NeedsCalibration:
        raise
    winutil.click_at(calib["x"], calib["y"])
    time.sleep(0.25)
    winutil.paste()
    time.sleep(0.35)
    if auto_enter:
        winutil.press_enter()
        time.sleep(0.2)
    # Give the browser time to read the clipboard before we put the old contents back.
    time.sleep(0.5)
    try:
        winutil.restore_clipboard(saved)
    except Exception:
        log.exception("Could not restore clipboard")
    log.info("Sent %d chars to %s", len(text), window.label())
