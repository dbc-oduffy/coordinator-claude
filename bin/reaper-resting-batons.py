"""reaper-resting-batons.py — read-only surfacing pass for `open`/`ready_to_fire`
resting handoff batons.

Purpose (sedge-19, "Resting batons no reaper covers"): all existing
reaper/sweep passes (`sweep-shipped-handoffs.py`,
`handoff-gate-aging`, `reap-orphaned-in-flight-handoffs.py`, `baton-drift-sweep.py`)
start their own selection predicate from `status: consumed` or a terminal
`deployment_state` (verified by reading each one's own module docstring/scope
statement, not the research consult's summary — see
state/roadmap/sedge-2026-08-06/research-corpus/writer-and-referent-shape.md §
Cluster 21). None names `status: open` + `deployment_state: ready_to_fire` in
scope, so that population — a legitimately machine-written resting-baton set,
not a bug or an orphan — sits invisible to every existing sweep. This script
composes with, and does not replace, any of them; it adds a new, additive
surfacing leg alongside them.

Delivery-shape choice (open per the OVERVIEW's Contested block, this stub's
implementer's call to make): standalone CLI, invoked on demand — same posture
as `coordinator_core.ops.cascade_backstop_sweep` ("reports, never flips"), not
wired into any auto-firing hook, cron, or commit-path trigger. Chosen over a
new ceremony leg because a new leg would touch `workday-start`/
`workday-complete` wiring outside this stub's declared scope
(`coordinator/bin/reaper-*`, `coordinator/bin/sweep-*`,
`coordinator/bin/handoff-gate-aging`, `coordinator/bin/baton-drift-sweep.py`,
`state/audits/*resting-batons*`); an operator or a ceremony can still shell out
to this CLI on whatever cadence it likes without this script itself owning
that wiring.

NEGATIVE-SPEC (read-only, load-bearing):
  - Does NOT write, anywhere, under any code path — no `Write`, no git-mv, no
    frontmatter mutation, no archive move. Grep this file for "open(" / "write"
    / "git mv" / "git-mv" to confirm: the only file I/O is `Path.read_bytes()`
    via `coordinator_core.dag.read_handoff_meta` (the public alias for
    `_read_meta`, a cached frontmatter reader shared
    with the rest of the fleet, itself read-only) and this script's own
    `print()` to stdout.
  - Does NOT claim, close, archive, or otherwise mutate any record it surfaces
    — visibility only, matching `cascade_backstop_sweep.py`'s posture.
  - Does NOT modify any of the five existing reapers' own selection predicates
    — this is a new, additive pass, never a change to an existing one.
  - Does NOT propose adding `crashed`/`orphaned` (or any new value) to
    `handoff.closed_reason`'s enum — that enum's omission of those terms is
    the ratified posture this pass must not disturb (see this stub's handoff,
    "Constraint carried forward, load-bearing").
  - Does NOT assert whether this repo's resting-share proportion versus DoE's
    fleet-combined figure reflects a population split or an authoring-cadence
    difference — flagged unresolved upstream, not re-settled here (see this
    stub's handoff, "Residual measurement gap").

Scan population: every `state/handoffs/*.md` (live tree only — an
already-archived record is out of scope for this pass by construction; this
mirrors `sweep-*`'s own live-tree-only scope, not `cascade_backstop_sweep`'s
wider archive+live join, since a resting baton by definition has not yet been
archived) whose frontmatter carries BOTH `status: open` AND
`deployment_state: ready_to_fire`. Age is `today - created` in whole days,
using the record's own `created:` frontmatter date; a record missing/
unparseable `created:` reports `age_days=unknown` rather than being silently
dropped (a resting baton must still surface even if its age can't be computed).

Usage:
    python3 reaper-resting-batons.py [<repo_root>]

    <repo_root>  Optional; defaults to `git rev-parse --show-toplevel` from cwd.

Stdout contract: a `#`-prefixed, machine-skippable header (`generated_at=` UTC
timestamp, then the regenerate command), followed by one line per surfaced
record (`<id> age_days=<n> path=<relpath>`), sorted oldest-first (missing-age
records last, id-sorted), followed by a `total=<n>` summary line —
diffable/inspectable, never a bare swallowed count.

Exit codes:
    0 — normal completion (including zero surfaced records — a clean sweep,
        not a degenerate one; this is a report, not a pass/fail gate).
    2 — repo-root unresolvable.

Spec backlink: state/handoffs/2026-08-06_170019_roadmap-sedge-19.md
"""
from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path


def _bootstrap_engine_root() -> None:
    """Put the engine root on `sys.path` before any `coordinator_core`
    import — same idiom as the sweep's other 8 fixed CLIs
    (`resolve_engine_root(__file__)` via the colocated `cc_invoke`), so
    the mirror case (`coordinator_core` not pip-installed, `sys.path[0]`
    is this file's own `bin/`) resolves rather than silently degrading.
    Best-effort: `cc_invoke` itself, or engine-root resolution, failing
    is left to the caller's own except clause to handle.
    """
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    lib_dir = os.path.join(bin_dir, "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)


def _no_console_creationflags() -> dict:
    # Review: coordinator:code-reviewer — `no_console_creationflags` is
    # always importable (POSIX and Windows alike; see
    # coordinator_core/win_portability.py's own docstring), so an import
    # failure here is never a legitimate "absent on non-Windows installs"
    # case — it is the mirror's unresolved-engine-root case, the exact
    # defect class this file's docstring names. Bootstrap first so that
    # case resolves instead of silently degrading to `{}`.
    try:
        _bootstrap_engine_root()
        from coordinator_core.win_portability import no_console_creationflags
        return no_console_creationflags()
    except Exception:  # noqa: BLE001 — best-effort helper; caller still runs
        return {}


def _resolve_repo_root(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        _bootstrap_engine_root()
        from coordinator_core.git.repo_root import show_toplevel

        return show_toplevel(cwd=os.getcwd())
    except Exception:  # noqa: BLE001 — mirrors `_no_console_creationflags`'s
        # best-effort bootstrap posture; an unresolvable engine root here
        # degrades to None (caller reports "cannot resolve"), not a raise.
        return None


def _import_read_meta():
    # Review: coordinator:code-reviewer — was its own ad hoc partial
    # bootstrap (the older private `cc_invoke._resolve_claude_klabauter_root`,
    # exception-swallowed on resolution only), now the same
    # `resolve_engine_root` idiom `_no_console_creationflags` and the
    # sweep's other 8 fixed CLIs use, so this file carries one bootstrap
    # strategy, not two. `read_handoff_meta` itself stays unwrapped: an
    # unresolvable engine root here is genuinely fatal (there's nothing
    # this script can report without it), so it should raise loud, not
    # degrade silently — see `main`'s caller, which lets it propagate.
    try:
        _bootstrap_engine_root()
    except Exception:  # noqa: BLE001 — fall through to a bare import attempt
        pass
    from coordinator_core.dag import read_handoff_meta
    return read_handoff_meta


def _age_days(created: object) -> int | None:
    """`created:` may already be a YAML-parsed date/datetime, or a plain
    string — best-effort parse either shape; unparseable returns None."""
    if isinstance(created, datetime.datetime):
        created_date = created.date()
    elif isinstance(created, datetime.date):
        created_date = created
    elif isinstance(created, str):
        try:
            created_date = datetime.date.fromisoformat(created.strip()[:10])
        except ValueError:
            return None
    else:
        return None
    return (datetime.date.today() - created_date).days


def scan(repo_root: Path, read_meta) -> list[dict]:
    """Read-only scan of state/handoffs/*.md for status:open +
    deployment_state:ready_to_fire. No write of any kind — see module
    NEGATIVE-SPEC."""
    handoffs_dir = repo_root / "state" / "handoffs"
    surfaced: list[dict] = []
    if not handoffs_dir.is_dir():
        return surfaced
    for path in sorted(handoffs_dir.glob("*.md")):
        fm = read_meta(str(path))
        if not fm:
            continue
        if fm.get("status") != "open":
            continue
        if fm.get("deployment_state") != "ready_to_fire":
            continue
        rel = path.relative_to(repo_root).as_posix()
        surfaced.append({
            "id": path.stem,
            "path": rel,
            "age_days": _age_days(fm.get("created")),
        })
    surfaced.sort(key=lambda r: (r["age_days"] is None, -(r["age_days"] or 0), r["id"]))
    return surfaced


def main(argv: list[str]) -> int:
    explicit_root = argv[1] if len(argv) > 1 else None
    repo_root_str = _resolve_repo_root(explicit_root)
    if repo_root_str is None:
        print("reaper-resting-batons.py: cannot resolve git repo root", file=sys.stderr)
        return 2

    repo_root = Path(repo_root_str)
    read_meta = _import_read_meta()
    surfaced = scan(repo_root, read_meta)

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"# generated_at={generated_at}")
    print("# regenerate: python3 coordinator/bin/reaper-resting-batons.py > state/audits/<date>-resting-batons.txt")
    for record in surfaced:
        age = record["age_days"] if record["age_days"] is not None else "unknown"
        print(f"{record['id']} age_days={age} path={record['path']}")
    print(f"total={len(surfaced)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
