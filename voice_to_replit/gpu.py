"""CUDA detection and DLL setup for faster-whisper (CTranslate2)."""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)
_dll_handles = []


def register_cuda_dlls() -> None:
    """Make pip-installed cuBLAS/cuDNN DLLs (nvidia-* wheels) loadable."""
    if _dll_handles:
        return
    roots = [Path(p) for p in sys.path if p.endswith("site-packages")]
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))
    for root in roots:
        nv = root / "nvidia"
        if not nv.is_dir():
            continue
        for bin_dir in nv.glob("*/bin"):
            try:
                _dll_handles.append(os.add_dll_directory(str(bin_dir)))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            except OSError:
                pass


def nvidia_smi() -> dict | None:
    """Return {'name', 'vram_mb', 'driver'} for the first NVIDIA GPU, or None."""
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    if not os.path.exists(exe):
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip().splitlines()
        if not out:
            return None
        name, mem, driver = [x.strip() for x in out[0].split(",")]
        return {"name": name, "vram_mb": int(float(mem)), "driver": driver}
    except Exception:
        return None


def cuda_available() -> bool:
    register_cuda_dlls()
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False
