"""bug-sweep-probes.py — naked-Python probes for the /bug-sweep skill.

Ports the genuine imperative logic out of DoE-claude's
coordinator/skills/bug-sweep/SKILL.md so the skill can call a single
maintained CLI by name instead of carrying inline bash fences. Two
subcommands, one per ported concern (D2's later repoint wires the skill's
prose to these invocation shapes):

  detect-stack   — Phase 0 step 1 (language / test-framework / config-file
                   detection probe). Read-only; no git state touched.
  verify-diff    — Phase 4 step 0 (mechanical diff gate: expected-vs-actual
                   changed-files comm-based verification, ALERT branch for
                   fix-now files claimed-but-not-diffed).

Deliberately self-contained — no coordinator_core / engine-root resolution.
Both ported concerns are pure stdlib logic (filesystem probes, `git diff`,
set difference) with no dependency on the claude-klabauter engine.

Self-resolving: every path this script touches is either an explicit CLI
argument or derived from Path(__file__); it never depends on cwd.

Spec backlink: DoE-claude coordinator/skills/bug-sweep/SKILL.md
  § Phase 0 step 1 (lines ~25-33) and § Phase 4 step 0 (lines ~278-290)
  (as of the 2026-07-23 bash-residual-migration read).
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
  (chunk C-BUGSWEEP)

NEGATIVE SPEC
  - Does NOT port the resolve-claude-klabauter-bin / _cc_trusted / _cc_root / _cc_claude_klabauter
    resolution ladder (SKILL.md lines ~44-67) — that's guard-preamble
    boilerplate, out of scope per the D-wave split (D1/D2's concern).
  - Does NOT compute the `DOCS_VERIFY` flag — SKILL.md frames that as a
    judgment call ("YOU do this... When in doubt, lean toward enabling
    it"), not a script-computed value; `detect-stack` reports raw probe
    data only and leaves the judgment to the calling agent.
"""

from __future__ import annotations

import argparse
import glob as glob_mod
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# detect-stack — SKILL.md Phase 0 step 1
# ---------------------------------------------------------------------------

# Extensions from the original `find . -name "*.py" -o -name "*.ts" ...` fence.
_LANGUAGE_EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".cpp", ".h")

# Directory names from the original `ls -d tests/ __tests__/ spec/ test/`.
_TEST_DIR_NAMES = ("tests", "__tests__", "spec", "test")

# Literal filenames + one glob pattern from the original
# `ls pytest.ini pyproject.toml jest.config.* tsconfig.json CMakeLists.txt`.
_CONFIG_FILE_NAMES = ("pytest.ini", "pyproject.toml", "tsconfig.json", "CMakeLists.txt")
_CONFIG_FILE_GLOBS = ("jest.config.*",)

# Directories excluded from the language-file walk purely for tractability on
# large repos — `find` in the original fence has no such exclusion, but a
# bounded first-20-hits scan degenerates badly inside dependency/build trees.
# Divergence noted in the port report; behavior on a repo without these dirs
# is identical to the original fence.
_WALK_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

_LANGUAGE_HEAD_LIMIT = 20


def _find_language_files(root: Path) -> list[str]:
    """Mirror `find . -name "*.py" -o ... | head -20`: first N matches, in
    filesystem traversal order, relative to `root`."""
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in sorted(dirnames) if d not in _WALK_EXCLUDE_DIRS]
        for filename in sorted(filenames):
            if filename.endswith(_LANGUAGE_EXTENSIONS):
                rel = os.path.relpath(os.path.join(dirpath, filename), root)
                hits.append(rel.replace(os.sep, "/"))
                if len(hits) >= _LANGUAGE_HEAD_LIMIT:
                    return hits
    return hits


def _find_test_dirs(root: Path) -> list[str]:
    """Mirror `ls -d tests/ __tests__/ spec/ test/ 2>/dev/null`: existing
    directories only, in the original listed order."""
    found = []
    for name in _TEST_DIR_NAMES:
        if (root / name).is_dir():
            found.append(f"{name}/")
    return found


def _find_config_files(root: Path) -> list[str]:
    """Mirror `ls pytest.ini pyproject.toml jest.config.* tsconfig.json
    CMakeLists.txt 2>/dev/null`: existing literal names, plus glob-expanded
    jest.config.* matches, in the original listed order."""
    found = []
    for name in _CONFIG_FILE_NAMES[:2]:  # pytest.ini, pyproject.toml
        if (root / name).is_file():
            found.append(name)
    for pattern in _CONFIG_FILE_GLOBS:  # jest.config.*
        for match in sorted(glob_mod.glob(str(root / pattern))):
            found.append(os.path.relpath(match, root))
    for name in _CONFIG_FILE_NAMES[2:]:  # tsconfig.json, CMakeLists.txt
        if (root / name).is_file():
            found.append(name)
    return found


def _detect_stack(root: Path) -> dict:
    return {
        "root": str(root),
        "language_files": _find_language_files(root),
        "test_dirs": _find_test_dirs(root),
        "config_files": _find_config_files(root),
    }


def cmd_detect_stack(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve() if args.path else Path.cwd()
    if not root.is_dir():
        print(f"bug-sweep-probes detect-stack: not a directory: {root}", file=sys.stderr)
        return 2
    result = _detect_stack(root)
    print(json.dumps(result, indent=2))
    return 0


# ---------------------------------------------------------------------------
# verify-diff — SKILL.md Phase 4 step 0 (mechanical diff gate)
# ---------------------------------------------------------------------------


def _git_diff_name_only(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git diff --name-only failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return [line for line in proc.stdout.splitlines() if line]


def _load_expected_files(fix_now_path: Path) -> list[str]:
    """Mirror `jq -r '.[].file' < phase2-fix-now.json | sort -u`."""
    with fix_now_path.open("r", encoding="utf-8") as fh:
        entries = json.load(fh)
    if not isinstance(entries, list):
        raise ValueError(f"{fix_now_path}: expected a JSON list, got {type(entries).__name__}")
    files = []
    for entry in entries:
        if not isinstance(entry, dict) or "file" not in entry:
            raise ValueError(f"{fix_now_path}: entry missing required 'file' key: {entry!r}")
        files.append(entry["file"])
    return files


def _verify_diff(expected_files: list[str], actual_changed: list[str]) -> list[str]:
    """Mirror `comm -23 <(echo "$EXPECTED_FILES") <(echo "$ACTUAL_CHANGED")`:
    sorted-unique files present in `expected_files` but absent from
    `actual_changed`."""
    expected_set = sorted(set(expected_files))
    actual_set = set(actual_changed)
    return [f for f in expected_set if f not in actual_set]


def cmd_verify_diff(args: argparse.Namespace) -> int:
    fix_now_path = Path(args.fix_now).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()

    if not fix_now_path.is_file():
        print(f"bug-sweep-probes verify-diff: no such file: {fix_now_path}", file=sys.stderr)
        return 2

    try:
        expected_files = _load_expected_files(fix_now_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"bug-sweep-probes verify-diff: {exc}", file=sys.stderr)
        return 2

    try:
        actual_changed = _git_diff_name_only(repo_root)
    except RuntimeError as exc:
        print(f"bug-sweep-probes verify-diff: {exc}", file=sys.stderr)
        return 2

    missing = _verify_diff(expected_files, actual_changed)

    result = {
        "expected_count": len(set(expected_files)),
        "actual_changed_count": len(actual_changed),
        "missing": missing,
    }
    print(json.dumps(result, indent=2))

    if missing:
        print(
            "ALERT: fix-now files with no diff (likely false-positive cohort):",
            file=sys.stderr,
        )
        for path in missing:
            print(path, file=sys.stderr)
        # Informational, not blocking (SKILL.md: "Do not block commit on a
        # non-empty MISSING set") — the calling agent decides whether/how to
        # surface this in the Phase 4 report. Exit 1 signals "alert present"
        # to any automation that wants to branch on it; it is not a failure
        # exit in the pytest/CI sense.
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bug-sweep-probes",
        description="Naked-Python probes ported out of the /bug-sweep skill's inline bash fences.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_detect = sub.add_parser(
        "detect-stack",
        help="Language / test-framework / config-file detection probe (Phase 0 step 1).",
    )
    p_detect.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Directory to scan (default: cwd). Corresponds to the skill's optional scope path.",
    )
    p_detect.set_defaults(func=cmd_detect_stack)

    p_verify = sub.add_parser(
        "verify-diff",
        help="Expected-vs-actual changed-files mechanical diff gate (Phase 4 step 0).",
    )
    p_verify.add_argument(
        "--fix-now",
        required=True,
        help="Path to phase2-fix-now.json (list of {file, ...} objects).",
    )
    p_verify.add_argument(
        "--repo-root",
        default=None,
        help="Repo root to run `git diff --name-only` against (default: cwd).",
    )
    p_verify.set_defaults(func=cmd_verify_diff)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
