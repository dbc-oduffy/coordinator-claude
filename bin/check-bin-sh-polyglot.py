# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""bin/check-bin-sh-polyglot.py — Tripwire: BIN-SH-POLYGLOT-INVARIANT

Purpose: Enforces the invariant that every member of the coordinator/bin/
sh/python polyglot class carries (a) line 1 == #!/bin/sh and (b) the
verbatim trampoline line:
  ''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''

Greppable token: BIN-SH-POLYGLOT-INVARIANT

Detection model — CONTENT-first, NOT extension-based:
  Enumerate ALL regular files directly under coordinator/bin/ and classify
  each as polyglot-class or out-of-scope by reading its content:
    - A file is IN-CLASS iff it contains the verbatim trampoline within the
      first 20 lines (has_trampoline). Trampoline past line 20 is invisible
      to sh at exec time — it would be treated as body code, not a re-exec.
    - This check script (check-bin-sh-polyglot.py) is SKIPPED from the scan
      because its source contains the trampoline as a data string (a
      constant and a comment), which would self-classify it as in-class. The
      script is not itself a sh/python polyglot CLI.
    - Pure #!/bin/sh tools WITHOUT the trampoline are NOT in-class and are
      silently skipped. A pure-#!/bin/sh non-polyglot is a valid other class.
    - #!/usr/bin/env python3 allowlisted scripts (age-sweep-lessons.py, etc.)
      have no trampoline and are silently skipped.
  For each IN-CLASS file, BOTH invariants are asserted:
    (a) line 1 == #!/bin/sh  (shebang-flip caught statically)
    (b) trampoline within first 20 lines (already required for membership)
  This avoids extension-glob undercounting: extensionless CLIs
  (cross-repo-memo, coordinator-lesson-promote, coordinator-queue-append,
  install-sentinel-write) are INVISIBLE to *.py globs — content-first
  classification catches them correctly.

Spec backlink: docs/plans/2026-06-18-bin-cli-sh-shebang-polyglot.md
Doctrine: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline
Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § E3-b

NOT A SECOND ENFORCEMENT SITE past claude-klabauter: claude-klabauter's
coordinator_core.bash_guards.commit_tripwires.check_bin_sh_polyglot is an
INDEPENDENT native re-implementation of this same invariant used at commit
time — it does not invoke this script. This script remains the manual/
ceremony-invocable CLI (see docs/wiki/coordinator-tripwires.md).

Usage:
  check-bin-sh-polyglot.py [--staged]

  (no flag)   Scan all regular files directly under coordinator/bin/ on disk.
  --staged    Scope scan to files that are both staged (git diff --cached)
              AND directly under coordinator/bin/. Suitable for pre-commit hooks.

Exit codes:
  0 — OK: every polyglot-class member has #!/bin/sh + verbatim trampoline
  1 — VIOLATION: one or more polyglot-class members are missing #!/bin/sh or
      the verbatim trampoline line

Output:
  stdout — human-readable status (OK or VIOLATION lines)
  stderr — error messages only

Negative-spec (hard-won):
  - Does NOT pre-filter by extension — extensionless CLIs are in-class.
  - Does NOT flag non-polyglot files (no trampoline in first 20 lines).
  - Does NOT flag pure-#!/bin/sh files that lack the trampoline.
  - Does NOT scan subdirectories — only directly under coordinator/bin/.
  - Does NOT scan itself (self-skip: this script's own path is excluded).
"""
from __future__ import annotations

import os
import subprocess
import sys

# The verbatim trampoline string every polyglot-class member must contain.
TRAMPOLINE = (
    '\'\'\'\'exec "$(command -v python3 || command -v python || command -v py)" '
    '"$0" "$@" #\'\'\''
)

TRAMPOLINE_WINDOW = 20

# A guard whose SUBJECT is the trampoline must carry the literal as a data
# value, so it would otherwise self-classify as in-class. This script and its
# repo-wide sibling (check-sh-suffix-polyglot.py) are the only two such guards.
# Membership is by construction, not convenience: merely mentioning the
# trampoline does not qualify — the file must be a checker that detects it.
#
# Three surfaces carry this exemption independently: this set,
# EXCLUDED_TRAMPOLINE_DOC_FILES in tests/test_no_bin_polyglot_invariant.py
# (keyed on repo-relative path), and _SELF_SKIP_BASENAMES in
# coordinator_core/bash_guards/commit_tripwires.py (keyed on basename, and
# additionally retaining the dead pre-rename basename check-bin-sh-polyglot.sh
# so a tree still carrying the old name stays exempt — inert wherever the
# rename has landed, which is why that asymmetry is deliberate rather than
# drift). The enforced invariant is therefore agreement on the LIVE-FILE
# SUBSET, not strict set equality: after dropping entries naming files absent
# from disk and normalizing basename-vs-repo-relative keying, all three must be
# identical, or one surface reads green while another fires on the same file.
# Mechanically checked by TestGuardSelfSkipCrossSetAgreement in
# coordinator_core/bash_guards/tests/test_commit_tripwires.py.
#
# Basename keying is safe only because this guard's scan domain is
# non-recursive over one directory (coordinator/bin/), so a basename collision
# is impossible; widening the scan domain would require re-keying this set on
# repo-relative path, as sh-suffix-polyglot-baseline.txt already is.
_GUARD_SELF_SKIP_BASENAMES = {
    "check-bin-sh-polyglot.py",
    "check-sh-suffix-polyglot.py",
}


def _show_toplevel(bin_dir: str) -> str:
    """Repo root for *bin_dir*, or "" if it is not inside a git worktree.

    Prefers ``coordinator_core.git.repo_root.show_toplevel`` (chunk C5,
    docs/plans/2026-08-16-a-process-per-predicate.md), which walks for a
    `.git` entry and spawns only when the walk finds none. Falls back to the
    original spawn if the engine is not importable — this runs on the commit
    path, where a guard that raises is worse than a guard that pays 13ms.

    The sibling `--show-prefix` call below is deliberately NOT routed through
    the seam: `show_prefix()` spawns there too (see that seam's own
    docstring), so converting it would trade one spawn for one spawn plus an
    indirection.
    """
    try:
        # The engine root is not on sys.path by construction on the published
        # mirror (coordinator_core is not pip-installed there), so the import
        # below cannot succeed without this. RuntimeError joins the except
        # tuple because an unresolvable root must degrade to the git spawn
        # below exactly as an absent module already does.
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel(bin_dir) or ""
    except (ImportError, RuntimeError):
        proc = subprocess.run(
            ["git", "-C", bin_dir, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""


def _candidate_paths(bin_dir: str, staged_only: bool) -> list[str]:
    if not staged_only:
        return sorted(
            os.path.join(bin_dir, name)
            for name in os.listdir(bin_dir)
            if os.path.isfile(os.path.join(bin_dir, name))
        )

    git_root = _show_toplevel(bin_dir)
    if not git_root:
        print("check-bin-sh-polyglot.py: ERROR — not a git repo", file=sys.stderr)
        return []

    prefix_proc = subprocess.run(
        ["git", "-C", bin_dir, "rev-parse", "--show-prefix"],
        capture_output=True,
        text=True,
        check=False,
    )
    bin_prefix = prefix_proc.stdout.strip() if prefix_proc.returncode == 0 else ""

    staged_proc = subprocess.run(
        ["git", "-C", git_root, "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    staged = staged_proc.stdout if staged_proc.returncode == 0 else ""
    if not staged:
        return []

    out: list[str] = []
    for rel in staged.splitlines():
        if bin_prefix and rel.startswith(bin_prefix):
            base = rel[len(bin_prefix):]
        elif not bin_prefix:
            base = rel
        else:
            continue
        if "/" in base:
            continue  # skip — in a subdirectory
        out.append(os.path.join(bin_dir, base))
    return out


def _first_n_lines(path: str, n: int) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = []
            for _ in range(n):
                line = fh.readline()
                if not line:
                    break
                lines.append(line)
            return "".join(lines)
    except OSError:
        return ""


def _has_trampoline(path: str) -> bool:
    return TRAMPOLINE in _first_n_lines(path, TRAMPOLINE_WINDOW)


def _has_sh_shebang(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            first_line = fh.readline().rstrip("\n")
    except OSError:
        return False
    return first_line == "#!/bin/sh"


def main(argv: list[str]) -> int:
    staged_only = False
    for arg in argv:
        if arg == "--staged":
            staged_only = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(
                "check-bin-sh-polyglot.py: unknown argument: %s" % arg,
                file=sys.stderr,
            )
            return 1

    bin_dir = os.path.dirname(os.path.abspath(__file__))

    offenders: list[str] = []
    for filepath in _candidate_paths(bin_dir, staged_only):
        if not os.path.isfile(filepath):
            continue
        if os.path.basename(filepath) in _GUARD_SELF_SKIP_BASENAMES:
            continue

        if not _has_trampoline(filepath):
            continue  # not in the polyglot class — skip

        if not _has_sh_shebang(filepath):
            offenders.append("  %s  (missing #!/bin/sh on line 1)" % filepath)

    if not offenders:
        print(
            "OK: all coordinator/bin/ sh/python polyglot members have "
            "#!/bin/sh + trampoline"
        )
        return 0

    print(
        "VIOLATION: BIN-SH-POLYGLOT-INVARIANT — the following coordinator/bin/ file(s)"
    )
    print(
        "  are in the sh/python polyglot class but are missing #!/bin/sh on "
        "line 1 and/or"
    )
    print("  the verbatim trampoline line.")
    print(
        "  See: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline"
    )
    print("  Plan: docs/plans/2026-06-18-bin-cli-sh-shebang-polyglot.md")
    print()
    for line in offenders:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
