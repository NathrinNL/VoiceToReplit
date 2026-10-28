@echo off
rem Tests each stage separately. Add --mic to test with your voice, or --stage NAME for one stage
rem (stages: mic whisper ollama rewrite window paste).
cd /d "%~dp0"
".venv\Scripts\python.exe" -m voice_to_replit --selftest %*
pause
