#!/usr/bin/env python3
"""Check that files changed in this branch don't exceed the size threshold.

Prevents accidental commits of large files that would permanently bloat the repo.
Only checks files in the diff against origin/main (not the full repo).
"""

import os
import subprocess
import sys

MAX_SIZE_BYTES = 1_000_000  # 1 MB
MAX_SIZE_LABEL = "1 MB"

def get_changed_files() -> list[str]:
    """Get files changed relative to origin/main."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            capture_output=True, text=True, check=True
        )
        return [f for f in result.stdout.strip().splitlines() if f]
    except subprocess.CalledProcessError:
        # Fallback: if origin/main doesn't exist (e.g., local-only run),
        # check all tracked files instead
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                capture_output=True, text=True, check=True
            )
            return [f for f in result.stdout.strip().splitlines() if f]
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"error: cannot list changed files: {e}", file=sys.stderr)
            sys.exit(1)


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    elif size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} B"


def main():
    errors = []

    changed = get_changed_files()

    for filepath in changed:
        if not os.path.exists(filepath):
            continue  # deleted file
        size = os.path.getsize(filepath)
        if size > MAX_SIZE_BYTES:
            errors.append(
                f"{filepath}: {format_size(size)} exceeds threshold of {MAX_SIZE_LABEL}"
            )

    if errors:
        print("File size check FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print(f"File size check passed ({len(changed)} files checked, threshold {MAX_SIZE_LABEL}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
