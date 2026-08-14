"""bin/check-machine-path-leak.py — Tripwire: prevent machine-specific absolute paths
from being committed into tracked configuration files.

Purpose: Guards against the "thislaptop leak" pattern — where a developer's local home
directory or drive-letter path lands in tracked settings.json (directory-source
marketplace entries, mcpServers paths, etc.) or working-repos.yaml (repo catalog paths).
These paths are machine-specific and must live in gitignored per-machine files, not in
the shared tracked tree.

Severity contract:
    settings.json  — HARD block. Any machine-absolute-path leaf value → exit 1.
    working-repos.yaml — SOFT warn. Current-machine $HOME-rooted paths → stderr WARN,
                         exit 0. Foreign machine paths (X:\\, E:\\, /Users/other/) are
                         intentional catalog content and are NOT flagged.

Negative-spec (hard-won):
    - Does NOT grep raw file text — structural JSON/YAML parsing only. Text-grep
      false-positives on fixtures, commit-message args, and comment blocks.
    - Does NOT flag X:\\, E:\\, or /Users/<other>/ paths in working-repos.yaml — those
      are documented cross-machine catalog content and must stay in the file.
    - Only flags paths rooted at the CURRENT machine's $HOME in working-repos.yaml.
    - settings.json is always a hard block regardless of path origin.

Windows de-bash (2026-07-19): this is the native-Python successor to the former
check-machine-path-leak.sh bash tool. Git-repo discovery and JSON/YAML structural
scanning are equally natural in Python and this collapses the two embedded `python3 -c`
subprocess hops that the bash version needed to zero. No shell is on the critical path —
the only subprocess spawns are to `git` (a native binary present on every supported
platform), used solely to read staged content when a file is not on disk.

Spec backlink: docs/plans/2026-06-23-machine-path-leak-guard.md [DEAD-CITATION: plan file never committed to this repo]
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md

Usage:
    check-machine-path-leak.py [--staged] [<file> ...]

    --staged       Read staged file list from `git diff --cached --name-only` and
                   inspect any settings.json or working-repos.yaml in that list.
                   (default when no file arguments are given)
    <file> ...     Explicit file path(s) to inspect. Useful for CI or ad-hoc checks.

Exit codes:
    0 — OK (no hard violations; soft warns printed to stderr but do not fail)
    1 — VIOLATION: settings.json contains a machine-specific absolute path leaf value
    2 — ERROR: unexpected failure (not a git repo, bad argument, etc.)

Output:
    stdout — human-readable status lines
    stderr — violation details and error messages

Environment:
    HOME  — used to determine the current machine's home directory for working-repos.yaml
             soft-warn matching. Falls back to os.path.expanduser("~") when unset (honors
             Windows USERPROFILE) so the soft-warn does not silently no-op off-POSIX.
"""

import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Machine-absolute-path patterns for the settings.json HARD block.
#
#   ^/Users/<name>/    macOS home
#   ^/home/<name>/     Linux home
#   ^C:[/\]Users[/\]   Windows C:\Users\
#   ^X:[/\]            cross-machine catalog X:\ drive
#   ^E:[/\]            cross-machine catalog E:\ dev drive
# ---------------------------------------------------------------------------

_SETTINGS_PATTERNS = [
    re.compile(r"^/Users/[^/]+/"),
    re.compile(r"^/home/[^/]+/"),
    re.compile(r"^C:[/\\]Users[/\\]"),
    re.compile(r"^X:[/\\]"),
    re.compile(r"^E:[/\\]"),
]

PROG = "check-machine-path-leak.py"


def _is_machine_abs(val):
    return any(p.search(val) for p in _SETTINGS_PATTERNS)


def _git(args):
    """Run a read-only git command, returning (returncode, stdout_text).

    git is a native binary on every supported platform; this is NOT a shell spawn.
    """
    try:
        proc = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return proc.returncode, proc.stdout
    except (OSError, ValueError):
        return 127, ""


def _in_git_repo():
    rc, _ = _git(["rev-parse", "--git-dir"])
    return rc == 0


def _read_file_or_index(path):
    """Return file content, reading from disk if present else the git index.

    Returns None when the file is neither on disk nor in the index (caller skips).
    """
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if _in_git_repo():
        rc, out = _git(["show", ":{}".format(path)])
        if rc == 0:
            return out
        # Deleted from index — nothing to check.
        return None
    sys.stderr.write("{}: WARN — {} not found on disk\n".format(PROG, path))
    return None


# ---------------------------------------------------------------------------
# JSON structural scan — collect leaf string values matching a machine-abs path.
# ---------------------------------------------------------------------------

def _walk_json(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = (path + "." + k) if path else k
            yield from _walk_json(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_json(v, path + "[" + str(i) + "]")
    elif isinstance(obj, str):
        if _is_machine_abs(obj):
            yield (path, obj)


def _check_settings_json(file, state):
    """HARD block. Any machine-absolute-path leaf value in settings.json → violation."""
    import json

    content = _read_file_or_index(file)
    if content is None:
        return

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        sys.stderr.write(
            "{}: ERROR — failed to parse {} as JSON: {}\n".format(PROG, file, e)
        )
        state["hard_violation"] = True
        return

    for leaf_path, leaf_val in _walk_json(data):
        sys.stderr.write(
            "VIOLATION: {}: machine-specific path in JSON leaf\n".format(file)
        )
        sys.stderr.write("  Leaf path : {}\n".format(leaf_path))
        sys.stderr.write("  Value     : {}\n".format(leaf_val))
        sys.stderr.write("  Remedy    : machine-specific paths must live in gitignored\n")
        sys.stderr.write("              settings.local.json or machine-local registry,\n")
        sys.stderr.write("              not in tracked settings.json\n")
        state["hard_violation"] = True


# ---------------------------------------------------------------------------
# YAML structural scan — collect leaf string values rooted at CURRENT_HOME only.
#
# X:\, E:\, and /Users/<other>/ are intentional cross-machine catalog content and
# must NOT be flagged here. When PyYAML is unavailable, fall back to a conservative
# line-scan that only flags a leaf VALUE starting with $HOME.
# ---------------------------------------------------------------------------

def _walk_yaml(obj, current_home, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = (path + "." + str(k)) if path else str(k)
            yield from _walk_yaml(v, current_home, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_yaml(v, current_home, path + "[" + str(i) + "]")
    elif isinstance(obj, str):
        if current_home and obj.startswith(current_home):
            yield (path, obj)


def _emit_yaml_warn(file, leaf_path, leaf_val):
    sys.stderr.write(
        "WARN: {}: leaf '{}' contains current-machine home-rooted path\n".format(
            file, leaf_path
        )
    )
    sys.stderr.write("  Value : {}\n".format(leaf_val))
    sys.stderr.write("  Note  : If this is an intentional catalog entry, no action needed.\n")
    sys.stderr.write("          If newly introduced, consider moving to machine-local registry.\n")


def _check_working_repos_yaml(file, current_home):
    """SOFT warn. Current-machine $HOME-rooted leaf values in working-repos.yaml."""
    content = _read_file_or_index(file)
    if content is None:
        return

    try:
        import yaml
    except ImportError:
        _check_working_repos_yaml_linescan(file, content, current_home)
        return

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError:
        sys.stderr.write(
            "{}: WARN — could not parse {} as YAML; skipping soft check\n".format(PROG, file)
        )
        return

    if data is None:
        return

    for leaf_path, leaf_val in _walk_yaml(data, current_home):
        _emit_yaml_warn(file, leaf_path, leaf_val)


def _check_working_repos_yaml_linescan(file, content, current_home):
    """Fallback conservative line-scan when PyYAML is absent.

    Only flags lines whose VALUE portion starts with $CURRENT_HOME. Foreign-machine
    paths (X:\\, /Users/other/) are skipped — intentional cross-machine catalog.
    Limitation: multiline/next-line YAML values are missed by this scan.
    """
    if not current_home:
        return
    sys.stderr.write("WARN: PyYAML absent — working-repos.yaml leak check is best-effort\n")

    list_re = re.compile(r"^\s*-\s+(.*)")
    kv_re = re.compile(r":\s+(.*)")

    for lineno, line in enumerate(content.splitlines(), start=1):
        value_part = ""
        m = list_re.match(line)
        if m:
            value_part = m.group(1)
        else:
            m = kv_re.search(line)
            if m:
                value_part = m.group(1)
        # Strip inline comments and surrounding quotes.
        value_part = value_part.split("#", 1)[0]
        value_part = value_part.strip()
        if len(value_part) >= 2 and value_part[0] == value_part[-1] and value_part[0] in ("'", '"'):
            value_part = value_part[1:-1]

        if value_part and value_part.startswith(current_home):
            sys.stderr.write(
                "WARN: {}:{}: current-machine home-rooted path: {}\n".format(
                    file, lineno, value_part
                )
            )
            sys.stderr.write("  Note  : If this is an intentional catalog entry, no action needed.\n")
            sys.stderr.write("          If newly introduced, consider moving to machine-local registry.\n")


# ---------------------------------------------------------------------------
# Argument parsing + candidate collection.
# ---------------------------------------------------------------------------

def _print_help():
    sys.stdout.write(__doc__.strip() + "\n")


def main(argv):
    mode = "staged"
    explicit_files = []

    for arg in argv:
        if arg == "--staged":
            mode = "staged"
        elif arg in ("-h", "--help"):
            _print_help()
            return 0
        elif arg.startswith("-"):
            sys.stderr.write("{}: unknown argument: {}\n".format(PROG, arg))
            return 2
        else:
            explicit_files.append(arg)
            mode = "explicit"

    settings_files = []
    working_repos_files = []

    def collect(f):
        base = os.path.basename(f)
        if base == "settings.json":
            settings_files.append(f)
        elif base == "working-repos.yaml":
            working_repos_files.append(f)

    if mode == "staged":
        if not _in_git_repo():
            sys.stderr.write("{}: ERROR — not a git repository\n".format(PROG))
            return 2
        rc, out = _git(["diff", "--cached", "--name-only"])
        for line in out.splitlines():
            if line.strip():
                collect(line)
    else:
        for f in explicit_files:
            collect(f)

    state = {"hard_violation": False}

    for sf in settings_files:
        _check_settings_json(sf, state)

    # Review: code-reviewer — F4: $HOME is POSIX-only; stock Windows (cmd.exe/
    # PowerShell without Git Bash/WSL) doesn't set it — falls back to os.path.expanduser
    # (which honors USERPROFILE on Windows) instead of silently no-oping the soft-warn.
    current_home = os.environ.get("HOME") or os.path.expanduser("~")
    for wf in working_repos_files:
        _check_working_repos_yaml(wf, current_home)

    total = len(settings_files) + len(working_repos_files)
    if total == 0:
        sys.stdout.write("OK: no settings.json or working-repos.yaml in scope — nothing to check\n")
        return 0

    if state["hard_violation"]:
        sys.stderr.write("BLOCKED: machine-path leak detected — commit rejected\n")
        return 1

    sys.stdout.write("OK: no machine-path leaks detected in {} file(s)\n".format(total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
