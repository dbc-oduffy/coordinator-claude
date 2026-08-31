# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-tasks-mirror.py — disk mirror for completeness-checklist items.

Purpose: write and update a per-session YAML mirror of the completeness-checklist
items created by /pickup Step 5.5. The mirror lives at state/tasks/<sid>/<name>.yaml
under the repo root — protected `state/` substrate (NOT bare tasks/, which is swept
aggressively by /distill and /update-docs).

Spec backlink: DoE-claude:pln-ceremony-as-pipeline-2-land-th-aa5ace § C1.2
Negative-spec: This script is ONLY called from within pickup Step 5.5's
completeness_checklist gate. It is NOT called unconditionally; absent
completeness_checklist baton field -> this helper is never invoked.

Usage:
    coordinator-tasks-mirror.py [--repo-root PATH] init <name> <item1_title> [<item2_title>...]
        -- Create the mirror file with all items as open.
           <name>  = sanitized slug for the checklist (used as the yaml filename stem)

    coordinator-tasks-mirror.py [--repo-root PATH] update <name> <item_title> <state>
        -- Update a single item's state in the mirror.
           <state> = open | done

    --repo-root PATH may appear anywhere in argv (before or after the
    positionals) and is stripped before positional parsing. It threads
    through to resolve_checked_repo_root(explicit_root=PATH), returning the
    EXPLICIT verdict — ungated, since a caller-supplied root never touched
    cwd. This is the deliberate-cross-repo escape hatch for a session
    anchored in repo A dispatching a workflow with cwd=<sibling repo B>;
    the MISMATCH gate for the None (cwd-derived) case is untouched.
    Only "--repo-root" is recognized as a flag here -- every other token,
    including one beginning with "-", is left as positional text so a
    free-form title is never misparsed as a flag.

<sid> resolution: coordinator_core.session.core.resolve_session_id(cwd) — tiers
1-3 only, the env ladder the retired bash oracle sourced from
coordinator-session.sh's cs_resolve_session_id:
    Tier 1: $COORDINATOR_SESSION_ID
    Tier 2: $CLAUDE_SESSION_ID
    Tier 3: $CLAUDE_CODE_SESSION_ID

The former Tier 4 (.git/coordinator-sessions/.current-session-id sentinel, plus
its ambiguity guard) was REMOVED from the resolver (KS-4, 2026-08-07): unsound
last-writer-wins under this fleet's concurrency, and its sole writer was deleted
by PM directive. It is documented here because its absence is load-bearing for
this script's cross-repo arm: the resolver reads env vars ONLY and ignores the
`cwd` it is handed (retained for API compatibility), so nothing about where this
script runs can influence which session its journal is filed under. There is no
cwd-derived tier left to mis-attribute through. An unresolvable sid returns ""
and this script refuses — never guesses.

Verified 2026-08-30 against the live cross-repo caller (klabauter `candidate`
@ e959b4ef0d, `workflow_fire/fire.py`): `build_fire_env` inherits the parent
environment and never narrows it, and the fired driver's harness always
populates CLAUDE_CODE_SESSION_ID with its OWN id, so tier 3 hits
unconditionally on that path. Note also that `workflow.fire`'s `cwd` argument
is never passed to Popen — the driver's process cwd is the FIRING repo, not
the sibling the work targets. That is precisely why --repo-root has to be
stated explicitly here: there is no correct root to infer from cwd.

Windows de-bash campaign (Plan C, Wave E3-d, per-op port): replaces the bash helper
bin/coordinator-tasks-mirror.sh, which sourced coordinator/lib/coordinator-claude-klabauter-root.sh
+ coordinator/lib/resolve-python.sh to build a local coordinator_trusted_root_guard
shell shim (a `python -c` subprocess dispatching coordinator_core.trusted_root_guard),
then sourced coordinator/lib/coordinator-session.sh itself just to reach
cs_resolve_session_id. Fix-in-port (DR-059): the coordinator-root resolution +
trusted-root-guard dance existed ONLY as bash's mechanism for safely `source`-ing a
sibling script — it is not needed here. This port imports
coordinator_core.session.core.resolve_session_id directly (via
cc_invoke.resolve_engine_root() for engine-root resolution — self-location-first,
so this co-located script finds its own checkout even on an install whose
machine-local registry was never populated — matching every other
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
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_session_id(cwd: str) -> str:
    """Import + call coordinator_core.session.core.resolve_session_id(cwd).

    Raises RuntimeError on engine-root/import failure (caller maps to exit 1,
    matching the bash oracle's fail-loud coordinator-root-unresolved path).
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.session.core import resolve_session_id as _resolve

    return _resolve(cwd)


def _resolve_repo_root(explicit_root: str | None = None) -> tuple[str | None, str | None]:
    """Resolve the target repo root via the checked resolver.

    WRITER script: this entry writes state/tasks/<sid>/<slug>.yaml under the
    resolved repo. Returns (root, mismatch_message) — on a positive
    MISMATCH, root is None and mismatch_message carries the refusal text
    (DR-277 carve-out: prevents a write into a foreign tree). UNRESOLVED
    never refuses (DR-277, AC4).

    explicit_root: when set (from a caller-supplied --repo-root), passed
    straight through as resolve_checked_repo_root(explicit_root=...),
    which returns the EXPLICIT verdict and is never gated by MISMATCH —
    a caller-supplied root never touched cwd, so the cwd-drift-vs-
    deliberate-cross-repo ambiguity the MISMATCH gate exists for does not
    apply. The None (cwd-derived) arm's MISMATCH/no-git-root/UNRESOLVED
    behaviour is unchanged.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from repo_identity import resolve_checked_repo_root

    root, verdict = resolve_checked_repo_root(explicit_root=explicit_root)
    if verdict["verdict"] == "MISMATCH":
        return None, verdict["message"]
    if not root:
        # No git root resolved from cwd at all -- distinct from the
        # MISMATCH identity gate above (positive evidence of a DIFFERENT
        # real repo). This is "nowhere to write"; refusing at the call
        # site below is not the AC4 "UNRESOLVED never refuses" carve-out
        # being violated. mismatch_message stays None so the caller prints
        # its own generic no-repo message rather than a MISMATCH string.
        return None, None
    return root, None


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
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
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
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
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


def _extract_repo_root_flag(args: list[str]) -> tuple[list[str], str | None, str | None]:
    """Strip a `--repo-root PATH` flag out of args wherever it appears.

    Only the literal token "--repo-root" is treated as a flag; every other
    token — including one starting with "-" — is left untouched in the
    returned positional list, so a free-form title beginning with "-" is
    never swallowed as an unrecognized flag.

    Returns (remaining_positional_args, repo_root_or_None, error_or_None).
    On error, remaining_positional_args and repo_root_or_None are
    meaningless and the caller must print error_or_None to stderr and exit 1.
    """
    out: list[str] = []
    repo_root: str | None = None
    i = 0
    n = len(args)
    while i < n:
        arg = args[i]
        if arg == "--repo-root":
            if i + 1 >= n:
                return [], None, "ERROR: --repo-root requires a value"
            repo_root = args[i + 1]
            i += 2
            continue
        out.append(arg)
        i += 1
    return out, repo_root, None


def main(argv: list[str]) -> int:
    raw_args = argv[1:]
    args, explicit_repo_root, flag_error = _extract_repo_root_flag(raw_args)
    if flag_error is not None:
        print(flag_error, file=sys.stderr)
        return 1

    if len(args) < 2:
        print("Usage: coordinator-tasks-mirror.py [--repo-root PATH] init <name> [<title>...]", file=sys.stderr)
        print("       coordinator-tasks-mirror.py [--repo-root PATH] update <name> <title> <state>", file=sys.stderr)
        return 1

    cmd, name = args[0], args[1]

    repo_root, mismatch_message = _resolve_repo_root(explicit_repo_root)
    if repo_root is None:
        if mismatch_message:
            print(mismatch_message, file=sys.stderr)
        else:
            print("ERROR: not inside a git repo; cannot resolve state/ path.", file=sys.stderr)
        return 1

    try:
        sid = _resolve_session_id(os.getcwd())
    except RuntimeError as exc:
        print(f"ERROR: could not resolve the engine root: {exc}", file=sys.stderr)
        return 1

    if not sid:
        print("ERROR: could not resolve session id; $COORDINATOR_SESSION_ID, $CLAUDE_SESSION_ID and $CLAUDE_CODE_SESSION_ID are all empty.", file=sys.stderr)
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
