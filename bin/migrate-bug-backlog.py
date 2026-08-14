"""
migrate-bug-backlog.py — one-shot migration of open bug entries from the
state/bug-backlog.md markdown table into structured per-entry YAML files via
coordinator-queue-append --schema bug-backlog.

Purpose: the bug-backlog.md table is the human-facing summary surface; this
script extracts each row from the `## Open Bugs (Backlog)` section, validates
its fields against the bug-backlog schema, and calls coordinator-queue-append
to write a per-entry YAML file to state/bug-backlog/<date>-<slug>.yaml.

Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C8

Modes:
  --dry-run   Parse bug-backlog.md and classify every parseable entry.
              Writes JSON audit log to state/migrate-bug-backlog-dryrun-<ISO>.json.
              Does NOT modify input file or invoke coordinator-queue-append.
  --apply     Read a prior dry-run output (must be <24h old); invoke
              coordinator-queue-append per to-migrate entry; remove migrated
              rows from state/bug-backlog.md.

Migration contract:
  - Only rows under `## Open Bugs (Backlog)` migrate.
  - `## Cross-repo candidates` and `## Spun off` sections are documentation
    only — classified as unmigrated-out-of-scope in dry-run output; untouched
    in --apply.
  - Content-match-not-tag-strip: an entry migrates ONLY if all 7 cells parse
    AND severity is in enum (P0/P1/P2/P3) AND id matches BS-YYYY-MM-DD-N.
    Ambiguous rows land in unmigrated-parse-error; their lines stay in place.
  - The bug-backlog.md frontmatter (last_sweep, last_sweep_commit, etc.) is
    preserved — only table data rows under ## Open Bugs are removed.

Negative-spec:
  - Do NOT copy or call _extract_promote_fields from migrate-improvement-queue-universals.py —
    bug-backlog has a completely different table shape (7 pipe-delimited cells).
  - Do NOT modify lessons-outbox files.
  - Do NOT commit; do NOT touch sibling migrators (C7, C9).
"""

from __future__ import annotations

import sys
import os
import re
import json
import hashlib
import datetime
import argparse
import subprocess
import glob as glob_module

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _queue_append_locator import find_queue_append_cmd  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────────────────

MUTATES = ["state/bug-backlog.md", "state/bug-backlog/*.yaml", "state/migrate-bug-backlog-dryrun-*.json"]

DEFAULT_INPUT = os.path.join("state", "bug-backlog.md")
DRYRUN_PREFIX = os.path.join("state", "migrate-bug-backlog-dryrun-")
DRYRUN_GLOB = os.path.join("state", "migrate-bug-backlog-dryrun-*.json")
DEFAULT_STALE_HOURS = 24

# Valid severity values per bug-backlog-schema.md.
SEVERITY_ENUM = {"P0", "P1", "P2", "P3"}

# ID pattern per bug-backlog-schema.md: BS-YYYY-MM-DD-N
ID_PATTERN = re.compile(r"^BS-\d{4}-\d{2}-\d{2}-\d+$")

# Heading markers for section detection.
OPEN_BUGS_HEADING = "## Open Bugs (Backlog)"

# Sections that are documentation-only and must NOT migrate.
OUT_OF_SCOPE_HEADINGS = {
    "## Cross-repo candidates",
    "## Spun off",
}


# ── Table parsing ──────────────────────────────────────────────────────────────


def _split_table_row(line: str) -> list[str] | None:
    """
    Split a markdown table row into cells.

    Returns a list of stripped cell strings if the line is a table row
    (starts and ends with |), or None otherwise. Skips alignment rows
    (cells containing only dashes and colons).
    """
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    # Remove leading/trailing pipes and split.
    inner = stripped[1:-1]
    cells = [c.strip() for c in inner.split("|")]
    # Detect alignment row (e.g. |---|---| or |:---:|).
    if all(re.match(r"^:?-+:?$", c) for c in cells if c):
        return None
    return cells


def _parse_date_from_found(found_str: str) -> str:
    """
    Extract an ISO date (YYYY-MM-DD) from a "Found" cell value.

    The cell often has the shape: "bug-sweep YYYY-MM-DD (F-C2-12)"
    or similar. Tries to extract the first date-like substring.
    Falls back to today's date if no date is found.
    """
    # Look for YYYY-MM-DD pattern.
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", found_str)
    if m:
        return m.group(1)
    return datetime.date.today().isoformat()


def _synthesize_title(description: str) -> str:
    """
    Derive a one-line title from the description cell.

    Title = first sentence (split on '.', '!', '?') or first 80 chars,
    whichever is shorter. Strips markdown backtick wrapping.
    """
    # Strip markdown code spans for title purposes.
    clean = re.sub(r"`[^`]*`", lambda m: m.group(0).strip("`"), description)
    # First sentence boundary.
    sentence = re.split(r"(?<=[.!?])\s", clean, maxsplit=1)[0]
    title = sentence.strip().rstrip(".!?")
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title


def _validate_id(id_str: str) -> bool:
    """Return True if id_str matches the BS-YYYY-MM-DD-N pattern."""
    return bool(ID_PATTERN.match(id_str.strip()))


def _validate_severity(sev: str) -> bool:
    """Return True if sev is a valid severity enum value."""
    return sev.strip() in SEVERITY_ENUM


# ── Section classifier ─────────────────────────────────────────────────────────


def _is_heading(line: str) -> bool:
    return line.lstrip().startswith("#")


def _heading_text(line: str) -> str:
    return line.strip()


# ── Dry-run ────────────────────────────────────────────────────────────────────


def _deterministic_id(text: str) -> str:
    """Return a 16-hex-char content hash for audit log IDs."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def run_dryrun(input_path: str, output_path: str | None) -> int:
    """
    Parse bug-backlog.md and classify every row.

    Classifications:
      to-migrate              — all 7 cells parsed, id valid, severity valid
      unmigrated-parse-error  — row doesn't parse cleanly; stays in place
      unmigrated-out-of-scope — row from Cross-repo / Spun-off sections

    Does NOT modify input_path. Writes JSON audit log to output_path.
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
    section = "preamble"  # preamble | open-bugs | out-of-scope | other
    in_open_bugs = False
    header_seen = False  # whether we've seen the table header row

    for lineno, raw_line in enumerate(lines, start=1):
        line_text = raw_line.rstrip("\n")

        # Detect section transitions at headings.
        if _is_heading(raw_line):
            h = _heading_text(raw_line)
            if h == OPEN_BUGS_HEADING:
                section = "open-bugs"
                in_open_bugs = True
                header_seen = False
                continue
            elif any(h.startswith(oos) for oos in OUT_OF_SCOPE_HEADINGS):
                section = "out-of-scope"
                in_open_bugs = False
                continue
            elif raw_line.startswith("##"):
                # Any other ## heading exits the open-bugs section.
                section = "other"
                in_open_bugs = False
                continue

        if section == "open-bugs":
            cells = _split_table_row(raw_line)
            if cells is None:
                # Not a table row — skip (blank lines, narrative paragraphs).
                continue
            if not header_seen:
                # First parseable row is the header — skip it.
                header_seen = True
                continue

            # Data row: expect exactly 7 cells.
            if len(cells) != 7:
                entries.append({
                    "source_line": lineno,
                    "classification": "unmigrated-parse-error",
                    "raw": line_text,
                    "reason": (
                        f"Expected 7 pipe-delimited cells, got {len(cells)}. "
                        "Row left in place."
                    ),
                })
                continue

            id_val, system, severity, description, why_blocked, found, cross_ref = cells

            # Validate ID pattern.
            if not _validate_id(id_val):
                entries.append({
                    "source_line": lineno,
                    "classification": "unmigrated-parse-error",
                    "raw": line_text,
                    "reason": (
                        f"ID '{id_val}' does not match BS-YYYY-MM-DD-N pattern. "
                        "Row left in place."
                    ),
                })
                continue

            # Validate severity.
            if not _validate_severity(severity):
                entries.append({
                    "source_line": lineno,
                    "classification": "unmigrated-parse-error",
                    "raw": line_text,
                    "reason": (
                        f"Severity '{severity}' not in enum P0/P1/P2/P3. "
                        "Row left in place."
                    ),
                })
                continue

            # All validation passes — mark as to-migrate.
            created = _parse_date_from_found(found)
            title = _synthesize_title(description)

            entry = {
                "source_line": lineno,
                "classification": "to-migrate",
                "raw": line_text,
                "proposed_id": _deterministic_id(id_val + description),
                "fields": {
                    "id": id_val.strip(),
                    "system": system,
                    "severity": severity.strip(),
                    "title": title,
                    "body": description,
                    "why_blocked": why_blocked if why_blocked else None,
                    "created": created,
                    "cross_ref": cross_ref if cross_ref else None,
                    "status": "open",
                },
                "reason": (
                    f"ID and severity valid; 7 cells parsed; "
                    f"created={created}, severity={severity.strip()}."
                ),
            }
            entries.append(entry)

        elif section == "out-of-scope":
            # Only classify non-blank, non-heading content from OOS sections.
            stripped = raw_line.strip()
            if stripped and not _is_heading(raw_line):
                # Only flag table rows or bullet points as out-of-scope;
                # skip blank/separator lines silently.
                if stripped.startswith("|") or stripped.startswith("-"):
                    entries.append({
                        "source_line": lineno,
                        "classification": "unmigrated-out-of-scope",
                        "raw": line_text,
                        "reason": (
                            "Row is in a Cross-repo candidates or Spun off section "
                            "— documentation only, never migrated."
                        ),
                    })

    # Write JSON audit log.
    os.makedirs(
        os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
        exist_ok=True,
    )
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
        fh.write("\n")

    # Summary.
    to_migrate = [e for e in entries if e["classification"] == "to-migrate"]
    parse_errors = [e for e in entries if e["classification"] == "unmigrated-parse-error"]
    out_of_scope = [e for e in entries if e["classification"] == "unmigrated-out-of-scope"]

    print(f"Dry-run complete: {output_path}")
    print(f"  to-migrate:                {len(to_migrate)}")
    print(f"  unmigrated-parse-error:    {len(parse_errors)}")
    print(f"  unmigrated-out-of-scope:   {len(out_of_scope)}")

    if parse_errors:
        print()
        print("Parse errors (left in place):")
        for e in parse_errors:
            print(f"  line {e['source_line']}: {e['reason']}")

    return 0


# ── Apply ──────────────────────────────────────────────────────────────────────


def _find_latest_dryrun() -> str | None:
    """Return the path to the most recent dry-run output file, or None."""
    matches = sorted(glob_module.glob(DRYRUN_GLOB))
    return matches[-1] if matches else None


def run_apply(
    dryrun_path: str | None,
    input_path: str,
    stale_hours: int,
) -> int:
    """
    Apply a prior dry-run: invoke coordinator-queue-append per to-migrate entry
    and remove migrated rows from the input file.

    Refuses if:
      - dry-run file is absent
      - dry-run file is older than stale_hours
      - coordinator-queue-append is not on PATH

    Header preservation contract: only the data rows classified as to-migrate
    are removed from bug-backlog.md. The frontmatter, narrative paragraphs,
    the ## Open Bugs (Backlog) heading, the table header and alignment rows,
    the ## Cross-repo candidates and ## Spun off sections, and all other
    prose are preserved exactly.
    """
    # Resolve dry-run path.
    if dryrun_path is None:
        dryrun_path = _find_latest_dryrun()
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
            print(
                f"ERROR: malformed dry-run JSON at {dryrun_path}: {exc}",
                file=sys.stderr,
            )
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
        fields = entry.get("fields", {})

        id_val = fields.get("id", "")
        system = fields.get("system", "")
        severity = fields.get("severity", "")
        title = fields.get("title", "")
        body = fields.get("body", "")
        why_blocked = fields.get("why_blocked") or ""
        created = fields.get("created", datetime.date.today().isoformat())
        cross_ref = fields.get("cross_ref") or ""
        status = fields.get("status", "open")

        # Build coordinator-queue-append invocation for bug-backlog schema.
        # Required: --schema bug-backlog --id --title --body --system --severity --status
        # Optional: --why-blocked --cross-ref --created
        extra_args = [
            "--schema", "bug-backlog",
            "--id", id_val,
            "--title", title,
            "--body", body,
            "--system", system,
            "--severity", severity,
            "--status", status,
            "--created", created,
        ]
        if why_blocked:
            extra_args += ["--why-blocked", why_blocked]
        if cross_ref:
            extra_args += ["--cross-ref", cross_ref]
        cmd = cmd_prefix + extra_args

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"WARNING: coordinator-queue-append failed for line {source_line} "
                f"(id={id_val}): {result.stderr.strip()}",
                file=sys.stderr,
            )
            failed.append(entry)
            continue

        migrated_lines.add(source_line)
        out_path = result.stdout.strip()
        print(f"  Migrated {id_val} → {out_path}")

    # Remove migrated data rows from the input file.
    # source_line values are 1-indexed; lines list is 0-indexed.
    new_lines = [
        line
        for idx, line in enumerate(lines, start=1)
        if idx not in migrated_lines
    ]
    with open(input_path, "w", encoding="utf-8") as fh:
        fh.writelines(new_lines)

    print(
        f"\nApplied: {len(migrated_lines)} entries migrated, "
        f"{len(failed)} failed (left in place), "
        f"input file updated: {input_path}"
    )
    if failed:
        print("Failed entries (left in place):")
        for e in failed:
            id_val = e.get("fields", {}).get("id", "?")
            print(f"  line {e['source_line']}: {id_val}")

    return 0 if not failed else 1


# ── CLI ────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for migrate-bug-backlog."""
    parser = argparse.ArgumentParser(
        prog="migrate-bug-backlog.py",
        description=(
            "One-shot migration of open bug entries from state/bug-backlog.md\n"
            "into structured per-entry YAML files via coordinator-queue-append.\n\n"
            "Only rows under '## Open Bugs (Backlog)' migrate. Cross-repo candidates\n"
            "and Spun-off sections are documentation-only and are never migrated.\n\n"
            "Content-match-not-tag-strip: an entry migrates ONLY if all 7 cells parse\n"
            "AND severity is in enum (P0/P1/P2/P3) AND id matches BS-YYYY-MM-DD-N.\n\n"
            "Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C8"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Parse bug-backlog.md and classify every row. Write a JSON audit log to "
            "state/migrate-bug-backlog-dryrun-<ISO-date>.json (or --output). "
            "Does NOT modify the input file."
        ),
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Read a prior dry-run output file and invoke coordinator-queue-append "
            "for each to-migrate entry, then remove those rows from the input file. "
            "Refuses if the dry-run file is absent or older than --stale-hours."
        ),
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        metavar="PATH",
        help=f"Path to bug-backlog.md. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Path for the dry-run JSON output file. "
            "Default: state/migrate-bug-backlog-dryrun-<ISO-date>.json"
        ),
    )
    parser.add_argument(
        "--from-dryrun",
        default=None,
        metavar="PATH",
        help=(
            "Path to the dry-run output file for --apply mode. "
            "Default: most recent state/migrate-bug-backlog-dryrun-*.json"
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
    """Entry point for migrate-bug-backlog CLI."""
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
