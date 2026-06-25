#!/usr/bin/env python3
"""emit-lesson-summaries.py — union-join {lessons.md} ∪ {lessons-outbox/} ∪ {lessons-outbox/drained/}
into a JSON array of LessonSummary records for the cockpit snapshot emitter.

Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C3
Schema: cockpit-contract/src/entities/lesson-summary.ts (frozen — do NOT modify)

Negative-spec:
  - Do NOT re-implement the lessons.md markdown parser; shell out to extract-lessons.py extract.
  - Do NOT skip/quarantine partial records — degrade and emit (C-F2).
  - Do NOT skip drained-only entries — union is a FULL OUTER JOIN (C-F3).
  - Do NOT hardcode absolute home paths — accept repo_root as argv[1] or discover via marker.
  - Do NOT import yaml — not available in the base python3 env; use the ---fence+key:value parser.
  - `from_repo` and `repo` are DISTINCT dimensions (C-F7) — do NOT unify.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Repo-root discovery
# ---------------------------------------------------------------------------

def _find_repo_root(start: Path) -> Path:
    """Walk up from start looking for a directory with state/ + plugins/ siblings,
    which is the ~/.claude meta-repo root. Falls back to start if not found."""
    candidate = start.resolve()
    for _ in range(10):
        if (candidate / "state").is_dir() and (candidate / "plugins").is_dir():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    # Review: code-reviewer — emit a warning when falling back to cwd so callers can diagnose
    # discovery failures rather than silently operating against the wrong tree.
    sys.stderr.write(
        f"[emit-lesson-summaries] warning: could not discover repo root from {start}; using cwd\n"
    )
    return start.resolve()


# ---------------------------------------------------------------------------
# lesson_key: first 16 lowercase hex chars of sha256(normalize(title))
# normalize: lowercase, strip, collapse internal whitespace to single space
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _lesson_key(title: str) -> str:
    normalized = _normalize_title(title)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:16]


# ---------------------------------------------------------------------------
# YAML front-matter parser for outbox/drained YAML files
# Uses --- fences + key: value parsing (no yaml dep required).
# ---------------------------------------------------------------------------

def _parse_outbox_yaml(path: Path) -> dict:
    """Parse a lessons-outbox YAML file using ---fence + simple key:value parser.

    Returns a dict with keys: id, created, from_repo, change_kind, target_wiki,
    title, body, scope_tags, evidence. Missing keys → None.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Strip --- fences — collect lines between the two --- delimiters
    body_lines: list[str] = []
    fence_count = 0
    for line in lines:
        if line.strip() == "---":
            fence_count += 1
            continue
        if fence_count >= 1:
            body_lines.append(line)

    # If no --- fences found, treat entire file as YAML body
    if fence_count == 0:
        body_lines = lines

    result: dict = {}
    i = 0
    current_key: str | None = None
    is_block: bool = False
    block_lines: list[str] = []
    block_indent: int = 0

    def _flush_block() -> None:
        nonlocal current_key, is_block, block_lines, block_indent
        if current_key and is_block:
            # Review: code-reviewer — trailing blank lines within the collected block_lines
            # are absorbed (they satisfy the indentation check) and stripped at flush via
            # .strip(). This is intentional: YAML block scalars end at the next non-indented
            # line, so trailing blanks before such a line are part of the block and stripped
            # cleanly. No behavior change needed.
            result[current_key] = "\n".join(
                line[block_indent:] if len(line) > block_indent else line.lstrip()
                for line in block_lines
            ).strip()
        current_key = None
        is_block = False
        block_lines = []
        block_indent = 0

    while i < len(body_lines):
        line = body_lines[i]

        if is_block:
            # Block scalar continues until a line at same or lesser indentation
            if line == "" or (line and line[0] == " " and len(line) - len(line.lstrip()) >= block_indent):
                block_lines.append(line)
                i += 1
                continue
            else:
                _flush_block()
                # fall through to process this line as a new key

        # Match top-level key: value
        m = re.match(r'^(\w+):\s*(.*)', line)
        if m:
            _flush_block()
            key = m.group(1)
            val = m.group(2).strip()
            current_key = key

            if val in ("|", ">", "|-", ">-"):
                # Block scalar — collect subsequent indented lines
                is_block = True
                block_lines = []
                # Determine indent from the first content line
                if i + 1 < len(body_lines):
                    next_line = body_lines[i + 1]
                    stripped = next_line.lstrip()
                    block_indent = len(next_line) - len(stripped) if stripped else 2
                else:
                    block_indent = 2
            elif val.startswith('"') and val.endswith('"') and len(val) >= 2:
                # Review: code-reviewer (F10) — escape sequences inside double-quoted strings
                # (e.g. `\"`) are NOT decoded; only the outer delimiters are stripped.
                # Limitation: a scope_tags value like `"universal\"s"` would be stored with
                # the literal backslash-quote rather than a real `"`. The outbox corpus does
                # not produce escaped quotes inside field values, so this is acceptable.
                # If the corpus ever does, apply `.replace('\\"', '"')` here.
                result[key] = val[1:-1]
                current_key = None
            elif val.startswith("'") and val.endswith("'") and len(val) >= 2:
                # Same limitation: single-quoted strings have no escape decoding.
                result[key] = val[1:-1]
                current_key = None
            elif val.strip().lower() == "null":
                # Review: code-reviewer — bare `null` YAML literal was previously absorbed by
                # the truthy `elif val:` branch and stored as the string "null". Intercept it
                # here and map to Python None, matching YAML semantics.
                result[key] = None
                current_key = None
            elif val:
                result[key] = val
                current_key = None
            else:
                # Review: code-reviewer (F1) — do NOT clear current_key on empty value.
                # A block-list-form field like `scope_tags:\n  - universal` has an empty
                # value on the key line; the list items on the next lines need current_key
                # to be live so the list-item branch (`re.match r"^\s{2,}-"`) can fire.
                # We set result[key]=None as a placeholder; the list-item branch replaces
                # None with a list on first item.
                result[key] = None
                # current_key intentionally NOT cleared here
        elif re.match(r"^\s{2,}- ", line) and current_key and not is_block:
            # Review: code-reviewer — broadened from literal "  - " (2-space) to any indent ≥2
            # so 4-space-indented list items (valid YAML) are also matched.
            # List item (e.g. scope_tags)
            existing = result.get(current_key)
            item = line.strip().lstrip("- ")
            if isinstance(existing, list):
                existing.append(item)
            else:
                result[current_key] = [item]
        i += 1

    _flush_block()

    # Normalize scope_tags to list
    if "scope_tags" in result and isinstance(result["scope_tags"], str):
        raw = result["scope_tags"].strip("[]")
        result["scope_tags"] = [t.strip() for t in raw.split(",") if t.strip()] if raw else []
    elif "scope_tags" not in result:
        result["scope_tags"] = []

    return result


# ---------------------------------------------------------------------------
# Load lessons from each surface
# ---------------------------------------------------------------------------

def _load_lessons_md(repo_root: Path, repo_name: str, coordinator_root: Path) -> dict[str, dict]:
    """Shell out to extract-lessons.py extract and return a map of lesson_key→record."""
    lessons_md = repo_root / "state" / "lessons.md"
    if not lessons_md.is_file():
        return {}

    extract_script = coordinator_root / "bin" / "extract-lessons.py"
    if not extract_script.is_file():
        return {}

    try:
        # creationflags: portable CREATE_NO_WINDOW — prevents console popup on Windows;
        # resolves to 0 (no-op) on macOS/Linux.
        result = subprocess.run(
            [sys.executable, str(extract_script), "extract",
             str(lessons_md), "--shortname", repo_name, "--format", "json"],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            sys.stderr.write(f"[emit-lesson-summaries] extract-lessons.py failed: {result.stderr}\n")
            return {}
        data = json.loads(result.stdout)
    except Exception as e:
        sys.stderr.write(f"[emit-lesson-summaries] error calling extract-lessons.py: {e}\n")
        return {}

    records = data.get("records", [])
    out: dict[str, dict] = {}
    for rec in records:
        title = rec.get("title") or ""
        if not title:
            # Review: code-reviewer (F9) — degrade-but-count, not silent-drop (C-F2/AC7).
            # Synthesize a key from the body hash (or source path) so the join produces an
            # [unparseable-...] sentinel with parse_status=partial rather than silently
            # omitting the record.  Body hash keeps the key stable across re-runs.
            body = rec.get("body") or rec.get("source", "") or ""
            synthetic = hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]
            key = _lesson_key(synthetic)
        else:
            key = _lesson_key(title)
        out[key] = rec

    return out


def _load_outbox_dir(dirpath: Path) -> dict[str, dict]:
    """Load all .yaml files from an outbox dir. Returns map of lesson_key→parsed_record."""
    if not dirpath.is_dir():
        return {}
    out: dict[str, dict] = {}
    for yaml_file in sorted(dirpath.glob("*.yaml")):
        try:
            rec = _parse_outbox_yaml(yaml_file)
        except Exception as e:
            sys.stderr.write(f"[emit-lesson-summaries] error parsing {yaml_file}: {e}\n")
            continue
        title = rec.get("title") or ""
        if not title:
            # Review: code-reviewer (F8) — degrade-but-count, not silent-drop (C-F2/AC7).
            # Key off the filename so the join produces an [unparseable-...] sentinel with
            # parse_status=partial rather than silently omitting the file from the output.
            key = _lesson_key(str(yaml_file))
            rec["title"] = ""  # build_lesson_summaries will produce the sentinel title
        else:
            key = _lesson_key(title)
        rec["_source_path"] = str(yaml_file)
        # Review: code-reviewer — silent last-writer-wins on duplicate lesson_key; warn now
        if key in out:
            sys.stderr.write(
                f"[emit-lesson-summaries] duplicate lesson_key {key!r} in outbox dir"
                f" — first: {out[key].get('_source_path', '?')!r},"
                f" last (wins): {str(yaml_file)!r}\n"
            )
        out[key] = rec
    return out


# ---------------------------------------------------------------------------
# Derive scope from lessons.md record or outbox scope_tags
# ---------------------------------------------------------------------------

def _scope_from_outbox(rec: dict) -> str:
    # Review: code-reviewer — removed body-scan fallback for [universal]; it caused false
    # positives when prose content mentioned "[universal]". Scope is determined solely from
    # scope_tags; default is "project" when scope_tags do not indicate universal.
    tags = rec.get("scope_tags") or []
    if isinstance(tags, list):
        for t in tags:
            if "universal" in str(t).lower():
                return "universal"
    return "project"


# ---------------------------------------------------------------------------
# Build a single LessonSummary record
# ---------------------------------------------------------------------------

def _make_record(
    lesson_key: str,
    title: str,
    scope: str,
    body: str,
    promotion_state: str,
    parse_status: str,
    prov_path: str,
    repo: str,
    git_branch: str,
    git_sha: str,
    observed_at: str,
    # nullable fields (D9 — present-as-null, never omitted)
    change_kind: str | None = None,
    target_wiki: str | None = None,
    from_repo: str | None = None,
    evidence: str | None = None,
    created: str | None = None,
) -> dict:
    return {
        "repo": repo,
        "coordinator_root_path": ".",
        "lesson_key": lesson_key,
        "title": title,
        "scope": scope,
        "body": body,
        "promotion_state": promotion_state,
        "parse_status": parse_status,
        "provenance": {
            "source_kind": "local_fs",
            "repo": repo,
            "ref": {"branch": git_branch, "sha": git_sha},
            "path": prov_path,
            "observed_at": observed_at,
            "derivation": "parsed",
        },
        # Nullable fields — present-as-null per D9
        "change_kind": change_kind,
        "target_wiki": target_wiki,
        "from_repo": from_repo,
        "evidence": evidence,
        "created": created,
    }


# ---------------------------------------------------------------------------
# Main join logic
# ---------------------------------------------------------------------------

def build_lesson_summaries(
    repo_root: Path,
    coordinator_root: Path,
    repo_name: str,
    git_branch: str,
    git_sha: str,
    observed_at: str,
) -> list[dict]:
    """Union {lessons.md} ∪ {outbox/} ∪ {drained/} and dedup on lesson_key.

    promotion_state precedence (C-F3, first match wins):
      1. Present in drained/ → "drained"
      2. Present in outbox/ (not drained) → "pending"
      3. Present in lessons.md only → "captured"

    An entry ONLY in drained/ (not in lessons.md) IS emitted — full outer join,
    not left-join. This is the load-bearing correctness property (AC6).
    """
    lessons_md_map = _load_lessons_md(repo_root, repo_name, coordinator_root)
    outbox_dir = repo_root / "state" / "lessons-outbox"
    drained_dir = outbox_dir / "drained"

    outbox_map = _load_outbox_dir(outbox_dir)
    drained_map = _load_outbox_dir(drained_dir)

    # Full union of all lesson_keys across all three surfaces
    all_keys: set[str] = set(lessons_md_map) | set(outbox_map) | set(drained_map)

    records: list[dict] = []
    for key in sorted(all_keys):  # sorted for deterministic output
        in_md = key in lessons_md_map
        in_outbox = key in outbox_map
        in_drained = key in drained_map

        # Determine promotion_state (C-F3 — first match wins)
        if in_drained:
            promotion_state = "drained"
            outbox_rec: dict | None = drained_map[key]
            prov_path = outbox_rec.get("_source_path", "state/lessons-outbox/drained")
        elif in_outbox:
            promotion_state = "pending"
            outbox_rec = outbox_map[key]
            prov_path = outbox_rec.get("_source_path", "state/lessons-outbox")
        else:
            promotion_state = "captured"
            outbox_rec = None
            prov_path = "state/lessons.md"

        parse_status = "ok"
        title = ""
        scope = "project"
        body = ""
        change_kind = None
        target_wiki = None
        from_repo = None
        evidence = None
        created = None

        if in_md:
            md_rec = lessons_md_map[key]
            title = md_rec.get("title") or ""
            body = md_rec.get("body") or ""
            scope = "universal" if md_rec.get("tag_universal") else "project"
            if not title or not body:
                parse_status = "partial"
        elif outbox_rec is not None:
            # Drained/outbox-only entry (not in lessons.md) — full outer join case
            title = outbox_rec.get("title") or ""
            body = outbox_rec.get("body") or ""
            scope = _scope_from_outbox(outbox_rec)
            if not title or not body:
                parse_status = "partial"
        else:
            # Should never happen (key came from one of the three maps), but be safe
            parse_status = "partial"

        # Overlay promotion metadata from outbox/drained record.
        # Review: code-reviewer (F14) — body is intentionally NOT overlaid from the outbox
        # record here. lessons.md is the canonical body spine (extract-lessons.py-as-spine
        # principle): when the lesson exists in lessons.md, body was already set from md_rec
        # above; for outbox/drained-only entries (full outer join case) body was set from
        # outbox_rec in the elif branch. The outbox/drained record only supplies promotion
        # metadata (change_kind, target_wiki, from_repo, evidence, created) — never body.
        # Changing this would mean outbox prose silently overwrites a potentially richer
        # lessons.md body for lessons present in both surfaces.
        if outbox_rec is not None:
            if not title:
                title = outbox_rec.get("title") or ""
            change_kind = outbox_rec.get("change_kind") or None
            target_wiki = outbox_rec.get("target_wiki") or None
            from_repo = outbox_rec.get("from_repo") or None
            evidence = outbox_rec.get("evidence") or None
            raw_created = outbox_rec.get("created")
            if raw_created:
                raw_created = str(raw_created).strip('"\'')
                created = raw_created if raw_created else None

        if not title:
            parse_status = "partial"
            title = f"[unparseable-{key}]"

        records.append(_make_record(
            lesson_key=key,
            title=title,
            scope=scope,
            body=body,
            promotion_state=promotion_state,
            parse_status=parse_status,
            prov_path=prov_path,
            repo=repo_name,
            git_branch=git_branch,
            git_sha=git_sha,
            observed_at=observed_at,
            change_kind=change_kind,
            target_wiki=target_wiki,
            from_repo=from_repo,
            evidence=evidence,
            created=created,
        ))

    return records


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Usage: emit-lesson-summaries.py <repo_root> <repo_name> [git_branch] [git_sha] [observed_at]

    repo_root and repo_name are required positional args (argv[0] and argv[1]).
    git_branch, git_sha, observed_at are optional; auto-discovered if omitted.
    Prints a JSON array of LessonSummary records to stdout.
    """
    # Discover coordinator root (this script lives at coordinator/bin/lib/)
    script_dir = Path(__file__).resolve().parent
    coordinator_root = script_dir.parent.parent  # bin/lib/ -> bin/ -> coordinator/

    # Repo root: coordinator -> plugins -> .claude/
    repo_root_inferred = coordinator_root.parent.parent.parent
    if not ((repo_root_inferred / "state").is_dir() and (repo_root_inferred / "plugins").is_dir()):
        repo_root_inferred = _find_repo_root(Path.cwd())

    argv = sys.argv[1:]
    # Review: code-reviewer — repo_name had a hardcoded author-identity default; now required arg
    if len(argv) <= 1:
        sys.stderr.write(
            "Usage: emit-lesson-summaries.py <repo_root> <repo_name>"
            " [git_branch] [git_sha] [observed_at]\n"
        )
        sys.exit(2)
    repo_root = Path(argv[0])
    repo_name = argv[1]
    git_branch = argv[2] if len(argv) > 2 else _git_branch(repo_root)
    git_sha = argv[3] if len(argv) > 3 else _git_sha(repo_root)
    observed_at = argv[4] if len(argv) > 4 else _now_iso()

    records = build_lesson_summaries(
        repo_root=repo_root,
        coordinator_root=coordinator_root,
        repo_name=repo_name,
        git_branch=git_branch,
        git_sha=git_sha,
        observed_at=observed_at,
    )

    print(json.dumps(records, ensure_ascii=False))


def _git_branch(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _git_sha(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _now_iso() -> str:
    # Review: code-reviewer — moved import to module top; replaced deprecated utcnow() with
    # timezone-aware now(timezone.utc) per Python 3.12+ deprecation path.
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    main()
