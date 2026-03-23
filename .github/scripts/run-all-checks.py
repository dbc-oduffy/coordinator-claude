#!/usr/bin/env python3
"""Run all validation checks locally.

Convention-based discovery: runs all validate-*.py and check-*.py scripts
in this directory (excluding itself). Reports pass/fail summary.
"""

import pathlib
import subprocess
import sys
import time

SCRIPTS_DIR = pathlib.Path(__file__).parent
SELF = pathlib.Path(__file__).name

PATTERNS = ["validate-*.py", "check-*.py"]


def discover_scripts() -> list[pathlib.Path]:
    """Find all validation scripts by naming convention."""
    scripts = set()
    for pattern in PATTERNS:
        for path in sorted(SCRIPTS_DIR.glob(pattern)):
            if path.name == SELF:
                continue
            scripts.add(path)
    return sorted(scripts)


def main():
    scripts = discover_scripts()

    if not scripts:
        print("No validation scripts found.")
        sys.exit(1)

    print(f"Running {len(scripts)} validation checks...\n")

    results: list[tuple[str, int, float]] = []

    for script in scripts:
        name = script.stem
        start = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True,
            cwd=SCRIPTS_DIR.parent.parent,  # repo root
        )
        elapsed = time.monotonic() - start
        results.append((name, result.returncode, elapsed))

        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"  [{status}] {name} ({elapsed:.1f}s)")

        if result.returncode != 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                print(f"         {line}")
        if result.returncode != 0 and result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                print(f"         {line}")

    # Summary
    passed = sum(1 for _, rc, _ in results if rc == 0)
    failed = sum(1 for _, rc, _ in results if rc != 0)
    total_time = sum(t for _, _, t in results)

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed ({total_time:.1f}s total)")
    print(f"{'='*50}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
