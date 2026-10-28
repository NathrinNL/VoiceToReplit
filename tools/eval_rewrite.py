"""Measure rewrite quality of one or more Ollama models on realistic rambling transcripts.

Usage (Ollama must be running and the models pulled):
    .venv\\Scripts\\python.exe tools\\eval_rewrite.py llama3.2 qwen2.5:3b

A case passes when the output has between 1 and the expected number of items, keeps every
required detail, and contains none of the "invented" phrases.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_to_replit.llm import Ollama  # noqa: E402
from voice_to_replit.settings import Settings  # noqa: E402

RUNS = 3
CASES = [
    # (transcript, max items, required phrases)
    ("Change the name of the project from Purple Llama Garden to Weather map on Replit.", 1,
     ["weather map"]),
    ("I want you to change the name of this project to Weather map.", 1, ["weather map"]),
    ("um so like on the map page I want the uh the city buttons to be, to be bigger, like twice as big, "
     "and uh make them orange instead of gray, and also add a reset button, a reset button in the bottom left "
     "corner that says Reset View", 3, ["orange", "reset view", "bottom left"]),
    ("okay so the title Rainfall This Week, make it smaller, um, maybe 32 pixels, yeah 32 pixels", 1, ["32"]),
    ("can you add dark mode, uh, with a toggle in the top right, and the toggle should remember the setting, "
     "and, um, also fix the typo in the about page where it says Wether instead of Weather", 3,
     ["dark mode", "top right", "remember", "weather"]),
]
INVENTED = ["remove", "verify", "test", "make sure", "purple llama", 'on replit"']


def main(models):
    system_prompt = Settings.load()["system_prompt"]
    o = Ollama()
    o.ensure_running()
    for model in models:
        score, total = 0, 0.0
        print(f"\n===== {model} =====")
        o.rewrite("warm up", model, system_prompt)
        for transcript, max_items, required in CASES:
            for _ in range(RUNS):
                t0 = time.time()
                out = o.rewrite(transcript, model, system_prompt)
                total += time.time() - t0
                low = out.lower()
                items = [l for l in out.splitlines() if l.strip()]
                missing = [p for p in required if p not in low]
                invented = [p for p in INVENTED if p in low]
                ok = 1 <= len(items) <= max_items and not missing and not invented
                score += ok
                print(f"[{'OK ' if ok else 'BAD'}] items={len(items)}/{max_items} missing={missing} invented={invented}")
                if not ok:
                    print("      " + out.replace("\n", "\n      "))
        n = len(CASES) * RUNS
        print(f"{model}: {score}/{n} passed, avg {total / n:.2f}s per rewrite")


if __name__ == "__main__":
    main(sys.argv[1:] or [Settings.load()["ollama_model"]])
