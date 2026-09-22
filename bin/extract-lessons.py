"""Deterministic structured extraction of `state/lessons/*.yaml` entries.

Replaces the LLM "scout extraction" step in `coordinator:learn-lessons` Phase 2.
Faithful extraction of source text is a *parse*, not a judgment call — so this
script does it deterministically and the fabrication failure mode (a Haiku scout
inventing plausible-but-nonexistent lessons to fill the record shape we demanded)
becomes structurally impossible rather than merely less likely.

Two responsibilities, two subcommands:

  extract   Enumerate a state/lessons/ directory and emit verbatim entry records:
            one record per YAML file, reading `created`, `scope`, `title`, and
            `body` from frontmatter. The `id` uses the format `{shortname}-L{N}`
            where N is the 1-based sorted-file-index (preserving verify-gate compat).
            No synthesis. The downstream routing layer (scope / target / change_kind)
            is the only step that needs judgment, and it consumes these faithful records.

  verify    The mechanical gate on the judgment layer. Given an extraction file and
            a routing-records file, assert every routing record's `id` matches a
            real extracted entry (PRIMARY, hard failure). `source` is advisory
            metadata (re-attached/warned, never fails the gate) — see A6 fix below.
            Records whose `id` matches no extracted entry are fabrication suspects
            and are reported non-zero.

This is the deterministic backbone that lets Haiku stay in the loop for bounded
routing classification: extraction can't be faked (no model runs it), and routing
fakery is caught (the cited source must exist).

Source format: state/lessons/<date>-<slug>.yaml (per-entry YAML, one file per lesson).
Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3a

Negative-spec: Do NOT point this at state/lessons.md — that path has been superseded
by the per-entry YAML directory. Use the `extract` subcommand's directory argument only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GENERATES = []  # writes only to the caller-supplied -o/--out path (or stdout when omitted) — no fixed tracked artifact


# ---------------------------------------------------------------------------
# Extraction from per-entry YAML directory
# ---------------------------------------------------------------------------

_TITLE_OVERLAP_MIN = 25  # min chars of title that must appear verbatim in routing summary


def _lesson_date(fm: dict) -> str | None:
    """Resolve an entry's date from whichever field carries it: `created` or `date`.

    Both spellings are in use across the corpus, and reading only `created` marks a dated
    entry `undated: true`. That is not cosmetic — `undated` drives the `--since` window
    and the age-sweep, so a misread date silently excludes a real lesson from both, and
    the `undated_universal_remaining` counter over-reports by the same amount.

    PyYAML parses an unquoted `2026-06-30` as a date object, so the value is normalised
    to a string either way.
    """
    for key in ("created", "date"):
        value = fm.get(key)
        if value is not None:
            return str(value)
    return None


def _load_lesson_file(path: Path) -> tuple[dict | None, str]:
    """Read one lesson entry into (frontmatter, trailing-text), tolerant of every shape on disk.

    Four shapes exist in `state/lessons/`, and the extension does not predict which:
      1. a bare YAML mapping — no `---` fences at all;
      2. a `---`-fenced frontmatter block followed by a markdown body;
      3. a `---`-fenced frontmatter block followed by MORE YAML, which `yaml.safe_load`
         rejects outright as a multi-document stream;
      4. plain markdown with no frontmatter at all, whose title is its first `#` heading
         and whose date is the `YYYY-MM-DD` prefix of its filename.

    Reading only shape 1 is how a lesson goes missing without an error: shape 3 raised
    "expected a single document" and was counted as malformed, and shape 2's body was
    dropped because nothing looked past the fence. Both failures are silent to the
    caller, which sees a smaller corpus and no signal that anything was skipped.

    Returns `(None, "")` and warns when the file genuinely cannot be parsed, so the
    caller skips it rather than emitting a record with invented content.
    """
    import yaml  # PyYAML — available in coordinator venv

    text = path.read_text(encoding="utf-8")
    trailing = ""
    head = text

    if text.lstrip().startswith("#"):
        return _synthesize_frontmatter(path, text)

    if text.startswith("---"):
        parts = re.split(r"^---[ \t]*$", text, flags=re.MULTILINE)
        # parts[0] is the empty string before the opening fence.
        if len(parts) >= 3:
            head, trailing = parts[1], "---".join(parts[2:])
        elif len(parts) == 2:
            head = parts[1]

    try:
        fm = yaml.safe_load(head)
    except Exception as e:
        print(f"warning: skipping unparseable frontmatter {path.name}: {e}", file=sys.stderr)
        return None, ""

    if not isinstance(fm, dict):
        print(f"warning: skipping {path.name}: frontmatter is not a mapping", file=sys.stderr)
        return None, ""
    return fm, trailing


def _synthesize_frontmatter(path: Path, text: str) -> tuple[dict | None, str]:
    """Derive frontmatter for a lesson written as plain markdown, with no `---` block.

    An entry in this shape carries the same two facts every other shape does, just
    positionally rather than in named fields: the title is its first `#` heading and the
    date is its filename's `YYYY-MM-DD` prefix. Deriving them is still a parse, not a
    judgment — nothing is inferred from the prose.

    `scope` is genuinely absent here, so the entry is never treated as `[universal]`:
    an absent tag is not a tag, and guessing one would promote a lesson nobody marked.
    """
    lines = text.lstrip().splitlines()
    title = lines[0].lstrip("#").strip() if lines else ""
    body = "\n".join(lines[1:]).strip()

    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    fm: dict = {"title": title}
    if m and m.group(1) != "0000-00-00":
        fm["created"] = m.group(1)
    return fm, body


def _lesson_title(fm: dict, trailing: str) -> str:
    """Resolve an entry's title: `title`, else `description`, else the body's first `#` heading.

    An entry can carry frontmatter and still leave the title out of it, stating it only as
    the markdown heading the body opens with. Reading the field alone yields an empty title
    for that shape, which is worse than an absent record: the verify gate's title-overlap
    check compares a routing summary against the title, and an empty title can never overlap,
    so every faithfully-routed record for such an entry is reported as a fabrication suspect.
    A real defect and a loader gap look identical in that report.

    A memory-node entry is the other case: it states its substance in `description` and keeps
    `name` as a slug, so `description` is what the title field means for that shape.

    Taking the first heading, or the description, is a parse, not a judgment — each is where
    its own shape puts the title.
    """
    for key in ("title", "description"):
        value = str(fm.get(key, "")).strip()
        if value:
            return value
    for line in trailing.lstrip().splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line.strip():
            break
    return ""


def _lesson_body(fm: dict, trailing: str) -> str:
    """Resolve an entry's body: the explicit `body` field, else the text after the fence.

    An entry carries its substance in one place or the other, never both, and which one
    is a property of the file rather than of its extension. A memory-node entry keeps it in
    `description`, which is why that key is read for the body as well as the title.
    """
    for key in ("body", "description"):
        value = fm.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    if trailing.strip():
        return trailing.strip()
    return ""


def extract(lessons_dir: Path, shortname: str, since: str | None,
            include_md: bool = False) -> tuple[list[dict], dict]:
    """Enumerate state/lessons/*.yaml and emit verbatim record dicts.

    Each YAML file is one lesson entry. Fields are read from YAML frontmatter:
    - id: {shortname}-L{N} where N is the 1-based sorted-file-index
    - source: {yaml_path}:{N}  (N keeps source_line unique per entry)
    - source_line: N  (unique 1-based index, not a real file line number)
    - tag_universal: True when scope == 'universal'
    - date: value of `created` field (YYYY-MM-DD string)
    - undated: True when created is absent
    - title: value of `title` field
    - body: value of `body` field

    The `{shortname}-L{N}` id convention is preserved for multi-repo shortname-routing
    compatibility (`_shortname_from_id` extracts the `{shortname}` prefix to dispatch
    a routing record to its matching extraction) — NOT for gating the id-existence
    check, which is now unconditional per the A6 fix (see `verify()`'s docstring).
    N encodes sorted-file-position rather than a line number.

    Negative-spec: do NOT read state/lessons.md — that path has been superseded.

    `include_md` additionally enumerates `state/lessons/*.md` — the markdown-bodied
    entry shape, whose frontmatter carries `title`/`created`/`scope` exactly as the
    YAML shape does but whose body is the markdown after the frontmatter rather than
    a `body:` field. Those records are appended AFTER the YAML ones and numbered in a
    separate `{shortname}-M{N}` namespace, so enabling the flag never renumbers or
    otherwise disturbs an existing `-L{N}` extraction used as a verify-gate oracle.
    Without the flag a `.md` entry is invisible to extraction and therefore to every
    routing and verify step downstream — silently, with no warning and no count.
    """
    import yaml  # PyYAML — available in coordinator venv

    yaml_files = sorted(lessons_dir.glob("*.yaml"))
    records: list[dict] = []
    stats = {
        "undated_excluded": 0,
        "dated_excluded_pre_window": 0,
        "total_blocks_seen": len(yaml_files),
        "malformed_skipped": 0,
        "malformed_files": [],
        # Visible even when include_md is False, so the blind spot is a reported
        # count rather than a silent absence — see `main()`'s post-extract warning.
        "md_files_present": len(sorted(lessons_dir.glob("*.md"))) if not include_md else 0,
    }

    for idx, f in enumerate(yaml_files, start=1):
        fm, trailing = _load_lesson_file(f)
        if fm is None:
            stats["malformed_skipped"] += 1
            stats["malformed_files"].append(f.name)
            continue

        date = _lesson_date(fm)

        if since:
            if date and date < since:
                stats["dated_excluded_pre_window"] += 1
                continue
            if not date:
                stats["undated_excluded"] += 1
                continue

        scope = str(fm.get("scope", "")).strip()
        title = _lesson_title(fm, trailing)
        body = _lesson_body(fm, trailing)

        records.append({
            "id": f"{shortname}-L{idx}",
            "source": f"{f.as_posix()}:{idx}",
            "source_line": idx,
            "tag_universal": scope == "universal",
            "date": date,
            "undated": date is None,
            "title": title,
            "body": body,
        })


    if include_md:
        md_files = sorted(lessons_dir.glob("*.md"))
        stats["total_blocks_seen"] += len(md_files)
        for idx, f in enumerate(md_files, start=1):
            fm, trailing = _load_lesson_file(f)
            if fm is None:
                stats["malformed_skipped"] += 1
                stats["malformed_files"].append(f.name)
                continue

            date = _lesson_date(fm)

            if since:
                if date and date < since:
                    stats["dated_excluded_pre_window"] += 1
                    continue
                if not date:
                    stats["undated_excluded"] += 1
                    continue

            records.append({
                "id": f"{shortname}-M{idx}",
                "source": f"{f.as_posix()}:{idx}",
                "source_line": idx,
                "tag_universal": str(fm.get("scope", "")).strip() == "universal",
                "date": date,
                "undated": date is None,
                "title": _lesson_title(fm, trailing),
                "body": _lesson_body(fm, trailing),
            })

    return records, stats


def _emit(records: list[dict], fmt: str, meta: dict) -> str:
    if fmt == "json":
        return json.dumps({"meta": meta, "records": records}, indent=2, ensure_ascii=False)
    # Minimal YAML emitter (no external dep). Bodies are block scalars to stay verbatim.
    out: list[str] = ["# extract-lessons.py — deterministic verbatim extraction"]
    for k, v in meta.items():
        out.append(f"# {k}: {v}")
    out.append("records:")
    for r in records:
        out.append(f"  - id: {json.dumps(r['id'])}")
        out.append(f"    source: {json.dumps(r['source'])}")
        out.append(f"    source_line: {r['source_line']}")
        out.append(f"    tag_universal: {str(r['tag_universal']).lower()}")
        out.append(f"    date: {json.dumps(r['date'])}")
        out.append(f"    undated: {str(r['undated']).lower()}")
        out.append(f"    title: {json.dumps(r['title'])}")
        # Verbatim body as a literal block scalar.
        out.append("    body: |")
        for bl in r["body"].splitlines():
            out.append(f"      {bl}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Verify gate — id-primary / source-advisory grounding (A6 fix, 2026-07-23).
# The gate now grounds on `id` (unconditional, hard failure on mismatch) as the
# PRIMARY key; `source` is ADVISORY metadata — missing, stripped, or rewritten
# `:N` is re-attached/noted, never a failure. A present-but-disagreeing `source`
# is a warning. Title-overlap remains a hard failure (catches summary-swap).
# Negative-spec: do NOT reinstate a hard failure on `source`'s `:N` shape — that
# shape is a synthetic enumeration index, not a real line number, and treating
# it as load-bearing produced a 29/29 false-failure on honest records whose
# `source` had merely been reformatted by a routing LLM. See verify()'s
# docstring for the full incident writeup.
# ---------------------------------------------------------------------------

_ID_LINE = re.compile(r'^\s*-\s+id:\s*["\']?([^"\']+?)["\']?\s*$')
_LIST_FIELD = re.compile(r'^\s{2,}(\w+):\s*["\']?(.*?)["\']?\s*$')


def _line_from_source(source: str) -> int | None:
    """Extract the trailing :N from a source string like 'state/lessons/foo.yaml:1'.

    Use rpartition (not a non-greedy regex on the whole string) so Windows paths whose
    drive prefix is `C:` don't capture the wrong colon. The Staff Engineer review F1."""
    if not source:
        return None
    _path, sep, tail = source.rpartition(":")
    if not sep or not tail.isdigit():
        return None
    return int(tail)


def _parse_records_file(path: Path) -> list[dict]:
    """Parse the YAML/JSON this script produces — also handles the hand-authored routing
    files we ingest at verify time. Records are list-items starting `- id:` with indented
    `source: …`, `summary: …`, `title: …` fields. Tolerant: ignores fields it doesn't
    recognize; stops a record when the next `- id:` appears or indent drops to zero.

    Replaces the prior pair of greedy regex `findall` calls that couldn't tell whether
    a captured `id:` was a top-level record id or a nested field key (the Staff Engineer F4)."""
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if "records" in data:
            return data["records"]
        return data if isinstance(data, list) else []
    records: list[dict] = []
    cur: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m_id = _ID_LINE.match(line)
        if m_id:
            if cur:
                records.append(cur)
            cur = {"id": m_id.group(1)}
            continue
        if cur is None:
            continue
        m_f = _LIST_FIELD.match(line)
        if m_f:
            k, v = m_f.group(1), m_f.group(2)
            # Only first occurrence wins (avoid `destinations: -` nested `target:` etc.).
            if k in ("source", "summary", "title", "source_line") and k not in cur:
                cur[k] = v
    if cur:
        records.append(cur)
    return records


def _title_overlap(title: str, summary: str) -> bool:
    """True if a verbatim slice of `title` of length >= _TITLE_OVERLAP_MIN appears in
    `summary`. Defends against the swap-summary-between-real-ids fabrication shape
    (the Staff Engineer F2): a routing record's id and source can be real while its summary
    describes a different entry — line+id grounding alone won't catch that. Real
    paraphrases share many consecutive title characters; swap-fabrications don't.

    Match is case-insensitive. Whitespace inside is preserved (titles often carry
    distinctive multi-word phrases the summary reproduces verbatim)."""
    if not title or not summary:
        return False
    t = title.lower()
    s = summary.lower()
    if _TITLE_OVERLAP_MIN >= len(t):
        return t in s
    for i in range(0, len(t) - _TITLE_OVERLAP_MIN + 1):
        if t[i : i + _TITLE_OVERLAP_MIN] in s:
            return True
    return False


def _parse_extraction_yaml_full(path: Path) -> list[dict]:
    """Reader for the extraction YAML this script emits — captures id, source_line,
    title, and source (verify uses title for the overlap check and source for the
    A6 advisory re-attachment note). Tolerant of unknown fields."""
    records: list[dict] = []
    cur: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m_id = _ID_LINE.match(line)
        if m_id:
            if cur:
                records.append(cur)
            cur = {"id": m_id.group(1)}
            continue
        if cur is None:
            continue
        m_f = _LIST_FIELD.match(line)
        if not m_f:
            continue
        k, v = m_f.group(1), m_f.group(2)
        if k == "source_line" and v.isdigit() and "source_line" not in cur:
            cur["source_line"] = int(v)
        elif k == "title" and "title" not in cur:
            cur["title"] = v
        elif k == "source" and "source" not in cur:
            cur["source"] = v
    if cur:
        records.append(cur)
    return records


def _load_extraction(extraction_path: Path) -> list[dict]:
    """Load extracted records from a single extraction file (json or yaml)."""
    if extraction_path.suffix == ".json":
        ext = json.loads(extraction_path.read_text(encoding="utf-8"))
        return ext.get("records", ext if isinstance(ext, list) else [])
    return _parse_extraction_yaml_full(extraction_path)


def _shortname_from_id(rid: str) -> str | None:
    """Extract shortname from a `<shortname>-L<N>` routing id. Returns None if the id
    does not match the convention (caller decides whether to treat that as ungrounded).

    Negative-spec: this regex is unrelated to, and does not resurrect, the removed
    id-existence-check carve-out documented in `verify()`'s docstring (A6) — that gate
    exempted ids from existence-checking based on shape; this one only routes an
    already-existence-checked id to its matching multi-repo extraction file."""
    m = re.match(r"(.+)-L\d+$", rid)
    return m.group(1) if m else None


def _discover_extractions(extraction_dir: Path) -> dict[str, Path]:
    """Find every `<shortname>-extracted-full.yaml` / `.json` under a directory and
    return {shortname: path}. Multiple matches for the same shortname is a fail-loud
    condition the caller surfaces — never silently pick one."""
    by_shortname: dict[str, list[Path]] = {}
    # Sort by name (not by Path) so duplicate-detection error messages are deterministic
    # across POSIX/Windows — Path.__lt__ folds in drive-prefix casing on Windows.
    for p in sorted(extraction_dir.iterdir(), key=lambda x: x.name):
        if not p.is_file():
            continue
        # Match `<shortname>-extracted-full.{yaml,json}` (the canonical verify-oracle name).
        m = re.match(r"(.+)-extracted-full\.(yaml|json)$", p.name)
        if not m:
            continue
        by_shortname.setdefault(m.group(1), []).append(p)
    out: dict[str, Path] = {}
    for shortname, paths in by_shortname.items():
        if len(paths) > 1:
            # Multiple full extractions for one shortname is operator error — surface, do not pick.
            raise RuntimeError(
                f"multiple `{shortname}-extracted-full.*` files in {extraction_dir}: "
                f"{[p.name for p in paths]}"
            )
        out[shortname] = paths[0]
    return out


def verify(extraction_path: Path, routing_path: Path) -> int:
    """Grounding gate on routing records against a trusted extraction.

    Grounding key is `id` (PRIMARY, unconditional, hard failure on mismatch) — `id`
    is the machine-generated, unique field a router cannot honestly emit without an
    extraction record backing it. `source` is ADVISORY metadata (SOFT — missing,
    stripped, or rewritten `:N` never fails the gate; a present-but-disagreeing
    `source` is a WARNING, not a failure).

    Negative-spec / regression context (A6, 2026-07-23): `source`'s trailing `:N` is
    a synthetic 1-based enumeration index across the extraction directory listing,
    NOT a real file line number (see `extract()` docstring). It only *looks* like a
    `path:line` citation, so LLM routers "helpfully" strip or rewrite it as a matter
    of routine formatting cleanup — with zero fabrication involved. A prior version
    of this gate treated `source`'s `:N` shape as load-bearing and failed 29/29
    otherwise-honest routing records in one live run purely because every record's
    `source` had been reformatted. Grounding on `id` primary / `source` advisory
    fixes this while keeping the fabrication catch intact: a record whose `id` does
    not exist in the extraction is real fabrication and still fails, unconditionally
    (the prior `re.match(r".+-L\\d+$", rid)` gate on the id-existence check has been
    removed — that regex silently exempted any id not matching the `-L<digits>`
    shape from being checked for existence at all, which was its own fabrication
    hole: a made-up id in a non-matching shape, paired with a title that happened to
    overlap, previously sailed through un-checked).

    Three checks per routing record:

    (1) id existence — PRIMARY, HARD failure. Cited `id` must match an extraction
        `id`, unconditionally (no shape carve-out).
    (2) source cross-check — ADVISORY. If `source` is absent/malformed (`:N`
        missing or non-numeric), the canonical `source` is re-attached from the
        extraction by `id` and reported as an informational note — NOT a failure.
        If `source` is present, well-formed, but disagrees with the extraction's
        recorded `source_line` for that `id`, that is a WARNING (possible content
        drift / stale extraction) — NOT a failure.
    (3) title overlap — HARD failure. Routing `summary` must share
        >= _TITLE_OVERLAP_MIN consecutive chars with the extracted entry's title
        (the Staff Engineer F2: catches summary-swap, the sophisticated fabrication shape the
        id/source gate misses — an honest id+source paired with a description of a
        *different* entry).

    Extraction is the trusted oracle (script produced it); routing is the untrusted
    input (a model or hand-author produced it). Exit 1 if any record fails checks
    (1) or (3); exit 0 otherwise — advisory notes/warnings from check (2) never
    change the exit code.

    **Multi-repo mode (auto-engaged when `extraction_path` is a directory):** discovers
    every `<shortname>-extracted-full.{yaml,json}` in the directory and dispatches each
    routing record to its matching extraction by id-prefix (`<shortname>-L<N>` →
    `<shortname>`). A record whose shortname has no matching extraction is reported as
    ungrounded with a clear "extraction missing for shortname X" message, NOT silently
    skipped. Use this when a single routing yaml spans N shortnames (the 2026-05-24
    `records-net-new.yaml` from the second-pass router was the empirical case)."""

    routing_records = _parse_records_file(routing_path)
    suspects: list[str] = []
    notes: list[str] = []

    if extraction_path.is_dir():
        # Multi-repo mode: discover extractions and route each routing record by shortname.
        try:
            extractions = _discover_extractions(extraction_path)
        except RuntimeError as e:
            print(f"verify: {e}", file=sys.stderr)
            return 2
        if not extractions:
            print(f"verify: no `*-extracted-full.{{yaml,json}}` files found in {extraction_path}",
                  file=sys.stderr)
            return 2
        # Pre-load per-shortname maps once.
        per_shortname: dict[str, tuple[dict, dict]] = {}
        for shortname, ext_path in extractions.items():
            ext_records = _load_extraction(ext_path)
            by_line = {r["source_line"]: r for r in ext_records if "source_line" in r}
            by_id = {r["id"]: r for r in ext_records if "id" in r}
            per_shortname[shortname] = (by_line, by_id)
        total_entries = sum(len(v[0]) for v in per_shortname.values())
    else:
        ext_records = _load_extraction(extraction_path)
        per_shortname = {
            "__single__": (
                {r["source_line"]: r for r in ext_records if "source_line" in r},
                {r["id"]: r for r in ext_records if "id" in r},
            )
        }
        total_entries = len(per_shortname["__single__"][0])

    for r in routing_records:
        rid = r.get("id", "(no id)")
        src = r.get("source", "")
        ln = _line_from_source(src)

        # Pick which (by_line, by_id) maps to use.
        if extraction_path.is_dir():
            shortname = _shortname_from_id(rid)
            if shortname is None:
                suspects.append(
                    f"  {rid}: id does not match `<shortname>-L<N>` convention — "
                    f"cannot route to an extraction in multi-repo mode"
                )
                continue
            if shortname not in per_shortname:
                suspects.append(
                    f"  {rid}: no extraction loaded for shortname `{shortname}` "
                    f"(have: {sorted(per_shortname)})"
                )
                continue
            by_line, by_id = per_shortname[shortname]
        else:
            by_line, by_id = per_shortname["__single__"]

        # (1) PRIMARY, HARD — id must exist in the extraction, unconditionally.
        # No shape carve-out: a fabricated id in ANY shape is real fabrication.
        if rid not in by_id:
            suspects.append(f"  {rid}: id not in extraction — fabricated id "
                            f"(cited source was `{src}`)")
            continue
        ext_rec = by_id[rid]

        # (2) ADVISORY, SOFT — source is re-attached/note-only when missing or
        # malformed; a present-but-disagreeing source is a warning, never a failure.
        if ln is None:
            canonical_source = ext_rec.get("source", "(none in extraction)")
            notes.append(
                f"  {rid}: source `{src}` missing/malformed `:N` suffix — re-attached "
                f"canonical source `{canonical_source}` from extraction by id "
                f"(advisory note, not a grounding failure)"
            )
        else:
            ext_source_line = ext_rec.get("source_line")
            if ln != ext_source_line:
                notes.append(
                    f"  {rid}: WARNING — cited source line {ln} disagrees with "
                    f"extraction's source_line {ext_source_line} for this id "
                    f"(possible content drift; not a grounding failure)"
                )

        # (3) HARD — title overlap catches the summary-swap fabrication shape that
        # an honest id+source pair does not.
        summary = r.get("summary", "")
        if summary and not _title_overlap(ext_rec.get("title", ""), summary):
            suspects.append(
                f"  {rid}: summary shares <{_TITLE_OVERLAP_MIN} consecutive chars with "
                f"extraction title — possible summary-swap (id+source OK, content drift)"
            )

    if notes:
        print(f"GROUNDING GATE: {len(notes)} advisory note(s) (informational — do NOT "
              f"affect the exit code):", file=sys.stderr)
        for n in notes:
            print(n, file=sys.stderr)

    if suspects:
        print(f"GROUNDING GATE VERDICT: FAIL (exit 1) — {len(suspects)} routing record(s) "
              f"failed grounding checks (id-existence / title-overlap):", file=sys.stderr)
        for s in suspects:
            print(s, file=sys.stderr)
        return 1
    if extraction_path.is_dir():
        print(f"GROUNDING GATE VERDICT: PASS (exit 0) — {len(routing_records)} routing "
              f"records all grounded against {len(per_shortname)} extraction(s) in "
              f"{extraction_path.name}/ ({total_entries} entries with valid source_line, "
              f"summed across extractions).")
    else:
        print(f"GROUNDING GATE VERDICT: PASS (exit 0) — {len(routing_records)} routing "
              f"records all grounded against {extraction_path.name} "
              f"({total_entries} entries with valid source_line).")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("extract", help="enumerate state/lessons/*.yaml into verbatim records")
    pe.add_argument(
        "directory",
        type=Path,
        help="path to state/lessons/ directory (was: path to state/lessons.md)",
    )
    pe.add_argument("--shortname", default=None,
                    help="repo shortname for ids (default: inferred from state/lessons parent dir)")
    pe.add_argument("--since", default=None, help="keep only entries dated >= YYYY-MM-DD")
    pe.add_argument("--require-tag", choices=["universal"], default=None,
                    help="keep only scope=universal entries")
    pe.add_argument("--include-md", action="store_true",
                    help="also enumerate state/lessons/*.md entries, in a separate "
                         "{shortname}-M{N} id namespace (default: YAML only)")
    pe.add_argument("--format", choices=["yaml", "json"], default="yaml")
    pe.add_argument("-o", "--out", type=Path, default=None, help="write here instead of stdout")

    pv = sub.add_parser(
        "verify",
        help="gate: every routing record's `id` must match a real extracted entry "
             "(`source` is advisory only — see A6 note below). "
             "If `extraction` is a directory, multi-repo mode auto-engages: every "
             "<shortname>-extracted-full.{yaml,json} in the dir is loaded, and each "
             "routing record is dispatched to its matching extraction by id-prefix.",
        description=(
            "Grounds routing records against a trusted extraction. Prints a "
            "`GROUNDING GATE VERDICT: PASS (exit 0)` or `GROUNDING GATE VERDICT: "
            "FAIL (exit 1)` line to stderr on every invocation.\n\n"
            "WARNING — piping to `| tail` (or any pager) hides the real exit code: "
            "`$?` after a pipeline reflects the LAST command in the pipe (`tail`), "
            "not `verify` itself. Check `$?` on an unpiped invocation, or use "
            "`set -o pipefail` (bash) first, or grep the printed VERDICT line — "
            "never infer pass/fail from a piped `$?`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pv.add_argument("extraction", type=Path,
                    help="extraction file OR directory of <shortname>-extracted-full.* files")
    pv.add_argument("routing", type=Path)

    args = ap.parse_args(argv)

    if args.cmd == "verify":
        return verify(args.extraction, args.routing)

    # extract
    if not args.directory.exists():
        print(f"error: {args.directory} does not exist", file=sys.stderr)
        return 2
    if not args.directory.is_dir():
        print(
            f"error: {args.directory} is not a directory; "
            f"pass the state/lessons/ directory, not a file.",
            file=sys.stderr,
        )
        return 2

    # Shortname default: infer from state/lessons/ parent chain.
    # Fail loud rather than silently pick a garbage shortname when the heuristic doesn't
    # hold — detect-then-silently-pick is the documented footgun (the Staff Engineer F3).
    if args.shortname:
        shortname = args.shortname
    else:
        resolved = args.directory.resolve()
        if resolved.name == "lessons" and resolved.parent.name == "state":
            shortname = resolved.parent.parent.name
        else:
            print(
                f"error: cannot infer --shortname from path `{args.directory}` "
                f"(expected a directory named `state/lessons`); "
                f"pass --shortname <name> explicitly.",
                file=sys.stderr,
            )
            return 2

    records, stats = extract(args.directory, shortname, args.since, args.include_md)

    # Visibility fix (klabauter#31): a `.md` capture is invisible to every downstream
    # consumer unless `--include-md` is passed, and that absence previously carried no
    # count and no warning — a smaller corpus with nothing to say why. Report it loudly
    # whenever it would otherwise pass unremarked.
    if not args.include_md and stats["md_files_present"]:
        print(
            f"warning: {stats['md_files_present']} `.md` lesson file(s) in "
            f"{args.directory} were NOT extracted (extract only reads `*.yaml` here) — "
            f"pass --include-md to include them.",
            file=sys.stderr,
        )

    # Fail-loud fix (klabauter#32): a malformed record previously warned to stderr and
    # vanished from the corpus with exit 0 — indistinguishable from "no such file
    # existed". A record that cannot be parsed is a defect in the source, not a file
    # to silently exclude, so it must fail the run rather than the run succeeding over
    # a smaller, unexplained count.
    if stats["malformed_skipped"]:
        print(
            f"error: {stats['malformed_skipped']} lesson file(s) could not be parsed "
            f"and were skipped: {', '.join(stats['malformed_files'])} "
            f"(see prior warning(s) above for the parse error on each)",
            file=sys.stderr,
        )
        return 1

    pre_tag_count = len(records)
    if args.require_tag == "universal":
        records = [r for r in records if r["tag_universal"]]
    meta = {
        "source": args.directory.as_posix(),
        "shortname": shortname,
        "since": args.since or "(all)",
        "require_tag": args.require_tag or "(none)",
        "record_count": len(records),
        "blocks_seen": stats["total_blocks_seen"],
        "undated_excluded_under_since": stats["undated_excluded"],
        "dated_excluded_pre_window": stats["dated_excluded_pre_window"],
        "filtered_by_require_tag": pre_tag_count - len(records),
        "md_files_present_but_not_extracted": stats["md_files_present"],
        "extractor": "extract-lessons.py (deterministic — no LLM)",
    }
    text = _emit(records, args.format, meta)
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {len(records)} records to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
