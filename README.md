# Voice to Replit

**Talk to the Replit Agent instead of typing to it.** Hold a hotkey and ramble. The app turns your speech into a clean, numbered prompt, lets you review it, and then pastes it into the Replit Agent chat box for you.

Everything runs **locally on your Windows PC**. There are no paid APIs, cloud services or accounts. You only need the internet once, to download the AI models.

```
hold hotkey + speak → Whisper (speech-to-text) → Ollama (rewrite) → YOU review/edit → paste into Replit
```

Nothing is ever sent to Replit until you click **Send to Replit**.

**Features**
- Push-to-talk from anywhere, using a global hotkey with conflict detection
- Local transcription with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), using an NVIDIA GPU if you have one and the CPU otherwise
- Local prompt rewriting with [Ollama](https://ollama.com). It removes filler words and false starts and keeps every concrete detail you mention.
- A review window where you can edit, regenerate or re-record before anything is sent
- Pastes via the clipboard (never simulated typing) and restores your clipboard afterwards
- Works with Chrome, Edge, Firefox and the Replit desktop app. It is DPI-aware and refuses to click if the window has moved since you calibrated.
- History of your last 50 prompts, an optional training log, a system check, and a `--selftest` mode
- Dark-themed system tray app

> This is an independent community tool. It is not affiliated with or endorsed by Replit.

---

## Requirements

- Windows 10 or 11, 64-bit
- About 5 GB of free disk space (for the models), and 8 GB of RAM or more
- **Python 3.10–3.12, 64-bit, from python.org.** The Microsoft Store version of Python quietly redirects `%APPDATA%` into a hidden folder, so your settings would end up somewhere you can't find them. To install the right one: `winget install Python.Python.3.11 --scope user`
- **Ollama** from <https://ollama.com/download>. The installer can install it for you.
- Optional: an NVIDIA GPU, which makes speech recognition much faster. Without one, the app uses the CPU automatically.

## Setup

1. **Get the code.** Either:
   - click **Code → Download ZIP** on GitHub and unzip it somewhere permanent (for example `Documents\VoiceToReplit`), or
   - run:
     ```
     git clone https://github.com/NathrinNL/VoiceToReplit.git
     ```

   Keep the folder where it is after installing, because the shortcut and the virtual environment point to it.
2. Double-click **`install.bat`**. It will:
   - run the **system check**, which stops with a clear message if your PC isn't supported
   - offer to install Ollama if it's missing
   - create a virtual environment in `.venv` and install the pinned dependencies
   - install the NVIDIA CUDA libraries, but only if you have an NVIDIA GPU
   - suggest models for your PC, which you can accept or change
   - download the models, showing progress (this is the only step that needs internet)
   - optionally test your microphone (records 3 seconds and plays it back)
   - create a **Voice to Replit** shortcut on your desktop
3. Start the app with the desktop shortcut or **`run.bat`**. A microphone icon appears in the system tray. If you can't see it, check the `^` overflow area.
4. **Calibrate once:** open your Replit project with the Agent chat visible. Right-click the tray icon, choose **Recalibrate**, hover your mouse over the Agent chat box and press **F8**. On many laptops F8 is a media key, so press **Fn+F8**.

## Daily use

1. **Hold Ctrl+Shift+X** and speak. A small red "Recording" pill shows at the top of the screen.
2. **Release the keys.** The pill switches to "Transcribing…" and then "Rewriting prompt…".
3. The **Review** window opens:
   - **Raw transcript** (click to expand) shows exactly what you said
   - the **prompt** box can be edited
   - **Send to Replit** (Ctrl+Enter) · **Re-record** · **Regenerate** · **Cancel** (Esc)
4. When you click Send, the app:
   - copies the prompt
   - brings Replit to the front and clicks the chat box
   - pastes the prompt and presses Enter (you can turn Enter off)
   - puts your original clipboard contents back

The tray menu has **Settings**, **History** (your last 50 prompts, each of which can be resent through the Review window), **Run System Check**, **Recalibrate** and **Quit**.

## Settings

All settings are in the Settings window and in `%APPDATA%\VoiceToReplit\settings.json`:

| Setting | Default | Notes |
|---|---|---|
| Hotkey | `Ctrl+Shift+X` | Click **Change…** and press a new combination. The app warns you if another program already uses it. |
| Whisper model | from the system check | `tiny` → `large-v3`. Bigger is more accurate but slower. Device can be auto, cuda or cpu. |
| Ollama model | `llama3.2` | Any model you've pulled, e.g. `qwen2.5:3b`, `qwen2.5:7b` |
| Rewriting prompt | built in | Editable. **Reset prompt to default** restores the original. |
| Microphone | system default | |
| Press Enter after pasting | on | Turn it off if you'd rather press Enter yourself. |
| Chat box position | — | Set with Recalibrate / F8. |
| Start with Windows | off | Uses your per-user startup entry, so no admin is needed. |
| Save training log | off | Logs each session's text locally for training. See below. |

**Where files are stored:**
- Settings, history (`history.json`), the log (`voice_to_replit.log`) and `system_check_report.txt` are in `%APPDATA%\VoiceToReplit\`
- Whisper models are in `%LOCALAPPDATA%\VoiceToReplit\models\`
- Ollama models are stored by Ollama itself

## Training log

When **Save training log** is on (Settings → Options), every voice session is added as one line to:

`%APPDATA%\VoiceToReplit\training\log.jsonl`

The **Open folder** button next to the option opens that folder. Only text is stored, never audio.

Each line is a JSON object with these fields:

| Field | Meaning |
|---|---|
| `id`, `timestamp` | When the session happened |
| `outcome` | One of the values below |
| `audio_seconds` | How long you spoke (a number only; no audio is saved) |
| `whisper_model`, `ollama_model` | The models used |
| `transcript` | What Whisper heard |
| `rewrites` | Every rewrite the AI produced, including Regenerate, in order |
| `model_prompt` | The last AI rewrite shown to you |
| `final_prompt` | The text in the box when you finished. For `sent`, this is exactly what was pasted. |
| `edited_by_user` | `true` if you changed the AI's text before finishing |
| `system_prompt_id` | Which rewriting prompt was used. The full text is in `training\prompts\<id>.txt`. |
| `target_window` | The Replit window it was sent to |
| `error` | The error message, if the session failed |

Possible `outcome` values:
- `sent`: pasted into Replit
- `copied`: no Replit window was found, so it was left on the clipboard
- `cancelled`: you clicked Cancel or closed the window
- `rerecorded`: you clicked Re-record
- `replaced`: you started a new recording while the review was open
- `app_closed`: the app quit with the review still open
- `error`: transcription or rewriting failed

How to use it:
- Sessions with `"outcome": "sent"` are confirmed examples of good output.
- Where `edited_by_user` is `true`, `model_prompt` → `final_prompt` shows how you corrected the AI. This is useful for improving the prompt or fine-tuning a model.
- Prompts resent from History aren't logged again.
- Silent recordings are never logged.

## Testing

```
selftest.bat                    tests mic, whisper, ollama, rewrite, window, paste
selftest.bat --mic              also records 3 s of your voice
selftest.bat --stage rewrite    runs only one stage
.venv\Scripts\python.exe -m voice_to_replit --syscheck --mic-test
```

The **whisper** stage uses Windows' built-in text-to-speech to create a test sentence, so it works without you speaking. The **paste** stage pastes into a temporary test window instead of Replit. Each stage prints PASS, WARN or FAIL, and the summary tells you which one failed.

## How it works

1. **Hotkey:** a [pynput](https://github.com/moses-palmer/pynput) keyboard listener watches for the push-to-talk combination. It needs no admin rights. To detect conflicts, the app briefly calls `RegisterHotKey`, which fails if another program already owns the combination.
2. **Recording:** while the hotkey is held, [sounddevice](https://python-sounddevice.readthedocs.io) records at the microphone's native rate, then resamples to 16 kHz mono.
3. **Transcription:** faster-whisper runs `int8_float16` on CUDA, or `int8` on the CPU, with voice-activity filtering. The model is loaded at startup and stays loaded.
4. **Rewriting:** the transcript goes to Ollama's `/api/chat` along with an editable system prompt and a few built-in worked examples. The model is kept loaded with `keep_alive: -1`. The output is cleaned up, and repeated items are removed.
5. **Review:** a Tk window shows the transcript and the editable prompt.
6. **Sending:** the app finds a window whose title contains "Replit" and brings it to the front. It checks the window still matches the calibrated position, clicks the saved chat-box point, pastes with Ctrl+V and optionally presses Enter. Then it restores the clipboard.

## Project structure

```
install.bat / run.bat / selftest.bat / build_exe.bat   Windows entry points
VoiceToReplit.pyw          windowless launcher
VoiceToReplit.spec         PyInstaller build definition
requirements*.txt          exact pinned dependencies (base / NVIDIA GPU / build)
voice_to_replit/
  main.py                  command line (--selftest, --syscheck, --download-models), single instance
  app.py                   tray app and the record → transcribe → rewrite → review → send pipeline
  audio.py                 microphone recording and silence detection
  stt.py                   faster-whisper wrapper
  llm.py                   Ollama client, worked examples and output clean-up
  sender.py, winutil.py    finding windows, focus, DPI, clipboard and input (Win32)
  hotkey.py                push-to-talk listener and conflict detection
  settings.py, history.py, training.py, autostart.py, paths.py
  syscheck.py              system check (uses only the standard library, so it runs before install)
  selftest.py              --selftest stages
  ui/                      dark theme, overlay, review / settings / history / system-check windows
tests/                     fast unit tests (no mic, GPU or Ollama needed)
tools/eval_rewrite.py      measures rewrite quality for one or more Ollama models
```

## Development

```
.venv\Scripts\python.exe -m unittest discover -s tests -v       unit tests
.venv\Scripts\python.exe tools\eval_rewrite.py llama3.2 qwen2.5:3b   compare rewrite quality
.venv\Scripts\python.exe -m voice_to_replit --selftest          end-to-end stage checks
```

If you change the rewriting prompt or the worked examples in `voice_to_replit/llm.py`, run `tools/eval_rewrite.py` before and after. Small local models are sensitive to prompt changes.

## Contributing

Issues and pull requests are welcome. Please:
- keep everything working offline
- add no paid or cloud dependencies
- pin any new dependency to an exact version in `requirements.txt`
- run the unit tests and `--selftest` before opening a PR

Ideas: support for macOS/Linux, more agent chat targets (Cursor, Bolt, Lovable), a streaming preview of the rewrite.

## License

[MIT](LICENSE)

## Acknowledgements

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and OpenAI Whisper
- [Ollama](https://ollama.com) and Meta Llama 3.2
- [pynput](https://github.com/moses-palmer/pynput), [pystray](https://github.com/moses-palmer/pystray) and [sounddevice](https://python-sounddevice.readthedocs.io)

## Optional: standalone .exe

```
build_exe.bat        (includes NVIDIA GPU support, ~2.3 GB folder)
build_exe.bat cpu    (CPU only, much smaller)
```

The result is in `dist\VoiceToReplit\`. Keep the **whole folder** together:
- `VoiceToReplit.exe` is the tray app
- `VoiceToReplit-console.exe --selftest` runs the self-test

You still need Ollama installed separately.

**SmartScreen and antivirus:** the .exe isn't code-signed, so Windows SmartScreen may show "Windows protected your PC". Click **More info → Run anyway**. Some antivirus tools flag PyInstaller apps because the app watches the keyboard (for the hotkey) and simulates paste. If yours does, add the `dist\VoiceToReplit` folder as an exclusion (Windows Security → Virus & threat protection → Manage settings → Exclusions). You can avoid this completely by using `run.bat` instead of the .exe.

## Troubleshooting

| Problem | Fix |
|---|---|
| **"Ollama is not installed"** | Install it from ollama.com, then run `install.bat` again. |
| **"Ollama … did not start"** | Open **Ollama** from the Start menu. The app normally starts it for you. |
| **"Model '…' is not downloaded"** | Run `ollama pull llama3.2` (or your chosen model) in a terminal. |
| **"No microphone found"** | Plug one in, then check Windows Settings → System → Sound → Input. |
| **"The recording was silent"** | Pick the right microphone in Settings, and check it isn't muted (some headsets have a mute switch). |
| **Hotkey does nothing** | Another app may use it. Change it in Settings, which warns about conflicts. |
| **"Replit window has moved or been resized"** | Click **Recalibrate** and press F8 over the chat box. The app won't click if the window has changed, so it never clicks in the wrong place. |
| **"No Replit window found"** | Open Replit in Chrome, Edge, Firefox or the Replit app. The window title must contain "Replit". Your prompt is left on the clipboard, so you can still press Ctrl+V. |
| **More than one Replit window** | The app asks which one to use. |
| **Paste lands in the wrong place** | Recalibrate, hovering over the middle of the Agent input box. |
| **Slow transcription** | With no GPU, choose `small` or `base` in Settings. |
| **First prompt after startup is slow** | The models load when the app starts. The tray tooltip says "Ready" once they're loaded. |
| **Anything else** | Check `%APPDATA%\VoiceToReplit\voice_to_replit.log`, and run `selftest.bat` to see which stage fails. |

## Privacy

Your audio, transcripts and prompts never leave your PC, apart from the prompts you choose to send to Replit. Audio is never saved to disk. The training log is off by default and, if you turn it on, it stays on your PC. The only other network use is the one-time model download, from Hugging Face (Whisper) and Ollama.
