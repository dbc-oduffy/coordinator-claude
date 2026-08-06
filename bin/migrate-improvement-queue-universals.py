#!/usr/bin/env python3
"""
migrate-improvement-queue-universals.py — one-shot migration of [universal]+central-wiki
entries from a per-project improvement-queue.md into the structured lessons-outbox.

Classification follows the content-match-then-confirm shape, not tag-strip, per the
2026-05-30 bulk-strip data-loss lesson in `state/coordinator-improvement-queue.md`:
"bulk strip-universals.py assumes all sibling [universal] entries were promoted to the
central queue — false on heavy-capture days; bulk strip archives non-promoted
project-specific over-tags (data loss). Strip only the run promotion set by
content-match, or defer to sibling local-mode."

This script refuses to migrate an entry unless BOTH conditions hold:
  (a) the [universal] tag is present in the entry text, AND
  (b) a central-wiki path is named in the entry body
      (substring match on "~/.claude/docs/wiki/" or "coordinator/docs/wiki/").
[universal] entries without a named central-wiki target land in "unmigrated-no-target"
and are LEFT IN PLACE — these are the data-loss class the 2026-05-30 lesson names.

Spec backlink: docs/plans/2026-06-15-universal-lesson-routing-mechanical-capture.md § C7

Modes:
  --dry-run   Classify all entries and write a JSON audit log. No input-file modification.
  --apply     Read a prior dry-run output; invoke coordinator-lesson-promote for each
              to-migrate entry; remove migrated lines from the input file.

Usage:
  python migrate-improvement-queue-universals.py --dry-run [--input <path>] [--output <path>]
  python migrate-improvement-queue-universals.py --apply [--from-dryrun <path>]
                                                 [--input <path>] [--stale-hours N]
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


# ── Central-wiki path patterns ─────────────────────────────────────────────────
# An entry migrates only if one of these substrings appears in the line body.
# Tag presence alone is NOT sufficient (content-match-then-confirm shape).
CENTRAL_WIKI_PATTERNS = [
    "~/.claude/docs/wiki/",
    "coordinator/docs/wiki/",
]

UNIVERSAL_TAG = "[universal]"

DEFAULT_INPUT = os.path.join("state", "improvement-queue.md")
DRYRUN_GLOB = os.path.join("state", "migrate-universals-dryrun-*.json")
DRYRUN_PREFIX = os.path.join("state", "migrate-universals-dryrun-")
DEFAULT_STALE_HOURS = 24


# ── Classification ─────────────────────────────────────────────────────────────

def has_universal_tag(line: str) -> bool:
    """Return True if the line contains the [universal] tag (case-sensitive)."""
    return UNIVERSAL_TAG in line


def extract_central_wiki_target(line: str) -> str | None:
    """
    Return the first central-wiki path substring found in the line, or None.
    Looks for ~/.claude/docs/wiki/<name>.md or coordinator/docs/wiki/<name>.md.
    """
    for pattern in CENTRAL_WIKI_PATTERNS:
        idx = line.find(pattern)
        if idx == -1:
            continue
        # Capture from the pattern start to the end of the wiki filename.
        # A wiki path ends at the first whitespace, backtick, quote, or end-of-line.
        end = len(line)
        for terminator in (" ", "\t", "`", "'", '"', ")", "(", "\n"):
            pos = line.find(terminator, idx + len(pattern))
            if pos != -1 and pos < end:
                end = pos
        return line[idx:end].rstrip(".,;")
    return None


def classify_line(line: str):
    """
    Classify a single improvement-queue entry line.

    Returns one of:
      "to-migrate"            — [universal] tag present AND central-wiki target found
      "unmigrated-no-target"  — [universal] tag present but no central-wiki path in body
      "project-specific"      — no [universal] tag
      None                    — not an entry line (blank, header, etc.)
    """
    stripped = line.strip()
    if not stripped.startswith("- "):
        return None
    if not has_universal_tag(stripped):
        return "project-specific"
    target = extract_central_wiki_target(stripped)
    if target:
        return "to-migrate"
    return "unmigrated-no-target"


# ── Deterministic ID for dry-run output ────────────────────────────────────────

def deterministic_id(entry_text: str) -> str:
    """
    Return a deterministic 16-hex-char ID for an entry based on its content.
    Used in dry-run output so the audit log is reproducible and testable.
    In --apply mode the real coordinator-lesson-promote generates a uuid4.
    """
    h = hashlib.sha256(entry_text.encode("utf-8")).hexdigest()
    return h[:16]


# ── Dry-run ────────────────────────────────────────────────────────────────────

def run_dryrun(input_path: str, output_path: str | None) -> int:
    """
    Classify every entry in input_path and write a JSON audit log.
    Does NOT modify input_path.

    Deduplication: entries with the same (normalized_title, target_wiki) are
    collapsed — the first occurrence becomes the canonical to-migrate row; later
    occurrences are classified as "to-migrate-duplicate" and their source_lines
    are recorded in the canonical row's multi_source field.

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
    # Map (title_key, target_wiki) → index in entries list for dedup.
    canonical_map: dict[tuple, int] = {}

    for idx, raw_line in enumerate(lines, start=1):
        classification = classify_line(raw_line)
        if classification is None:
            # Not an entry line — skip (header/blank).
            continue

        entry_text = raw_line.strip()
        target_wiki = extract_central_wiki_target(entry_text) if classification == "to-migrate" else None

        # Build a normalised title key for dedup: extract the prose description
        # (the part after the last `|` pipe if present, else the full text).
        parts = entry_text.split("|")
        raw_title = parts[-1].strip() if len(parts) > 1 else entry_text

        # Collapse duplicate to-migrate entries (same target_wiki, same title key).
        dedup_key = None
        if classification == "to-migrate" and target_wiki:
            dedup_key = (deterministic_id(raw_title[:80]), target_wiki)
            if dedup_key in canonical_map:
                # Annotate the canonical entry with this additional source.
                canon_idx = canonical_map[dedup_key]
                existing = entries[canon_idx]
                if "multi_source" not in existing:
                    existing["multi_source"] = [existing["source_line"]]
                existing["multi_source"].append(idx)
                existing["reason"] = (
                    existing["reason"].rstrip(".")
                    + f"; also seen at line {idx} (multi-source, priority signal)."
                )
                # Record this line as duplicate in the output.
                entries.append(
                    {
                        "source_line": idx,
                        "classification": "to-migrate-duplicate",
                        "entry_text": entry_text,
                        "proposed_outbox_id": existing["proposed_outbox_id"],
                        "reason": (
                            f"Duplicate of line {existing['source_line']} "
                            f"(same target_wiki and title key); collapsed into canonical entry."
                        ),
                    }
                )
                continue

        # Build the audit entry.
        if classification == "to-migrate":
            outbox_id = deterministic_id(entry_text)
            reason = f"[universal] tag present and central-wiki target identified: {target_wiki}"
        elif classification == "unmigrated-no-target":
            outbox_id = None
            reason = (
                "[universal] tag present but no central-wiki path found in body; "
                "LEFT IN PLACE — manual review required to identify target wiki."
            )
        else:  # project-specific
            outbox_id = None
            reason = "No [universal] tag; project-specific entry LEFT IN PLACE."

        entry = {
            "source_line": idx,
            "classification": classification,
            "entry_text": entry_text,
            "proposed_outbox_id": outbox_id,
            "reason": reason,
        }
        if classification == "to-migrate" and target_wiki:
            entry["target_wiki"] = target_wiki

        if dedup_key is not None:
            canonical_map[dedup_key] = len(entries)

        entries.append(entry)

    # Write JSON audit log.
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)
        fh.write("\n")

    # Print summary to stdout.
    to_migrate = [e for e in entries if e["classification"] == "to-migrate"]
    duplicates = [e for e in entries if e["classification"] == "to-migrate-duplicate"]
    unmigrated = [e for e in entries if e["classification"] == "unmigrated-no-target"]
    project_specific = [e for e in entries if e["classification"] == "project-specific"]

    print(f"Dry-run complete: {output_path}")
    print(f"  to-migrate:            {len(to_migrate)}")
    print(f"  to-migrate-duplicate:  {len(duplicates)}")
    print(f"  unmigrated (no target): {len(unmigrated)}")
    print(f"  project-specific:      {len(project_specific)}")

    if unmigrated:
        print()
        print("unmigrated — manual review:")
        for e in unmigrated:
            print(f"  line {e['source_line']}: {e['entry_text'][:80]}...")

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
    Read a prior dry-run output; invoke coordinator-lesson-promote for each
    to-migrate entry; remove migrated lines from input_path.

    Refuses if:
      - dry-run file is absent
      - dry-run file is older than stale_hours
      - coordinator-lesson-promote is not on PATH

    Deliberate isolation boundary — do not convert to an in-process
    import. This is a distinct-target probe: a `--help` liveness check
    on a candidate CLI before committing to it, so the probe must
    observe that CLI's own process exit rather than this script's.
    Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
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

    # Check coordinator-lesson-promote is on PATH.
    promote_bin = None
    for candidate in ("coordinator-lesson-promote", "coordinator-lesson-promote.py"):
        try:
            result = subprocess.run(
                [candidate, "--help"],
                capture_output=True,
                text=True,
            )
        except OSError:
            # FileNotFoundError on Windows when executable not on PATH; subclass of OSError.
            continue
        if result.returncode == 0:
            promote_bin = candidate
            break
    if promote_bin is None:
        print(
            "ERROR: coordinator-lesson-promote not found on PATH. "
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
        entry_text = entry.get("entry_text", "")
        target_wiki = entry.get("target_wiki", "unknown")

        # Extract fields for coordinator-lesson-promote.
        title, body, change_kind = _extract_promote_fields(entry_text)

        cmd = [
            promote_bin,
            "--title", title,
            "--body", body,
            "--change-kind", change_kind,
            "--target-wiki", target_wiki,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(
                f"WARNING: coordinator-lesson-promote failed for line {source_line}: "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            failed.append(entry)
            continue

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


def _extract_promote_fields(entry_text: str) -> tuple[str, str, str]:
    """
    Extract (title, body, change_kind) from a raw improvement-queue entry line.

    Entry format (pipe-delimited): "- DATE | REPO | SOURCE | BODY | proposed target: WIKI"
    Title is derived from the body section; change_kind is wiki-append by default.
    """
    stripped = entry_text.lstrip("- ").strip()
    parts = [p.strip() for p in stripped.split("|")]

    if len(parts) >= 4:
        # DATE | REPO | SOURCE | BODY [| proposed target: ...]
        body_raw = parts[3]
        # Strip the [universal] tag from the title candidate.
        body_clean = body_raw.replace(UNIVERSAL_TAG, "").strip()
        # Title: first sentence or first 100 chars.
        title = re.split(r"[.!?]", body_clean)[0].strip()[:100]
        body = body_clean
    else:
        # Fallback: use full text.
        body = stripped.replace(UNIVERSAL_TAG, "").strip()
        title = body[:100]

    # Infer change_kind: wiki-append for entries targeting an existing wiki section.
    change_kind = "wiki-append"

    return title, body, change_kind


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate-improvement-queue-universals.py",
        description=(
            "One-shot migration of [universal]+central-wiki-target entries from "
            "state/improvement-queue.md into the structured lessons-outbox.\n\n"
            "Classification follows the content-match-then-confirm shape, not tag-strip, "
            "per the 2026-05-30 bulk-strip data-loss lesson: an entry migrates ONLY if "
            "(a) [universal] tag present AND (b) a central-wiki path is named in the body. "
            "[universal] entries WITHOUT a named central-wiki target are left in place "
            "under 'unmigrated — manual review'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Classify all entries and write a JSON audit log to "
            "state/migrate-universals-dryrun-<ISO-date>.json (or --output). "
            "Does NOT modify the input file."
        ),
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Read a prior dry-run output file and invoke coordinator-lesson-promote "
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
            "Default: state/migrate-universals-dryrun-<ISO-date>.json"
        ),
    )
    parser.add_argument(
        "--from-dryrun",
        default=None,
        metavar="PATH",
        help=(
            "Path to the dry-run output file for --apply mode. "
            "Default: most recent state/migrate-universals-dryrun-*.json"
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
