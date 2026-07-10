#!/bin/sh
# ── sh/python polyglot trampoline ──────────────────────────────────────────────
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
migrate-queues-to-base.py — Port all three queue directories to the unified base field
shape (D1/D2 from the tc-2 plan) and drain straggler bullets from debt-backlog.md.

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C6

Operations (idempotent — safe to re-run):
  1. Port improvement-queue/*.yaml:
       proposed_target → proposed_action, scope_tags → tags, drop id:
  2. Port bug-backlog/*.yaml:
       system → surface, cross_ref → evidence, recommended_fix → proposed_action, drop id:
  3. Port debt-backlog/*.yaml:
       suggested_action → proposed_action, resolved_at → closed_at,
       resolution_note → closed_by, cross_ref → evidence, drop id:
       Status: resolved→closed; open for-weekly-arch-review→open + tags:[weekly-arch-review]
  4. Archive 9 terminal (now-closed) debt entries via git mv to archive/debt-backlog/<YYYY-MM>/
  5. Drain 13 straggler bullets from state/debt-backlog.md into per-entry YAML files.

Idempotency:
  - Steps 1–3: skip entries that lack an `id:` field (already ported).
  - Step 4: skip files already absent from the open dir (already archived).
  - Step 5: skip drain targets whose output YAML file already exists.

Negative-spec:
  - Does NOT rename the 5 DSR-2026-06-23-*.yaml files (filenames stay as-is).
  - Does NOT delete state/debt-backlog.md (that is C7).
  - Does NOT touch coordinator-queue-append, query-records, or wiki files.
  - Does NOT add a `---` document-start delimiter to any file.
  - Does NOT add `id:` to newly drained entries.
"""

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

# ── Repo root resolution ───────────────────────────────────────────────────────
# Script lives at plugins/coordinator/bin/migrate-queues-to-base.py
# So __file__'s 4th ancestor is the repo root (~/.claude/).
_SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent

IMPROVEMENT_DIR = REPO_ROOT / "state" / "improvement-queue"
BUG_DIR = REPO_ROOT / "state" / "bug-backlog"
DEBT_DIR = REPO_ROOT / "state" / "debt-backlog"
ARCHIVE_DEBT_BASE = REPO_ROOT / "archive" / "debt-backlog"
DEBT_BACKLOG_MD = REPO_ROOT / "state" / "debt-backlog.md"

# ── Idempotency sentinel ───────────────────────────────────────────────────────

_HAS_ID_RE = re.compile(r"^id:", re.MULTILINE)


def _already_ported(content: str) -> bool:
    """Return True if this YAML file has no id: field (i.e. already ported)."""
    return not _HAS_ID_RE.search(content)


# ── Line-by-line field transformer ────────────────────────────────────────────

def _rename_field(line: str, old_key: str, new_key: str) -> str:
    """
    Rename a YAML key on a single line.

    Only matches lines where the key appears at column 0 (top-level field),
    followed by `:`. Value (everything after the colon) is preserved verbatim.
    """
    prefix = old_key + ":"
    if line.startswith(prefix):
        return new_key + ":" + line[len(prefix):]
    return line


def _drop_field(line: str, key: str) -> bool:
    """Return True if this line is a top-level YAML field whose key should be dropped."""
    # Review: code-reviewer — F8: second condition (key + ": ") is subsumed by the first
    # (key + ":") which matches key:, key: value, etc. — removed the redundant branch.
    return line.startswith(key + ":")


def _transform_lines(content: str, transforms) -> str:
    """
    Apply a sequence of per-line transforms to YAML content.

    Each transform is a callable(line: str) → str | None.
    Returning None drops the line.
    """
    lines = content.splitlines(keepends=True)
    out = []
    for raw_line in lines:
        result = raw_line
        for fn in transforms:
            if result is None:
                break
            result = fn(result)
        if result is not None:
            out.append(result)
    return "".join(out)


# ── Status + tag reconciliation helpers ───────────────────────────────────────

def _reconcile_debt_status(content: str) -> str:
    """
    Reconcile debt-backlog status values:
      resolved               → closed
      open for-weekly-arch-review → open  + insert `tags:\\n  - weekly-arch-review`

    Handles the case where no `tags:` block is present (all 12 open-for-weekly entries
    verified to have no existing tags field).
    """
    lines = content.splitlines(keepends=True)
    out = []
    for line in lines:
        # Review: code-reviewer F5 — rstrip("\r\n") handles CRLF; original rstrip("\n") would
        # leave \r on stripped, causing "status: resolved\r" to silently NOT match.
        stripped = line.rstrip("\r\n")
        eol = "\n" if line.endswith("\n") else ""

        if stripped == "status: resolved":
            out.append("status: closed" + eol)
        elif stripped == "status: open for-weekly-arch-review":
            out.append("status: open" + eol)
            out.append("tags:" + eol)
            out.append("  - weekly-arch-review" + eol)
        else:
            out.append(line)
    return "".join(out)


# ── Per-queue port functions ───────────────────────────────────────────────────

def port_improvement_entry(path: Path) -> str | None:
    """
    Port one improvement-queue YAML file to the unified shape.

    Returns 'skipped', 'ported', or raises on error.
    """
    content = path.read_text(encoding="utf-8")
    if _already_ported(content):
        return "skipped"

    def transform(line: str) -> str | None:
        # Drop id: field
        if _drop_field(line, "id"):
            return None
        # proposed_target → proposed_action
        line = _rename_field(line, "proposed_target", "proposed_action")
        # scope_tags → tags
        line = _rename_field(line, "scope_tags", "tags")
        return line

    new_content = _transform_lines(content, [transform])
    path.write_text(new_content, encoding="utf-8")
    return "ported"


def port_bug_entry(path: Path) -> str | None:
    """Port one bug-backlog YAML file to the unified shape."""
    content = path.read_text(encoding="utf-8")
    if _already_ported(content):
        return "skipped"

    def transform(line: str) -> str | None:
        if _drop_field(line, "id"):
            return None
        line = _rename_field(line, "system", "surface")
        line = _rename_field(line, "cross_ref", "evidence")
        line = _rename_field(line, "recommended_fix", "proposed_action")
        return line

    new_content = _transform_lines(content, [transform])
    path.write_text(new_content, encoding="utf-8")
    return "ported"


def port_debt_entry(path: Path) -> str | None:
    """Port one debt-backlog YAML file to the unified shape + reconcile status."""
    content = path.read_text(encoding="utf-8")
    if _already_ported(content):
        return "skipped"

    def transform(line: str) -> str | None:
        if _drop_field(line, "id"):
            return None
        line = _rename_field(line, "suggested_action", "proposed_action")
        line = _rename_field(line, "resolved_at", "closed_at")
        line = _rename_field(line, "resolution_note", "closed_by")
        line = _rename_field(line, "cross_ref", "evidence")
        return line

    new_content = _transform_lines(content, [transform])
    new_content = _reconcile_debt_status(new_content)
    path.write_text(new_content, encoding="utf-8")
    return "ported"


# ── Archive terminal debt entries ──────────────────────────────────────────────

_CREATED_RE = re.compile(r"^created:\s*(\S+)", re.MULTILINE)


def _get_created(content: str) -> str | None:
    """Extract the `created:` field value from YAML content."""
    m = _CREATED_RE.search(content)
    if m is None:
        return None
    # Review: code-reviewer — F11: _CREATED_RE captures \S+ which includes surrounding
    # quotes on quoted date values (e.g. created: '2026-06-25'). Strip them so the
    # downstream re.match(r"\d{4}-\d{2}-\d{2}", created) works reliably.
    return m.group(1).strip("'\"")


def archive_terminal_debt_entries() -> list[Path]:
    """
    git mv every state/debt-backlog/*.yaml with status: closed to
    archive/debt-backlog/<YYYY-MM>/ derived from its `created` field.

    Returns list of archived paths.
    """
    archived = []
    for yaml_path in sorted(DEBT_DIR.glob("*.yaml")):
        content = yaml_path.read_text(encoding="utf-8")
        # Check for closed status (after porting, resolved→closed)
        if not re.search(r"^status: closed", content, re.MULTILINE):
            continue

        # Derive archive month
        created = _get_created(content)
        if created and re.match(r"\d{4}-\d{2}-\d{2}", created):
            yyyymm = created[:7]
        else:
            # Fallback: current month
            # Review: code-reviewer — F10: import datetime moved to module level.
            yyyymm = datetime.date.today().strftime("%Y-%m")

        archive_dir = ARCHIVE_DEBT_BASE / yyyymm
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / yaml_path.name

        if dest.exists():
            print(f"  [archive] already archived: {yaml_path.name}")
            continue

        result = subprocess.run(
            ["git", "mv", str(yaml_path), str(dest)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"  [archive] ERROR git mv {yaml_path.name}: {result.stderr.strip()}",
                file=sys.stderr,
            )
        else:
            print(f"  [archive] {yaml_path.name} → archive/debt-backlog/{yyyymm}/")
            archived.append(yaml_path)

    return archived


# ── Straggler drain — debt-backlog.md ─────────────────────────────────────────

_BULLET_RE = re.compile(
    r"^-\s+\[[ x]\]\s+((?:DSR|CDX|BS)-(\d{4}-\d{2}-\d{2})-\d+)"  # DSR-YYYY-MM-DD-N
    r"\s+(?:\[([^\]]*)\]\s+)?"  # optional [tag]
    r"(.*)",  # rest of line (body + surfaces)
    re.DOTALL,
)

# Separator between body text and surfaces clause
_SURFACES_RE = re.compile(r"\s+—\s+surfaces:\s*(.+)$", re.DOTALL)

# Risk extraction for DSR-25 style entries (embedded "Risk: <text>." marker)
_RISK_INLINE_RE = re.compile(
    r"\s+Risk:\s+(.+?)(?=\.\s+Source:|\.\s+Status:|$)", re.DOTALL
)

# Source extraction from inline format
_SOURCE_INLINE_RE = re.compile(
    r"\s+Source:\s+([^.]+)\.", re.DOTALL
)

# Trailing ". Status: open." or "Status: open." at end of body
_STATUS_TRAILER_RE = re.compile(r"\.?\s+Status:\s+open\.\s*$", re.DOTALL)


def _slug_from_title(title: str) -> str:
    """Derive a kebab-case slug from a title string (≤ 40 chars)."""
    slug = title.lower()
    slug = re.sub(r"[`'\"/\\{}()\[\]*]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:40].rstrip("-")


def _derive_title(text: str) -> str:
    """Derive a title from prose text (first sentence or first 80 chars)."""
    if not text:
        return ""
    parts = re.split(r"[.!?]", text, maxsplit=1)
    candidate = parts[0].strip() if parts else text.strip()
    return candidate[:80].rstrip(".,;:")


def _yaml_scalar(val: str) -> str:
    """
    Format a string value for bare YAML output.

    Short plain values → bare.
    Long or multi-line values → block scalar (|- strips trailing newline).
    Values with YAML special characters → double-quoted.
    """
    if not val:
        return '""'
    if "\n" in val or len(val) > 70:
        # block scalar
        # Review: code-reviewer F6 — avoid emitting two-space-padded empty lines in block
        # scalar; empty split segments become "" (a true blank line) not "  " (two spaces).
        indented = "\n".join("  " + l if l else "" for l in val.split("\n"))
        return "|-\n" + indented
    # Check for special YAML characters that require quoting
    needs_quote = re.search(
        r'[:{}\[\],#|>&*!%@`]|^\?|^-\s|^ |^"', val
    )
    if needs_quote:
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return val


def _build_drain_yaml(
    dsr_id: str,
    created: str,
    source: str,
    status: str,
    tags: list[str],
    title: str,
    body: str,
    risk: str,
    proposed_action: str,
    surface: str,
    from_repo: str,
) -> str:
    """
    Build a bare YAML string for a newly drained straggler entry.

    No `---` delimiter, no `id:` field (per D2 — the filename is the handle).
    """
    lines = []
    lines.append(f"created: {created}")
    lines.append(f"source: {_yaml_scalar(source)}")
    lines.append(f"status: {status}")
    if tags:
        lines.append("tags:")
        for t in tags:
            lines.append(f"  - {t}")
    lines.append(f"title: {_yaml_scalar(title)}")
    lines.append(f"body: {_yaml_scalar(body)}")
    lines.append(f"risk: {_yaml_scalar(risk)}")
    lines.append(f"proposed_action: {_yaml_scalar(proposed_action)}")
    if surface:
        lines.append(f"surface: {_yaml_scalar(surface)}")
    lines.append(f"from_repo: {from_repo}")
    return "\n".join(lines) + "\n"


def _parse_bullet(line: str) -> dict | None:
    """
    Parse a straggler bullet entry from debt-backlog.md.

    Format: - [ ] DSR-YYYY-MM-DD-N [tag] <body text> — surfaces: <paths>

    Returns a dict with extracted fields, or None if line doesn't match.
    """
    stripped = line.strip()
    m = _BULLET_RE.match(stripped)
    if not m:
        return None

    dsr_id = m.group(1)
    date_str = m.group(2)  # YYYY-MM-DD
    tag = m.group(3) or ""
    remainder = m.group(4).strip()

    # Extract surfaces clause
    surfaces_match = _SURFACES_RE.search(remainder)
    surface = ""
    if surfaces_match:
        surface = surfaces_match.group(1).strip()
        remainder = remainder[: surfaces_match.start()].strip()

    # For DSR-25 entries: try to extract embedded Risk: marker
    risk = "see body"
    proposed_action = "manual review required"
    body = remainder

    # Try to extract "Risk: <text>." from the body
    risk_m = _RISK_INLINE_RE.search(remainder)
    if risk_m:
        risk_raw = risk_m.group(1).strip()
        # Strip any trailing ". Source:" or ". Status:" fragments
        risk_raw = re.sub(r"\s*\.\s*(Source|Status):.*$", "", risk_raw, flags=re.DOTALL).strip()
        if risk_raw:
            risk = risk_raw
        # Extract body = everything before "Risk:"
        body = remainder[: risk_m.start()].strip()
        # Also strip trailing ". Source: ... Status: open." from body
        body = _STATUS_TRAILER_RE.sub("", body).strip()
        # Strip source from body if present
        body = _SOURCE_INLINE_RE.sub("", body).strip()
        body = body.rstrip(".").strip()

    # Determine source from ID date + context
    if date_str == "2026-06-25":
        source = "workday-complete/step4/sonnet-observer/2026-06-25"
    else:
        source = "daily-review"

    # Determine tags
    tags: list[str] = []
    if "for-weekly-arch-review" in tag or "weekly" in tag.lower():
        tags.append("weekly-arch-review")

    title = _derive_title(body if body else remainder)
    # Review: code-reviewer — F4: _derive_title can return "" (empty text, no sentence
    # boundary found). An empty title violates the non-empty-title contract. Fall back
    # to the DSR id so the YAML remains structurally valid.
    if not title:
        title = dsr_id
    status = "open"

    return {
        "dsr_id": dsr_id,
        "created": date_str,
        "source": source,
        "status": status,
        "tags": tags,
        "title": title,
        "body": body if body else remainder,
        "risk": risk,
        "proposed_action": proposed_action,
        "surface": surface,
        # Review: code-reviewer F12 — migration-specific hardcode: state/debt-backlog.md
        # lives in the claude-central-em repo. Do not generalize; script is not reusable
        # across repos by design (negative-spec says "Do NOT auto-resolve from_repo from cwd").
        "from_repo": "claude-central-em",
    }


def _output_path_for_drain(entry: dict) -> Path:
    """
    Derive the output YAML path for a drain entry.

    Filename: state/debt-backlog/<created>-<slug>.yaml
    """
    slug = _slug_from_title(entry["title"])
    filename = f"{entry['created']}-{slug}.yaml"
    return DEBT_DIR / filename


def drain_straggler_bullets() -> int:
    """
    Parse all bullet entries from state/debt-backlog.md and write per-entry YAML files.

    Returns count of newly written files.
    """
    if not DEBT_BACKLOG_MD.exists():
        print("  [drain] debt-backlog.md not found — skipping drain step.")
        return 0

    md_content = DEBT_BACKLOG_MD.read_text(encoding="utf-8")
    written = 0

    for raw_line in md_content.splitlines():
        line = raw_line.strip()
        # Review: code-reviewer — F1: _BULLET_RE accepts DSR|CDX|BS prefixes but the
        # per-line pre-filter was DSR-only, silently dropping CDX-/BS- bullets. Widened.
        if not (line.startswith("- [") and re.search(r"(?:DSR|CDX|BS)-\d{4}-\d{2}-\d{2}-\d+", line)):
            continue

        entry = _parse_bullet(line)
        if entry is None:
            print(f"  [drain] WARNING: could not parse bullet: {line[:80]}...")
            continue

        dest = _output_path_for_drain(entry)
        if dest.exists():
            print(f"  [drain] already exists, skipping: {dest.name}")
            continue

        yaml_content = _build_drain_yaml(
            dsr_id=entry["dsr_id"],
            created=entry["created"],
            source=entry["source"],
            status=entry["status"],
            tags=entry["tags"],
            title=entry["title"],
            body=entry["body"],
            risk=entry["risk"],
            proposed_action=entry["proposed_action"],
            surface=entry["surface"],
            from_repo=entry["from_repo"],
        )

        dest.write_text(yaml_content, encoding="utf-8")
        print(f"  [drain] wrote: {dest.name}")
        written += 1

    return written


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"migrate-queues-to-base: repo root = {REPO_ROOT}")
    print()

    # ── Step 1: Port improvement-queue ────────────────────────────────────────
    print("Step 1: Porting improvement-queue/*.yaml …")
    iq_ported = 0
    iq_skipped = 0
    for yaml_path in sorted(IMPROVEMENT_DIR.glob("*.yaml")):
        result = port_improvement_entry(yaml_path)
        if result == "ported":
            iq_ported += 1
        else:
            iq_skipped += 1
    print(f"  ported: {iq_ported}  skipped (already done): {iq_skipped}")
    print()

    # ── Step 2: Port bug-backlog ───────────────────────────────────────────────
    print("Step 2: Porting bug-backlog/*.yaml …")
    bb_ported = 0
    bb_skipped = 0
    for yaml_path in sorted(BUG_DIR.glob("*.yaml")):
        result = port_bug_entry(yaml_path)
        if result == "ported":
            bb_ported += 1
        else:
            bb_skipped += 1
    print(f"  ported: {bb_ported}  skipped (already done): {bb_skipped}")
    print()

    # ── Step 3: Port debt-backlog ──────────────────────────────────────────────
    print("Step 3: Porting debt-backlog/*.yaml …")
    db_ported = 0
    db_skipped = 0
    for yaml_path in sorted(DEBT_DIR.glob("*.yaml")):
        result = port_debt_entry(yaml_path)
        if result == "ported":
            db_ported += 1
        else:
            db_skipped += 1
    print(f"  ported: {db_ported}  skipped (already done): {db_skipped}")
    print()

    # ── Step 4: Archive terminal debt entries ──────────────────────────────────
    print("Step 4: Archiving terminal (closed) debt entries …")
    archived = archive_terminal_debt_entries()
    print(f"  archived: {len(archived)}")
    print()

    # ── Step 5: Drain straggler bullets ───────────────────────────────────────
    print("Step 5: Draining straggler bullets from state/debt-backlog.md …")
    drain_count = drain_straggler_bullets()
    print(f"  drained: {drain_count} new entries written")
    print()

    # ── Summary ────────────────────────────────────────────────────────────────
    open_count = len(list(DEBT_DIR.glob("*.yaml")))
    archive_count = len(list(ARCHIVE_DEBT_BASE.rglob("*.yaml"))) if ARCHIVE_DEBT_BASE.exists() else 0
    print("Summary:")
    print(f"  improvement-queue: {iq_ported} ported, {iq_skipped} skipped")
    print(f"  bug-backlog:       {bb_ported} ported, {bb_skipped} skipped")
    print(f"  debt-backlog:      {db_ported} ported, {db_skipped} skipped")
    print(f"  archived:          {len(archived)}")
    print(f"  drained:           {drain_count}")
    print(f"  debt open-dir:     {open_count} files")
    print(f"  debt archive:      {archive_count} files")

    return 0


if __name__ == "__main__":
    sys.exit(main())
