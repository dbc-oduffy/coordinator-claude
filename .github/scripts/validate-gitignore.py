#!/usr/bin/env python3
"""Validate .gitignore complies with repo policy: no deny-all patterns.

Policy (docs/gitignore-policy.md):
  - Deny-all (* then !exceptions) patterns are forbidden
  - Default failure mode must be "tracked too much", never "silently lost work"
  - Allow-all-then-exclude only
"""

import re
import sys
import pathlib

# Patterns that deny everything at some scope
GLOBAL_DENY_ALL = re.compile(r"^\*\s*$")       # bare *
GLOBAL_DENY_FILES = re.compile(r"^\*\.\*\s*$")  # *.*
ROOT_DENY_ALL = re.compile(r"^/\*\s*$")         # /*


def validate_gitignore(path: pathlib.Path, errors: list):
    if not path.exists():
        return  # no .gitignore is fine

    lines = path.read_text(encoding="utf-8").splitlines()

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments and blanks
        if not stripped or stripped.startswith("#"):
            continue

        if GLOBAL_DENY_ALL.match(stripped):
            errors.append(f".gitignore:{line_num}: forbidden deny-all pattern '{stripped}' — "
                          "policy requires allow-all-then-exclude (see docs/gitignore-policy.md)")

        elif GLOBAL_DENY_FILES.match(stripped):
            errors.append(f".gitignore:{line_num}: forbidden deny-all-files pattern '{stripped}' — "
                          "policy requires allow-all-then-exclude")

        elif ROOT_DENY_ALL.match(stripped):
            errors.append(f".gitignore:{line_num}: forbidden root deny-all pattern '{stripped}' — "
                          "policy requires allow-all-then-exclude")

    # Detect directory-scoped deny-all-then-allowlist pattern:
    # A line like "somedir/*" followed by mostly "!somedir/..." exceptions
    # indicates a deny-all-then-allowlist pattern within that directory.
    dir_deny_pattern = re.compile(r"^([a-zA-Z0-9_./-]+)/\*\s*$")
    non_comment_lines = [(num, l.strip()) for num, l in enumerate(lines, 1)
                         if l.strip() and not l.strip().startswith("#")]

    for idx, (line_num, stripped) in enumerate(non_comment_lines):
        match = dir_deny_pattern.match(stripped)
        if not match:
            continue

        dirname = match.group(1)
        # Count how many subsequent lines are !-prefixed exceptions for this dir
        exceptions = 0
        total_following = 0
        for _, (_, following) in enumerate(non_comment_lines[idx + 1:], 1):
            # Stop at the next section (blank line gaps are already filtered)
            if not following.startswith("!"):
                break
            if following.startswith(f"!{dirname}/") or following.startswith(f"!{dirname}\\"):
                exceptions += 1
            total_following += 1

        if exceptions >= 3 and total_following > 0 and exceptions / total_following > 0.5:
            errors.append(
                f".gitignore:{line_num}: likely deny-all-then-allowlist pattern for '{dirname}/' — "
                f"found '{stripped}' followed by {exceptions} '!' exceptions. "
                "Policy requires allow-all-then-exclude.")


def main():
    errors = []

    validate_gitignore(pathlib.Path(".gitignore"), errors)

    if errors:
        print("Gitignore policy validation FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Gitignore policy validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
