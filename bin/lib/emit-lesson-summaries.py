#!/usr/bin/env python3
"""emit-lesson-summaries.py — union-join {state/lessons/} ∪ {lessons-outbox/} ∪ {lessons-outbox/drained/}
into a JSON array of LessonSummary records for the cockpit snapshot emitter.

Spec backlink: docs/plans/2026-06-23-cockpit-contract-ext-wave2-emit-and-queue-migration.md § C3
Schema: cockpit-contract/src/entities/lesson-summary.ts (frozen — do NOT modify)

Negative-spec:
  - Do NOT re-implement the YAML frontmatter parser; reuse _parse_outbox_yaml (---fence + key:value).
  - Do NOT skip/quarantine partial records — degrade and emit (C-F2).
  - Do NOT skip drained-only entries — union is a FULL OUTER JOIN (C-F3).
  - Do NOT hardcode absolute home paths — repo_root is a required positional CLI arg (argv[0]).
  - Do NOT emit absolute operator-home provenance paths — relativize to repo-root-relative
    POSIX at source (via _relativize_prov_path), matching the goals/handoff conventions in the
    same cockpit envelope. Absolute paths leak /Users/<operator> and machine-lock parity.
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

def _load_lessons_yaml_dir(repo_root: Path) -> dict[str, dict]:
    """Enumerate state/lessons/*.yaml and return a map of lesson_key→record.

    Reads title, body, scope, created, status, from_repo, evidence, target_wiki
    from each per-entry YAML file's frontmatter. The ---fence + key:value parser
    (_parse_outbox_yaml) is reused — no yaml module dependency.

    Returns an empty dict if state/lessons/ does not exist (fleet not yet migrated).

    Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3c
    Negative-spec:
      - Do NOT fall back to state/lessons.md — if the YAML dir is absent, return {}.
      - Do NOT import yaml — reuse _parse_outbox_yaml (---fence+key:value parser).
      - Do NOT shell out to extract-lessons.py — fields are stored in YAML frontmatter.
    """
    lessons_dir = repo_root / "state" / "lessons"
    if not lessons_dir.is_dir():
        return {}
    out: dict[str, dict] = {}
    for yaml_file in sorted(lessons_dir.glob("*.yaml")):
        try:
            fm = _parse_outbox_yaml(yaml_file)
        except Exception as e:
            sys.stderr.write(f"[emit-lesson-summaries] error parsing {yaml_file}: {e}\n")
            continue
        title = fm.get("title") or ""
        if not title:
            # Degrade-but-count: key off filename so join produces a sentinel.
            key = _lesson_key(str(yaml_file.name))
            fm["title"] = ""
        else:
            key = _lesson_key(title)
        scope = fm.get("scope") or ""
        raw_created = fm.get("created")
        rec = {
            "title": title,
            "body": fm.get("body") or "",
            # tag_universal: join logic reads this to derive scope="universal"
            "tag_universal": scope == "universal",
            "_source_path": str(yaml_file),
            # Stored fields — available for future overlay; not forwarded to the output
            # record by the current join logic when outbox_rec is None.
            "from_repo": fm.get("from_repo") or None,
            "target_wiki": fm.get("target_wiki") or None,
            "evidence": fm.get("evidence") or None,
            "created": str(raw_created).strip("\"'") if raw_created else None,
            "status": fm.get("status") or None,
        }
        if key in out:
            sys.stderr.write(
                f"[emit-lesson-summaries] duplicate lesson_key {key!r} in lessons dir"
                f" — first: {out[key].get('_source_path', '?')!r},"
                f" last (wins): {str(yaml_file)!r}\n"
            )
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
# Normalize a `created` value from per-entry YAML to a valid IsoDateTime or None.
# ---------------------------------------------------------------------------

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # Note (F6): matches calendrically invalid dates (e.g. "2026-13-45"); schema validation catches these downstream.
_SENTINEL_DATE = "0000-00-00"


def _normalize_created(val: str | None) -> str | None:
    """Coerce a raw `created` string from state/lessons/*.yaml into IsoDateTime or None.

    Rules (in order):
      - None / empty string → None  (missing value)
      - "0000-00-00" → None         (sentinel for unknown date — emit honest null, NOT
                                     the fake "0000-00-00T00:00:00Z" which would mislead
                                     date-bounded queries into thinking they have a real ts)
      - YYYY-MM-DD (date-only)      → "YYYY-MM-DDT00:00:00Z"  (honest start-of-day-UTC
                                     widening so it satisfies the IsoDateTime contract)
      - already contains "T"        → pass through unchanged (assume caller supplied valid IsoDateTime)

    Applied on the captured/lessons-dir forward path where per-entry YAMLs store only a
    date-only `created`. The outbox/drained path uses coordinator-lesson-promote output
    which is already IsoDateTime; applying this helper there is safe but not required.

    Spec backlink: docs/plans/2026-06-30-lesson-structured-facets-and-emit-metadata-fix.md § C1
    """
    if not val:
        return None
    s = str(val).strip().strip("\"'")
    if not s:
        return None
    if s == _SENTINEL_DATE:
        return None
    if "T" in s:
        # Review: code-reviewer (F3) — regex-guard ISO shape to catch malformed datetimes
        # like "2026-01-01T" or non-Z offsets that slip through silently. Warn on mismatch
        # but still pass through so schema validation downstream can flag the value.
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", s):
            sys.stderr.write(
                f"[emit-lesson-summaries] warning: created value {s!r} contains 'T'"
                " but does not match ISO datetime shape — passing through\n"
            )
        return s
    if _DATE_ONLY_RE.match(s):
        return s + "T00:00:00Z"
    # Unrecognised format — pass through; schema validator will catch it
    return s


# ---------------------------------------------------------------------------
# Relativize a provenance path to repo-root-relative POSIX
# ---------------------------------------------------------------------------

def _relativize_prov_path(prov_path: str, repo_root: Path) -> str:
    """Coerce a provenance path to repo-root-relative POSIX form.

    The cockpit LessonSummary provenance path must be portable: an absolute
    operator-home path (e.g. /Users/<operator>/X/<repo>/state/lessons/x.yaml)
    both leaks the operator's home directory into the ingested cockpit artifact
    and machine-locks parity to one checkout path — a consumer/CI/fresh-clone at
    a different path cannot reproduce it. Emit repo-root-relative POSIX to match
    the goals/handoff provenance conventions already used in the same envelope.
    Values only — schema shape/key/version are unchanged.

    Spec backlink: cross-repo/archive/2026-07-21-claude-klabauter-em-lessons-producer-absolute-provenance-path-relativize-at-source.md
    """
    p = Path(prov_path)
    if not p.is_absolute():
        # Already relative (e.g. the "state/lessons" fallback strings) — POSIX-normalize only.
        return p.as_posix()
    # Review: code-reviewer (Finding 3) — the two-iteration relative_to loop is dead defensive
    # code now that repo_root is resolved once at build_lesson_summaries entry (Finding 1):
    # every p is constructed by joining onto that same resolved repo_root, so a single
    # relative_to attempt covers the real case; the ValueError fallback below is purely
    # never-crash safety, not an expected path.
    try:
        return p.relative_to(repo_root).as_posix()
    except ValueError:
        pass
    # Absolute but outside repo_root (should not happen by construction now that repo_root is
    # resolved at entry — Finding 1) — fall back to a relative path so we never emit the raw
    # absolute operator-home path.
    # Review: code-reviewer (Finding 2) — os.path.relpath raises ValueError on Windows
    # cross-drive paths (repo is Windows-primary); never let this "should not happen" branch
    # crash the emitter — degrade to the raw POSIX-normalized absolute-turned-string path with
    # a stderr warning, matching the file's existing degrade-and-emit convention.
    try:
        return Path(os.path.relpath(str(p), str(repo_root))).as_posix()
    except ValueError:
        sys.stderr.write(
            f"[emit-lesson-summaries] warning: could not relativize {p!r} against"
            f" repo_root {repo_root!r} (cross-drive?) — emitting as-is\n"
        )
        return p.as_posix()


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
            # source_kind:local_fs is non-git; ProvenanceEnvelope requires
            # ref:null for non-git source_kinds (D9 — see
            # artifact-shape-contract.schema.json ~line 4482-4485). The
            # lesson YAML is read from the working tree (possibly
            # uncommitted), so branch/sha is emission context, not source
            # identity; repo is already carried above and in provenance.
            "ref": None,
            "path": prov_path,
            "observed_at": observed_at,
            "derivation": "parsed",
            "entity_anchor": None,
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
    repo_name: str,
    git_branch: str,
    git_sha: str,
    observed_at: str,
) -> list[dict]:
    """Union {state/lessons/} ∪ {outbox/} ∪ {drained/} and dedup on lesson_key.

    promotion_state precedence (C-F3, first match wins):
      1. Present in drained/ → "drained"
      2. Present in outbox/ (not drained) → "pending"
      3. Present in lessons.md only → "captured"

    An entry ONLY in drained/ (not in lessons.md) IS emitted — full outer join,
    not left-join. This is the load-bearing correctness property (AC6).
    """
    # Review: code-reviewer (Finding 1) — resolve repo_root ONCE here, before it is used to
    # derive outbox_dir/drained_dir or passed to _load_lessons_yaml_dir, so every downstream
    # _source_path is built on an absolute+resolved basis. This closes the "relative repo_root
    # leaks a caller-relative prefix" gap at the root instead of guarding it defensively inside
    # _relativize_prov_path. Transparent to callers below — they only ever join onto repo_root
    # to build Paths.
    repo_root = repo_root.resolve()
    # Review: code-reviewer Slice-B — (B-F4) renamed lessons_md_map → lessons_yaml_map;
    # the source is the per-entry YAML dir state/lessons/, not the legacy lessons.md.
    lessons_yaml_map = _load_lessons_yaml_dir(repo_root)
    outbox_dir = repo_root / "state" / "lessons-outbox"
    drained_dir = outbox_dir / "drained"

    outbox_map = _load_outbox_dir(outbox_dir)
    drained_map = _load_outbox_dir(drained_dir)

    # Full union of all lesson_keys across all three surfaces
    all_keys: set[str] = set(lessons_yaml_map) | set(outbox_map) | set(drained_map)

    records: list[dict] = []
    for key in sorted(all_keys):  # sorted for deterministic output
        in_md = key in lessons_yaml_map
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
            prov_path = lessons_yaml_map[key].get("_source_path", "state/lessons")

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
            md_rec = lessons_yaml_map[key]
            title = md_rec.get("title") or ""
            body = md_rec.get("body") or ""
            scope = "universal" if md_rec.get("tag_universal") else "project"
            if not title or not body:
                parse_status = "partial"
            # Forward born-attributable fields from the per-entry YAML.
            # Lessons are born-attributable: the per-entry YAML at capture time already
            # carries from_repo/target_wiki/evidence/created, so captured entries can emit
            # non-null values for these fields without requiring outbox promotion.
            # Precedence: the outbox/drained overlay block below will override these values
            # when outbox_rec is present (outbox/drained promotion metadata wins).
            # `created` is normalized via _normalize_created because per-entry YAMLs store
            # date-only values (e.g. "2026-06-30") that must be widened to IsoDateTime,
            # and sentinel "0000-00-00" must be emitted as honest null (not a fake datetime).
            from_repo = md_rec.get("from_repo") or None
            target_wiki = md_rec.get("target_wiki") or None
            evidence = md_rec.get("evidence") or None
            created = _normalize_created(md_rec.get("created"))
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
        # record here. The per-entry YAML in state/lessons/*.yaml is the canonical body spine
        # (lessons.md→per-entry-YAML migration): when the lesson exists in the YAML dir,
        # body was already set from md_rec above; for outbox/drained-only entries (full outer
        # join case) body was set from outbox_rec in the elif branch. The outbox/drained
        # record only supplies promotion metadata (change_kind, target_wiki, from_repo,
        # evidence, created) — never body. Changing this would mean outbox prose silently
        # overwrites the richer per-entry YAML body for lessons present in both surfaces.
        if outbox_rec is not None:
            if not title:
                title = outbox_rec.get("title") or ""
            change_kind = outbox_rec.get("change_kind") or None
            # Review: code-reviewer (F1) — fall back to captured value when outbox lacks the
            # field, mirroring the created guard. Without this, an outbox record missing
            # from_repo/target_wiki/evidence would wipe born-attributable values already set
            # from the per-entry YAML in the `if in_md:` block above.
            target_wiki = outbox_rec.get("target_wiki") or target_wiki
            from_repo = outbox_rec.get("from_repo") or from_repo
            evidence = outbox_rec.get("evidence") or evidence
            # Review: code-reviewer (F2) — normalize outbox created via _normalize_created to
            # handle date-only and "0000-00-00" sentinel values in hand-crafted/legacy drained
            # records. Fall back to the captured value when outbox lacks a created field.
            created = _normalize_created(outbox_rec.get("created")) or created

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
            prov_path=_relativize_prov_path(prov_path, repo_root),
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
