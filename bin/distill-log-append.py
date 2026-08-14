# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
coordinator/bin/distill-log-append.py — thin CLI wrapper over
coordinator_core.distill.log_append.

Purpose: the claude-klabauter-owned canonical-log WRITER. Every distill-run append to
`state/distillation-log.md` (or any canonical-format log file) should go THROUGH this
tool — never a hand-rolled string append — so the on-disk format can never drift from
what `coordinator_core.distill._common.parse_distillation_log` consumes.

Single-row usage:
    python3 coordinator/bin/distill-log-append.py --log-path state/distillation-log.md \\
        --path archive/specs/foo.md --disposition DISTILLED \\
        --fate "distilled into wiki/foo.md" --run-id 2026-07-12-abc123

Bulk usage (PREFERRED for any multi-row run — one invocation, all-or-nothing):
    python3 coordinator/bin/distill-log-append.py --log-path state/distillation-log.md \\
        --batch rows.jsonl
    ... | python3 coordinator/bin/distill-log-append.py --log-path state/distillation-log.md --batch -

  The batch file is JSON Lines: one JSON object per line with keys
  {"path": ..., "disposition": ..., "fate": ..., "run_id": ...}. `--run-id` may be
  given alongside `--batch` as a default for rows that omit "run_id" (a row-level
  "run_id" wins). Validation is atomic: every row is validated BEFORE any write —
  one bad row fails the whole batch and NOTHING is written.

Emits a single-line JSON result object on stdout. Single-row: {"row": "<rendered row
text>", "header_opened": <bool>, "log_path": "<str>"}. Batch: {"rows_appended": <int>,
"rows": ["<rendered row text>", ...], "log_path": "<str>"}. Exits 0 on success; exits 1
with a JSON error object on stdout ({"error": "<message>"}) for an invalid disposition,
empty field, or malformed batch line.

Negative-spec: does not rewrite existing rows, does not reorder `## Run` blocks, and
never writes a partial batch — a batch reaches disk whole or not at all.

Relocated from bin/distill-log-append.py (DEC-3, 2026-07-23
Claude-klabauter-driven-ceremony-redesign) to coordinator/bin/ conventions — discoverability
(fleet `resolve-claude-klabauter-bin` machinery points at coordinator/bin, not top-level bin/)
plus Windows `.cmd` twin coverage. The old bin/ path is now a thin deprecation
forwarder; see that file. CLAUDE_KLABAUTER_ROOT is resolved via cc_invoke's
resolve_colocated_claude_klabauter_root ladder: this file's own coordinator/bin/ parent-of-
parent location is tried FIRST (self-location, zero external dependency, cannot be
unset) and accepted once it probes as a real claude-klabauter checkout; the machine-local
registry lookup is a fallback reached only if that probe misses (this file has been
published/vendored to a location outside the claude-klabauter checkout).

Spec backlink: pln-distill-ceremony-mechanical-su-1bcb38 § C7
Spec backlink: pln-claude-klabauter-driven-ceremony-redesig-c7fe9a § C6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_LIB_DIR = str(Path(__file__).resolve().parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

try:
    require_colocated_engine_on_path(__file__)
except RuntimeError as _exc:
    print(f"{Path(__file__).name}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)

from coordinator_core.distill.log_append import append_row, append_rows  # noqa: E402


def _load_batch_rows(batch_arg: str, default_run_id: str | None) -> list[dict[str, str]]:
    """Parse a JSON Lines batch from a file path (or stdin via '-') into row dicts,
    applying `default_run_id` to rows that omit "run_id". Raises ValueError on a
    malformed line — before anything is written."""
    if batch_arg == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(batch_arg).read_text(encoding="utf-8")

    rows: list[dict[str, str]] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"batch line {lineno}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"batch line {lineno}: expected a JSON object, got {type(obj).__name__}")
        if "run_id" not in obj and default_run_id:
            obj["run_id"] = default_run_id
        rows.append(obj)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Append canonical row(s) to a distillation log via the claude-klabauter writer. "
            "For multiple rows, ALWAYS use --batch (JSON Lines file, or '-' for stdin) — "
            "one invocation, validated all-or-nothing — never a loop of single-row calls "
            "and NEVER a hand-rolled string append."
        )
    )
    parser.add_argument("--log-path", required=True, help="Path to the canonical log file.")
    parser.add_argument(
        "--batch",
        help=(
            "Bulk mode: JSON Lines file of rows ('-' = stdin), one object per line: "
            '{"path": ..., "disposition": ..., "fate": ..., "run_id": ...}. '
            "All rows validated before any write; one bad row rejects the whole batch. "
            "Mutually exclusive with --path/--disposition/--fate."
        ),
    )
    parser.add_argument("--path", help="The distilled/archived spec path (single-row mode).")
    parser.add_argument(
        "--disposition",
        help="DISTILLED|PROMOTE|EPHEMERAL|SKIP|PRESERVE (single-row mode).",
    )
    parser.add_argument("--fate", help="Free-text fate description (single-row mode).")
    parser.add_argument(
        "--run-id",
        help=(
            "The distill run id grouping the row(s). Required in single-row mode; "
            "optional with --batch as the default for rows omitting \"run_id\"."
        ),
    )
    args = parser.parse_args(argv)

    single_row_args = [args.path, args.disposition, args.fate]
    if args.batch:
        if any(a is not None for a in single_row_args):
            parser.error("--batch is mutually exclusive with --path/--disposition/--fate")
    else:
        if any(a is None for a in single_row_args) or args.run_id is None:
            parser.error(
                "single-row mode requires --path, --disposition, --fate, and --run-id "
                "(or use --batch for bulk mode)"
            )

    try:
        if args.batch:
            rows = _load_batch_rows(args.batch, args.run_id)
            results = append_rows(Path(args.log_path), rows)
            payload = {
                "rows_appended": len(results),
                "rows": [r.row_text for r in results],
                "log_path": str(args.log_path),
            }
        else:
            result = append_row(
                Path(args.log_path),
                path=args.path,
                disposition=args.disposition,
                fate=args.fate,
                run_id=args.run_id,
            )
            payload = {
                "row": result.row_text,
                "header_opened": result.header_opened,
                "log_path": str(args.log_path),
            }
    except (ValueError, OSError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1

    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
