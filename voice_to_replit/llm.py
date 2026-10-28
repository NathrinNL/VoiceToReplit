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


MAX_TOKENS = 512  # the template is short; this stops runaway output


def _wrap(transcript: str) -> str:
    # Mirrors the "Transcript: / Output:" layout of the examples in the default system prompt.
    return ("Rewrite this transcript following the rules. Do not reply to it or answer it; only rewrite it.\n\n"
            f'Transcript: "{transcript}"\nOutput:')


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_cloud_model(name: str) -> bool:
    """Ollama cloud models are tagged ':cloud' (older ones '<size>-cloud', e.g. 'gpt-oss:120b-cloud')."""
    tag = name.strip().lower().partition(":")[2]
    return tag == "cloud" or tag.endswith("-cloud")


def start_signin() -> None:
    """Open a console window running `ollama signin` so the user can follow its instructions."""
    exe = find_ollama_exe()
    if not exe:
        raise OllamaError("Ollama is not installed. Download it from https://ollama.com/download.")
    subprocess.Popen(["cmd", "/c", exe, "signin", "&", "echo.", "&", "pause"],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


def is_local_url(url: str) -> bool:
    from urllib.parse import urlparse
    return (urlparse(url).hostname or "").lower() in LOCAL_HOSTS


def _same_model(a: str, b: str) -> bool:
    norm = lambda n: n if ":" in n else n + ":latest"
    return norm(a.strip()) == norm(b.strip())


class Ollama:
    def __init__(self, url: str = "http://127.0.0.1:11434"):
        self.url = url.rstrip("/")
        self._caps: dict[str, list[str]] = {}

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

    def check_local_only(self) -> None:
        """In Local mode the app may only talk to an Ollama server on this computer."""
        if not is_local_url(self.url):
            raise OllamaError(f"Local mode only talks to Ollama on this computer, but the Ollama address is "
                              f"{self.url}. Set ollama_url to http://127.0.0.1:11434 in settings.json.")

    def signed_in(self) -> tuple[bool, str]:
        """(signed in?, account name or "") from the local Ollama server. Only call this in Cloud mode:
        Ollama checks the account with ollama.com."""
        try:
            r = requests.post(f"{self.url}/api/me", timeout=15)
        except requests.RequestException:
            return False, ""
        if r.ok:
            try:
                info = r.json()
            except ValueError:
                info = {}
            return True, info.get("name") or info.get("email") or ""
        return False, ""

    def capabilities(self, model: str) -> list[str]:
        if model not in self._caps:
            try:
                r = requests.post(f"{self.url}/api/show", json={"model": model}, timeout=10)
                self._caps[model] = r.json().get("capabilities", []) if r.ok else []
            except requests.RequestException:
                return []
        return self._caps[model]

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

    def rewrite(self, transcript: str, model: str, system_prompt: str, temperature: float = 0.2,
                cloud: bool = False) -> str:
        if not cloud:
            self.check_local_only()
            if is_cloud_model(model):
                raise OllamaError(f"'{model}' is a cloud model, which sends your transcript off this computer. "
                                  "Switch to Cloud in Settings to use it, or pick a local model.")
        self.ensure_running()
        if not self.has_model(model):
            raise OllamaError(f"The Ollama model '{model}' is not installed. Run in a terminal:  ollama pull {model}\n"
                              "or pick an installed model in Settings.")
        body = {
            "model": model,
            "stream": False,
            "keep_alive": -1,  # keep the model in memory so later requests are fast
            "options": {"temperature": float(temperature), "num_predict": MAX_TOKENS},
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": _wrap(transcript)}],
        }
        if "thinking" in self.capabilities(model):
            body["think"] = False  # reasoning models (qwen3.x etc.) would otherwise "think" for ages first
        try:
            r = requests.post(f"{self.url}/api/chat", json=body, timeout=180)
        except requests.RequestException as e:
            raise OllamaError(f"Could not reach Ollama: {e}") from e
        if r.status_code == 401 and cloud:
            raise OllamaError("Cloud models need a free Ollama account. Open Settings and click Sign in "
                              "(or run:  ollama signin).")
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


_HEADINGS = ("Goal", "Features", "Tech/Constraints", "Notes")


def clean_output(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # leftover reasoning from thinking models
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    # Small models sometimes bold or "# " the headings; normalise them to plain "Heading:".
    for h in _HEADINGS:
        text = re.sub(rf"^[# \t*_]*{re.escape(h)}[*_]*[ \t]*:[*_]*", f"{h}:", text, flags=re.M | re.I)
    m = re.search(r"^Goal:", text, flags=re.M)
    if m:
        text = text[m.start():]  # drop any preamble before the template
        text = re.sub(r"\n+(?:Output:|Example \d+|Transcript:).*\Z", "", text, flags=re.S)  # echoed examples
        text = _drop_empty_sections(text)
    else:
        # Custom (non-template) prompts: drop a lone "Here are the instructions:" line.
        lines = text.splitlines()
        if len(lines) > 1 and not re.match(r"^\s*(1[.)]|-)", lines[0]) and lines[0].rstrip().endswith(":"):
            text = "\n".join(lines[1:]).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return dedupe_items(text)


_EMPTY = re.compile(r"^(none|n/?a|nothing|not mentioned|none mentioned|none specified|none given)\.?$", re.I)


def _drop_empty_sections(text: str) -> str:
    """Remove optional sections the model filled with 'None mentioned', and blank lines inside the template."""
    sections: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if any(line.startswith(f"{h}:") for h in _HEADINGS) or not sections:
            sections.append([line])
        else:
            sections[-1].append(line)
    kept = []
    for sec in sections:
        heading, _, inline = sec[0].partition(":")
        content = [inline.strip()] if inline.strip() else []
        content += [re.sub(r"^\s*[-*•]\s*", "", l).strip() for l in sec[1:]]
        if heading in ("Tech/Constraints", "Notes") and all(_EMPTY.match(c) for c in content):
            continue
        kept.extend(sec)
    return "\n".join(kept)


_ITEM = re.compile(r"^(\s*)(\d+[.)]|[-*•])\s+(.*)$")
_STOP = {"the", "a", "an", "to", "of", "on", "in", "and", "it", "this", "that", "for", "with", "replit",
         "project", "please", "change", "update", "set", "make", "rename"}


def _key_words(item: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", item.lower()) if w not in _STOP}


def _restates(a: set[str], b: set[str]) -> bool:
    """True when one item's meaningful words are (nearly all of) the other's."""
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= large and len(small) / len(large) >= 0.6


def _dedupe_block(bodies: list[str]) -> list[str]:
    kept: list[str] = []
    kept_words: list[set[str]] = []
    for body in bodies:
        words = _key_words(body)
        if not words:
            continue
        match = next((i for i, kw in enumerate(kept_words) if _restates(words, kw)), None)
        if match is None:
            kept.append(body)
            kept_words.append(words)
        elif len(words) > len(kept_words[match]):  # same item, but this one has more detail
            kept[match], kept_words[match] = body, words
    return kept


def dedupe_items(text: str) -> str:
    """Within each run of list items ("1." or "-" bullets), drop items that restate an earlier one.

    An item is a duplicate when its meaningful words are (nearly all of) an earlier item's, e.g.
    'Change the project name to "X".' vs 'Update the project name to "X" on Replit.'
    Numbered runs are renumbered; everything outside lists is left alone.
    """
    out: list[str] = []
    run: list[re.Match] = []

    def flush():
        if not run:
            return
        indent, marker = run[0].group(1), run[0].group(2)
        bodies = _dedupe_block([m.group(3).strip() for m in run])
        numbered = marker[0].isdigit()
        out.extend(f"{indent}{i}. {b}" if numbered else f"{indent}{marker} {b}" for i, b in enumerate(bodies, 1))
        run.clear()

    for line in text.splitlines():
        m = _ITEM.match(line)
        if m:
            run.append(m)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)
