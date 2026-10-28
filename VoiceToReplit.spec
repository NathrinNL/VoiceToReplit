# PyInstaller spec - builds dist\VoiceToReplit\ with two programs sharing one folder:
#   VoiceToReplit.exe          the tray app (no console window)
#   VoiceToReplit-console.exe  same app with a console, for --selftest / --syscheck
# Set VTR_CPU_ONLY=1 to leave out the ~1 GB of NVIDIA CUDA libraries.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

cpu_only = os.environ.get("VTR_CPU_ONLY") == "1"

binaries = collect_dynamic_libs("ctranslate2")
if not cpu_only:
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            binaries += collect_dynamic_libs(pkg)
        except Exception:
            pass

datas = collect_data_files("faster_whisper") + collect_data_files("onnxruntime")

a = Analysis(
    ["VoiceToReplit.pyw"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32",
                   "win32timezone", "voice_to_replit.app", "voice_to_replit.selftest",
                   "voice_to_replit.setup_models", "voice_to_replit.shortcut"],
    excludes=["matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

common = dict(debug=False, bootloader_ignore_signals=False, strip=False, upx=False, icon="icon.ico")
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoiceToReplit", console=False, **common)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoiceToReplit-console", console=True, **common)

coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="VoiceToReplit")
