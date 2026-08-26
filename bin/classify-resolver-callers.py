# Unix shebang.
"""classify-resolver-callers.py — mechanical bucket enumerator for the
resolve_claude_klabauter naming retirement (C7,
docs/plans/2026-08-19-an-engine-root-is-a-stamped-build.md).

THE ENUMERATION IS MECHANICAL, NOT MANUAL (C7's own body). A raw grep over
this tree for the resolver symbol family returns hundreds of hits across
hundreds of files — not a number a human should triage file-by-file. This
script assigns each matching file to exactly ONE bucket, by an explicit
PRIORITY ORDER, so two runs of the same tree agree even where a file's raw
grep hits span more than one bucket's pattern (a `require_engine_on_path`
caller commonly also contains a bare `_resolve_claude_klabauter_root` reference in a
comment or docstring, for instance).

Bucket priority order (first match wins — checked in this order):
  1. resolve_claude_klabauter_root_with_class  — class-aware DISPATCH callers. Route
     individually; verdict recorded per-file, not blanket.
  2. resolve_engine_root / resolve_colocated_claude_klabauter_root — self-location
     LOCATOR family. Bucket verdict: wanted the SOURCE TREE.
  3. require_engine_on_path / ensure_engine_on_path /
     require_colocated_engine_on_path — LOCATOR axis (NOT dispatch — see
     C7's body for why routing this bucket to dispatch would shadow an
     editable install and break Hard constraint 2 in substance).
  4. bare _resolve_claude_klabauter_root() — class-blind DISPATCH callers. Bucket
     verdict: wanted the ENGINE.

A file matching none of the four patterns is not enumerated at all — it is
not a resolver caller.

This script MEASURES; it does not assert the plan's prose numbers. Numbers
drift as the tree changes — the plan prose that quoted an earlier run is
allowed to go stale, and a re-run against a mismatched prose figure is
itself the signal, not a bug in the script. Run it and read what it prints;
do not hardcode expectations from a stale doc into this file.

Usage:
    python classify-resolver-callers.py [--root PATH] [--out PATH] [--json]

Exit code: always 0 (an enumeration tool, not a gate).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPT_DIR.parent.parent

_EXCLUDE_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv", "archive",
}

# Priority-ordered bucket definitions: (bucket_id, label, verdict, pattern).
# Patterns are checked as plain substring/regex hits against a file's raw
# text; a file is assigned to the FIRST bucket (in this order) any of whose
# patterns hit.
_BUCKETS = [
    (
        "1-class-aware",
        "resolve_claude_klabauter_root_with_class (class-aware DISPATCH callers)",
        "route individually — thirteen-ish, tractable by hand",
        [re.compile(r"resolve_claude_klabauter_root_with_class")],
    ),
    (
        "2-self-location",
        "resolve_engine_root / resolve_colocated_claude_klabauter_root (self-location LOCATOR family)",
        "SOURCE TREE — inspect file-by-file, do not blanket-verdict",
        [
            re.compile(r"\bresolve_engine_root\b"),
            re.compile(r"\bresolve_colocated_claude_klabauter_root\b"),
        ],
    ),
    (
        "3-on-path-locator",
        "require_engine_on_path / ensure_engine_on_path / require_colocated_engine_on_path",
        "SOURCE TREE, routed to the LOCATOR axis — NOT dispatch",
        [
            re.compile(r"\brequire_engine_on_path\b"),
            re.compile(r"\bensure_engine_on_path\b"),
            re.compile(r"\brequire_colocated_engine_on_path\b"),
        ],
    ),
    (
        "4-bare-class-blind",
        "bare _resolve_claude_klabauter_root() (class-blind DISPATCH callers)",
        "ENGINE",
        [re.compile(r"_resolve_claude_klabauter_root\s*\(")],
    ),
]

_SCAN_EXTENSIONS = {".py"}


def _iter_candidate_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIR_NAMES]
        for name in filenames:
            if Path(name).suffix in _SCAN_EXTENSIONS:
                yield Path(dirpath) / name


def classify(root: Path) -> dict:
    """Walk `root`, bucket every matching file by priority order, and
    return the routing table plus per-bucket hit counts (raw hit count,
    not file count — a distinct measure kept alongside the file bucketing
    so a reader can see how far raw grep's number diverges from the
    disjoint bucketing)."""
    buckets: dict[str, list[str]] = {b[0]: [] for b in _BUCKETS}
    raw_hit_count = 0
    raw_file_count = 0
    exceptions: list[str] = []

    for path in sorted(_iter_candidate_files(root)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        any_pattern_hit_count = 0
        for _, _, _, patterns in _BUCKETS:
            for pat in patterns:
                any_pattern_hit_count += len(pat.findall(text))

        if any_pattern_hit_count == 0:
            continue

        raw_hit_count += any_pattern_hit_count
        raw_file_count += 1

        rel = path.relative_to(root).as_posix()
        assigned = False
        for bucket_id, _, _, patterns in _BUCKETS:
            if any(pat.search(text) for pat in patterns):
                buckets[bucket_id].append(rel)
                assigned = True
                break
        if not assigned:
            # Unreachable given any_pattern_hit_count > 0 above, but keep
            # the exception path explicit rather than silently dropping a
            # file — a caller that does not fit its bucket is an exception
            # row, not a silent reclassification (C7's own instruction).
            exceptions.append(rel)

    return {
        "root": str(root),
        "raw_hit_count": raw_hit_count,
        "raw_file_count": raw_file_count,
        "buckets": {
            bucket_id: {
                "label": label,
                "verdict": verdict,
                "file_count": len(buckets[bucket_id]),
                "files": buckets[bucket_id],
            }
            for bucket_id, label, verdict, _ in _BUCKETS
        },
        "exceptions": exceptions,
    }


def render_markdown(table: dict) -> str:
    lines = []
    lines.append("<!-- Generated by coordinator/bin/classify-resolver-callers.py — do not hand-edit the tables below; regenerate. -->")
    lines.append("")
    lines.append(f"Raw grep hit count: **{table['raw_hit_count']}** across **{table['raw_file_count']}** files (measured, not the plan's prose numbers — see the module docstring on WHY those two can legitimately diverge).")
    lines.append("")
    for bucket_id, info in table["buckets"].items():
        lines.append(f"### Bucket {bucket_id}: {info['label']}")
        lines.append("")
        lines.append(f"Verdict: {info['verdict']}")
        lines.append("")
        lines.append(f"File count: **{info['file_count']}**")
        lines.append("")
        if info["files"]:
            lines.append("<details><summary>Files</summary>")
            lines.append("")
            for f in info["files"]:
                lines.append(f"- `{f}`")
            lines.append("")
            lines.append("</details>")
        lines.append("")
    if table["exceptions"]:
        lines.append("### Exceptions (matched a pattern but not bucketed)")
        lines.append("")
        for f in table["exceptions"]:
            lines.append(f"- `{f}`")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(_REPO_ROOT_DEFAULT))
    parser.add_argument("--out", default=None, help="write markdown table to this path")
    parser.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    table = classify(root)

    if args.json:
        print(json.dumps(table, indent=2))
    else:
        rendered = render_markdown(table)
        if args.out:
            Path(args.out).write_text(rendered, encoding="utf-8", newline="\n")
            print(f"wrote routing table to {args.out}", file=sys.stderr)
        else:
            print(rendered)

    return 0


if __name__ == "__main__":
    sys.exit(main())
