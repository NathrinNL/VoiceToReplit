"""Prompt rewriting via a local Ollama server."""
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class OllamaError(Exception):
    pass


def find_ollama_exe() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
              Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Ollama" / "ollama.exe"):
        if p.exists():
            return str(p)
    return None


# Worked examples sent before the real transcript. Small models follow examples far
# better than rules alone - especially "one request = one item".
FEW_SHOT = [
    ("um so can you uh change the name of this project from, uh, Purple Fancy Tiger to, to Recipe Box on Replit",
     '1. Change the project name to "Recipe Box".'),
    ("the submit button, can you change it from blue to, um, purple",
     "1. Change the submit button colour from blue to purple."),
    ("okay so the login button, make it like red, no wait, green, and uh move it to the top right, "
     "and the header should say Welcome Back, yeah Welcome Back",
     '1. Make the login button green.\n2. Move the login button to the top right.\n'
     '3. Change the header text to "Welcome Back".'),
    ("I want a footer, um, at the bottom of every page with the text 2025 Acme, and make that text "
     "small, like 12 pixels, and gray",
     '1. Add a footer at the bottom of every page with the text "2025 Acme".\n'
     "2. Make the footer text 12px and gray."),
]


def _wrap(transcript: str) -> str:
    return ("Rewrite this spoken transcript following the rules. Do not reply to it or answer it; "
            f'only rewrite it.\n\nTranscript:\n"""\n{transcript}\n"""')


def _same_model(a: str, b: str) -> bool:
    norm = lambda n: n if ":" in n else n + ":latest"
    return norm(a.strip()) == norm(b.strip())


class Ollama:
    def __init__(self, url: str = "http://127.0.0.1:11434"):
        self.url = url.rstrip("/")

    def is_running(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/version", timeout=2).ok
        except requests.RequestException:
            return False

    def ensure_running(self, wait: float = 25.0) -> None:
        """Start `ollama serve` in the background if Ollama is installed but not running."""
        if self.is_running():
            return
        exe = find_ollama_exe()
        if not exe:
            raise OllamaError("Ollama is not installed. Download it from https://ollama.com/download and run install.bat again.")
        log.info("Starting Ollama in the background: %s serve", exe)
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        deadline = time.time() + wait
        while time.time() < deadline:
            if self.is_running():
                return
            time.sleep(0.5)
        raise OllamaError("Ollama is installed but did not start. Open the Ollama app from the Start menu and try again.")

    def models(self) -> list[str]:
        r = requests.get(f"{self.url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def has_model(self, name: str) -> bool:
        return any(_same_model(m, name) for m in self.models())

    def pull(self, name: str, progress=None) -> None:
        """Download a model. progress(status: str, fraction: float | None) is called as it goes."""
        with requests.post(f"{self.url}/api/pull", json={"model": name, "stream": True}, stream=True, timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if "error" in msg:
                    raise OllamaError(f"Could not download model '{name}': {msg['error']}")
                if progress:
                    total, done = msg.get("total"), msg.get("completed")
                    progress(msg.get("status", ""), (done / total) if total and done else None)

    def rewrite(self, transcript: str, model: str, system_prompt: str) -> str:
        self.ensure_running()
        if not self.has_model(model):
            raise OllamaError(f"The Ollama model '{model}' is not downloaded. Run:  ollama pull {model}")
        body = {
            "model": model,
            "stream": False,
            "keep_alive": -1,  # keep the model in memory so later requests are fast
            "options": {"temperature": 0.1},
            "messages": [{"role": "system", "content": system_prompt}],
        }
        for said, rewritten in FEW_SHOT:
            body["messages"] += [{"role": "user", "content": _wrap(said)},
                                 {"role": "assistant", "content": rewritten}]
        body["messages"].append({"role": "user", "content": _wrap(transcript)})
        try:
            r = requests.post(f"{self.url}/api/chat", json=body, timeout=180)
        except requests.RequestException as e:
            raise OllamaError(f"Could not reach Ollama: {e}") from e
        if not r.ok:
            raise OllamaError(f"Ollama returned an error: {r.text[:300]}")
        return clean_output(r.json()["message"]["content"])

    def warm_up(self, model: str) -> None:
        requests.post(f"{self.url}/api/generate", json={"model": model, "keep_alive": -1}, timeout=120)

    def unload(self, model: str) -> None:
        try:
            requests.post(f"{self.url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=5)
        except requests.RequestException:
            pass


def clean_output(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    # Drop a leading preamble line like "Here are the instructions:" if the list follows.
    lines = text.splitlines()
    if len(lines) > 1 and not re.match(r"^\s*1[.)]", lines[0]) and lines[0].rstrip().endswith(":"):
        text = "\n".join(lines[1:]).strip()
    return dedupe_items(text)


_ITEM = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_STOP = {"the", "a", "an", "to", "of", "on", "in", "and", "it", "this", "that", "for", "with", "replit",
         "project", "please", "change", "update", "set", "make", "rename"}


def _key_words(item: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", item.lower()) if w not in _STOP}


def _restates(a: set[str], b: set[str]) -> bool:
    """True when one item's meaningful words are (nearly all of) the other's."""
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= large and len(small) / len(large) >= 0.6


def dedupe_items(text: str) -> str:
    """Drop numbered items that restate an earlier item, then renumber.

    An item is a duplicate when its meaningful words are a subset of an earlier item's
    (or vice versa), e.g. 'Change the project name to "X".' vs 'Update the project name to "X" on Replit.'
    """
    lines = text.splitlines()
    items = [_ITEM.match(l) for l in lines]
    if not all(items) or len(items) < 2:
        return text
    kept: list[str] = []
    kept_words: list[set[str]] = []
    for m in items:
        body = m.group(1).strip()
        words = _key_words(body)
        if not words:
            continue
        match = next((i for i, kw in enumerate(kept_words) if _restates(words, kw)), None)
        if match is None:
            kept.append(body)
            kept_words.append(words)
        elif len(words) > len(kept_words[match]):  # same action, but this one has more detail
            kept[match], kept_words[match] = body, words
    return "\n".join(f"{i}. {b}" for i, b in enumerate(kept, 1))
