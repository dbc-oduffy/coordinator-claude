#!/usr/bin/env python3
"""goal-kr-evidence — read-only per-KR evidence correlator for never-assessed goals.

Ported from DoE-claude `coordinator/bin/goal-kr-evidence.py` (W2-C6,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`). Mechanical move except one path-resolution seam:
DoE's copy loaded the shared `bin/lib/atomic_record.py` primitives by `sys.path`-inserting
`bin/lib` and importing `load_by_path` from it (that hyphenated-CLI workaround exists because
DoE's `goal-assessment-staleness.py` sibling is itself not import-safe as a package module). This
copy imports `load_by_path` directly from `coordinator_core.group_em.atomic_record` — an "engine"
class resolution (§ Path resolution): the primitive already lives in this engine's own tree
(ported at W2-C1), with no `bin/lib` shim needed here. The by-path load of the hyphenated sibling
module (`goal-assessment-staleness.py`, landing in this same chunk) is unchanged, since claude-klabauter's
`coordinator/bin/*.py` CLIs are hyphenated the same way DoE's are.

WHY THIS EXISTS. `goal-assessment-staleness.py` (imported here, never re-derived) already tells
`/workweek-complete` Step 1 that a goal was never assessed. It cannot say whether any of that
goal's key results were actually met, or point at what would prove it. Every week the EM
re-correlates handoffs, completions and plans against each KR by hand, from scratch, and throws
the correlation away when the ceremony ends. This module is the read-only instrument that
recalls candidate evidence for each KR of every never-assessed goal — three legs, no scoring:

  1. FK leg — handoffs, plans and completions whose `origin_goal_id` list contains the goal's own
     `id` field. NOT the goal's separate `goal_id` hash: a goal's `id` and `goal_id` are distinct
     fields (see `state/goals/*.yaml`), and joining on the wrong one silently returns zero
     candidates for every goal — a false negative indistinguishable from "checked and clean".
     `assess()`'s own returned rows key a `goal_id` field that itself prefers the goal's
     `goal_id` hash over its `id`; this module re-reads each flagged goal's own YAML by path to
     recover its actual `id` rather than trusting that returned field.
  2. Period-window leg — bounds the corpus in time: every `archive/completed/**/*.md` record,
     plus every `docs/plans/*.md` record whose frontmatter `status` is `implemented`, dated (by
     frontmatter `created`) from the Monday of the goal's `period_value` ISO week
     (`datetime.date.fromisocalendar(year, week, 1)`) through `today`, inclusive. NOT the single
     period week alone — the evidence a never-assessed goal's KR was actually met mostly lands
     after the goal's own period week closed, and a single-week window misses nearly all of it.
  3. Keyword-overlap leg — of the period-window leg's records, keeps only the ones whose title
     shares at least `_MIN_SHARED_TOKENS` distinct content tokens with the KR's own `text`.
     Tokens: lowercase both strings, split on `[^a-z0-9]+`, drop tokens shorter than
     `_MIN_TOKEN_LEN` characters, drop `_STOPWORDS`. This is a recall filter, not a score — a
     record either passes or it isn't a candidate, and every passing record renders with equal
     standing (Anti-scope: no scoring model, no ranking, no confidence value).

A window record is a keyword-leg candidate only if it also passes the period-window leg; the FK
leg is independent of both. A record found by both is tagged with both legs and rendered once.
A KR with no candidate from either leg renders the literal string `no attributable evidence` —
required output, not a fallback, so silence and zero-evidence are never conflated.

NO WRITE-BACK SEAM. This module writes nothing, anywhere, ever: no `state/` mutation, no cache,
no derived artifact, no index. Every run recomputes from what is already on disk. Pinned by
`coordinator/tests/test_arrival_goal_kr_evidence.py`'s AST-walk test, which asserts no disk-write
call appears anywhere in this module's source.

NO SCORING MODEL. See leg 3 above — `_MIN_SHARED_TOKENS` is a recall threshold, not a weight.

MULTI-OS / NO SINGLE-MACHINE ASSUMPTIONS. `pathlib` for every path join, root resolved from
`__file__` (never `cwd`), zero `subprocess` calls, `--goals-dir`/`--repo-root` overridable for
fixtures so no test anchors to this checkout's `state/goals/` (Anti-scope: never anchor a test
to the live goal tree).

Flags: `--goals-dir` (default `<repo-root>/state/goals`), `--repo-root` (default resolved from
`__file__`), `--json` (machine-readable emission for ceremony consumption).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MIN_SHARED_TOKENS = 2
_MIN_TOKEN_LEN = 4
_STOPWORDS = frozenset(
    {
        "with", "from", "that", "this", "each", "every", "into", "against", "before",
        "after", "either", "explicitly", "remaining", "exists", "named", "plan", "plans",
        "goal", "goals", "their", "which", "when", "than", "then", "none", "over", "under",
        "least",
        # Domain-common vocabulary this repo's own titles are saturated with. Without these, two
        # unrelated records sharing only generic coordinator vocabulary (e.g. "review" +
        # "session") clear `_MIN_SHARED_TOKENS` and register as a false-positive KR-evidence
        # candidate.
        "coordinator", "session", "review", "handoff", "dispatch", "agent", "fix", "update",
        "test",
    }
)
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_goal_assessment_staleness():
    """Import the hyphenated sibling module (not a valid Python identifier), sharing the loader
    `coordinator_core.group_em.atomic_record.load_by_path` exists to save every such call site
    re-typing."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from coordinator_core.group_em.atomic_record import load_by_path as _load_by_path

    module_path = Path(__file__).resolve().parent / "goal-assessment-staleness.py"
    return _load_by_path("goal_assessment_staleness", module_path)


def _tokenize(text: str) -> "set[str]":
    lowered = str(text or "").lower()
    tokens = _TOKEN_SPLIT_RE.split(lowered)
    return {
        token
        for token in tokens
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS
    }


def _shares_enough_tokens(kr_text: str, title: str) -> bool:
    shared = _tokenize(kr_text) & _tokenize(title)
    return len(shared) >= _MIN_SHARED_TOKENS


def _parse_frontmatter(text: str) -> dict:
    """The frontmatter dict for a `---`-delimited markdown file; `{}` if absent OR unparseable.
    The body is never consumed by any caller, so only the dict is returned.

    Malformed frontmatter YAML is treated as no-frontmatter rather than crashing the tool: this
    module does not control the contents of `state/handoffs/*.md`, `docs/plans/*.md`, or
    `archive/completed/**/*.md`, and a stray unquoted colon or unterminated quote in any one of
    them must not take down the whole correlation run (mirrors
    `goal-assessment-staleness.py::_load_goal`'s own `yaml.YAMLError` guard)."""
    import yaml

    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.load(parts[1], Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_markdown_records(paths: "list[Path]") -> "list[dict]":
    """`{"path": Path, "frontmatter": dict, "title": str}` per readable markdown record."""
    records = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        frontmatter = _parse_frontmatter(text)
        title = frontmatter.get("title") or path.stem
        records.append({"path": path, "frontmatter": frontmatter, "title": title})
    return records


def _parse_date(value) -> "datetime.date | None":
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _period_window_start(period_value, parse_iso_week) -> "datetime.date | None":
    """Monday of the ISO week `period_value` names, via the already-loaded sibling module's own
    `_parse_iso_week` -- this module already imports `goal-assessment-staleness.py` for
    `assess()`, so re-deriving its week parse here would be a second answer to a question that
    module already answers.

    `None` on either an unparseable `period_value` OR a syntactically-valid-but-nonexistent ISO
    week (e.g. `2026-W53` in a 52-week year) -- both collapse `_window_records` to `[]` for the
    affected goal, which is indistinguishable from a genuinely empty window unless surfaced. The
    latter case is reported to stderr here because it is not caught by `_is_closed`'s own week
    validation (a tuple compare, never raises) upstream in
    `goal-assessment-staleness.py::assess()` -- this is the one place in either module that
    actually calls the calendar-validating `fromisocalendar`."""
    parsed = parse_iso_week(period_value)
    if parsed is None:
        return None
    year, week = parsed
    try:
        return datetime.date.fromisocalendar(year, week, 1)
    except ValueError:
        print(
            f"  window leg skipped: period_value={period_value!r} names a nonexistent ISO week "
            f"(year {year} has no week {week})",
            file=sys.stderr,
        )
        return None


def _fk_leg_candidates(goal_id: str, records: "list[dict]") -> "set[Path]":
    hits: "set[Path]" = set()
    for record in records:
        origin = record["frontmatter"].get("origin_goal_id")
        if isinstance(origin, list) and goal_id in origin:
            hits.add(record["path"])
    return hits


def _window_records(records: "list[dict]", window_start: "datetime.date | None", today: datetime.date) -> "list[dict]":
    if window_start is None:
        return []
    in_window = []
    for record in records:
        record_date = _parse_date(record["frontmatter"].get("created"))
        if record_date is None:
            continue
        if window_start <= record_date <= today:
            in_window.append(record)
    return in_window


def evidence_for_kr(
    kr_text: str,
    fk_hits: "set[Path]",
    window_hits: "list[dict]",
    by_path: "dict[Path, dict]",
) -> "list[dict]":
    """Merged, leg-tagged candidate list for one KR, or `[]` when there is no evidence.

    `fk_hits`, `window_hits` and `by_path` are goal-invariant -- computed once per goal by
    `build_report` and passed in here unchanged, rather than re-derived for every KR of that
    goal. Only the keyword-overlap leg below varies per KR.
    """
    keyword_hits = {
        record["path"]: record
        for record in window_hits
        if _shares_enough_tokens(kr_text, record["title"])
    }

    candidates: "dict[Path, dict]" = {}
    for path in fk_hits:
        record = by_path.get(path)
        title = record["title"] if record else path.stem
        candidates.setdefault(path, {"path": str(path), "title": title, "legs": set()})
        candidates[path]["legs"].add("fk")
    for path, record in keyword_hits.items():
        candidates.setdefault(path, {"path": str(path), "title": record["title"], "legs": set()})
        candidates[path]["legs"].add("window+keyword")

    result = []
    for entry in candidates.values():
        entry = dict(entry)
        entry["legs"] = sorted(entry["legs"])
        result.append(entry)
    result.sort(key=lambda entry: entry["path"])
    return result


def build_report(
    goals_dir: Path,
    repo_root: Path,
    today: "datetime.date | None" = None,
) -> dict:
    """Per-KR evidence for every never-assessed goal, plus the terminal-unstamped bucket.

    Returns `{"goals": [...]}`, each entry `{"goal_id", "title", "key_results": [...]}` and each
    KR entry `{"id", "text", "status", "evidence": [...] | None}` — `evidence` is `None` (rendered
    as `no attributable evidence`) when neither leg finds a candidate.

    NOTE ON `goal_id`: this module's `goal_id` output key holds the FK-join `id` (falling back to
    `goal_id` only when `id` is absent) -- the opposite preference from `assess()`'s own
    `goal_id` field in `goal-assessment-staleness.py`, which prefers the `goal_id` hash over
    `id`. By design (see the FK-leg docstring above); a caller reading both tools' JSON side by
    side must not assume the identically-named key shares an identifier space.
    """
    today = today or datetime.date.today()
    gas_module = _load_goal_assessment_staleness()
    assessment = gas_module.assess(goals_dir, today=today)
    parse_iso_week = gas_module._parse_iso_week

    handoffs_dir = repo_root / "state" / "handoffs"
    plans_dir = repo_root / "docs" / "plans"
    completed_dir = repo_root / "archive" / "completed"

    handoff_records = _load_markdown_records(sorted(handoffs_dir.glob("*.md")) if handoffs_dir.is_dir() else [])
    plan_records = _load_markdown_records(sorted(plans_dir.glob("*.md")) if plans_dir.is_dir() else [])
    completed_records = _load_markdown_records(sorted(completed_dir.rglob("*.md")) if completed_dir.is_dir() else [])

    fk_records = handoff_records + plan_records + completed_records
    implemented_plans = [
        record for record in plan_records if record["frontmatter"].get("status") == "implemented"
    ]
    window_capable_records = completed_records + implemented_plans
    # Corpus-invariant across every goal and every KR -- built once here rather than inside the
    # per-KR loop below.
    by_path = {record["path"]: record for record in fk_records + window_capable_records}

    goals_out = []
    for flagged in assessment["never_assessed"]:
        # `flagged["id"]` is the goal's own `id` field (assess() carries it), distinct from
        # `flagged["goal_id"]`'s preferred `goal_id` hash -- the FK leg must join on `id`.
        # Carrying it on the assess() row means this loop no longer re-reads each goal's YAML by
        # path just to recover it or its `key_results`.
        fk_join_id = flagged.get("id") or flagged["goal_id"]
        title = flagged["title"]
        window_start = _period_window_start(flagged.get("period_value"), parse_iso_week)
        key_results = flagged.get("key_results") or []

        # Goal-invariant across every KR of this goal -- computed once per goal, not per KR.
        fk_hits = _fk_leg_candidates(fk_join_id, fk_records)
        window_hits = _window_records(window_capable_records, window_start, today)

        kr_out = []
        for kr in key_results:
            if not isinstance(kr, dict):
                continue
            kr_text = kr.get("text") or ""
            evidence = evidence_for_kr(
                kr_text=kr_text,
                fk_hits=fk_hits,
                window_hits=window_hits,
                by_path=by_path,
            )
            kr_out.append(
                {
                    "id": kr.get("id"),
                    "text": kr_text,
                    "status": kr.get("status"),
                    "evidence": evidence or None,
                }
            )
        goals_out.append({"goal_id": fk_join_id, "title": title, "key_results": kr_out})

    return {"goals": goals_out}


def _render_text(report: dict) -> str:
    lines = []
    for goal in report["goals"]:
        lines.append(f"{goal['goal_id']}: {goal['title']}")
        for kr in goal["key_results"]:
            lines.append(f"  [{kr['status']}] {kr['id']}: {kr['text']}")
            if not kr["evidence"]:
                lines.append("    no attributable evidence")
            else:
                for entry in kr["evidence"]:
                    legs = "+".join(entry["legs"])
                    lines.append(f"    ({legs}) {entry['title']}  [{entry['path']}]")
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="goal-kr-evidence",
        description="Per-KR evidence candidates for never-assessed goals — read-only, no scoring.",
    )
    parser.add_argument("--goals-dir", help="override the default state/goals directory")
    parser.add_argument("--repo-root", help="override the resolved repo root (fixtures use this)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else _repo_root()
    goals_dir = Path(args.goals_dir).resolve() if args.goals_dir else repo_root / "state" / "goals"

    report = build_report(goals_dir, repo_root)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
