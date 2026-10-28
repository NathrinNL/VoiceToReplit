"""Fast unit tests - no microphone, GPU, Ollama or Replit needed.

Run:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import json
import tempfile
import unittest
from pathlib import Path

from voice_to_replit import hotkey, training
from voice_to_replit.llm import clean_output, dedupe_items
from voice_to_replit.settings import DEFAULT_SYSTEM_PROMPT, OLD_SYSTEM_PROMPTS, Settings


class DedupeTests(unittest.TestCase):
    def test_restated_item_removed(self):
        text = '1. Change the project name to "X".\n2. Update the project name to "X" on Replit.'
        self.assertEqual(dedupe_items(text), '1. Change the project name to "X".')

    def test_more_detailed_duplicate_wins(self):
        self.assertEqual(dedupe_items("1. Make the header blue.\n2. Make the header blue and bold."),
                         "1. Make the header blue and bold.")

    def test_distinct_items_kept_and_renumbered(self):
        text = "1. Make the login button green.\n2. Make the login button green.\n3. Move the login button to the top right."
        self.assertEqual(dedupe_items(text),
                         "1. Make the login button green.\n2. Move the login button to the top right.")

    def test_short_items_not_merged(self):
        self.assertEqual(dedupe_items("1. Do A.\n2. Do B."), "1. Do A.\n2. Do B.")

    def test_related_but_different_items_kept(self):
        text = "1. Delete the button.\n2. Delete the button text and the header image."
        self.assertEqual(dedupe_items(text), text)

    def test_non_list_untouched(self):
        self.assertEqual(dedupe_items("Just a sentence."), "Just a sentence.")


class CleanOutputTests(unittest.TestCase):
    def test_strips_fences_and_preamble(self):
        raw = "```\nHere are the instructions:\n1. Do A.\n2. Do B.\n```"
        self.assertEqual(clean_output(raw), "1. Do A.\n2. Do B.")


class HotkeyTests(unittest.TestCase):
    def test_parse_modifiers_and_letter(self):
        self.assertEqual(hotkey.parse("<ctrl>+<shift>+x"), frozenset({"ctrl", "shift", "vk88"}))

    def test_parse_function_key_alone(self):
        self.assertEqual(hotkey.parse("<f9>"), frozenset({"f9"}))

    def test_rejects_single_plain_key(self):
        with self.assertRaises(hotkey.HotkeyError):
            hotkey.parse("x")

    def test_known_conflict(self):
        self.assertIn("window", hotkey.check_conflict("<alt>+<space>").lower())

    def test_pretty(self):
        self.assertEqual(hotkey.pretty("<ctrl>+<shift>+x"), "Ctrl + Shift + X")


class SettingsTests(unittest.TestCase):
    def test_old_default_prompt_is_upgraded(self):
        s = Settings({"system_prompt": OLD_SYSTEM_PROMPTS[0]})
        self.assertEqual(s["system_prompt"], DEFAULT_SYSTEM_PROMPT)

    def test_custom_prompt_is_kept(self):
        self.assertEqual(Settings({"system_prompt": "my own"})["system_prompt"], "my own")

    def test_unknown_keys_ignored(self):
        self.assertNotIn("bogus", Settings({"bogus": 1}).data)


class TrainingLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = training.TRAINING_DIR, training.LOG_FILE
        training.TRAINING_DIR, training.LOG_FILE = self.tmp, self.tmp / "log.jsonl"

    def tearDown(self):
        training.TRAINING_DIR, training.LOG_FILE = self._orig

    def test_record_written_once_text_only(self):
        r = training.Record(3.0, Settings())
        r.transcript = "um make it blue"
        r.add_rewrite("1. Make it blue.")
        r.finish(training.SENT, final_prompt="1. Make it dark blue.", target="App - Replit")
        r.finish(training.CANCELLED)  # ignored
        rows = [json.loads(l) for l in training.LOG_FILE.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "sent")
        self.assertTrue(rows[0]["edited_by_user"])
        self.assertEqual(list(self.tmp.rglob("*.wav")), [])
        self.assertTrue((self.tmp / "prompts" / f"{rows[0]['system_prompt_id']}.txt").exists())


if __name__ == "__main__":
    unittest.main()
