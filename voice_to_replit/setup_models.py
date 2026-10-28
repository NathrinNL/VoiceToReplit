"""One-time model downloads with progress (used by install.bat)."""
import sys

from .llm import Ollama, OllamaError
from .stt import Transcriber


def download_all(settings) -> int:
    ok = True
    wm = settings["whisper_model"]
    t = Transcriber()
    if t.is_downloaded(wm):
        print(f"Whisper '{wm}' already downloaded.")
    else:
        print(f"Downloading Whisper '{wm}' (one time)...", flush=True)
        try:
            t.download(wm)
            print("  done.")
        except Exception as e:
            print(f"  FAILED: {e}")
            ok = False

    om = settings["ollama_model"]
    o = Ollama(settings["ollama_url"])
    try:
        o.ensure_running()
        if o.has_model(om):
            print(f"Ollama model '{om}' already downloaded.")
        else:
            print(f"Downloading Ollama model '{om}' (one time)...", flush=True)
            last = [""]

            def progress(status, frac):
                line = f"  {status:<30} {frac * 100:5.1f}%" if frac is not None else f"  {status}"
                if line != last[0]:
                    sys.stdout.write("\r" + line.ljust(60))
                    sys.stdout.flush()
                    last[0] = line
            o.pull(om, progress)
            print("\n  done.")
    except OllamaError as e:
        print(f"  FAILED: {e}")
        ok = False
    return 0 if ok else 1
