@echo off
setlocal EnableExtensions
title Voice to Replit - Installer
cd /d "%~dp0"
echo ============================================================
echo   Voice to Replit - installer
echo ============================================================
echo.

rem ---------- 1. Find a suitable Python (python.org install preferred) ----------
set "PY="
for %%V in (312 311 310) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
    if not defined PY if exist "%ProgramFiles%\Python%%V\python.exe" set "PY=%ProgramFiles%\Python%%V\python.exe"
)
if not defined PY (
    where py >nul 2>nul && for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
)
if not defined PY (
    where python >nul 2>nul && for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
)
if not defined PY (
    echo [FAIL] Python 3.10+ 64-bit was not found.
    echo        Install it from https://www.python.org/downloads/windows/
    echo        or run:  winget install Python.Python.3.11 --scope user
    echo        then run install.bat again.
    pause & exit /b 1
)
echo Using Python: %PY%
echo.

rem ---------- 2. System check (standard library only - nothing installed yet) ----------
echo Running system check...
"%PY%" -m voice_to_replit.syscheck
if errorlevel 2 (
    echo.
    echo [FAIL] This PC does not meet the requirements. See the report above.
    pause & exit /b 1
)
echo.

rem ---------- 3. Ollama ----------
set "OLLAMA="
where ollama >nul 2>nul && set "OLLAMA=ollama"
if not defined OLLAMA if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA (
    echo Ollama is not installed. It runs the local AI model that rewrites your prompts.
    choice /c YN /m "Install Ollama now with winget (per-user, no admin)"
    if errorlevel 2 (
        echo Please install Ollama from https://ollama.com/download and run install.bat again.
        pause & exit /b 1
    )
    winget install --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    if not defined OLLAMA (
        echo [FAIL] Ollama install did not complete. Install it from https://ollama.com/download
        pause & exit /b 1
    )
)

rem ---------- 4. Virtual environment + dependencies ----------
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    "%PY%" -m venv .venv || (echo [FAIL] Could not create the virtual environment. & pause & exit /b 1)
)
set "VPY=%~dp0.venv\Scripts\python.exe"
echo Installing dependencies (this can take a few minutes)...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check -q
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (echo [FAIL] Dependency install failed. See the messages above. & pause & exit /b 1)

where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    echo NVIDIA GPU found - installing CUDA libraries for fast speech recognition ^(~1 GB^)...
    "%VPY%" -m pip install -r requirements-gpu.txt --disable-pip-version-check
    if errorlevel 1 echo [WARN] GPU libraries failed to install - the app will use the CPU instead.
)
echo.

rem ---------- 5. Choose models, then download them (one time, needs internet) ----------
"%VPY%" -m voice_to_replit.syscheck --choose
echo.
"%VPY%" -m voice_to_replit --download-models
if errorlevel 1 (
    echo [WARN] A model download failed. Check your internet connection and run install.bat again.
)
echo.

rem ---------- 6. Microphone test ----------
choice /c YN /m "Test your microphone now (records 3 seconds and plays it back)"
if not errorlevel 2 "%VPY%" -m voice_to_replit.syscheck --mic-test
echo.

rem ---------- 7. Desktop shortcut ----------
"%VPY%" -m voice_to_replit.shortcut
echo.
echo ============================================================
echo   Installed! Start it with the desktop shortcut or run.bat.
echo   Test each stage any time with:  selftest.bat
echo ============================================================
choice /c YN /m "Start Voice to Replit now"
if not errorlevel 2 start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0VoiceToReplit.pyw"
endlocal
