"""pet launcher - starts AI backend then desktop pet."""
import subprocess
import sys
import time
import urllib.request
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PET_EXE = ROOT / "pet-desktop" / "publish" / "pet.exe"
PET_PROJ = ROOT / "pet-desktop" / "pet" / "pet.csproj"

def log(msg: str):
    print(f"  {msg}")

def main():
    print("=" * 48)
    print("  pet - NuanNuan Desktop Companion")
    print("=" * 48)
    print()

    # 1. Start AI backend
    print("[1/3] Starting AI backend...")
    python = str(ROOT / ".venv" / "Scripts" / "python.exe")

    backend_process = subprocess.Popen(
        [python, str(BACKEND / "__main__.py")],
        cwd=str(BACKEND),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 2. Wait for health check
    print("       Waiting for backend...")
    for i in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:9876/health", timeout=1)
            print(f"       Backend ready (http://127.0.0.1:9876)")
            break
        except Exception:
            time.sleep(1)
    else:
        print("       [WARN] Backend not responding, continuing...")

    # 3. Build EXE if needed
    if not PET_EXE.exists():
        print("[2/3] Building desktop pet EXE (first time, ~3 min)...")
        r = subprocess.run([
            "dotnet", "publish", str(PET_PROJ),
            "-c", "Release", "-r", "win-x64",
            "--self-contained",
            "-p:PublishSingleFile=true",
            "-o", str(PET_EXE.parent),
        ], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[FAIL] Build failed:\n{r.stderr[-500:]}")
            input("Press Enter to exit...")
            sys.exit(1)
        print("       Build done")

    # 4. Launch pet
    print("[3/3] Launching NuanNuan...")
    print()
    print("=" * 48)
    print("  NuanNuan is here!")
    print("  Right-click her for menu")
    print("  Middle-click for AI chat")
    print("  Ctrl+Shift+S to show/hide")
    print("=" * 48)
    print()
    print("Close this window or press Ctrl+C to stop.")
    print()

    try:
        # os.startfile uses ShellExecute (handles UAC correctly)
        os.startfile(str(PET_EXE))
        print("Pet launched. Keep this window open while using it.")
        # Wait for user to close this window
        input()
    except KeyboardInterrupt:
        pass
    finally:
        backend_process.terminate()
        print("Backend stopped.")

if __name__ == "__main__":
    main()
    input("Press Enter to exit...")
