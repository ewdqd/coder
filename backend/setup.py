"""Check and install backend dependencies."""
import sys
import subprocess
import importlib

PKGS = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("yaml", "pyyaml"),
    ("httpx", "httpx"),
    ("anthropic", "anthropic"),
    ("openai", "openai"),
]

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

missing = []
for mod, pkg in PKGS:
    try:
        importlib.import_module(mod)
        print(f"  [OK] {pkg}")
    except ImportError:
        print(f"  [MISSING] {pkg}")
        missing.append(pkg)

if missing:
    print(f"\nInstalling: {missing}")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-i", MIRROR] + missing)
    if r.returncode != 0:
        print("  Mirror failed, trying PyPI...")
        r = subprocess.run([sys.executable, "-m", "pip", "install"] + missing)
        if r.returncode != 0:
            print("[FAIL]")
            sys.exit(1)
    print("[OK] Done")
else:
    print("All packages ready")

sys.exit(0)
