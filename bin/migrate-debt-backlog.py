"""
migrate-debt-backlog.py — one-shot migration of state/debt-backlog.md table rows
and bullet-list entries into per-entry YAML files via coordinator-queue-append.

Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C7

Two distinct entry shapes in state/debt-backlog.md are parsed:

1. Markdown table rows:
   | ID | Source | Status | Item | Risk | Suggested Action |
   Each data row has 6 pipe-delimited cells. Skip the header and alignment rows.

2. Bullet-list entries (section-style):
   - [ ] DSR-YYYY-MM-DD-N [tag] body — surfaces: path1, path2
   Parse the ID, body, and optional surfaces: cross-ref hint.

An entry migrates ONLY if BOTH conditions hold:
  (a) the row parses unambiguously into all required schema fields, AND
  (b) all required debt-backlog schema fields are populated.

Ambiguous parse or missing required field → unmigrated-parse-error bucket,
line stays. This is the content-match-not-tag-strip shape per Hard Constraint (e).

Modes:
  --dry-run   Classify all entries; write state/migrate-debt-backlog-dryrun-<ISO-date>.json.
              Does NOT modify the input file.
  --apply     Read a prior dry-run output (--from-dryrun or auto-discover latest).
              For each to-migrate entry, invoke coordinator-queue-append --schema debt-backlog.
              Removes migrated lines from state/debt-backlog.md once written.
              Refuses if dry-run file is absent or older than --stale-hours (default: 24h).

Negative-spec:
  - Does NOT copy _extract_promote_fields from migrate-improvement-queue-universals.py;
    parser is debt-backlog-specific (plan Hard Constraint i / the Staff Engineer F4).
  - Does NOT modify state/debt-backlog.md outside --apply mode.
  - Does NOT add third-party deps.

Usage:
  python migrate-debt-backlog.py --dry-run [--input <path>] [--output <path>]
  python migrate-debt-backlog.py --apply [--from-dryrun <path>] [--stale-hours N]
"""

from __future__ import annotations

import sys
import os
import re
import json
import datetime
import argparse
import subprocess
import glob as glob_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _queue_append_locator import find_queue_append_cmd  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────────────────

MUTATES = ["state/debt-backlog.md", "state/debt-backlog/*.yaml", "state/migrate-debt-backlog-dryrun-*.json"]

DEFAULT_INPUT = os.path.join("state", "debt-backlog.md")
DRYRUN_GLOB = os.path.join("state", "migrate-debt-backlog-dryrun-*.json")
DRYRUN_PREFIX = os.path.join("state", "migrate-debt-backlog-dryrun-")
DEFAULT_STALE_HOURS = 24

# Required schema fields for debt-backlog (per debt-backlog-schema.md).
REQUIRED_FIELDS = ["id", "created", "source", "status", "title", "body", "risk", "suggested_action"]

# Valid status values for debt-backlog schema.
VALID_STATUSES = ["open", "resolved", "open for-weekly-arch-review", "deferred"]

# Regex to detect and capture the ID from a bullet-list entry.
# Matches: - [ ] DSR-2026-06-08-1 or similar
_BULLET_ID_RE = re.compile(
    r"^-\s+\[[ x]\]\s+((DSR|CDX|BS)-(\d{4}-\d{2}-\d{2})-\d+)\s*(.*)", re.DOTALL
)

# Regex to detect the alignment row: |----|...
_ALIGNMENT_ROW_RE = re.compile(r"^\s*\|[-| ]+\|\s*$")

# Regex to extract the date component from an ID like DSR-2026-04-02-1
_ID_DATE_RE = re.compile(r"-((\d{4}-\d{2}-\d{2})-\d+)$")


# ── Parsing — Table Rows ───────────────────────────────────────────────────────

def _is_table_header(line: str) -> bool:
    """Return True if the line is the debt-backlog table header row."""
    stripped = line.strip()
    return (
        stripped.startswith("|")
        and "ID" in stripped
        and "Source" in stripped
        and "Status" in stripped
        and "Item" in stripped
    )


def _is_alignment_row(line: str) -> bool:
    """Return True if the line is a markdown table alignment row (|---|...)."""
    return bool(_ALIGNMENT_ROW_RE.match(line.strip()))


def _is_table_row(line: str) -> bool:
    """Return True if the line looks like a markdown table data row (starts and ends with |)."""
    stripped = line.strip()
    return (
        stripped.startswith("|")
        and stripped.endswith("|")
        and not _is_alignment_row(line)
        and not _is_table_header(line)
    )


def _parse_table_row(line: str, source_line_num: int) -> tuple[dict | None, str | None]:
    """
    Parse a markdown table data row into a debt-backlog schema dict.

    Table format: | ID | Source | Status | Item | Risk | Suggested Action |

    Returns (entry_dict, None) on success, or (None, error_reason) on failure.
    """
    stripped = line.strip().strip("|")
    cells = [c.strip() for c in stripped.split("|")]

    if len(cells) < 6:
        return None, f"expected 6 pipe-delimited cells, got {len(cells)}"

    entry_id = cells[0].strip()
    source = cells[1].strip()
    status_raw = cells[2].strip()
    item = cells[3].strip()
    risk = cells[4].strip()
    suggested_action = cells[5].strip()

    # Validate ID is non-empty and looks like a DSR/CDX/BS ID.
    if not entry_id:
        return None, "empty ID cell"

    # Extract date from ID (e.g. DSR-2026-04-02-1 → 2026-04-02).
    date_match = _ID_DATE_RE.search(entry_id)
    if not date_match:
        return None, f"cannot extract date from ID: {entry_id!r}"
    created = date_match.group(2)

    # Normalize status: strip backticks and extra whitespace.
    status = status_raw.replace("`", "").strip()

    # Validate status against known enum values.
    if status not in VALID_STATUSES:
        # Attempt to coerce common patterns.
        if "for-weekly-arch-review" in status or "for-weekly" in status:
            status = "open for-weekly-arch-review"
        elif status.startswith("open"):
            status = "open"
        elif status.startswith("resolved"):
            status = "resolved"
        elif status.startswith("deferred"):
            status = "deferred"
        else:
            return None, f"unrecognized status value: {status_raw!r}"

    # Derive title (first sentence or first 80 chars of item).
    title = _derive_title(item)

    # Check required fields are populated.
    if not source:
        return None, "empty source cell"
    if not item:
        return None, "empty item/body cell"
    if not risk:
        return None, "empty risk cell"
    if not suggested_action:
        return None, "empty suggested_action cell"

    return {
        "id": entry_id,
        "created": created,
        "source": source,
        "status": status,
        "title": title,
        "body": item,
        "risk": risk,
        "suggested_action": suggested_action,
    }, None


# ── Parsing — Bullet-List Entries ──────────────────────────────────────────────

def _is_bullet_entry(line: str) -> bool:
    """Return True if the line is a daily-observer-flags bullet entry."""
    stripped = line.strip()
    return stripped.startswith("- [") and bool(_BULLET_ID_RE.match(stripped))


def _parse_bullet_entry(line: str, source_line_num: int) -> tuple[dict | None, str | None]:
    """
    Parse a bullet-list entry into a debt-backlog schema dict.

    Bullet format: - [ ] DSR-2026-06-08-N [tag] body — surfaces: path1, path2

    Returns (entry_dict, None) on success, or (None, error_reason) on failure.
    """
    stripped = line.strip()
    match = _BULLET_ID_RE.match(stripped)
    if not match:
        return None, "bullet ID pattern did not match"

    entry_id = match.group(1)
    date_str = match.group(3)
    remainder = match.group(4).strip()

    # Extract optional [tag] from the remainder.
    tag_match = re.match(r"^\[([^\]]+)\]\s*(.*)", remainder, re.DOTALL)
    tag = None
    if tag_match:
        tag = tag_match.group(1).strip()
        remainder = tag_match.group(2).strip()

    # Extract surfaces: cross-ref hint if present.
    cross_ref = None
    surfaces_match = re.search(r"\s+—\s+surfaces:\s*(.+)$", remainder, re.DOTALL)
    if surfaces_match:
        surfaces_raw = surfaces_match.group(1).strip()
        cross_ref = surfaces_raw
        # Strip surfaces from body.
        remainder = remainder[: surfaces_match.start()].strip()

    body = remainder

    if not body:
        return None, "empty body in bullet entry"

    title = _derive_title(body)

    # Derive status from tag.
    if tag and "for-weekly-arch-review" in tag:
        status = "open for-weekly-arch-review"
    else:
        status = "open"

    # Bullet entries use a synthesized source and risk since these fields are
    # not explicitly present in the bullet format. We derive them from context.
    # source: infer from the ID prefix convention.
    source = _infer_source_from_id(entry_id, date_str)

    # risk and suggested_action cannot be reliably parsed from the single-line
    # bullet format — mark as unmigrated-parse-error to avoid data loss.
    # These entries require manual migration with full field population.
    return None, (
        "bullet entries do not carry risk/suggested_action fields inline; "
        "manual migration required to populate all debt-backlog required fields"
    )


def _infer_source_from_id(entry_id: str, date_str: str) -> str:
    """Infer the source field value from the ID prefix and date."""
    if entry_id.startswith("DSR-"):
        return f"workday-complete/step4/sonnet-observer/{date_str}"
    if entry_id.startswith("CDX-"):
        return f"codex-review-gate/{date_str}"
    return f"daily-review/{date_str}"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _derive_title(text: str) -> str:
    """
    Derive a title from prose: first sentence or first 80 chars.

    Splits on the first sentence-ending punctuation (. ! ?) to get a natural
    title. Truncates at 80 chars. Strips trailing punctuation.
    """
    if not text:
        return ""
    # Find first sentence boundary.
    sentence_match = re.split(r"[.!?]", text, maxsplit=1)
    if sentence_match:
        candidate = sentence_match[0].strip()
        if candidate:
            return candidate[:80].rstrip(".,;:")
    return text[:80].rstrip(".,;:")


# ── Line Classification ────────────────────────────────────────────────────────

class EntryKind:
    TABLE_ROW = "table_row"
    BULLET = "bullet"
    NON_ENTRY = "non_entry"


def _classify_line_kind(line: str) -> str:
    """Classify a source line as table_row, bullet, or non_entry."""
    stripped = line.strip()
    if not stripped:
        return EntryKind.NON_ENTRY
    if _is_table_row(line) and not _is_table_header(line) and not _is_alignment_row(line):
        return EntryKind.TABLE_ROW
    if _is_bullet_entry(line):
        return EntryKind.BULLET
    return EntryKind.NON_ENTRY


def _parse_entry(line: str, line_num: int, kind: str) -> tuple[dict | None, str | None]:
    """Dispatch to the appropriate parser based on entry kind."""
    if kind == EntryKind.TABLE_ROW:
        return _parse_table_row(line, line_num)
    if kind == EntryKind.BULLET:
        return _parse_bullet_entry(line, line_num)
    return None, "not an entry line"


# ── Dry-Run ────────────────────────────────────────────────────────────────────

def run_dryrun(input_path: str, output_path: str | None) -> int:
    """
    Classify every entry in input_path and write a JSON audit log.
    Does NOT modify input_path.

    Returns 0 on success, non-zero on error.
    """
    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    with open(input_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    today = datetime.date.today().isoformat()
    if output_path is None:
        output_path = f"{DRYRUN_PREFIX}{today}.json"

    entries = []

    for idx, raw_line in enumerate(lines, start=1):
        kind = _classify_line_kind(raw_line)
        if kind == EntryKind.NON_ENTRY:
            continue

        entry_dict, error = _parse_entry(raw_line, idx, kind)

        if entry_dict is not None:
            # Validate all required fields are present and non-empty.
            missing = [f for f in REQUIRED_FIELDS if not entry_dict.get(f)]
            if missing:
                entries.append({
                    "source_line": idx,
                    "classification": "unmigrated-parse-error",
                    "entry_text": raw_line.rstrip("\n"),
                    "entry_kind": kind,
                    "reason": f"parsed ok but missing required fields: {', '.join(missing)}",
                })
            else:
                entries.append({
                    "source_line": idx,
                    "classification": "to-migrate",
                    "entry_text": raw_line.rstrip("\n"),
                    "entry_kind": kind,
                    "parsed": entry_dict,
                    "reason": "parsed successfully; all required debt-backlog fields populated",
                })
        else:
            entries.append({
                "source_line": idx,
                "classification": "unmigrated-parse-error",
                "entry_text": raw_line.rstrip("\n"),
                "entry_kind": kind,
                "reason": error or "parse failed",
            })

    # Write JSON audit log.
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
        fh.write("\n")

    # Print summary.
    to_migrate = [e for e in entries if e["classification"] == "to-migrate"]
    parse_errors = [e for e in entries if e["classification"] == "unmigrated-parse-error"]

    print(f"Dry-run complete: {output_path}")
    print(f"  to-migrate:             {len(to_migrate)}")
    print(f"  unmigrated-parse-error: {len(parse_errors)}")

    if parse_errors:
        print()
        print("unmigrated-parse-error entries (left in place):")
        for e in parse_errors:
            print(f"  line {e['source_line']}: {e['entry_text'][:80]}...")
            print(f"    reason: {e['reason']}")

    return 0


# ── Apply ──────────────────────────────────────────────────────────────────────

def find_latest_dryrun() -> str | None:
    """Return the path to the most recent dry-run output file, or None."""
    matches = sorted(glob_module.glob(DRYRUN_GLOB))
    return matches[-1] if matches else None


def run_apply(
    dryrun_path: str | None,
    input_path: str,
    stale_hours: int,
) -> int:
    """
    Read a prior dry-run output and invoke coordinator-queue-append for each
    to-migrate entry, then remove migrated lines from input_path.

    Refuses if:
      - dry-run file is absent
      - dry-run file is older than stale_hours
      - coordinator-queue-append is not on PATH
    """
    # Resolve dry-run path.
    if dryrun_path is None:
        dryrun_path = find_latest_dryrun()
    if dryrun_path is None or not os.path.exists(dryrun_path):
        print(
            "ERROR: No dry-run output file found. "
            "Run with --dry-run first, then re-run with --apply.",
            file=sys.stderr,
        )
        return 1

    # Check staleness.
    file_mtime = os.path.getmtime(dryrun_path)
    age_hours = (datetime.datetime.now().timestamp() - file_mtime) / 3600.0
    if age_hours > stale_hours:
        print(
            f"ERROR: dry-run file is {age_hours:.1f}h old "
            f"(limit: {stale_hours}h). Re-run --dry-run to refresh.",
            file=sys.stderr,
        )
        return 1

    # Check coordinator-queue-append is on PATH.
    cmd_prefix = find_queue_append_cmd(os.path.dirname(os.path.abspath(__file__)))
    if cmd_prefix is None:
        print(
            "ERROR: coordinator-queue-append not found on PATH. "
            "Ensure the CLI is installed before running --apply.",
            file=sys.stderr,
        )
        return 1

    # Load dry-run output.
    with open(dryrun_path, "r", encoding="utf-8") as fh:
        try:
            dryrun_entries = json.load(fh)
        except json.JSONDecodeError as exc:
            print(f"ERROR: malformed dry-run JSON at {dryrun_path}: {exc}", file=sys.stderr)
            return 1

    # Load input file.
    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    with open(input_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    to_migrate = [e for e in dryrun_entries if e["classification"] == "to-migrate"]
    migrated_lines: set[int] = set()
    failed: list[dict] = []

    for entry in to_migrate:
        source_line = entry["source_line"]
        parsed = entry.get("parsed", {})

        cmd = _build_append_command(cmd_prefix, parsed)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"WARNING: coordinator-queue-append failed for line {source_line}: "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            failed.append(entry)
            continue

        migrated_lines.add(source_line)
        # Print the output path from coordinator-queue-append.
        if result.stdout.strip():
            print(f"  written: {result.stdout.strip()}")

    # Remove migrated lines from input file.
    new_lines = [
        line
        for idx, line in enumerate(lines, start=1)
        if idx not in migrated_lines
    ]
    with open(input_path, "w", encoding="utf-8") as fh:
        fh.writelines(new_lines)

    # Summary.
    print(
        f"Applied: {len(migrated_lines)} entries migrated, "
        f"{len(failed)} failed (left in place), "
        f"input file updated: {input_path}"
    )
    if failed:
        print("Failed entries (left in place):")
        for e in failed:
            print(f"  line {e['source_line']}: {e['entry_text'][:80]}")

    return 0


def _build_append_command(cmd_prefix: list[str], parsed: dict) -> list[str]:
    """
    Build the coordinator-queue-append command list for a parsed entry.

    `cmd_prefix` is the already-resolved argv prefix from
    find_queue_append_cmd (e.g. ["coordinator-queue-append"] or
    [sys.executable, "/abs/path/to/coordinator-queue-append"]).
    """
    cmd = list(cmd_prefix) + [
        "--schema", "debt-backlog",
        "--id", parsed["id"],
        "--title", parsed["title"],
        "--body", parsed["body"],
        "--source", parsed["source"],
        "--status", parsed["status"],
        "--risk", parsed["risk"],
        "--suggested-action", parsed["suggested_action"],
        "--created", parsed["created"],
    ]

    # Optional fields.
    if parsed.get("cross_ref"):
        cmd += ["--cross-ref", parsed["cross_ref"]]
    if parsed.get("severity"):
        cmd += ["--severity", parsed["severity"]]

    return cmd


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate-debt-backlog.py",
        description=(
            "One-shot migration of state/debt-backlog.md entries into per-entry YAML files\n"
            "via coordinator-queue-append --schema debt-backlog.\n\n"
            "Two entry shapes are parsed:\n"
            "  1. Markdown table rows: | ID | Source | Status | Item | Risk | Suggested Action |\n"
            "  2. Bullet-list entries: - [ ] DSR-YYYY-MM-DD-N [tag] body — surfaces: path\n\n"
            "An entry migrates ONLY if it parses unambiguously AND all required schema\n"
            "fields are populated. Ambiguous or incomplete entries stay in place.\n\n"
            "Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C7"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Classify all entries and write a JSON audit log to "
            "state/migrate-debt-backlog-dryrun-<ISO-date>.json (or --output). "
            "Does NOT modify the input file."
        ),
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Read a prior dry-run output file and invoke coordinator-queue-append "
            "for each to-migrate entry, then remove those lines from the input file. "
            "Refuses if the dry-run file is absent or older than --stale-hours."
        ),
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        metavar="PATH",
        help=f"Path to the debt-backlog.md to read. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Path for the dry-run JSON output file. "
            "Default: state/migrate-debt-backlog-dryrun-<ISO-date>.json"
        ),
    )
    parser.add_argument(
        "--from-dryrun",
        default=None,
        metavar="PATH",
        help=(
            "Path to the dry-run output file for --apply mode. "
            "Default: most recent state/migrate-debt-backlog-dryrun-*.json"
        ),
    )
    parser.add_argument(
        "--stale-hours",
        type=int,
        default=DEFAULT_STALE_HOURS,
        metavar="N",
        help=(
            f"Reject --apply if the dry-run file is older than N hours. "
            f"Default: {DEFAULT_STALE_HOURS}"
        ),
    )
    return parser


def main() -> int:
    """Entry point for migrate-debt-backlog."""
    parser = build_parser()
    args = parser.parse_args()

    if args.dry_run:
        return run_dryrun(input_path=args.input, output_path=args.output)
    elif args.apply:
        return run_apply(
            dryrun_path=args.from_dryrun,
            input_path=args.input,
            stale_hours=args.stale_hours,
        )
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
