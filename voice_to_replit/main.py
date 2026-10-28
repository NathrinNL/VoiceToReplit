"""Entry point: python -m voice_to_replit [--selftest [--mic] [--stage NAME]] [--syscheck]"""
import argparse
import logging
import os
import sys

from . import APP_ID, APP_NAME
from .winutil import make_dpi_aware

log = logging.getLogger(__name__)
_mutex = None


def _single_instance() -> bool:
    global _mutex
    import win32api
    import win32event
    import winerror
    _mutex = win32event.CreateMutex(None, False, f"Local\\{APP_ID}_SingleInstance")
    return win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS


def main(argv=None) -> int:
    make_dpi_aware()  # must happen before any window is created
    ap = argparse.ArgumentParser(prog=APP_ID, description=APP_NAME)
    ap.add_argument("--selftest", action="store_true", help="test each stage and report which fails")
    ap.add_argument("--mic", action="store_true", help="with --selftest: record 3 s of your voice")
    ap.add_argument("--stage", action="append", help="with --selftest: run only this stage (repeatable)")
    ap.add_argument("--syscheck", action="store_true", help="run the system compatibility check")
    ap.add_argument("--download-models", action="store_true", help="download the configured models")
    args, rest = ap.parse_known_args(argv)

    from .paths import setup_logging
    setup_logging()
    for noisy in ("httpx", "httpx2", "huggingface_hub", "faster_whisper", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from .settings import Settings

    if args.syscheck:
        from . import syscheck
        return syscheck.main(rest)
    if args.download_models:
        from .setup_models import download_all
        return download_all(Settings.load())
    if args.selftest:
        from .selftest import STAGES, SelfTest
        bad = [s for s in (args.stage or []) if s not in STAGES]
        if bad:
            print(f"Unknown stage(s): {bad}. Choose from {STAGES}")
            return 2
        return SelfTest(Settings.load(), args.mic).run(args.stage)

    if not _single_instance():
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f"{APP_NAME} is already running - look for the microphone icon "
                                               "in the system tray.", APP_NAME, 0x40)
        return 0
    log.info("%s starting (pid %d)", APP_NAME, os.getpid())
    try:
        from .app import App
        App().run()
    except Exception:
        log.exception("Fatal error")
        import ctypes
        from .paths import LOG_FILE
        ctypes.windll.user32.MessageBoxW(None, f"{APP_NAME} crashed. Details are in:\n{LOG_FILE}", APP_NAME, 0x10)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
