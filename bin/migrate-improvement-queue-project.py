#!/usr/bin/env python3
"""
migrate-improvement-queue-project.py — one-shot migration of project-specific entries
from the legacy pipe-delimited state/improvement-queue.md into structured YAML files
under state/improvement-queue/ via coordinator-queue-append.

This migrator owns the PROJECT-SPECIFIC TAIL of state/improvement-queue.md.
Universal entries (tagged [universal]) are the domain of the predecessor migrator
(migrate-improvement-queue-universals.py). If any [universal]-tagged entries survive
here, they are surfaced as "unmigrated-universal-leftover" for human review — do NOT
re-process them.

Entry format (pipe-delimited, five cells):
  - CREATED | from_repo (always "self") | SURFACE | BODY | proposed target: TARGET

Field mapping (per improvement-queue-schema.md):
  created        → first field (ISO date)
  from_repo      → resolved via coordinator-queue-append's standard resolution
                   (pass through CLI — never trust the literal "self" string)
  surface        → third field
  body           → fourth field
  proposed_target → fifth field with "proposed target: " prefix stripped
  title          → first 80 chars of body (synthesized)
  change_kind    → inferred from surface:
                     contains ".sh"        → script-edit
                     contains "SKILL.md"   → skill-edit
                     contains "docs/wiki/" → wiki-append
                     otherwise             → script-edit (default), inference flagged as "ambiguous"
  status         → "open" (the queue surface is the open set)

Classification buckets:
  "to-migrate"                    — 5 cells parsed unambiguously, no [universal] tag
  "unmigrated-universal-leftover" — entry carries [universal] tag (predecessor missed it)
  "unmigrated-parse-error"        — fewer than 5 pipe-cells or cells empty after strip

Modes:
  --dry-run   Classify all entries and write a JSON audit log to
              state/migrate-improvement-queue-project-dryrun-<ISO-date>.json.
              Does NOT modify the input file.
  --apply     Read a prior dry-run output (≤24h old); invoke coordinator-queue-append
              --schema improvement-queue per to-migrate entry; remove migrated lines
              from state/improvement-queue.md.

Usage:
  python migrate-improvement-queue-project.py --dry-run [--input <path>] [--output <path>]
  python migrate-improvement-queue-project.py --apply [--from-dryrun <path>]
                                              [--input <path>] [--stale-hours N]

Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C9

Negative-spec:
  - Do NOT copy _extract_promote_fields from migrate-improvement-queue-universals.py
    (different field contract; this migrator owns project-specific shape — Hard Constraint i).
  - Do NOT touch state/coordinator-improvement-queue.md (central queue — stays per plan F5).
  - Do NOT commit (caller is an executor with no-commit brief).
  - Do NOT touch sibling migrators (C7, C8).
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

UNIVERSAL_TAG = "[universal]"
_PROPOSED_TARGET_PREFIX = "proposed target: "

DEFAULT_INPUT = os.path.join("state", "improvement-queue.md")
DRYRUN_GLOB = os.path.join(
    "state", "migrate-improvement-queue-project-dryrun-*.json"
)
DRYRUN_PREFIX = os.path.join(
    "state", "migrate-improvement-queue-project-dryrun-"
)
DEFAULT_STALE_HOURS = 24

# change_kind inference rules: evaluated in order; first match wins.
# Each rule is (substring_in_surface, change_kind_value).
_CHANGE_KIND_RULES: list[tuple[str, str]] = [
    (".sh", "script-edit"),
    ("SKILL.md", "skill-edit"),
    ("docs/wiki/", "wiki-append"),
]
_CHANGE_KIND_DEFAULT = "script-edit"


# ── Row parsing ────────────────────────────────────────────────────────────────


def _infer_change_kind(surface: str) -> tuple[str, bool]:
    """
    Infer change_kind from the surface field.

    Returns (change_kind, is_ambiguous).
    is_ambiguous is True when no rule matched and the default was applied.
    """
    for substring, kind in _CHANGE_KIND_RULES:
        if substring in surface:
            return kind, False
    return _CHANGE_KIND_DEFAULT, True


def _parse_project_entry(line: str) -> dict | None:
    """
    Parse a pipe-delimited improvement-queue entry line into a field dict.

    Expected shape:
      - CREATED | from_repo | SURFACE | BODY | proposed target: TARGET

    Returns None for non-entry lines (blank lines, header paragraphs).
    Returns a dict with classification and extracted fields otherwise.

    Classification:
      "unmigrated-universal-leftover"  — [universal] tag present
      "unmigrated-parse-error"         — fewer than 5 cells or required cells empty
      "to-migrate"                     — clean 5-cell row, no [universal] tag

    Hard Constraint i / the Staff Engineer F4: this is its own parser, NOT a copy of
    _extract_promote_fields from migrate-improvement-queue-universals.py.
    The universals migrator targets a different field contract (it extracts
    title/body/change_kind for coordinator-lesson-promote); this migrator
    extracts all 5 pipe-fields for coordinator-queue-append --schema improvement-queue.
    """
    stripped = line.strip()
    if not stripped.startswith("- "):
        return None

    # Universal-leftover guard — predecessor should have caught these.
    if UNIVERSAL_TAG in stripped:
        return {
            "classification": "unmigrated-universal-leftover",
            "entry_text": stripped,
            "reason": (
                f"{UNIVERSAL_TAG} tag found; predecessor migrator should have "
                "processed this. Left in place for human review."
            ),
        }

    # Strip the leading "- " before splitting.
    body_text = stripped[2:].strip()

    # Split on "|" — require exactly 5 cells.
    raw_cells = body_text.split("|")
    if len(raw_cells) < 5:
        return {
            "classification": "unmigrated-parse-error",
            "entry_text": stripped,
            "reason": (
                f"Expected 5 pipe-delimited cells, got {len(raw_cells)}. "
                "Entry left in place for manual migration."
            ),
        }

    # Extract exactly the 5 canonical cells; any trailing cells are folded
    # back into the fifth (handles bodies that happen to contain pipes).
    created = raw_cells[0].strip()
    _from_repo_literal = raw_cells[1].strip()  # always "self" — resolved via CLI
    surface = raw_cells[2].strip()
    body = raw_cells[3].strip()
    proposed_target_raw = "|".join(raw_cells[4:]).strip()

    # Validate required cells are non-empty.
    missing = [
        name
        for name, val in [
            ("created", created),
            ("surface", surface),
            ("body", body),
            ("proposed_target_raw", proposed_target_raw),
        ]
        if not val
    ]
    if missing:
        return {
            "classification": "unmigrated-parse-error",
            "entry_text": stripped,
            "reason": f"Empty required cell(s): {', '.join(missing)}. Left in place.",
        }

    # Strip the "proposed target: " prefix from the fifth cell.
    if proposed_target_raw.startswith(_PROPOSED_TARGET_PREFIX):
        proposed_target = proposed_target_raw[len(_PROPOSED_TARGET_PREFIX):].strip()
    else:
        # The prefix is missing — still usable; note the deviation.
        proposed_target = proposed_target_raw

    # Synthesize title from first 80 chars of body.
    title = body[:80].rstrip()

    # Infer change_kind from surface.
    change_kind, is_ambiguous = _infer_change_kind(surface)

    return {
        "classification": "to-migrate",
        "entry_text": stripped,
        "created": created,
        "surface": surface,
        "body": body,
        "proposed_target": proposed_target,
        "title": title,
        "change_kind": change_kind,
        "inference": "ambiguous" if is_ambiguous else "matched",
        "reason": (
            f"5 cells parsed; change_kind={change_kind!r}"
            + (" (ambiguous surface — default applied)" if is_ambiguous else "")
            + "."
        ),
    }


# ── Deterministic ID ───────────────────────────────────────────────────────────


def _deterministic_id(entry_text: str) -> str:
    """Return a 16-hex-char deterministic ID for dry-run output reproducibility."""
    h = hashlib.sha256(entry_text.encode("utf-8")).hexdigest()
    return h[:16]


# ── Dry-run ────────────────────────────────────────────────────────────────────


def run_dryrun(input_path: str, output_path: str | None) -> int:
    """
    Classify every entry in input_path and write a JSON audit log.
    Does NOT modify input_path.

    Returns 0 on success, non-zero on error.
    """
    if not os.path.exists(input_path):
        print(
            f"ERROR: input file not found: {input_path}",
            file=sys.stderr,
        )
        return 1

    with open(input_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    today = datetime.date.today().isoformat()
    if output_path is None:
        output_path = f"{DRYRUN_PREFIX}{today}.json"

    entries = []

    for idx, raw_line in enumerate(lines, start=1):
        parsed = _parse_project_entry(raw_line)
        if parsed is None:
            # Non-entry line (header paragraph, blank line) — skip.
            continue

        audit = {
            "source_line": idx,
            "classification": parsed["classification"],
            "entry_text": parsed["entry_text"],
            "reason": parsed.get("reason", ""),
        }

        if parsed["classification"] == "to-migrate":
            audit["proposed_dryrun_id"] = _deterministic_id(parsed["entry_text"])
            audit["title"] = parsed["title"]
            audit["created"] = parsed["created"]
            audit["surface"] = parsed["surface"]
            audit["body"] = parsed["body"]
            audit["proposed_target"] = parsed["proposed_target"]
            audit["change_kind"] = parsed["change_kind"]
            audit["inference"] = parsed["inference"]

        entries.append(audit)

    # Write JSON audit log.
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
        fh.write("\n")

    # Print summary.
    to_migrate = [e for e in entries if e["classification"] == "to-migrate"]
    leftover = [
        e for e in entries if e["classification"] == "unmigrated-universal-leftover"
    ]
    parse_errors = [
        e for e in entries if e["classification"] == "unmigrated-parse-error"
    ]
    ambiguous = [e for e in to_migrate if e.get("inference") == "ambiguous"]

    print(f"Dry-run complete: {output_path}")
    print(f"  to-migrate:                       {len(to_migrate)}")
    print(f"    of which ambiguous change_kind:  {len(ambiguous)}")
    print(f"  unmigrated-universal-leftover:    {len(leftover)}")
    print(f"  unmigrated-parse-error:           {len(parse_errors)}")

    if leftover:
        print()
        print("unmigrated-universal-leftover — predecessor migrator should review:")
        for e in leftover:
            print(f"  line {e['source_line']}: {e['entry_text'][:80]}")

    if parse_errors:
        print()
        print("unmigrated-parse-error — manual review:")
        for e in parse_errors:
            print(f"  line {e['source_line']}: {e['entry_text'][:80]}")

    if ambiguous:
        print()
        print(
            "ambiguous change_kind (default script-edit applied) — verify before --apply:"
        )
        for e in ambiguous:
            print(f"  line {e['source_line']}: surface={e['surface']!r}")

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
    Read a prior dry-run output; invoke coordinator-queue-append --schema improvement-queue
    for each to-migrate entry; remove migrated lines from input_path.

    Refuses if:
      - dry-run file is absent
      - dry-run file is older than stale_hours
      - coordinator-queue-append is not locatable
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

    # Staleness guard.
    file_mtime = os.path.getmtime(dryrun_path)
    age_hours = (datetime.datetime.now().timestamp() - file_mtime) / 3600.0
    if age_hours > stale_hours:
        print(
            f"ERROR: dry-run file is {age_hours:.1f}h old "
            f"(limit: {stale_hours}h). Re-run --dry-run to refresh.",
            file=sys.stderr,
        )
        return 1

    # Locate coordinator-queue-append.
    cmd_prefix = find_queue_append_cmd(os.path.dirname(os.path.abspath(__file__)))
    if cmd_prefix is None:
        print(
            "ERROR: coordinator-queue-append not found on PATH or next to this script. "
            "Ensure it is installed before running --apply.",
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
        print(
            f"ERROR: input file not found: {input_path}",
            file=sys.stderr,
        )
        return 1
    with open(input_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    to_migrate = [e for e in dryrun_entries if e["classification"] == "to-migrate"]
    migrated_lines: set[int] = set()
    failed: list[dict] = []

    for entry in to_migrate:
        source_line = entry["source_line"]

        # Build coordinator-queue-append invocation.
        cmd = list(cmd_prefix) + [
            "--schema", "improvement-queue",
            "--title", entry["title"],
            "--body", entry["body"],
            "--surface", entry["surface"],
            "--proposed-target", entry["proposed_target"],
            "--change-kind", entry["change_kind"],
            "--created", entry["created"],
            "--status", "open",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"WARNING: coordinator-queue-append failed for line {source_line}: "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            failed.append(entry)
            continue

        out_path = result.stdout.strip()
        print(f"  migrated line {source_line} → {out_path}")
        migrated_lines.add(source_line)

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


# ── CLI ────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for migrate-improvement-queue-project.py."""
    parser = argparse.ArgumentParser(
        prog="migrate-improvement-queue-project.py",
        description=(
            "One-shot migration of project-specific entries from "
            "state/improvement-queue.md into structured YAML files under "
            "state/improvement-queue/ via coordinator-queue-append.\n\n"
            "Owns the project-specific TAIL of state/improvement-queue.md. "
            "Universal ([universal]-tagged) entries are surfaced as "
            "'unmigrated-universal-leftover' — the predecessor migrator "
            "(migrate-improvement-queue-universals.py) should have handled them."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Classify all entries and write a JSON audit log to "
            "state/migrate-improvement-queue-project-dryrun-<ISO-date>.json "
            "(or --output). Does NOT modify the input file."
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
        help=f"Path to the improvement-queue.md to read. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Path for the dry-run JSON output file. "
            "Default: state/migrate-improvement-queue-project-dryrun-<ISO-date>.json"
        ),
    )
    parser.add_argument(
        "--from-dryrun",
        default=None,
        metavar="PATH",
        help=(
            "Path to the dry-run output file for --apply mode. "
            "Default: most recent state/migrate-improvement-queue-project-dryrun-*.json"
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
    """Entry point for migrate-improvement-queue-project."""
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
