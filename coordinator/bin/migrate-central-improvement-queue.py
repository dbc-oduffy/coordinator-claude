#!/bin/sh
# ── sh/python polyglot trampoline ──────────────────────────────────────────────
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
"""
migrate-central-improvement-queue.py — one-shot migration of the universal central
improvement queue from prose (state/coordinator-improvement-queue.md) into structured
YAML records under state/improvement-queue/<date>-<slug>.yaml.

Each produced record:
  - type: improvement (implicit in directory placement)
  - queue_scope: central
  - from_repo: parsed from the prose <source-repo> field (NOT auto-resolved)
  - [recurring: N] → scope_tags: ["recurring:N"]
  - change_kind inferred from proposed_target path

Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C2a  # Review: code-reviewer (F6) — corrected from stale 2026-06-22 plan path
Research: state/roadmap/cockpit-contract-ext-2026-06-22/research-corpus/central-queue-restructure.md

Negative-spec:
  - Do NOT auto-resolve from_repo from cwd — the prose field names the originating repo.
  - Do NOT invoke coordinator-queue-append — it lacks queue_scope and from_repo override
    in combination; write YAML directly.
  - Do NOT commit — caller (EM) commits the union.
  - Do NOT touch existing state/improvement-queue/*.yaml files (per-project rows).
"""

from __future__ import annotations  # Review: code-reviewer (F4) — dict | None syntax requires 3.10+ without this; add for 3.9 compat (mirrors emit-lesson-summaries.py)

import sys
import os
import re
import uuid
import datetime
import argparse


# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_INPUT = os.path.join(
    os.path.expanduser("~"), ".claude", "state", "coordinator-improvement-queue.md"
)
DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "state", "improvement-queue"
)

# Source-repo normalisation: prose uses short names; map to registry shortnames.
# Identity: if not in this map, use the raw string as-is.
_REPO_NORMALISE = {
    # Review: code-reviewer (F5) — duplicate keys removed; Python dict literals silently keep
    # the last occurrence when a key appears twice, so duplicates were harmless but confusing.
    "self": "claude-central-em",
    "claude-central": "claude-central-em",
    "coordinator (.claude)": "claude-central-em",
    "coordinator-claude (~/.claude)": "claude-central-em",
    ".claude (coord meta-repo)": "claude-central-em",
    ".claude (meta-repo)": "claude-central-em",
    ".claude(meta)": "claude-central-em",
    ".claude(meta-repo)": "claude-central-em",
    ".claude (meta)": "claude-central-em",
    "~/.claude": "claude-central-em",
    "~/.claude (claude-central)": "claude-central-em",
    "~/.claude (coordinator-root-system-prereqs)": "claude-central-em",
    "~/.claude (meta)": "claude-central-em",
    "~/.claude (meta-repo)": "claude-central-em",
    "claude-central (~/.claude)": "claude-central-em",
}

# change_kind inference rules from proposed_target (first match wins).
_CHANGE_KIND_RULES = [
    ("SKILL.md", "skill-edit"),
    ("skills/", "skill-edit"),
    ("hooks/", "hook-edit"),
    ("docs/wiki/", "wiki-append"),
    ("wiki/", "wiki-append"),
    (".sh", "script-edit"),
    (".py", "script-edit"),
    ("bin/", "script-edit"),
    ("agents/", "agent-prompt-edit"),
    ("commands/", "wiki-append"),
]
_CHANGE_KIND_DEFAULT = "script-edit"

_PROPOSED_TARGET_PREFIX = "proposed target: "

# Regex to extract [recurring: N] suffix.
_RECURRING_RE = re.compile(r"\[recurring:\s*(\d+)\]", re.IGNORECASE)


# ── Source-repo normalisation ──────────────────────────────────────────────────


def _normalise_from_repo(raw: str) -> str:
    """
    Normalise the prose <source-repo> field to a registry shortname.

    Priority:
      1. Exact match in _REPO_NORMALISE map.
      2. Substring match (handles parenthetical variants like "~/.claude (meta)").
      3. Raw string as-is (preserves project-rag, claude-unreal-holodeck, etc.).
    """
    stripped = raw.strip()
    if stripped in _REPO_NORMALISE:
        return _REPO_NORMALISE[stripped]
    # Try case-insensitive exact match.
    lower = stripped.lower()
    for key, val in _REPO_NORMALISE.items():
        if key.lower() == lower:
            return val
    # Substring heuristics for common aliases.
    if "claude-central" in lower or "coordinator" in lower:
        if "~/.claude" in stripped or ".claude" in stripped or "meta" in lower:
            return "claude-central-em"
    if stripped.startswith("~/.claude"):
        return "claude-central-em"
    # Return raw — peer repos (project-rag, claude-unreal-holodeck, etc.) keep their name.
    return stripped


# ── change_kind inference ──────────────────────────────────────────────────────


def _infer_change_kind(proposed_target: str) -> tuple:
    """
    Infer change_kind from the proposed_target field.

    Returns (change_kind, is_ambiguous).
    """
    for substring, kind in _CHANGE_KIND_RULES:
        if substring in proposed_target:
            return kind, False
    return _CHANGE_KIND_DEFAULT, True


# ── Slug ───────────────────────────────────────────────────────────────────────


def _slugify(title: str, max_len: int = 40) -> str:
    """
    Produce a filename-safe slug from title.
    Lowercase alphanumeric + hyphens, max max_len chars.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_len].rstrip("-")


# ── YAML serialisation ─────────────────────────────────────────────────────────


def _yaml_str(value: str) -> str:
    """
    Emit a YAML scalar string.

    Rules:
      - If it contains a colon followed by a space, newline, or end-of-string,
        or starts with a special YAML character, wrap in double quotes with
        internal double-quotes escaped.
      - Otherwise emit bare.
    """
    needs_quoting = (
        value.startswith(("- ", "| ", "> ", "!", "&", "*", "{", "[", "\"", "'", "`"))
        or ": " in value
        or value.endswith(":")
        or "\n" in value
        or value.startswith(" ")
        or value.endswith(" ")
    )
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _write_yaml(path: str, record: dict) -> None:
    """Write a single improvement-queue record to a YAML file (no --- delimiters)."""
    lines = []
    # Required fields in canonical order (matches existing project YAML shape).
    lines.append(f"id: {record['id']}")
    lines.append(f"created: {record['created']}")
    lines.append(f"from_repo: {_yaml_str(record['from_repo'])}")
    lines.append(f"queue_scope: central")
    lines.append(f"title: {_yaml_str(record['title'])}")
    lines.append(f"body: {_yaml_str(record['body'])}")
    lines.append(f"surface: {_yaml_str(record['surface'])}")
    lines.append(f"proposed_target: {_yaml_str(record['proposed_target'])}")
    lines.append(f"change_kind: {record['change_kind']}")
    if record.get("scope_tags"):
        tags = ", ".join(record["scope_tags"])
        lines.append(f"scope_tags: [{tags}]")
    lines.append(f"status: open")
    lines.append("")  # trailing newline

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ── Row parsing ────────────────────────────────────────────────────────────────


def _parse_row(line: str) -> dict | None:
    """
    Parse a single prose improvement-queue entry line.

    Format: - YYYY-MM-DD | <source-repo> | <source-file>:<line> | <body> | proposed target: <target>

    Returns None for non-entry lines. Returns a dict with classification and fields.

    Classification:
      "to-migrate"         — clean 5-cell row
      "parse-error"        — fewer than 5 cells or required cells empty
    """
    stripped = line.strip()
    if not stripped.startswith("- "):
        return None

    body_text = stripped[2:].strip()

    # Extract [recurring: N] before splitting (it might appear anywhere).
    recurring_match = _RECURRING_RE.search(body_text)
    scope_tags = []
    if recurring_match:
        n = recurring_match.group(1)
        scope_tags.append(f"recurring:{n}")
        body_text = _RECURRING_RE.sub("", body_text).strip()

    # Split on | — prefer 5 cells (date, repo, source, body, target).
    # 4-cell rows (no proposed target field) are accepted with a TBD target.
    raw_cells = body_text.split("|")
    if len(raw_cells) < 4:
        return {
            "classification": "parse-error",
            "entry_text": stripped,
            "reason": f"Expected ≥4 pipe-cells, got {len(raw_cells)}.",
        }

    created = raw_cells[0].strip()
    source_repo = raw_cells[1].strip()
    surface = raw_cells[2].strip()
    # Body: everything in cell 4; may span multiple original characters.
    body = raw_cells[3].strip()
    # Proposed target: cell 5+ joined (handles bodies with extra pipes).
    # If only 4 cells, set TBD and note it in body.
    if len(raw_cells) >= 5:
        proposed_target_raw = "|".join(raw_cells[4:]).strip()
    else:
        proposed_target_raw = "TBD - see body for full context"

    # Validate required cells.
    missing = [
        name
        for name, val in [
            ("created", created),
            ("source_repo", source_repo),
            ("body", body),
            ("proposed_target_raw", proposed_target_raw),
        ]
        if not val
    ]
    if missing:
        return {
            "classification": "parse-error",
            "entry_text": stripped,
            "reason": f"Empty required cell(s): {', '.join(missing)}.",
        }

    # Strip "proposed target: " prefix.
    if proposed_target_raw.lower().startswith(_PROPOSED_TARGET_PREFIX.lower()):
        proposed_target = proposed_target_raw[len(_PROPOSED_TARGET_PREFIX):].strip()
    else:
        proposed_target = proposed_target_raw

    # Normalise from_repo.
    from_repo = _normalise_from_repo(source_repo)

    # Synthesize title: first 80 chars of body.
    title = body[:80].rstrip()

    # Infer change_kind from proposed_target.
    change_kind, is_ambiguous = _infer_change_kind(proposed_target)

    return {
        "classification": "to-migrate",
        "entry_text": stripped,
        "created": created,
        "source_repo": source_repo,
        "from_repo": from_repo,
        "surface": surface,
        "body": body,
        "proposed_target": proposed_target,
        "title": title,
        "change_kind": change_kind,
        "scope_tags": scope_tags,
        "is_ambiguous": is_ambiguous,
    }


# ── Main migration ─────────────────────────────────────────────────────────────


def migrate(input_path: str, output_dir: str, dry_run: bool) -> tuple[int, int, list] | int:
    """
    Parse input_path and write one YAML file per row to output_dir.

    Returns (migrated, errors, written_paths) on success, or -1 on file-not-found.

    Review: code-reviewer (F3/F13) — annotation was `-> int` but the function returns a tuple
    on the success path and -1 on file-not-found. Corrected to reflect both shapes.
    """
    if not os.path.exists(input_path):
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return -1

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    migrated = 0
    errors = 0
    skipped = 0
    written_paths = []

    for idx, raw_line in enumerate(lines, start=1):
        parsed = _parse_row(raw_line)
        if parsed is None:
            # Non-entry line.
            skipped += 1
            continue

        if parsed["classification"] == "parse-error":
            print(
                f"  SKIP line {idx} (parse-error): {parsed['reason']} — {parsed['entry_text'][:60]}",
                file=sys.stderr,
            )
            errors += 1
            continue

        # Build the record.
        record_id = str(uuid.uuid4())
        slug = _slugify(parsed["title"])
        created = parsed["created"]
        # Normalise date: if it looks like YYYY-MM-DD, use as-is.
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", created):
            # Fall back to today.
            created = datetime.date.today().isoformat()
            print(
                f"  WARN line {idx}: non-ISO created date '{parsed['created']}', "
                f"using today ({created})",
                file=sys.stderr,
            )

        filename = f"{created}-{slug}.yaml"
        out_path = os.path.join(output_dir, filename)

        # Handle filename collisions by appending a short ID suffix.
        # Review: code-reviewer (F7) — re-run overwrite hazard: if the collision-resolved
        # filename already exists on disk AND was not written this run (i.e. it's a pre-existing
        # file from a previous run), warn and skip rather than silently overwriting it.
        # This is a one-shot script; idempotency is defensive — the EM re-runs should not
        # clobber YAML files that may have been manually edited or archived.
        if os.path.exists(out_path) or filename in [os.path.basename(p) for p in written_paths]:
            short = record_id[:8]
            filename = f"{created}-{slug}-{short}.yaml"
            out_path = os.path.join(output_dir, filename)
            # After collision resolution, check if the new path also exists from a prior run
            if os.path.exists(out_path) and out_path not in written_paths:
                print(
                    f"  WARN line {idx}: collision-resolved path already exists from a prior run "
                    f"({filename}) — skipping to avoid overwrite. Delete the file to re-migrate.",
                    file=sys.stderr,
                )
                errors += 1
                continue

        record = {
            "id": record_id,
            "created": created,
            "from_repo": parsed["from_repo"],
            "title": parsed["title"],
            "body": parsed["body"],
            "surface": parsed["surface"],
            "proposed_target": parsed["proposed_target"],
            "change_kind": parsed["change_kind"],
            "scope_tags": parsed["scope_tags"],
        }

        if dry_run:
            print(
                f"  [dry-run] line {idx}: would write {filename} "
                f"(from_repo={parsed['from_repo']!r}, change_kind={parsed['change_kind']!r}"
                + (" [ambiguous]" if parsed["is_ambiguous"] else "")
                + ")"
            )
        else:
            _write_yaml(out_path, record)
            print(f"  wrote: {filename}")

        written_paths.append(out_path)
        migrated += 1

    return migrated, errors, written_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-central-improvement-queue.py",
        description=(
            "One-shot migration of state/coordinator-improvement-queue.md "
            "(pipe-delimited prose) into structured YAML files under "
            "state/improvement-queue/ with queue_scope: central.\n\n"
            "Spec backlink: C2a of 2026-06-22-project-opticon-cockpit-contract plan."
        ),
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        metavar="PATH",
        help=f"Path to coordinator-improvement-queue.md. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        metavar="PATH",
        help=f"Directory to write YAML files into. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify all entries and print what would be written; do not write files.",
    )
    args = parser.parse_args()

    print(f"Input:      {args.input}")
    print(f"Output dir: {args.output_dir}")
    if args.dry_run:
        print("Mode:       dry-run (no files written)")
    print()

    result = migrate(args.input, args.output_dir, args.dry_run)
    if result == -1:
        return 1

    migrated, errors, written_paths = result
    print()
    print(f"Summary: {migrated} migrated, {errors} parse-errors (skipped).")
    if errors > 0:
        print(
            "WARNING: some rows had parse errors — review stderr output above.",
            file=sys.stderr,
        )

    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
