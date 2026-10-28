@echo off
rem Builds an optional standalone version in dist\VoiceToReplit\
rem Usage:  build_exe.bat          (includes NVIDIA GPU libraries, ~2 GB folder)
rem         build_exe.bat cpu      (CPU-only, much smaller)
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat first.
    pause & exit /b 1
)
set "VPY=.venv\Scripts\python.exe"
if /i "%~1"=="cpu" (set "VTR_CPU_ONLY=1") else (set "VTR_CPU_ONLY=0")

"%VPY%" -m pip install -r requirements-build.txt --disable-pip-version-check -q || (echo pip failed & pause & exit /b 1)
"%VPY%" -c "from voice_to_replit.ui.icon import save_ico; save_ico('icon.ico')"
"%VPY%" -m PyInstaller --noconfirm --clean VoiceToReplit.spec
if errorlevel 1 (echo [FAIL] Build failed - see the messages above. & pause & exit /b 1)

echo.
echo Built: %~dp0dist\VoiceToReplit\VoiceToReplit.exe
echo Self-test: dist\VoiceToReplit\VoiceToReplit-console.exe --selftest
echo Copy the whole dist\VoiceToReplit folder (not just the .exe) if you move it.
echo Ollama must still be installed separately (https://ollama.com/download).
pause
endlocal
