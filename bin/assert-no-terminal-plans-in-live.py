# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")

_TERMINAL_PLAN_QUERY_LIMIT = 100000


def _query_terminal_paths() -> list[str]:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from records_query import query_records  # noqa: E402  (sys.path-dependent)

    paths: list[str] = []
    for status in ("implemented", "superseded", "abandoned"):
        result = query_records(
            "plan",
            "status=%s" % status,
            format_="paths",
            limit=_TERMINAL_PLAN_QUERY_LIMIT,
        )
        for line in result.splitlines():
            line = line.strip()
            if line:
                paths.append(line)
    return sorted(set(paths))


def _coordinator_state_root() -> str | None:
    from cc_invoke import _resolve_claude_klabauter_root, ensure_engine_on_path  # noqa: E402

    try:
        _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return None

    ensure_engine_on_path(__file__)

    from coordinator_core.state_root import CrossCuttingStateRoot, StateRootError, coordinator_state_root

    try:
        root = coordinator_state_root()
    except (CrossCuttingStateRoot, StateRootError):
        return None
    return root.strip() or None


def _read_frontmatter_status(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    fence_count = 0
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("---"):
            fence_count += 1
            if fence_count > 1:
                break
            continue
        if fence_count == 1 and stripped.startswith("status:"):
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def _read_full(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def main(argv: list[str]) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path (same

    root = ""
    i = 0
    while i < len(argv):
        if argv[i] == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
        else:
            i += 1

    if not root:
        from cc_invoke import ensure_engine_on_path  # noqa: E402  (sys.path-dependent)

        ensure_engine_on_path(__file__)
        from coordinator_core.git.repo_root import show_toplevel

        root = show_toplevel() or ""

    if not root:
        return 0

    plans_dir = os.path.join(root, "docs", "plans")
    if not os.path.isdir(plans_dir):
        return 0

    records_query_py = os.path.join(_LIB_DIR, "records_query.py")
    if not os.path.isfile(records_query_py):
        print(
            "assert-no-terminal-plans-in-live: records_query.py unavailable "
            "— cannot verify",
            file=sys.stderr,
        )
        return 0

    try:
        term_paths = _query_terminal_paths()
    except Exception as exc:  # noqa: BLE001 — mirrors the bash State-3 hard-error contract
        print(
            "FATAL: assert-no-terminal-plans-in-live: records.query State-3 "
            "hard error (%s) — native engine present-but-broken; aborting to "
            "avoid dead-gate false pass" % exc,
            file=sys.stderr,
        )
        return 3

    if not term_paths:
        print("OK: docs/plans/ contains zero terminal plans")
        return 0

    active_handoff_refs = ""
    state_root = _coordinator_state_root()
    if state_root:
        handoffs_dir = os.path.join(state_root, "handoffs")
        if os.path.isdir(handoffs_dir):
            # coordinator/bin/lib/handoff_lifecycle.py TERMINAL_STATUS constant
            from handoff_lifecycle import TERMINAL_STATUS  # noqa: E402  (sys.path-dependent)

            for name in sorted(os.listdir(handoffs_dir)):
                if not name.endswith(".md"):
                    continue
                hfile = os.path.join(handoffs_dir, name)
                if not os.path.isfile(hfile):
                    continue
                status = _read_frontmatter_status(hfile)
                if status in TERMINAL_STATUS:
                    continue
                active_handoff_refs += "\n" + _read_full(hfile)

    live_plan_refs = ""
    for name in sorted(os.listdir(plans_dir)):
        lfile = os.path.join(plans_dir, name)
        if not os.path.isfile(lfile) or not name.endswith(".md"):
            continue
        stem = name[: -len(".md")]
        if "." in stem:
            continue
        status = _read_frontmatter_status(lfile)
        if status in ("implemented", "superseded", "abandoned"):
            continue
        live_plan_refs += "\n" + _read_full(lfile)

    movable = 0
    for rel in term_paths:
        fname = os.path.basename(rel)
        if fname in active_handoff_refs:
            continue
        if fname in live_plan_refs:
            continue
        movable += 1
        print("MOVABLE terminal plan still in docs/plans/: %s" % fname, file=sys.stderr)

    if movable > 0:
        print(
            "FAIL: %d movable terminal plan(s) in docs/plans/ — "
            "cs_sweep_terminal_plans owes work" % movable,
            file=sys.stderr,
        )
        return 1

    print(
        "OK: no movable terminal plans in docs/plans/ (all remaining "
        "terminal plans are live-ref-held)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
