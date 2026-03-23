#!/usr/bin/env python3
"""Scan for accidental secrets in tracked files."""

import re
import sys
import pathlib
import subprocess

PATTERNS = [
    ("API key (sk-style)", re.compile(r'sk-[a-zA-Z0-9]{20,}')),
    ("AWS access key", re.compile(r'AKIA[A-Z0-9]{16}')),
    ("GitHub personal access token", re.compile(r'ghp_[a-zA-Z0-9]{36}')),
    ("Hardcoded password", re.compile(r'password\s*[:=]\s*[\'"][^\'"]+[\'"]', re.IGNORECASE)),
    ("Hardcoded secret", re.compile(r'secret\s*[:=]\s*[\'"][^\'"]+[\'"]', re.IGNORECASE)),
]

# Inline suppression: add "# noqa: secrets" to a line to skip it
NOQA_RE = re.compile(r'#\s*noqa:\s*secrets', re.IGNORECASE)

# File-based allowlist: .github/.secrets-allowlist
# Format: one "filepath:line_number" per line
ALLOWLIST_PATH = pathlib.Path(".github/.secrets-allowlist")

# Files to skip
SELF = pathlib.Path(__file__).resolve()

def load_allowlist() -> set[str]:
    """Load file-based allowlist entries as 'filepath:line_number' strings."""
    if not ALLOWLIST_PATH.exists():
        return set()
    entries = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return entries


def check_allowlist_staleness(allowlist: set[str], warnings: list):
    """Warn about allowlist entries that no longer match anything."""
    for entry in sorted(allowlist):
        parts = entry.split(":", 1)
        if len(parts) != 2:
            warnings.append(f"allowlist: malformed entry '{entry}' (expected 'filepath:line_number')")
            continue
        fpath, line_str = parts
        if not pathlib.Path(fpath).exists():
            warnings.append(f"allowlist: stale entry '{entry}' — file no longer exists")
            continue
        try:
            int(line_str)
        except ValueError:
            warnings.append(f"allowlist: malformed entry '{entry}' — line number must be integer")


def get_tracked_files() -> list[pathlib.Path]:
    """Get list of git-tracked files."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached"],
            capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"error: cannot list tracked files: {e}", file=sys.stderr)
        sys.exit(1)
    return [pathlib.Path(f) for f in result.stdout.strip().splitlines() if f]


def main():
    errors = []
    warnings = []

    tracked = get_tracked_files()
    allowlist = load_allowlist()
    check_allowlist_staleness(allowlist, warnings)

    for fpath in tracked:
        if not fpath.exists() or fpath.resolve() == SELF:
            continue
        if str(fpath).startswith(".git/"):
            continue

        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(text.splitlines(), 1):
            # Skip lines with inline noqa suppression
            if NOQA_RE.search(line):
                continue

            # Skip lines in file-based allowlist
            allowlist_key = f"{fpath}:{line_num}"
            if allowlist_key in allowlist:
                continue

            for pattern_name, pattern in PATTERNS:
                if pattern.search(line):
                    errors.append(f"{fpath}:{line_num}: potential {pattern_name} detected")

    if warnings:
        print("Secrets scan warnings:")
        for w in warnings:
            print(f"  {w}")

    if errors:
        print("Secrets scan FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Secrets scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
