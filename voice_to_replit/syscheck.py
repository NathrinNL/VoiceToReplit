"""System compatibility check.

The core checks use only the standard library so install.bat can run this *before*
any dependencies are installed:  python -m voice_to_replit.syscheck
"""
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import winreg
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
NEEDED_DISK_GB = 5


@dataclass
class Check:
    name: str
    status: str
    detail: str


@dataclass
class Report:
    checks: list = field(default_factory=list)
    recommended_whisper: str = "small"
    recommended_ollama: str = "llama3.2"
    gpu: dict | None = None

    def add(self, name, status, detail):
        self.checks.append(Check(name, status, detail))

    @property
    def fatal(self) -> bool:
        return any(c.status == FAIL and c.name in ("Windows", "Python") for c in self.checks)

    def text(self) -> str:
        lines = [f"Voice to Replit - System Check ({datetime.now():%Y-%m-%d %H:%M:%S})", "=" * 64]
        for c in self.checks:
            lines.append(f"[{c.status:4}] {c.name:<22} {c.detail}")
        lines += ["", "Recommended models for this machine:",
                  f"  Whisper (speech-to-text): {self.recommended_whisper}",
                  f"  Ollama (rewriting):       {self.recommended_ollama}"]
        if self.fatal:
            lines += ["", "UNSUPPORTED: fix the FAIL items above before installing."]
        return "\n".join(lines)


class _MEMSTAT(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_gb() -> float:
    m = _MEMSTAT()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys / 1024 ** 3


def _reg(root, path, name):
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ | view) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            continue
    return None


def _nvidia():
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    if not os.path.exists(exe):
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip().splitlines()
        name, mem, drv = [x.strip() for x in out[0].split(",")]
        return {"name": name, "vram_mb": int(float(mem)), "driver": drv}
    except Exception:
        return None


def _ollama_exe():
    exe = shutil.which("ollama")
    if exe:
        return exe
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(p) if p.exists() else None


def _http_json(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def recommend(ram: float, gpu: dict | None) -> tuple[str, str]:
    vram = gpu["vram_mb"] / 1024 if gpu else 0
    if vram >= 5.5:
        return "large-v3-turbo", "llama3.2"
    if vram >= 3.5:
        return "small", "llama3.2"
    if ram >= 12:
        return "small", "llama3.2"
    if ram >= 8:
        return "base", "qwen2.5:1.5b"
    return "tiny", "qwen2.5:0.5b"


def run_checks(ollama_url="http://127.0.0.1:11434", ollama_model=None) -> Report:
    rep = Report()

    # Windows version + architecture
    ver = sys.getwindowsversion()
    is64 = platform.machine().endswith("64")
    winname = "Windows 11" if ver.build >= 22000 else "Windows 10" if ver.major == 10 else f"Windows {ver.major}"
    ok = ver.major == 10 and is64
    rep.add("Windows", PASS if ok else FAIL,
            f"{winname} build {ver.build}, {platform.machine()}" + ("" if ok else " - Windows 10/11 64-bit is required"))

    # RAM
    ram = ram_gb()
    rep.add("RAM", PASS if ram >= 8 else WARN, f"{ram:.1f} GB" + ("" if ram >= 8 else " (8 GB+ recommended)"))

    # Disk
    for label, path in (("Disk (models)", os.environ.get("LOCALAPPDATA", "C:\\")),):
        free = shutil.disk_usage(path).free / 1024 ** 3
        rep.add(label, PASS if free >= NEEDED_DISK_GB else FAIL,
                f"{free:.1f} GB free on {Path(path).drive} (about {NEEDED_DISK_GB} GB needed)")

    # CPU
    cpu = _reg(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
    rep.add("CPU", INFO, f"{(cpu or platform.processor()).strip()}, {os.cpu_count()} threads")

    # GPU
    gpu = _nvidia()
    rep.gpu = gpu
    if gpu:
        rep.add("NVIDIA GPU / CUDA", PASS, f"{gpu['name']}, {gpu['vram_mb'] / 1024:.1f} GB VRAM, driver {gpu['driver']}")
    else:
        rep.add("NVIDIA GPU / CUDA", INFO, "No NVIDIA GPU found - Whisper will run on the CPU (slower, still works)")

    rep.recommended_whisper, rep.recommended_ollama = recommend(ram, gpu)

    # Python
    v = sys.version_info
    py64 = sys.maxsize > 2 ** 32
    store = "WindowsApps" in sys.executable
    if v >= (3, 10) and py64:
        status = WARN if store else PASS
        extra = (" - Microsoft Store Python redirects %APPDATA% into a hidden sandbox; "
                 "the python.org installer is recommended") if store else ""
        rep.add("Python", status, f"{platform.python_version()} 64-bit ({sys.executable}){extra}")
    else:
        rep.add("Python", FAIL, f"{platform.python_version()} {'64' if py64 else '32'}-bit - need 64-bit 3.10+")

    # Ollama
    exe = _ollama_exe()
    if not exe:
        rep.add("Ollama", FAIL, "Not installed - get it from https://ollama.com/download")
    else:
        try:
            ov = _http_json(f"{ollama_url}/api/version")["version"]
            rep.add("Ollama", PASS, f"Running (v{ov})")
            names = [m["name"] for m in _http_json(f"{ollama_url}/api/tags").get("models", [])]
            want = ollama_model or rep.recommended_ollama
            have = any(n == want or n == want + ":latest" for n in names)
            rep.add("Ollama model", PASS if have else WARN,
                    f"'{want}' " + ("downloaded" if have else "not downloaded yet (install.bat pulls it)"))
        except Exception:
            rep.add("Ollama", WARN, f"Installed ({exe}) but not running - the app will start it automatically")

    # Microphone (waveIn count works without extra packages)
    n_in = ctypes.windll.winmm.waveInGetNumDevs()
    rep.add("Microphone", PASS if n_in else FAIL,
            f"{n_in} input device(s) detected" if n_in else "No microphone detected")

    # VC++ runtime
    vc = _reg(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64", "Installed")
    vcver = _reg(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64", "Version")
    if vc == 1:
        rep.add("VC++ Redistributable", PASS, f"x64 {vcver}")
    elif os.path.exists(r"C:\Windows\System32\vcruntime140_1.dll"):
        rep.add("VC++ Redistributable", PASS, "vcruntime140 present")
    else:
        rep.add("VC++ Redistributable", WARN,
                "Not found - install from https://aka.ms/vs/17/release/vc_redist.x64.exe")

    # Admin rights
    admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    rep.add("Admin rights", PASS, "Not required - everything installs per-user"
            + (" (currently running as admin)" if admin else ""))
    return rep


def mic_test(device_name: str = "", seconds: float = 3.0) -> Check:
    """Record and play back. Needs the app's dependencies (sounddevice/numpy)."""
    try:
        from .audio import AudioError, check_not_silent, play, record_seconds, rms
        audio = record_seconds(seconds, device_name)
        level = rms(audio)
        try:
            check_not_silent(audio)
        except AudioError as e:
            return Check("Mic test", WARN, f"Recorded {len(audio) / 16000:.1f}s but it was silent (level {level:.4f}). {e}")
        play(audio)
        return Check("Mic test", PASS, f"Recorded {len(audio) / 16000:.1f}s, level {level:.4f}, played back")
    except Exception as e:
        return Check("Mic test", FAIL, str(e))


def save_report(rep: Report, path: Path | None = None) -> Path:
    if path is None:
        base = Path(os.environ.get("APPDATA", Path.home())) / "VoiceToReplit"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "system_check_report.txt"
    path.write_text(rep.text(), encoding="utf-8")
    return path


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Voice to Replit system check")
    ap.add_argument("--mic-test", action="store_true", help="also record 3 s and play it back")
    ap.add_argument("--json", help="write recommendations to this JSON file")
    ap.add_argument("--apply", action="store_true", help="save recommended models into settings.json")
    ap.add_argument("--choose", action="store_true", help="ask to accept or change the recommended models, then save")
    args = ap.parse_args(argv)
    rep = run_checks()
    if args.mic_test:
        input("\n>>> Microphone test: press Enter, then speak for 3 seconds...")
        print("    Recording... (it will play back afterwards)", flush=True)
        rep.checks.append(mic_test())
    print(rep.text())
    print(f"\nReport saved to {save_report(rep)}")
    whisper, ollama = rep.recommended_whisper, rep.recommended_ollama
    if args.choose and not rep.fatal:
        ans = input(f"\nUse the recommended models (Whisper '{whisper}', Ollama '{ollama}')? [Y/n] ").strip().lower()
        if ans.startswith("n"):
            print("Whisper sizes: tiny, base, small, medium, large-v3-turbo, large-v3")
            whisper = input(f"  Whisper model [{whisper}]: ").strip() or whisper
            print("Ollama examples: llama3.2, qwen2.5:3b, qwen2.5:7b, llama3.2:1b")
            ollama = input(f"  Ollama model [{ollama}]: ").strip() or ollama
    if args.json:
        Path(args.json).write_text(json.dumps({"whisper": whisper, "ollama": ollama}), encoding="utf-8")
    if args.apply or args.choose:
        from .settings import Settings
        s = Settings.load()
        s["whisper_model"], s["ollama_model"] = whisper, ollama
        s.save()
        print(f"Saved: Whisper '{whisper}', Ollama '{ollama}'")
    return 2 if rep.fatal else 0


if __name__ == "__main__":
    sys.exit(main())
