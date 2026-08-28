# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""assert-no-terminal-plans-in-live.py — AC6 gate for programmatic terminal-plan archival.

Asserts that NO *movable* terminal plan remains in docs/plans/ — i.e. running
cs_sweep_terminal_plans would move zero files. A terminal plan
(status in {implemented, superseded, abandoned}) is allowed to remain in
docs/plans/ ONLY when it is legitimately HELD by a live reference:
  - an active (non-consumed/superseded) handoff in state/handoffs/, or
  - a live (non-terminal) plan body in docs/plans/.

Why "movable", not "zero terminal plans": the sweep deliberately skips
terminal plans cited by live work (cleanup-sweep-hazards §1 — don't bury an
in-flight thread's referenced plan). Most shipped plans stay cited by some
live plan for a while, so a literal zero-terminal-plans assertion would be
permanently red. The operative invariant the sweep CAN guarantee is "nothing
left that the sweep should have moved" — which is exactly what regressed when
review sidecars were mis-counted as live plans (sidecar-self-hold bug).

This predicate MIRRORS the sweep in coordinator/bin/sweep-terminal-plans.py:
three-status enum via query-records, active-handoff skip, live-plan skip with
review sidecars excluded. Keep the two in sync.

Spec backlink: docs/plans/2026-06-23-programmatic-terminal-plan-archival.md § AC6 / C4.
Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § E3-b

Usage:   assert-no-terminal-plans-in-live.py [--root <dir>]
Exit:    0 = no movable terminal plan remains; 1 = >=1 movable (sweep owes work).
         3 = records.query State-3 hard error (native engine present-but-broken).
"""
from __future__ import annotations

import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")

# records.query defaults --limit 50. Claude-klabauter has ~158 terminal plans, so a
# per-status cap of 50 would make this assert see only a subset — a latent
# dead-gate. Pass a high sentinel to uncap. NOT 0: the claude-klabauter op treats 0 as
# zero-records, not unlimited.
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
    from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return None

    env = dict(os.environ)
    pythonpath = env.get("PYTHONPATH", "")
    sep = ";" if os.name == "nt" else ":"
    env["PYTHONPATH"] = claude_klabauter_root + (sep + pythonpath if pythonpath else "")

    # `claude_klabauter_root` above only reaches the CHILD subprocess's env
    # (PYTHONPATH) -- this process's own `sys.path` never got it, so the
    # coordinator_core import below died on a mirror checkout where
    # coordinator_core isn't pip-installed. `ensure_engine_on_path` puts it
    # on THIS process's sys.path too.
    from cc_invoke import ensure_engine_on_path

    ensure_engine_on_path(__file__)

    from coordinator_core.win_portability import no_console_creationflags

    proc = subprocess.run(
        [sys.executable, "-m", "coordinator_core.state_root"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        **no_console_creationflags(),
    )
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return root or None


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
        return 0  # non-git consumer: no-op pass

    plans_dir = os.path.join(root, "docs", "plans")
    if not os.path.isdir(plans_dir):
        return 0  # no plans dir: no-op pass

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
            # DR-084: status: consumed -> status: claimed. P0 additive widen —
            # accept both vocabularies while the on-disk corpus is mixed, so a
            # handoff already migrated to `claimed` isn't misread as active and
            # spuriously counted as a live-ref hold. Sourced from the shared
            # coordinator/bin/lib/handoff_lifecycle.py TERMINAL_STATUS constant
            # (mirrors coordinator/bin/lib/consumed-marker.js's set of the same
            # name on the JS side) rather than a locally re-declared literal —
            # this file previously carried its own hardcoded tuple here, which
            # is exactly the per-caller-drift shape the shared accessor exists
            # to close.
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
            continue  # sidecar, not a plan
        status = _read_frontmatter_status(lfile)
        if status in ("implemented", "superseded", "abandoned"):
            continue
        live_plan_refs += "\n" + _read_full(lfile)

    movable = 0
    for rel in term_paths:
        fname = os.path.basename(rel)
        if fname in active_handoff_refs:
            continue  # held by handoff
        if fname in live_plan_refs:
            continue  # held by live plan
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
