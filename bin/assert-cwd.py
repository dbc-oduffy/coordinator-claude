# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: assert-cwd <expected-abs-path>", file=sys.stderr)
        return 2

    expected = str(Path(argv[0]).resolve())

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        print(f"ERROR: cannot invoke git: {exc}", file=sys.stderr)
        return 1

    if proc.returncode != 0:
        print(
            f"ERROR: git rev-parse --show-toplevel failed (not inside a git "
            f"working tree?): {proc.stderr.strip()}",
            file=sys.stderr,
        )
        return 1

    actual = str(Path(proc.stdout.strip()).resolve())

    if actual != expected:
        print(f"ERROR: cwd is {actual}, expected {expected}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
