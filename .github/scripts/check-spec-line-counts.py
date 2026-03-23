#!/usr/bin/env python3
"""Enforce 500-line ceiling on behavioral spec files."""

import sys
import pathlib

PLUGINS_ROOT = pathlib.Path("plugins")

CEILING = 500
WARNING_THRESHOLD = 400

KNOWN_EXCEPTIONS: set[str] = set()

SPEC_PATTERNS = [
    "*/agents/*.md",
    "*/commands/*.md",
    "*/skills/*/SKILL.md",
    "*/pipelines/*/PIPELINE.md",
]

def main():
    errors = []

    if not PLUGINS_ROOT.is_dir():
        print(f"Plugin root not found: {PLUGINS_ROOT}")
        return 1

    for pattern in SPEC_PATTERNS:
        for spec_file in sorted(PLUGINS_ROOT.glob(pattern)):
            lines = spec_file.read_text(encoding="utf-8").splitlines()
            count = len(lines)

            relative = spec_file.relative_to(PLUGINS_ROOT).as_posix()
            if count > CEILING:
                if relative in KNOWN_EXCEPTIONS:
                    print(
                        f"Warning: {spec_file}: {count} lines exceeds ceiling (known exception, pending trim)",
                        file=sys.stderr,
                    )
                else:
                    errors.append(f"{spec_file}: {count} lines exceeds 500-line ceiling")
            elif count > WARNING_THRESHOLD:
                print(
                    f"Warning: {spec_file}: {count} lines approaching 500-line ceiling",
                    file=sys.stderr,
                )

    if errors:
        print("Spec line count check FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Spec line count check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
