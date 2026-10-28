"""User settings stored in %APPDATA%\\VoiceToReplit\\settings.json."""
import copy
import json
import logging

from .paths import SETTINGS_FILE, ensure_dirs

log = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You turn a rambling voice transcript into a clean prompt for the Replit Agent (an AI that builds and edits web apps).

Output EXACTLY this template and nothing else:

Goal: <one sentence: what the user wants>
Features:
- <one short line per concrete thing the user asked for>
Tech/Constraints:
- <technologies, libraries, limits or requirements the user mentioned>
Notes:
- <anything ambiguous or unclear in what the user said>

Rules:
- Never invent features, details or requirements the user did not say. No suggestions, no best practices.
- Keep every concrete detail: names, colours, positions, sizes, numbers, and exact text (in double quotes).
- Drop filler words (um, uh, like, you know, so, basically), repetitions and false starts. If the user corrects themselves ("red, no wait, green"), keep only the correction.
- "Change X from A to B" means change X to B; the old value is not a separate feature.
- Never list the same feature twice.
- Leave out Tech/Constraints if the user mentioned none. Leave out Notes if nothing is ambiguous.
- Output only the template: no preamble, no explanations, no markdown code fences, no bold.

Example 1
Transcript: "um so can you uh change the name of this project from, uh, Purple Fancy Tiger to, to Recipe Box"
Output:
Goal: Rename the project to "Recipe Box".
Features:
- Change the project name to "Recipe Box".

Example 2
Transcript: "okay so I want a, a contact page, um, with a form, name email and message, and it should email me the messages I guess, using like Flask, and the send button green, no wait, blue, and make it look nice"
Output:
Goal: Add a contact page with a form that emails submitted messages to the user.
Features:
- Add a contact page with a form with the fields name, email and message.
- Email each submitted message to the user.
- Make the send button blue.
Tech/Constraints:
- Use Flask.
Notes:
- The destination email address was not given.
- "Make it look nice" was not described further."""

# Earlier built-in prompts; a saved copy of one of these is upgraded to the current default.
OLD_SYSTEM_PROMPTS = [
    """You turn a user's spoken, rambling request into a clean prompt for the Replit Agent (an AI that builds and edits web apps).

Rules:
1. Write one numbered item (1., 2., 3., ...) per DIFFERENT action the speaker asked for. If they asked for one thing, output exactly one item.
2. Never repeat or rephrase the same action as a second item. Each item must ask for something the other items do not.
3. "Change X from A to B" is ONE action: write it as one item that changes X to B. The old value A is not a separate instruction.
4. Remove filler words ("um", "uh", "like", "you know", "so", "basically"), repetitions and false starts. If the speaker corrects themselves ("red, no wait, green"), keep only the correction.
5. Keep EVERY concrete detail the speaker mentions: element names, page names, colours, positions, sizes, numbers, exact text/labels, file names and technologies. Put exact text the user wants shown in double quotes.
6. Never invent features, details, steps or requirements the speaker did not say (no "remove", "test", "verify", "make sure" unless they said it). No suggestions or explanations.
7. Write short imperative sentences addressed to the Replit Agent (e.g. "Change the header background to dark blue.").
8. Output ONLY the numbered list. No preamble, title, closing remarks or markdown code fences.""",
    """You turn a user's spoken, rambling request into a clean prompt for the Replit Agent (an AI that builds and edits web apps).

Rules:
1. Write one numbered item (1., 2., 3., ...) per DIFFERENT action the speaker asked for. If they asked for one thing, output exactly one item.
2. Never repeat or rephrase the same action as a second item. Each item must ask for something the other items do not.
3. Remove filler words ("um", "uh", "like", "you know", "so", "basically"), repetitions and false starts. If the speaker corrects themselves ("red, no wait, green"), keep only the correction.
4. Keep EVERY concrete detail the speaker mentions: element names, page names, colours, positions, sizes, numbers, exact text/labels, file names and technologies. Put exact text the user wants shown in double quotes.
5. Never invent features, details, steps or requirements the speaker did not say. No suggestions, explanations, testing steps or best practices.
6. Write short imperative sentences addressed to the Replit Agent (e.g. "Change the header background to dark blue.").
7. Output ONLY the numbered list. No preamble, title, closing remarks or markdown code fences.""",
    """You rewrite a user's spoken, rambling instructions into a clean prompt for the Replit Agent (an AI that builds and edits web apps).

Rules:
1. Rewrite the speech into clear, concise, numbered instructions (1., 2., 3., ...). One action per item.
2. Remove filler words ("um", "uh", "like", "you know", "so", "basically"), repetitions and false starts. If the speaker corrects themselves, keep only the corrected version.
3. Keep EVERY concrete detail the speaker mentions: element names, page names, colours, positions, sizes, numbers, exact text/labels, file names and technologies.
4. Never invent features, details, or requirements the speaker did not say. Do not add suggestions, explanations, or best practices.
5. Write in the imperative, addressed to the Replit Agent (e.g. "Change the header background to dark blue.").
6. Output ONLY the final numbered instructions. No preamble, no title, no closing remarks, no quotes, no markdown code fences.""",
]

DEFAULTS = {
    "hotkey": "<ctrl>+<shift>+x",
    "whisper_model": "small",
    "whisper_device": "auto",  # auto | cuda | cpu
    "llm_mode": "local",  # "local" = only local models via Ollama on localhost; "cloud" = Ollama :cloud models
    "ollama_model": "llama3.2",  # model used in Local mode
    "ollama_cloud_model": "",  # model used in Cloud mode
    "temperature": 0.2,  # rewriting creativity: 0 = most literal
    "ollama_url": "http://127.0.0.1:11434",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "microphone": "",  # empty = system default input device
    "auto_enter": True,
    "chat_position": None,  # {"x", "y", "window_rect": [l, t, r, b], "window_title"}
    "start_with_windows": False,
    "training_log": False,  # save transcripts, rewrites and confirmed prompts locally (opt-in)
}


class Settings:
    def __init__(self, data: dict | None = None):
        self.data = copy.deepcopy(DEFAULTS)
        if data:
            self.data.update({k: v for k, v in data.items() if k in DEFAULTS})
        if self.data["system_prompt"].strip() in (p.strip() for p in OLD_SYSTEM_PROMPTS):
            self.data["system_prompt"] = DEFAULT_SYSTEM_PROMPT

    @classmethod
    def load(cls) -> "Settings":
        ensure_dirs()
        if SETTINGS_FILE.exists():
            try:
                return cls(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
            except Exception:
                log.exception("settings.json is corrupt; using defaults (old file kept as .bak)")
                SETTINGS_FILE.replace(SETTINGS_FILE.with_suffix(".json.bak"))
        s = cls()
        s.save()
        return s

    def save(self) -> None:
        ensure_dirs()
        tmp = SETTINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_FILE)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def cloud(self) -> bool:
        return self.data["llm_mode"] == "cloud"

    @property
    def active_model(self) -> str:
        """The Ollama model to use for rewriting in the current Local/Cloud mode."""
        return self.data["ollama_cloud_model"] if self.cloud else self.data["ollama_model"]
