"""
migrate-provenance-stamp.py — stamp an honest provenance marker onto work-item
records that lack a top-level `system:` block.

Purpose: the ccos-3 C1 schema change added `system.provenance_completeness` as
a required field on work-item records. This script is the one-shot migration
that retroactively stamps existing records that predate the schema change with
`system:\n  provenance_completeness: unknown` — the only honest marker for
records whose provenance cannot be recovered after the fact.

Spec backlink: [ccos-3 plan] § C3a

Operation:
  - Accepts a single YAML file path OR a directory (processes all *.yaml files
    in that directory, non-recursive).
  - For each record:
    - If the record ALREADY has a top-level `system:` key, it is left UNTOUCHED.
      Re-running the script is a no-op (idempotent).
    - If the record has NO top-level `system:` key, appends:
        system:
          provenance_completeness: unknown
      to the end of the file. All pre-existing content is preserved
      byte-equivalently (lossless — only the new block is added).
  - Default mode is DRY-RUN: reports what would change without modifying files.
  - Pass --apply to write changes to disk.

Negative-spec:
  - Do NOT fabricate provenance (created_by_session, linked_sessions, commits).
    The only honest stamp for pre-migration records is `provenance_completeness:
    unknown`. Do NOT invent values for any provenance sub-field.
  - Do NOT reorder, reformat, or drop any existing top-level key or value.
    The file must be identical to the original except for the appended block.
  - Do NOT auto-run over the live state/ corpus on import. This script acts only
    on the path(s) explicitly passed as CLI arguments.
  - Do NOT commit. Do NOT modify sibling migrators.
"""

from __future__ import annotations

import sys
import os
import re
import glob as glob_module
import argparse

# ── Sentinel ───────────────────────────────────────────────────────────────────

# The YAML block appended to records missing a system: key.
# Two-space indent matches the coordinator queue-schema convention.
_PROVENANCE_BLOCK = "system:\n  provenance_completeness: unknown\n"

# Regex to detect a top-level `system:` key at column 0 in the file content.
# Matches `system:` or `system: value` but NOT `  system:` (indented sub-key).
_SYSTEM_KEY_RE = re.compile(r"^system\s*:", re.MULTILINE)


# ── Core logic ─────────────────────────────────────────────────────────────────


def _has_system_block(content: str) -> bool:
    """Return True if the record already has a top-level `system:` key."""
    return bool(_SYSTEM_KEY_RE.search(content))


def _stamp_record(content: str) -> str:
    """
    Return content with the provenance block appended.

    Ensures exactly one trailing newline before the block so the appended
    block begins on its own line. The original content is otherwise unchanged.
    """
    if content and not content.endswith("\n"):
        content = content + "\n"
    return content + _PROVENANCE_BLOCK


def process_file(path: str, apply: bool) -> str:
    """
    Process a single YAML record file.

    Returns one of:
      'skipped'           — record already has system:, left untouched.
      'stamped'           — block was added (or would be added in dry-run).
      'error:<message>'   — read/write failure.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
    except OSError as exc:
        # Review: code-reviewer Slice-B — (F7) separator space added ("error: " not "error:")
        # so the consumer slice at main():len('error: ') == 7 parses the message correctly.
        return f"error: read failed: {exc}"

    if _has_system_block(content):
        return "skipped"

    stamped = _stamp_record(content)

    if apply:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(stamped)
        except OSError as exc:
            return f"error: write failed: {exc}"  # Review: code-reviewer Slice-B — (F7)

    return "stamped"


def collect_paths(targets: list[str]) -> list[str]:
    """
    Expand CLI targets into a sorted list of YAML file paths.

    Each target is either:
    - A file path — used directly.
    - A directory path — expanded to *.yaml files within it (non-recursive).
    Unknown / missing targets emit a warning and are skipped.
    """
    paths: list[str] = []
    for target in targets:
        if os.path.isdir(target):
            pattern = os.path.join(target, "*.yaml")
            found = sorted(glob_module.glob(pattern))
            if not found:
                print(
                    f"WARNING: no *.yaml files found in directory: {target}",
                    file=sys.stderr,
                )
            paths.extend(found)
        elif os.path.isfile(target):
            paths.append(target)
        else:
            # Review: code-reviewer Slice-B — (F3) a missing EXPLICIT target is a caller
            # error (typo'd path); detect-then-fail-loud rather than warn-and-continue.
            # An existing-but-empty directory stays a warning (not fatal — valid use case:
            # directory exists but contains no *.yaml files yet).
            print(f"WARNING: target not found: {target}", file=sys.stderr)
            sys.exit(1)
    return paths


# ── CLI ────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for migrate-provenance-stamp."""
    parser = argparse.ArgumentParser(
        prog="migrate-provenance-stamp.py",
        description=(
            "Stamp an honest provenance marker onto work-item records that lack\n"
            "a top-level system: block.\n\n"
            "Accepts one or more YAML file paths and/or directory paths.\n"
            "Directories are expanded to the *.yaml files they contain\n"
            "(non-recursive).\n\n"
            "Records that already have a top-level system: key are left UNTOUCHED\n"
            "(idempotent — re-running is always a no-op for already-stamped records).\n\n"
            "Records missing system: receive the following block appended at EOF:\n"
            "  system:\n"
            "    provenance_completeness: unknown\n\n"
            "Default mode is DRY-RUN: reports what would change without modifying\n"
            "any file. Pass --apply to write changes to disk.\n\n"
            "Spec backlink: [ccos-3 plan] § C3a"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "targets",
        nargs="+",
        metavar="PATH",
        help=(
            "One or more YAML record files or directories of *.yaml files to "
            "process. Directories are searched non-recursively."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Write the provenance block to disk for each record that is missing "
            "it. Without this flag the script is a dry-run that reports what would "
            "change without modifying any file."
        ),
    )
    return parser


def main() -> int:
    """Entry point for migrate-provenance-stamp CLI."""
    parser = build_parser()
    args = parser.parse_args()

    paths = collect_paths(args.targets)
    if not paths:
        print("No YAML files found for the given targets.", file=sys.stderr)
        return 1

    apply = args.apply
    mode_label = "APPLY" if apply else "DRY-RUN"
    print(f"Mode: {mode_label}")

    stamped_count = 0
    skipped_count = 0
    error_count = 0

    for path in paths:
        result = process_file(path, apply=apply)
        if result == "skipped":
            skipped_count += 1
            print(f"  skipped (already has system:): {path}")
        elif result == "stamped":
            stamped_count += 1
            verb = "stamped" if apply else "would stamp"
            print(f"  {verb}: {path}")
        else:
            error_count += 1
            print(f"  ERROR: {path}: {result[len('error: '):]}", file=sys.stderr)  # Review: code-reviewer Slice-B — (F7) len('error: ')==7 matches updated sentinel prefix

    print()
    print(
        f"{'Applied' if apply else 'Dry-run'}: "
        f"{stamped_count} {'stamped' if apply else 'would-stamp'}, "
        f"{skipped_count} skipped, "
        f"{error_count} errors"
    )
    if not apply and stamped_count > 0:
        print("Re-run with --apply to write changes to disk.")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
