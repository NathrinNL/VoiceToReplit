"""Compare rewrite quality of Ollama models on messy voice transcripts.

Usage (Ollama must be running and the models pulled):
    .venv\\Scripts\\python.exe tools\\eval_rewrite.py llama3.2 qwen3.5:4b
    .venv\\Scripts\\python.exe tools\\eval_rewrite.py llama3.2 qwen3.5:4b --runs 3 --markdown report.md

Uses the system prompt and temperature from your settings. Each output is checked for: following the
Goal/Features template, keeping the required details, dropping filler words, and not inventing things.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from voice_to_replit.llm import Ollama, is_cloud_model  # noqa: E402
from voice_to_replit.settings import Settings  # noqa: E402

CASES = [
    {
        "name": "Self-corrections and sizes",
        "transcript": "um okay so on the home page the, the big title, make it, like, red, no actually dark green, "
                      "and uh make it a bit bigger, maybe 48 pixels, and move the sign up button so it's like "
                      "under the title instead of on the right",
        "required": ["dark green", "48", "sign up", "(under|below) the title"],
        "forbidden": ["red", "um", "uh"],
    },
    {
        "name": "Feature with tech constraints",
        "transcript": "so I want to add, um, a dark mode, you know, a toggle in the top right corner, and it should "
                      "remember what you picked, like save it in local storage I think, and uh don't use any new "
                      "libraries, just plain CSS, and oh also the footer text should say Made with love in Amsterdam",
        "required": ["dark mode", "top right", "local storage", "made with love in amsterdam",
                     r"tech/constraints:(.|\n)*plain css", r"tech/constraints:(.|\n)*librar"],
        "forbidden": ["um", "you know", "tailwind", "react", "none mentioned"],
    },
    {
        "name": "Vague request with false starts",
        "transcript": "hey so the uh, the map thing, the map page, it's kind of slow when you, when you zoom in, can "
                      "you make it faster, and maybe add like a search bar, a search bar where you type a city and "
                      "it jumps there, and um I'm not sure about the colours, maybe change them, whatever looks better",
        "required": ["map", "zoom", "search", "city", r"notes:(.|\n)*colou?r"],
        "forbidden": ["uh", "um", "the map thing", "none mentioned"],
    },
]


def check(case, out):
    low = out.lower()
    problems = []
    if not out.startswith("Goal:") or "Features:" not in out:
        problems.append("template not followed")
    # "required" entries are regexes; "forbidden" entries are whole words/phrases.
    problems += [f"missing '{r}'" for r in case["required"] if not re.search(r, low)]
    problems += [f"contains '{f}'" for f in case["forbidden"] if re.search(rf"\b{re.escape(f)}\b", low)]
    goal = next((l for l in out.splitlines() if l.startswith("Goal:")), "")
    if goal.count(". ") > 1:
        problems.append("goal is more than one sentence")
    return problems


def vram_split(url, model):
    try:
        for m in requests.get(f"{url}/api/ps", timeout=5).json().get("models", []):
            if m["name"].startswith(model.split(":")[0]) and (":" not in model or m["name"] == model):
                total, vram = m.get("size", 0), m.get("size_vram", 0)
                return f"{total / 1e9:.1f} GB, {100 * vram / total:.0f}% on GPU" if total else "?"
    except Exception:
        pass
    return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--markdown", help="write a side-by-side report to this file")
    ap.add_argument("--json", help="write raw results to this file")
    args = ap.parse_args()
    s = Settings.load()
    models = args.models or [s.active_model]
    o = Ollama(s["ollama_url"])
    o.ensure_running()
    results = {}
    for model in models:
        cloud = is_cloud_model(model)  # passing a :cloud model name is an explicit opt-in to cloud
        o.rewrite("warm up", model, s["system_prompt"], s["temperature"], cloud)
        res = {"cases": [], "passed": 0, "total": 0, "seconds": 0.0}
        print(f"\n===== {model} =====")
        for case in CASES:
            outs = []
            for _ in range(args.runs):
                t0 = time.time()
                out = o.rewrite(case["transcript"], model, s["system_prompt"], s["temperature"], cloud)
                dt = time.time() - t0
                problems = check(case, out)
                outs.append({"output": out, "problems": problems, "seconds": round(dt, 2)})
                res["passed"] += not problems
                res["total"] += 1
                res["seconds"] += dt
                print(f"[{'OK ' if not problems else 'BAD'}] {case['name']} ({dt:.1f}s) {problems or ''}")
            res["cases"].append(outs)
        res["memory"] = vram_split(o.url, model)
        res["avg_seconds"] = round(res["seconds"] / res["total"], 2)
        print(f"{model}: {res['passed']}/{res['total']} passed, avg {res['avg_seconds']}s, {res['memory']}")
        if not cloud:
            o.unload(model)  # free VRAM for the next model
        results[model] = res
    if args.json:
        Path(args.json).write_text(json.dumps({"cases": CASES, "results": results}, indent=2), encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown(models, results), encoding="utf-8")
    if not s.cloud:
        o.warm_up(s["ollama_model"])  # leave the app's model loaded


def markdown(models, results):
    lines = ["# Rewrite comparison", "",
             "| Model | Passed | Avg time | Memory |", "|---|---|---|---|"]
    for m in models:
        r = results[m]
        lines.append(f"| {m} | {r['passed']}/{r['total']} | {r['avg_seconds']}s | {r['memory']} |")
    for i, case in enumerate(CASES):
        lines += ["", f"## {i + 1}. {case['name']}", "", "**Before (transcript):**", "", f"> {case['transcript']}", ""]
        for m in models:
            first = results[m]["cases"][i][0]
            verdict = "✅" if not first["problems"] else "⚠️ " + "; ".join(first["problems"])
            lines += [f"**After - {m}** ({first['seconds']}s) {verdict}", "", "```", first["output"], "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
