"""workday-start-handoff-triage.py — self-contained naked-Python port of the
`/workday-start` Step 0.8 / Step 1.1 / Step 1.2 orientation-triage logic.

Subcommands:

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
no subprocess re-invocation of that CLI).

Exit codes:
  0 — subcommand ran (`trim-notes` is ALWAYS exit 0: advisory, never blocks;
      `ready`/`awaiting-gate` are also exit 0 on a clean query, including an
      empty result set — an empty inbox is not a failure).
  2 — setup/transport error (e.g. `records_query.query_records()` raised —
      the engine root unresolvable, engine unreachable, or a malformed CLI
      invocation). Mirrors `check-no-illegal-paths.py`'s 2 = setup error
      convention.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

_SETUP_ERROR = 2

_DEFAULT_NOTES_FILE = "tasks/orphan-sweep-notes.md"
_DEFAULT_HEADER_LINES = 4


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
    tmp_path.write_text("\n".join(header) + ("\n" if header else ""), newline="\n")
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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from records_query import query_records  # noqa: PLC0415 (deliberate: avoid import cost on unrelated subcommands)

    explicit_root = getattr(args, "repo_root", None)
    try:
        out = query_records(
            _HANDOFF_TYPE, _READY_WHERE, "markdown-list", 0, sort="-created",
            explicit_root=explicit_root,
        )
    except RuntimeError as exc:
        print(f"workday-start-handoff-triage.py: ready: {exc}", file=sys.stderr)
        return _SETUP_ERROR
    print(out, end="")
    return 0


def _cmd_awaiting_gate(args: argparse.Namespace) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from records_query import query_records  # noqa: PLC0415

    explicit_root = getattr(args, "repo_root", None)
    try:
        full_listing = query_records(
            _HANDOFF_TYPE, _AWAITING_GATE_WHERE, "markdown-list", 0, sort="-created",
            explicit_root=explicit_root,
        )
        stale_listing = query_records(
            _HANDOFF_TYPE, _AWAITING_GATE_WHERE, "markdown-list", 0, older_than="6d",
            explicit_root=explicit_root,
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
            "workday-start handoff-triage subcommands: "
            "trim-notes | ready | awaiting-gate"
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    trim_notes = subparsers.add_parser(
        "trim-notes", help="Surface + rotate tasks/orphan-sweep-notes.md."
    )
    trim_notes.add_argument("notes_file", nargs="?", default=_DEFAULT_NOTES_FILE)
    trim_notes.add_argument("--header-lines", type=int, default=_DEFAULT_HEADER_LINES)
    trim_notes.set_defaults(func=_cmd_trim_notes)

    ready = subparsers.add_parser("ready", help="List actionable-now (ready_to_fire) handoffs.")
    ready.add_argument(
        "--repo-root", dest="repo_root", default=None,
        help="Explicit repo root forwarded to records_query.query_records "
        "(explicit_root=...); omitted preserves the prior cwd-relative "
        "resolution unchanged.",
    )
    ready.set_defaults(func=_cmd_ready)

    awaiting_gate = subparsers.add_parser(
        "awaiting-gate", help="List awaiting_gate handoffs + the >6d stale subset."
    )
    awaiting_gate.add_argument(
        "--repo-root", dest="repo_root", default=None,
        help="Explicit repo root forwarded to records_query.query_records "
        "(explicit_root=...); omitted preserves the prior cwd-relative "
        "resolution unchanged.",
    )
    awaiting_gate.set_defaults(func=_cmd_awaiting_gate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
