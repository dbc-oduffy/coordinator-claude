"""workday-start-handoff-triage.py — self-contained naked-Python port of the
`/workday-start` Step 0.8 / Step 1.1 / Step 1.2 orientation-triage logic.

Consolidates four small pieces of imperative bash that previously lived
inline as embedded fences in DoE-claude's `coordinator/commands/workday-start.md`
into one CLI, each exposed as a subcommand:

  stale-plans   — Step 0.8's stale-executing-plan advisory scan: flags any
                  `docs/plans/*.md` whose frontmatter says `status: executing`
                  but whose last git-touch is older than a threshold (default
                  3 days). Advisory only — never blocks the ceremony, never
                  writes anything.
  trim-notes    — Step 0.8's `tasks/orphan-sweep-notes.md` handling: surfaces
                  any orphan-archive lines `session-init.sh` appended since
                  the last `/workday-start`, then rotates the file back down
                  to its header (preserving the header, trimming the body) —
                  mirrors the bash `tail -n +5` / `head -n 4` idiom exactly.
  ready         — Step 1.1's actionable-now handoffs listing
                  (`deployment_state=ready_to_fire AND status=open`).
  awaiting-gate — Step 1.2's gated-handoffs listing: the full
                  `deployment_state=awaiting_gate AND status=open` set,
                  plus the coarse informational `--older-than 6d` stale
                  subset. (The load-bearing 14d/7d force-recheck predicate is
                  a SEPARATE mechanized tool, `handoff-gate-aging` — this
                  subcommand only reproduces the two thin `records_query`
                  listing calls Step 1.2 made directly, not that aging gate.)

`ready` and `awaiting-gate` import `query_records()` from the co-located
`coordinator/bin/lib/records_query.py` directly (in-process function call,
no subprocess re-invocation of that CLI) — per the porting brief's "lift the
Python, don't re-translate it" instruction, since that fence was already a
`python3 records_query.py ...` call into claude-klabauter Python.

Not ported (out of scope for this file — handled elsewhere in the same
extirpation plan): the `_cc_root`/`_cc_doe`/`_cc_trusted` coordinator-root
resolver preamble, the `_cc_claude_klabauter` resolution ladder, and the 14d/7d
`handoff-gate-aging` / `draft-plan-aging.py` mechanized checks (those already
exist as their own dedicated claude-klabauter entrypoints and Step 1.2 only shells out
to them — nothing to lift).

Exit codes:
  0 — subcommand ran (advisory subcommands `stale-plans`/`trim-notes` are
      ALWAYS exit 0, per their bash originals: "Advisory only — never
      blocks."; `ready`/`awaiting-gate` are also exit 0 on a clean query,
      including an empty result set — an empty inbox is not a failure).
  2 — setup/transport error (e.g. `records_query.query_records()` raised —
      CLAUDE_KLABAUTER_ROOT unresolvable, engine unreachable, or a malformed CLI
      invocation). Mirrors `check-no-illegal-paths.py`'s 2 = setup error
      convention.

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (the wider
extirpation-of-structural-bash-from-instruction-files campaign this chunk
belongs to).
Port of: DoE-claude coordinator/commands/workday-start.md § Step 0.8 (Stale-
Executing Plan Nudge) and § Step 1 (Handoff Triage) Steps 1.1/1.2 — the
bash bodies there are slated for a later D2 repoint to call this CLI by name;
this file does not edit that source (out of scope for this chunk).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_SETUP_ERROR = 2

_DEFAULT_PLANS_DIR = "docs/plans"
_DEFAULT_NOTES_FILE = "tasks/orphan-sweep-notes.md"
_DEFAULT_STALE_THRESHOLD_DAYS = 3
_DEFAULT_HEADER_LINES = 4


# --------------------------------------------------------------------------
# stale-plans
# --------------------------------------------------------------------------


def _read_frontmatter_lines(plan_path: Path) -> list[str]:
    """Return the lines strictly between the first and second `---` delimiter.

    Mirrors the bash original's `awk '/^---$/{n++; next} n==1'` exactly: the
    delimiter lines themselves are never returned, and nothing after the
    second delimiter is returned either (a plan with no closing `---` yields
    everything after the opening one, same as the awk pipeline would).
    """
    try:
        text = plan_path.read_text(errors="replace")
    except OSError:
        return []
    n = 0
    collected: list[str] = []
    for line in text.splitlines():
        if line == "---":
            n += 1
            continue
        if n == 1:
            collected.append(line)
    return collected


def _frontmatter_status_is_executing(frontmatter_lines: list[str]) -> bool:
    """`grep -qE '^status:[[:space:]]*executing'` — no `$` anchor, so a value
    that merely STARTS with "executing" (e.g. a hypothetical "executing-foo")
    also matches; preserved verbatim rather than tightened, since tightening
    would be a behavior change beyond what this port is scoped to make."""
    for line in frontmatter_lines:
        stripped_prefix = line[len("status:") :] if line.startswith("status:") else None
        if stripped_prefix is None:
            continue
        if stripped_prefix.lstrip(" \t").startswith("executing"):
            return True
    return False


# --------------------------------------------------------------------------
# DELIBERATE DUPLICATION NOTICE (do not consolidate onto draft_plan_aging):
#
# `coordinator_core/ops/draft_plan_aging.py::list_stale_executing` computes a
# closely-related "stale status:executing plan" answer, but the two diverge
# on FOUR observable axes and must stay independent implementations:
#   1. prefix vs exact status match — this file's `status:` match is a
#      documented-deliberate PREFIX match (see `_frontmatter_status_is_executing`
#      docstring), preserved verbatim from the original bash; draft_plan_aging
#      matches exact "executing".
#   2. `>=` vs `>` staleness threshold comparison.
#   3. sidecar-file skipping (draft_plan_aging excludes checker sidecars;
#      this file does not).
#   4. UTC-calendar (`date.today()`) vs epoch-floor (`// 86400`) age arithmetic.
# Re-pointing this CLI at draft_plan_aging would silently change behavior on
# all four axes to buy a performance win that in-place git-call batching
# (below) already delivers without the behavior change. Do not import from
# draft_plan_aging here.
# --------------------------------------------------------------------------


def _git_last_commit_epochs_batch(plan_paths: list[Path]) -> dict[Path, int | None]:
    """Resolve each `plan_paths` entry's most-recent-commit epoch via ONE
    multi-pathspec `git log` walk plus in-memory grouping, instead of one
    `git log -1 -- <path>` subprocess per plan (the N+1 git-spawn class this
    batching chunk exists to close).

    This is a per-path last-touch-timestamp query, not a range query (no
    positive/negative ref sets to combine) — `reachable(...) \\ reachable(...)`
    set-subtraction collapse does not apply here, so a single combined walk
    is a safe batching shape (see `emit/sections/handoffs.py`'s
    `_resolve_shipped_in_dates` for the sibling batching-plus-reconciliation
    pattern this mirrors).

    The walk is reverse-chronological by default, so for each requested path
    the FIRST commit in the output that touches it is that path's most
    recent commit — matching `git log -1 -- <path>` exactly.

    Absence is never defaulted: every requested path is reconciled against
    what the walk actually returned, and any path the walk never touches
    (never committed, or git failure) is explicitly mapped to None rather
    than silently omitted from the returned dict.
    """
    result: dict[Path, int | None] = {p: None for p in plan_paths}
    if not plan_paths:
        return result
    # `git log --name-only` reports paths repo-root-relative regardless of
    # how the pathspec argument itself was spelled, so normalize both the
    # pathspecs sent to git and the lookup key off the CWD-relative form
    # (the CLI's own callers always pass CWD-relative plan paths in
    # practice; the relpath call is a no-op for those).
    relspecs = [os.path.relpath(str(p)) for p in plan_paths]
    pathspecs = [Path(r).as_posix() for r in relspecs]
    try:
        proc = subprocess.run(
            [
                "git", "log",
                "--format=%x01%ct",
                "--name-only",
                # Merge commits print NO file-list line under plain
                # --name-only (git suppresses it by default for merges,
                # even ones that survive history simplification under a
                # pathspec because they are non-TREESAME to every parent).
                # Without this, a path whose most recent touch was a
                # conflict-resolution merge silently attributes to the
                # next, older commit that does print a name line — a
                # stale timestamp with no error signal. A kept merge under
                # default simplification is always non-TREESAME to its
                # first parent (implied by non-TREESAME-to-every-parent),
                # so first-parent diffing always emits its file list.
                "--diff-merges=first-parent",
                "--",
                *pathspecs,
            ],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return result
    if proc.returncode != 0 or not proc.stdout:
        return result

    posix_to_path = {
        Path(r).as_posix(): p for r, p in zip(relspecs, plan_paths)
    }
    matched: set[str] = set()
    current_epoch: int | None = None
    for raw_line in proc.stdout.replace("\r", "").splitlines():
        if raw_line.startswith("\x01"):
            try:
                current_epoch = int(raw_line[1:])
            except ValueError:
                current_epoch = None
            continue
        if not raw_line or current_epoch is None:
            continue
        name = raw_line.strip()
        if name in matched:
            continue
        target = posix_to_path.get(name)
        if target is not None:
            result[target] = current_epoch
            matched.add(name)
    return result


def find_stale_executing_plans(
    plans_dir: str = _DEFAULT_PLANS_DIR,
    threshold_days: int = _DEFAULT_STALE_THRESHOLD_DAYS,
    *,
    now: float | None = None,
) -> list[str]:
    """Return one advisory line per plan whose frontmatter says `status:
    executing` and whose last git touch is older than `threshold_days`.

    `now` is injectable for deterministic testing; production callers leave
    it as None (real wall clock, matching the bash original's `date +%s`).
    """
    directory = Path(plans_dir)
    if not directory.is_dir():
        return []
    reference_time = time.time() if now is None else now

    executing_paths: list[Path] = []
    for plan_path in sorted(directory.glob("*.md")):
        if not plan_path.is_file():
            continue
        frontmatter_lines = _read_frontmatter_lines(plan_path)
        if not _frontmatter_status_is_executing(frontmatter_lines):
            continue
        executing_paths.append(plan_path)

    epochs = _git_last_commit_epochs_batch(executing_paths)

    results: list[str] = []
    for plan_path in executing_paths:
        last_commit_epoch = epochs.get(plan_path)
        if last_commit_epoch is None:
            continue
        age_days = int((reference_time - last_commit_epoch) // 86400)
        if age_days > threshold_days:
            results.append(f"  - {plan_path} (status: executing, untouched {age_days}d)")
    return results


def _cmd_stale_plans(args: argparse.Namespace) -> int:
    for line in find_stale_executing_plans(args.plans_dir, args.threshold_days):
        print(line)
    return 0


# --------------------------------------------------------------------------
# trim-notes
# --------------------------------------------------------------------------


def trim_orphan_sweep_notes(
    notes_file: str = _DEFAULT_NOTES_FILE,
    header_lines: int = _DEFAULT_HEADER_LINES,
) -> str | None:
    """Rotate `notes_file` back down to its first `header_lines` lines,
    returning the trimmed body (everything after the header) so the caller
    can surface it, or None if there was nothing to surface (file absent, or
    at-or-under the header-line count already).

    Mirrors the bash original's `tail -n +5 file` (return body) followed by
    `head -n 4 file > file.new && mv file.new file` (atomic rewrite to just
    the header) exactly — including the `<= header_lines` guard (bash: `-gt
    4`, i.e. do nothing at exactly 4 or fewer lines).
    """
    path = Path(notes_file)
    if not path.is_file():
        return None
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if len(lines) <= header_lines:
        return None
    header = lines[:header_lines]
    body = lines[header_lines:]
    tmp_path = path.with_name(path.name + ".new")
    tmp_path.write_text("\n".join(header) + ("\n" if header else ""))
    tmp_path.replace(path)
    return "\n".join(body) + "\n"


def _cmd_trim_notes(args: argparse.Namespace) -> int:
    body = trim_orphan_sweep_notes(args.notes_file, args.header_lines)
    if body is None:
        return 0
    print("Orphan handoffs archived by session-init since last workday-start:")
    print(body, end="")
    return 0


# --------------------------------------------------------------------------
# ready / awaiting-gate
# --------------------------------------------------------------------------

_HANDOFF_TYPE = "handoff"
_READY_WHERE = "deployment_state=ready_to_fire AND status=open"
_AWAITING_GATE_WHERE = "deployment_state=awaiting_gate AND status=open"


def _cmd_ready(args: argparse.Namespace) -> int:
    from records_query import query_records  # noqa: PLC0415 (deliberate: avoid import cost on unrelated subcommands)

    try:
        out = query_records(_HANDOFF_TYPE, _READY_WHERE, "markdown-list", 0, sort="-created")
    except RuntimeError as exc:
        print(f"workday-start-handoff-triage.py: ready: {exc}", file=sys.stderr)
        return _SETUP_ERROR
    print(out, end="")
    return 0


def _cmd_awaiting_gate(args: argparse.Namespace) -> int:
    from records_query import query_records  # noqa: PLC0415

    try:
        full_listing = query_records(
            _HANDOFF_TYPE, _AWAITING_GATE_WHERE, "markdown-list", 0, sort="-created"
        )
        stale_listing = query_records(
            _HANDOFF_TYPE, _AWAITING_GATE_WHERE, "markdown-list", 0, older_than="6d"
        )
    except RuntimeError as exc:
        print(f"workday-start-handoff-triage.py: awaiting-gate: {exc}", file=sys.stderr)
        return _SETUP_ERROR

    print(full_listing, end="")
    if stale_listing.strip():
        print("--- awaiting_gate, older than 6d ---")
        print(stale_listing, end="")
    return 0


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workday-start-handoff-triage.py",
        description=(
            "workday-start handoff-triage subcommands: stale-plans | "
            "trim-notes | ready | awaiting-gate"
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    stale_plans = subparsers.add_parser(
        "stale-plans", help="Advisory scan for stale status:executing plans."
    )
    stale_plans.add_argument("plans_dir", nargs="?", default=_DEFAULT_PLANS_DIR)
    stale_plans.add_argument(
        "--threshold-days", type=int, default=_DEFAULT_STALE_THRESHOLD_DAYS
    )
    stale_plans.set_defaults(func=_cmd_stale_plans)

    trim_notes = subparsers.add_parser(
        "trim-notes", help="Surface + rotate tasks/orphan-sweep-notes.md."
    )
    trim_notes.add_argument("notes_file", nargs="?", default=_DEFAULT_NOTES_FILE)
    trim_notes.add_argument("--header-lines", type=int, default=_DEFAULT_HEADER_LINES)
    trim_notes.set_defaults(func=_cmd_trim_notes)

    ready = subparsers.add_parser("ready", help="List actionable-now (ready_to_fire) handoffs.")
    ready.set_defaults(func=_cmd_ready)

    awaiting_gate = subparsers.add_parser(
        "awaiting-gate", help="List awaiting_gate handoffs + the >6d stale subset."
    )
    awaiting_gate.set_defaults(func=_cmd_awaiting_gate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
