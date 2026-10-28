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

    def test_template_preamble_bold_and_thinking_removed(self):
        raw = ("<think>The user wants...</think>\nSure! Here is the prompt:\n\n**Goal:** Rename the project.\n"
               "**Features:**\n- Change the project name to \"X\".\n- Update the project name to \"X\" on Replit.")
        self.assertEqual(clean_output(raw),
                         'Goal: Rename the project.\nFeatures:\n- Change the project name to "X".')

    def test_echoed_example_after_output_removed(self):
        raw = 'Goal: Make it blue.\nFeatures:\n- Make the header blue.\n\nExample 3\nTranscript: "..."'
        self.assertEqual(clean_output(raw), "Goal: Make it blue.\nFeatures:\n- Make the header blue.")

    def test_empty_optional_sections_removed(self):
        raw = ("Goal: Speed up the map.\n\nFeatures:\n- Make zooming faster.\n\nTech/Constraints:\n- None mentioned.\n"
               "Notes: None")
        self.assertEqual(clean_output(raw), "Goal: Speed up the map.\nFeatures:\n- Make zooming faster.")

    def test_real_notes_kept(self):
        raw = "Goal: X.\nFeatures:\n- Do X.\nNotes:\n- None of the colours were given."
        self.assertEqual(clean_output(raw), raw)

    def test_bullets_deduped_per_section(self):
        raw = ("Goal: Add a footer.\nFeatures:\n- Add a footer with the text \"Acme\".\n"
               "- Add a footer with the text \"Acme\".\nNotes:\n- Footer colour not given.")
        self.assertEqual(clean_output(raw), 'Goal: Add a footer.\nFeatures:\n- Add a footer with the text "Acme".\n'
                                            "Notes:\n- Footer colour not given.")


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


class WindowTitleTests(unittest.TestCase):
    def test_replit_titles(self):
        from voice_to_replit.winutil import _is_replit_title
        self.assertTrue(_is_replit_title("Nathrin Webpage - Replit"))
        self.assertTrue(_is_replit_title("My App - Replit - Google Chrome"))
        self.assertTrue(_is_replit_title("My App - Replit — Mozilla Firefox"))
        self.assertTrue(_is_replit_title("My App - Replit - Microsoft​ Edge"))
        self.assertFalse(_is_replit_title("NathrinNL/VoiceToReplit: Talk to the Replit Agent - Google Chrome"))
        self.assertFalse(_is_replit_title("Replit Docs: Agent overview - Google Chrome"))


class LocalCloudTests(unittest.TestCase):
    def test_cloud_model_names(self):
        from voice_to_replit.llm import is_cloud_model
        for n in ("glm-5.3-flash:cloud", "kimi-k3:cloud", "gpt-oss:120b-cloud"):
            self.assertTrue(is_cloud_model(n), n)
        for n in ("llama3.2", "qwen3.5:4b", "llama3.2:latest", "cloudy-model:3b"):
            self.assertFalse(is_cloud_model(n), n)

    def test_local_urls(self):
        from voice_to_replit.llm import is_local_url
        self.assertTrue(is_local_url("http://127.0.0.1:11434"))
        self.assertTrue(is_local_url("http://localhost:11434"))
        self.assertTrue(is_local_url("http://[::1]:11434"))
        self.assertFalse(is_local_url("http://192.168.1.20:11434"))
        self.assertFalse(is_local_url("https://ollama.com"))

    def test_local_mode_never_touches_network(self):
        """In Local mode, a cloud model or a non-localhost Ollama is refused before any request is made."""
        from unittest import mock

        from voice_to_replit.llm import Ollama, OllamaError

        def boom(*a, **k):
            raise AssertionError("network used in Local mode")

        with mock.patch("requests.get", boom), mock.patch("requests.post", boom):
            with self.assertRaisesRegex(OllamaError, "cloud model"):
                Ollama().rewrite("hi", "glm-5.3-flash:cloud", "p", cloud=False)
            with self.assertRaisesRegex(OllamaError, "only talks to Ollama on this computer"):
                Ollama("https://remote.example.com").rewrite("hi", "llama3.2", "p", cloud=False)

    def test_active_model_follows_mode(self):
        s = Settings({"ollama_model": "llama3.2", "ollama_cloud_model": "kimi-k3:cloud"})
        self.assertEqual((s.cloud, s.active_model), (False, "llama3.2"))
        s["llm_mode"] = "cloud"
        self.assertEqual((s.cloud, s.active_model), (True, "kimi-k3:cloud"))


class SettingsTests(unittest.TestCase):
    def test_old_default_prompt_is_upgraded(self):
        s = Settings({"system_prompt": OLD_SYSTEM_PROMPTS[0]})
        self.assertEqual(s["system_prompt"], DEFAULT_SYSTEM_PROMPT)

    def test_custom_prompt_is_kept(self):
        self.assertEqual(Settings({"system_prompt": "my own"})["system_prompt"], "my own")

    def test_unknown_keys_ignored(self):
        self.assertNotIn("bogus", Settings({"bogus": 1}).data)

    def test_defaults(self):
        s = Settings()
        self.assertEqual((s["ollama_model"], s["temperature"], s["llm_mode"]), ("llama3.2", 0.2, "local"))
        for part in ("Goal:", "Features:", "Tech/Constraints:", "Notes:", "Example 1", "Example 2"):
            self.assertIn(part, s["system_prompt"])


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
