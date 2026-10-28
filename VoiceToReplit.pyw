"""Windowless launcher (used by run.bat, the desktop shortcut and Start with Windows)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_to_replit.main import main  # noqa: E402

sys.exit(main())
