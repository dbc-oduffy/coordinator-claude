#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-tasks-mirror.py — disk mirror for completeness-checklist items.

Purpose: write and update a per-session YAML mirror of the completeness-checklist
items created by /pickup Step 5.5. The mirror lives at state/tasks/<sid>/<name>.yaml
under the repo root — protected `state/` substrate (NOT bare tasks/, which is swept
aggressively by /distill and /update-docs).

Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C1.2
Negative-spec: This script is ONLY called from within pickup Step 5.5's
completeness_checklist gate. It is NOT called unconditionally; absent
completeness_checklist baton field -> this helper is never invoked.

Usage:
    coordinator-tasks-mirror.py init <name> <item1_title> [<item2_title>...]
        -- Create the mirror file with all items as open.
           <name>  = sanitized slug for the checklist (used as the yaml filename stem)

    coordinator-tasks-mirror.py update <name> <item_title> <state>
        -- Update a single item's state in the mirror.
           <state> = open | done

<sid> resolution: coordinator_core.session.core.resolve_session_id(cwd) — the same
canonical 4-tier chain the retired bash oracle sourced from coordinator-session.sh's
cs_resolve_session_id:
    Tier 1: $COORDINATOR_SESSION_ID
    Tier 2: $CLAUDE_SESSION_ID
    Tier 3: $CLAUDE_CODE_SESSION_ID
    Tier 4: .git/coordinator-sessions/.current-session-id (ambiguity-aware)

Windows de-bash campaign (Plan C, Wave E3-d, per-op port): replaces the bash helper
bin/coordinator-tasks-mirror.sh, which sourced coordinator/lib/coordinator-claude-klabauter-root.sh
+ coordinator/lib/resolve-python.sh to build a local coordinator_trusted_root_guard
shell shim (a `python -c` subprocess dispatching coordinator_core.trusted_root_guard),
then sourced coordinator/lib/coordinator-session.sh itself just to reach
cs_resolve_session_id. Fix-in-port (DR-059): the coordinator-root resolution +
trusted-root-guard dance existed ONLY as bash's mechanism for safely `source`-ing a
sibling script — it is not needed here. This port imports
coordinator_core.session.core.resolve_session_id directly (via
cc_invoke._resolve_claude_klabauter_root() for CLAUDE_KLABAUTER_ROOT resolution, matching every other
Windows-campaign per-op port) — no bash-source chain, no coordinator-root trust check,
one fewer subprocess than the bash oracle's shell-wrapping-python shape.

Output path: <repo-root>/state/tasks/<sid>/<slug>.yaml where <slug> is <name> sanitized
to [a-zA-Z0-9_-]+. The file is created if absent; updated atomically if already present.

Exit codes:
    0  -- success
    1  -- usage / resolution error (message on stderr)

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Plan C, Wave E3-d)
"""
from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402

# Windows: suppresses the console popup a subprocess.run(...) would otherwise
# trigger under the headless Claude Code Bash-tool parent. No-op (0) elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _resolve_session_id(cwd: str) -> str:
    """Import + call coordinator_core.session.core.resolve_session_id(cwd).

    Raises RuntimeError on CLAUDE_KLABAUTER_ROOT/import failure (caller maps to exit 1,
    matching the bash oracle's fail-loud coordinator-root-unresolved path).
    """
    claude_klabauter_root = cc_invoke._resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.session.core import resolve_session_id as _resolve

    return _resolve(cwd)


def _resolve_repo_root() -> str | None:
    """Resolve the current git worktree root from PWD (no shell)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    root = result.stdout.strip()
    if result.returncode != 0 or not root:
        return None
    return root


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _yaml_escape_scalar(v: str) -> str:
    """Emit a single-quoted YAML scalar value (safe for arbitrary strings)."""
    return "'" + v.replace("'", "''") + "'"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
    slug = slug.strip("-")
    if not slug:
        # F6 parity: a degenerate all-punctuation name (e.g. "!!!") strips to
        # empty or a bare "-" — fall back to the default slug.
        slug = "completeness-checklist"
    return slug


def _mirror_paths(repo_root: str, sid: str, name: str) -> tuple[str, str]:
    slug = _slugify(name)
    mirror_dir = os.path.join(repo_root, "state", "tasks", sid)
    mirror_file = os.path.join(mirror_dir, f"{slug}.yaml")
    return mirror_dir, mirror_file


def cmd_init(repo_root: str, sid: str, name: str, titles: list[str]) -> int:
    mirror_dir, mirror_file = _mirror_paths(repo_root, sid, name)
    os.makedirs(mirror_dir, exist_ok=True)

    now = _now_iso()
    lines = [
        "# completeness-checklist mirror — managed by coordinator-tasks-mirror.py",
        "# Spec: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § C1.2",
        "# state/tasks/<sid>/ is protected substrate (never bare tasks/ — DR-173)",
        "#",
        "schema: completeness-checklist-mirror-v1",
        f"sid: {_yaml_escape_scalar(sid)}",
        f"created_at: {now}",
        f"updated_at: {now}",
        "items:",
    ]
    for t in titles:
        lines.append(f"  - title: {_yaml_escape_scalar(t)}")
        lines.append("    state: open")
        lines.append(f"    updated_at: {now}")

    tmp_path = mirror_file + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp_path, mirror_file)

    print(f"mirror: wrote {mirror_file} ({len(titles)} items)")
    return 0


def cmd_update(repo_root: str, sid: str, name: str, title: str, state: str) -> int:
    if state not in ("open", "done"):
        print(f"ERROR: state must be 'open' or 'done', got '{state}'", file=sys.stderr)
        return 1

    _mirror_dir, mirror_file = _mirror_paths(repo_root, sid, name)
    if not os.path.isfile(mirror_file):
        print(
            f"ERROR: mirror file not found at {mirror_file} — call 'init' first.",
            file=sys.stderr,
        )
        return 1

    now = _now_iso()
    escaped_title = _yaml_escape_scalar(title)
    item_header = f"  - title: {escaped_title}"

    with open(mirror_file, "r", encoding="utf-8") as f:
        raw_lines = f.read().splitlines()

    out_lines: list[str] = []
    found = False
    in_matching_item = False
    for line in raw_lines:
        if line == item_header:
            in_matching_item = True
            found = True
            out_lines.append(line)
            continue

        if in_matching_item and re.match(r"^[ \t]+state:", line):
            out_lines.append(f"    state: {state}")
            continue

        if in_matching_item and re.match(r"^[ \t]+updated_at:", line):
            out_lines.append(f"    updated_at: {now}")
            in_matching_item = False  # reset after last per-item field we mutate
            continue

        if in_matching_item and (re.match(r"^[ \t]*-[ \t]", line) or re.match(r"^\S", line)):
            in_matching_item = False

        out_lines.append(line)

    # Also update the top-level updated_at timestamp.
    for i, line in enumerate(out_lines):
        if line.startswith("updated_at:"):
            out_lines[i] = f"updated_at: {now}"

    tmp_path = mirror_file + ".update.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    os.replace(tmp_path, mirror_file)

    if not found:
        print(
            f"WARN: item title not found in mirror — no update applied. Title: {title}",
            file=sys.stderr,
        )
        # F2 parity: exit 1 (not 0) so callers using $? can distinguish
        # "update applied" from "title not found" — a silent 0 leaves the
        # disk mirror out of sync with the Task state.
        return 1

    print(f"mirror: updated '{title}' -> {state} in {mirror_file}")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if len(args) < 2:
        print("Usage: coordinator-tasks-mirror.py init <name> [<title>...]", file=sys.stderr)
        print("       coordinator-tasks-mirror.py update <name> <title> <state>", file=sys.stderr)
        return 1

    cmd, name = args[0], args[1]

    repo_root = _resolve_repo_root()
    if repo_root is None:
        print("ERROR: not inside a git repo; cannot resolve state/ path.", file=sys.stderr)
        return 1

    try:
        sid = _resolve_session_id(os.getcwd())
    except RuntimeError as exc:
        print(f"ERROR: could not resolve CLAUDE_KLABAUTER_ROOT: {exc}", file=sys.stderr)
        return 1

    if not sid:
        print("ERROR: could not resolve session id (all 4 tiers empty/ambiguous).", file=sys.stderr)
        print("Set COORDINATOR_SESSION_ID to an explicit value and retry.", file=sys.stderr)
        return 1

    if cmd == "init":
        titles = args[2:]
        return cmd_init(repo_root, sid, name, titles)

    if cmd == "update":
        if len(args) < 4:
            print("Usage: coordinator-tasks-mirror.py update <name> <title> <state>", file=sys.stderr)
            return 1
        title, state = args[2], args[3]
        return cmd_update(repo_root, sid, name, title, state)

    print(f"ERROR: unknown subcommand '{cmd}'. Expected: init | update", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
