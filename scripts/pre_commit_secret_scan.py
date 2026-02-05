#!/usr/bin/env python3
"""
Simple pre-commit helper to block commits that obviously contain secrets.

Usage:
    1. Make this file executable if needed.
    2. Create .git/hooks/pre-commit with:

       #!/usr/bin/env bash
       python scripts/pre_commit_secret_scan.py

    3. git config core.hooksPath .git/hooks  # if not already using default.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# Patterns that should never appear in committed code
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("client_secret", re.compile(r"client_secret\s*=", re.IGNORECASE)),
    ("EPROC_CLIENT_SECRET", re.compile(r"EPROC_CLIENT_SECRET", re.IGNORECASE)),
    ("Bearer token", re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9\-_.]+", re.IGNORECASE)),
    ("OAuth token URL with inline credentials", re.compile(r"https?://[^/\s]+:[^@\s]+@")),
]


def get_staged_files() -> list[Path]:
    """Return a list of staged files (paths relative to repo root)."""
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    out = subprocess.check_output(cmd, cwd=ROOT, text=True)
    files = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ignore generated / vendor directories
        if line.startswith("web/node_modules/"):
            continue
        files.append(ROOT / line)
    return files


def scan_file(path: Path) -> list[str]:
    """Scan a single file for secret patterns; return list of human messages."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    hits: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(f"{label} in {path.relative_to(ROOT)}")
    return hits


def main() -> int:
    staged_files = get_staged_files()
    if not staged_files:
        return 0

    all_hits: list[str] = []
    for path in staged_files:
        all_hits.extend(scan_file(path))

    if all_hits:
        print("✗ Commit blocked: potential secrets detected:", file=sys.stderr)
        for hit in all_hits:
            print(f"  - {hit}", file=sys.stderr)
        print("\nIf these are false positives, update scripts/pre_commit_secret_scan.py patterns.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

