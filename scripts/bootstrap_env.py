#!/usr/bin/env python3
"""
Bootstrap the current Python environment with required dependencies.
Uses only the current interpreter (sys.executable); never relies on bare pip.
"""
import subprocess
import sys
from pathlib import Path

# Required packages: (pip_install_name, import_module_name)
# Use import name for "import X" so we can detect if already installed
REQUIRED_PACKAGES = [
    ("requests", "requests"),
    ("fastapi", "fastapi"),
    ("pydantic", "pydantic"),
    ("pydantic-settings", "pydantic_settings"),
    ("sqlalchemy", "sqlalchemy"),
    ("alembic", "alembic"),
    ("uvicorn", "uvicorn"),
    ("httpx", "httpx"),
    ("pytest", "pytest"),
]

# Repo root: parent of scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
VENV_DIR = REPO_ROOT / ".venv"


def _in_venv() -> bool:
    """Return True if the current interpreter is inside REPO_ROOT/.venv."""
    try:
        prefix = Path(sys.prefix).resolve()
        venv_resolved = VENV_DIR.resolve()
        # prefix is e.g. repo/.venv or repo/.venv/Scripts; venv is repo/.venv
        return (venv_resolved in prefix.parents) or (prefix == venv_resolved)
    except Exception:
        return False


def _venv_exists() -> bool:
    """Return True if .venv exists at repo root."""
    return VENV_DIR.is_dir()


def check_venv() -> None:
    """
    Optional venv detection (non-breaking).
    Warn if .venv is missing or if current interpreter is not inside it.
    """
    if not _venv_exists():
        print(
            "[WARNING] No .venv directory found at repo root. "
            "Consider using a virtual environment for isolation."
        )
        print("  To create one manually:")
        print(f"    {sys.executable} -m venv .venv")
        print("  Then activate (PowerShell):")
        print("    .\\.venv\\Scripts\\Activate.ps1")
        return

    if not _in_venv():
        print(
            "[WARNING] A .venv exists but the current interpreter is not inside it. "
            "You may be using a different Python (e.g. system or another venv)."
        )
        print(f"  Current interpreter: {sys.executable}")
        print(f"  Expected venv:       {VENV_DIR / 'Scripts' / 'python.exe'}")
    else:
        print("[OK] Using interpreter from .venv")


def ensure_package(pip_name: str, import_name: str) -> bool:
    """
    Try to import the module; if it fails, install via current interpreter -m pip.
    Returns True if available (already or after install), False on failure.
    """
    try:
        __import__(import_name)
        print(f"[OK] {pip_name} already installed")
        return True
    except ModuleNotFoundError:
        pass
    except Exception as e:
        # Other import errors (e.g. missing deps) — try installing anyway
        print(f"[INSTALL] {pip_name} import failed ({e}); attempting install...")

    print(f"[INSTALL] Installing {pip_name}...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name],
            check=True,
            capture_output=False,
        )
        print(f"[OK] {pip_name} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Installation failed for {pip_name}: {e}")
        return False
    except FileNotFoundError:
        print(
            f"[ERROR] Installation failed for {pip_name}: "
            f"pip not found for this interpreter ({sys.executable}). "
            "Ensure pip is installed (e.g. ensurepip or get-pip.py)."
        )
        return False


def main() -> int:
    """Install any missing required packages and print summary."""
    print("ProcureWatch environment bootstrap")
    print("Using current interpreter only (no bare pip).")
    print("-" * 50)

    check_venv()
    print("-" * 50)

    failed: list[str] = []
    for pip_name, import_name in REQUIRED_PACKAGES:
        if not ensure_package(pip_name, import_name):
            failed.append(pip_name)

    print("-" * 50)
    print(f"Python executable: {sys.executable}")
    print(f"Python version:    {sys.version.split()[0]}")
    if failed:
        print(f"[ERROR] Environment not ready. Failed packages: {', '.join(failed)}")
        return 1
    print("[OK] Environment is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
