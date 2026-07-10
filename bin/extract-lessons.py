#!/usr/bin/env python3
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
            a routing-records file, assert every routing record cites a source line
            that a real extracted entry occupies. Records whose `source` line matches
            no extracted entry are fabrication suspects and are reported non-zero.

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

import yaml  # PyYAML — available in coordinator venv


# ---------------------------------------------------------------------------
# Extraction from per-entry YAML directory
# ---------------------------------------------------------------------------

_TITLE_OVERLAP_MIN = 25  # min chars of title that must appear verbatim in routing summary


def extract(lessons_dir: Path, shortname: str, since: str | None) -> tuple[list[dict], dict]:
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

    The `{shortname}-L{N}` id convention preserves backward compatibility with the
    verify-gate regex `re.match(r".+-L\\d+$", rid)` that gates the id-existence check.
    N encodes sorted-file-position rather than a line number — the verify semantics
    (cited N must map to a real entry) are identical.

    Negative-spec: do NOT read state/lessons.md — that path has been superseded.
    """
    yaml_files = sorted(lessons_dir.glob("*.yaml"))
    records: list[dict] = []
    stats = {
        "undated_excluded": 0,
        "dated_excluded_pre_window": 0,
        "total_blocks_seen": len(yaml_files),
    }

    for idx, f in enumerate(yaml_files, start=1):
        try:
            fm = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception as e:
            # Malformed YAML — skip with a warning; callers get accurate count
            print(f"warning: skipping malformed YAML {f.name}: {e}", file=sys.stderr)
            continue

        created = fm.get("created")
        # PyYAML parses `created: 2026-06-30` (unquoted) as a date object; normalise to str.
        date = str(created) if created is not None else None

        if since:
            if date and date < since:
                stats["dated_excluded_pre_window"] += 1
                continue
            if not date:
                stats["undated_excluded"] += 1
                continue

        scope = str(fm.get("scope", "")).strip()
        title = str(fm.get("title", "")).strip()
        body_val = fm.get("body")
        body = str(body_val).strip() if body_val is not None else ""

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
# Verify gate — UNCHANGED from the markdown-parse version.
# The grounding semantics are identical: routing records must cite a source :N
# that exists in the extraction, the id must exist, and the summary must overlap
# with the extracted entry title. Source format changes from
# `state/lessons.md:N` to `state/lessons/<slug>.yaml:N` but the `:N` parsing
# logic is identical — the synthetic index N satisfies the same uniqueness check.
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
    and title (verify uses title for the overlap check). Tolerant of unknown fields."""
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
    does not match the convention (caller decides whether to treat that as ungrounded)."""
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
    """Three-check grounding gate on routing records against a trusted extraction.

    (1) source-line existence — cited :N must map to a real entry's source_line.
        For YAML-backed extractions, source has the form `<yaml_path>:N` where N is
        the 1-based sorted-file-index (unique per entry, not a real file line number).
    (2) id existence — cited <shortname>-L<N> ids must match an extraction id.
    (3) title overlap — routing `summary` must share >= _TITLE_OVERLAP_MIN consecutive
        chars with the extracted entry's title (the Staff Engineer F2: catches summary-swap, the
        sophisticated fabrication shape the line/id gate misses).

    Extraction is the trusted oracle (script produced it); routing is the untrusted
    input (a model or hand-author produced it). Exit 1 on any failure; exit 0 if all
    routing records pass all three checks.

    **Multi-repo mode (auto-engaged when `extraction_path` is a directory):** discovers
    every `<shortname>-extracted-full.{yaml,json}` in the directory and dispatches each
    routing record to its matching extraction by id-prefix (`<shortname>-L<N>` →
    `<shortname>`). A record whose shortname has no matching extraction is reported as
    ungrounded with a clear "extraction missing for shortname X" message, NOT silently
    skipped. Use this when a single routing yaml spans N shortnames (the 2026-05-24
    `records-net-new.yaml` from the second-pass router was the empirical case)."""

    routing_records = _parse_records_file(routing_path)
    suspects: list[str] = []

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
        if ln is None:
            suspects.append(f"  {rid}: source `{src}` does not end in `:N` — cannot ground")
            continue

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

        if ln not in by_line:
            suspects.append(f"  {rid}: cites source line {ln} — no extracted entry starts there")
            continue
        ext_rec = by_line[ln]
        # id check (only when the routing id follows our `<name>-L<n>` scheme).
        if re.match(r".+-L\d+$", rid) and rid not in by_id:
            suspects.append(f"  {rid}: id not in extraction (line cite was {ln}; "
                            f"extraction has {ext_rec['id']} at that line)")
            continue
        summary = r.get("summary", "")
        if summary and not _title_overlap(ext_rec.get("title", ""), summary):
            suspects.append(
                f"  {rid}: summary shares <{_TITLE_OVERLAP_MIN} consecutive chars with "
                f"extraction title — possible summary-swap (id+line cite OK, content drift)"
            )

    if suspects:
        print(f"GROUNDING GATE: {len(suspects)} routing record(s) failed grounding checks "
              f"(line / id / title-overlap):", file=sys.stderr)
        for s in suspects:
            print(s, file=sys.stderr)
        return 1
    if extraction_path.is_dir():
        print(f"OK: {len(routing_records)} routing records all grounded against "
              f"{len(per_shortname)} extraction(s) in {extraction_path.name}/ "
              f"({total_entries} entries with valid source_line, summed across extractions).")
    else:
        print(f"OK: {len(routing_records)} routing records all grounded against "
              f"{extraction_path.name} ({total_entries} entries with valid source_line).")
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
    pe.add_argument("--format", choices=["yaml", "json"], default="yaml")
    pe.add_argument("-o", "--out", type=Path, default=None, help="write here instead of stdout")

    pv = sub.add_parser(
        "verify",
        help="gate: every routing record must cite a real extracted entry. "
             "If `extraction` is a directory, multi-repo mode auto-engages: every "
             "<shortname>-extracted-full.{yaml,json} in the dir is loaded, and each "
             "routing record is dispatched to its matching extraction by id-prefix.",
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

    records, stats = extract(args.directory, shortname, args.since)
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
        "extractor": "extract-lessons.py (deterministic — no LLM)",
    }
    text = _emit(records, args.format, meta)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {len(records)} records to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
