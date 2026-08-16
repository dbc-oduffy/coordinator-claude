"""plan-task-brief.py — lift one task's brief out of a plan's `## Tasks` spine
into `fan-out-dispatch.py`'s `@file` brief shape.

Purpose: given (plan-path, task-id), locate that one row in the plan's
fenced ` ```yaml plan-tasks ` spine and emit exactly the brief text
`fan-out-dispatch.py`'s `@file` form reads (see that script's docstring,
lines 587-603 as of this writing). Replaces the EM hand-copying a task's
prose into an ad-hoc `Agent` dispatch prompt.

Vocabulary check (per the requesting memo): this is SINGLE-TASK, AD-HOC
dispatch-BRIEF production — a plain read-and-format over one row, called by
hand when an EM wants to dispatch one task outside a wave. It is NOT
pcli-03/pcli-04's wave-oriented dispatch-SIDECAR work, which shares the word
"dispatch" and reads the same spine but provisions a run-report sidecar
across a whole fan-out wave. Do not conflate the two.

Parses via `coordinator_core.ops.plan_tasks_render.load_rows` exclusively —
no fresh parser, no local `yaml.safe_load` over a hand-located fence (that
module's own docstring documents the fenced-block traps this reuse avoids).

Field partition (re-verified against plan-tasks.schema.json x-schema-version
1.7.0, DoE-claude coordinator/schemas/plan-tasks.schema.json, as of this
writing):
  IN  — title, surface, change_kind, body (id heads the brief as a label).
  OUT — queue_scope, pm_approved, deferred, writes, reads, case_against,
        depends_on, disposition, disposition_detail, disposition_ref —
        all planning-deliberation / harvest-routing /
        gate-graph metadata, noise in a dispatch prompt.
The formatter is forward-safe by construction: it formats the named IN-set
explicitly (an allowlist) and silently ignores any field not in that list —
never a dump-everything-minus-a-denylist that would leak a future schema
addition into a dispatch prompt unreviewed.

Byte-faithfulness: `--out FILE`'s contents are exactly what
`fan-out-dispatch.py`'s `@file` reader expects — it rejects a non-existent
file and an empty file, and rstrips trailing newlines, so a trailing
newline here is harmless. Deliberately does NOT embed the peer-scope block,
the destructive-action prohibition, or the disk-first preamble that
compiler assembles itself — duplicating those here is the exact waste this
capability exists to avoid.

Negative-spec:
  - Zero writes to the plan file, ever — pure read + format. No lock taken,
    no mutation op called.
  - Not a retrofit of execute-plan's Phase 1.5 TSV `<brief>` field or Phase
    1.6 ledger cell — deliberately deferred, larger, separate work.
  - No spine schema changes — pure reader of the schema as it stands.

House style: mirrors `fan-out-dispatch.py`'s arg parsing, `_err` stderr
helper, and 0/1/2 exit-code contract (0 success, 1 data/spec error, 2 usage
error). Pure Python 3.11+, naked .py, no bash.

Spec backlink: cross-repo/inbox/2026-08-13-doe-claude-em-pcli-02-plan-task-brief-copyout.md

Usage:
  python plan-task-brief.py <plan-path> <task-id> [--out FILE]

Exit codes:
  0 — brief emitted (stdout, or written to --out FILE).
  1 — data/spec error: unknown task id, duplicate task id, ABSENT spine,
      MALFORMED spine, or the plan file could not be read.
  2 — usage error (missing/extra positional args, unresolvable flag).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import cc_invoke  # noqa: E402

# The IN-set (executor-relevant fields) — an explicit allowlist, not
# derived by subtracting a denylist from whatever a row happens to carry.
# See module docstring's Field partition section.
_IN_FIELDS = ("title", "surface", "change_kind", "body")

GENERATES = []  # the only write is `--out FILE`, an arbitrary caller-supplied path — no fixed artifact


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plan-task-brief.py",
        description=(
            "Lift one task row's brief out of a plan's '## Tasks' spine, "
            "formatted for fan-out-dispatch.py's @file brief form."
        ),
    )
    parser.add_argument("plan_path", help="path to the plan file (docs/plans/...)")
    parser.add_argument("task_id", help="the task row's id (e.g. C1, D2)")
    parser.add_argument(
        "--out",
        dest="out_file",
        default=None,
        metavar="FILE",
        help="write the brief to FILE instead of stdout",
    )
    return parser


def format_brief(row: dict) -> str:
    """Format one task row into the @file brief text.

    Formats exactly the IN-set (see module docstring) — any other key on
    `row` (including a field this schema has not yet grown) is silently
    ignored, never dumped. `id` heads the brief as a label; `body` (if
    present) is appended verbatim, unreflowed — the primary failure mode
    this formatter guards against is a hand-rolled formatter mangling a
    multi-line block-scalar body.
    """
    lines: list = [f"Task {row.get('id', '')}: {row.get('title', '')}"]
    surface = row.get("surface")
    if surface:
        lines.append(f"Surface: {surface}")
    change_kind = row.get("change_kind")
    if change_kind:
        lines.append(f"Change kind: {change_kind}")
    body = row.get("body")
    if body:
        lines.append("")
        lines.append(str(body))
    return "\n".join(lines) + "\n"


def main(argv: "list[str] | None" = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    # coordinator_core must be import-reachable; this CLI lives inside the
    # engine checkout, so the colocated resolver is expected to succeed —
    # fail loud (exit 2, usage/environment class) if it doesn't.
    try:
        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.frontmatter.body_blocks import LocateStatus
        from coordinator_core.ops.plan_tasks_render import load_rows
    except Exception as exc:
        _err(f"plan-task-brief.py: ERROR — coordinator_core unresolvable: {exc}")
        return 2

    plan_path = Path(args.plan_path)
    try:
        source = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        _err(f"plan-task-brief.py: ERROR — cannot read plan {args.plan_path!r}: {exc}")
        return 1

    result = load_rows(source)

    if result.status is LocateStatus.ABSENT:
        _err(
            f"plan-task-brief.py: ERROR — no 'plan-tasks' spine found in "
            f"{args.plan_path!r} (ABSENT: no fenced yaml plan-tasks block yet)."
        )
        return 1
    if result.status is LocateStatus.MALFORMED:
        _err(
            f"plan-task-brief.py: ERROR — the 'plan-tasks' spine in "
            f"{args.plan_path!r} is MALFORMED (fenced block located, but its "
            "body did not parse as a list of task-row mappings)."
        )
        return 1

    matches = [row for row in result.rows if row.get("id") == args.task_id]

    if not matches:
        _err(
            f"plan-task-brief.py: ERROR — task id {args.task_id!r} not found "
            f"in {args.plan_path!r}."
        )
        return 1
    if len(matches) > 1:
        _err(
            f"plan-task-brief.py: ERROR — task id {args.task_id!r} appears "
            f"{len(matches)} times in {args.plan_path!r}'s spine — duplicate "
            "ids are a fail-loud spec violation, not a first-wins pick."
        )
        return 1

    brief = format_brief(matches[0])

    if args.out_file:
        # DR-276: this CLI reads via `plan_tasks_render.load_rows` (a
        # library function, not an op `main(argv)` -- there is no op
        # entrypoint to route through `run_op_main`), and its one write is
        # the caller-supplied `--out FILE`. Wrapped in
        # `recording_declared_writes()` with an explicit `declare_write()`
        # at the write site, per cli_entry's documented carve-out for a CLI
        # that owns its own body (see gen-launcher-shim.py's `main()`).
        from coordinator_core.cli_entry import recording_declared_writes
        from coordinator_core.session.declared_writes import declare_write

        try:
            with recording_declared_writes():
                Path(args.out_file).write_text(brief, encoding="utf-8")
                declare_write(args.out_file)
        except OSError as exc:
            _err(f"plan-task-brief.py: ERROR — cannot write --out file {args.out_file!r}: {exc}")
            return 1
    else:
        sys.stdout.write(brief)

    return 0


if __name__ == "__main__":
    sys.exit(main())
