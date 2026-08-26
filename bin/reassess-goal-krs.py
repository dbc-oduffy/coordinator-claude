from __future__ import annotations

# Review: code-reviewer P1 — the polyglot trampoline's exec probe line (line 2)
# is itself the first bare string-literal statement in the module, so CPython
# assigns __doc__ from THAT text, not from the usage text below (which is a
# second, inert string expression — same shape cross-repo-memo documents at
# its own line ~102-108). `_print_help()` previously wrote `__doc__`, so
# `--help` printed the shell-exec probe instead of Usage/Options/Exit-codes.
# Fix: assign the usage text to an explicit module-level constant instead of
# relying on __doc__, and have `_print_help()` read that constant.
# Spec backlink: DoE-claude:pln-per-repo-okr-goal-setting-syst-80bced § C6
_USAGE_TEXT = """
reassess-goal-krs — CLI trampoline over claude-klabauter coordinator_core.goals.reassess_krs.

Weekly KR re-assessment for per-repo state/goals/*.yaml goal artifacts. For each
active goal, parses the key_results[] YAML list block and correlates each KR's
extracted keywords against existing weekly signal (query-completions.py,
query-records.js, state/week-changelog/HEADER.md) to propose a per-KR status and
a perceptible_movement flag. READS existing signal only — builds no new
instrumentation. Writes a "proposed re-assessment" comment block to each active
goal artifact's end-of-file (non-dry-run only) for EM/PM confirmation; never
overwrites the live `status:` field.

Usage:
  reassess-goal-krs [--goals-dir <path>] [--since <date>] [--dry-run]

Options:
  --goals-dir <path>  Directory containing goal *.yaml files
                      (default: <repo-root>/state/goals)
  --since <date>      Week-start date for signal queries (default: 7d)
  --dry-run           Print proposed changes without writing to artifacts

Exit codes:
  0 — assessment complete (even if some goals have no movement, or the op
      degraded a signal source to a warning)
  1 — fatal error (engine-root resolution failure, op transport failure, or
      the op itself returned exit_code != 0)

Recipe: scratch/subagent-sandbox/bash-to-python-engine-migration/recipe-t3a-g3.md § 1
"""

import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import cc_invoke  # noqa: E402


def _find_repo_root(start: str) -> str:
    """Walk upward from `start` looking for a `.git` entry; falls back to
    `start` itself if none is found (mirrors the original bash script's
    REPO_ROOT derivation — coordinator/bin/.. is the plugin root, one more
    level up is the repo root — but derived here via .git discovery so this
    trampoline is correct regardless of install layout).
    """
    cur = start
    while True:
        if os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return start
        cur = parent


def _print_help() -> None:
    sys.stdout.write(_USAGE_TEXT or "")


def main() -> None:
    argv = sys.argv[1:]

    goals_dir = ""
    since = "7d"
    dry_run = False

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--goals-dir":
            if i + 1 >= len(argv):
                print("ERROR: --goals-dir requires an argument", file=sys.stderr)
                sys.exit(1)
            goals_dir = argv[i + 1]
            i += 2
        elif arg == "--since":
            if i + 1 >= len(argv):
                print("ERROR: --since requires an argument", file=sys.stderr)
                sys.exit(1)
            since = argv[i + 1]
            i += 2
        elif arg == "--dry-run":
            dry_run = True
            i += 1
        elif arg in ("--help", "-h"):
            _print_help()
            sys.exit(0)
        else:
            print(f"ERROR: Unknown argument: {arg}", file=sys.stderr)
            sys.exit(1)

    # Repo whose state/goals + state/week-changelog we operate on: the caller's
    # cwd-derived git root (matches the bash script's "never rely on cwd for
    # SCRIPT_DIR, but REPO_ROOT for state/ IS the repo the user is standing in"
    # split — bin_dir below is this script's OWN location; signal_repo_root is
    # the working repo).
    cwd_repo_root = _find_repo_root(os.getcwd())

    if not goals_dir:
        goals_dir = os.path.join(cwd_repo_root, "state", "goals")

    params = {
        "goals_dir": goals_dir,
        "since": since,
        "dry_run": dry_run,
        "bin_dir": _SCRIPT_DIR,
        "signal_repo_root": cwd_repo_root,
    }

    try:
        result = cc_invoke("goals.reassess_krs", params, cwd_repo_root)
    except RuntimeError as exc:
        print(f"reassess-goal-krs: op transport failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(result, dict):
        print(f"reassess-goal-krs: malformed result from cc_invoke: not a dict ({result!r})", file=sys.stderr)
        sys.exit(1)

    for warning in result.get("warnings") or []:
        print(f"WARNING: {warning}", file=sys.stderr)

    exit_code = result.get("exit_code", 1)
    if exit_code != 0:
        print(
            f"reassess-goal-krs: op reported failure: {result.get('error', '(no error message)')}",
            file=sys.stderr,
        )
        sys.exit(1)

    report = result.get("report", "")
    if report:
        print(report)

    sys.exit(0)


if __name__ == "__main__":
    main()
