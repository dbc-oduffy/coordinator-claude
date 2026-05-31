#!/usr/bin/env python3
"""Age-archive aged [universal] entries out of a repo's tasks/lessons.md.

WHY THIS EXISTS
---------------
`tasks/lessons.md` is read in full by `/learn-lessons` itself, by the central-mode
strip-local pull-pass, and by the PM-invoked `/session-start` ceremony (it is NOT
a Tier-0 boot read; see coordinator/CLAUDE.md § Session Orientation). It is an
append log: local-mode `/learn-lessons` folds recent lessons to wikis but
historically had no step that *bounds the file's size*, so it grows unbounded and
each of those consumers pays a proportional read tax.

A `[universal]` lesson's canonical home is the CENTRAL coordinator wikis
(promoted by central-mode `/learn-lessons`, surfaced to planners by the
prior-art-checker pre-flight). Once an entry is older than the central
promotion window, keeping it on the sibling's boot surface is redundant: its
durable home is central, and this script's archive + git history are the
recovery net. So we age-archive aged universals and KEEP everything else.

PARTITION (per entry, on the CURRENT file — drift-safe under concurrent edits)
  ARCHIVE  iff  [universal]-tagged  AND  has an ISO date  AND  date < cutoff
  KEEP     otherwise:
             - project-specific entries (no central home) — any age
             - undated entries (can't prove aged) — conservative keep
             - universals within the window (may not be promoted yet)

Boundary parsing is delegated to extract-lessons.py (imported), so entry cuts
land on IDENTICAL boundaries to extraction/verify — no second parser to drift.

SAFETY
  - Default DRY-RUN. `--apply` is required to write.
  - Archive is append-only to <repo>/archive/lessons-archived/YYYY-MM.md with a
    per-entry provenance header (recoverable by date / source line).
  - Operates on the current file in one pass and rewrites atomically; run on a
    clean tree and commit with an explicit pathspec (concurrent-EM discipline).

CUTOFF
  --before YYYY-MM-DD   explicit cutoff (preferred: pass the last central-run
                        date so only entries that already had a promotion
                        opportunity are swept).
  --days N              explicit conservative floor: cutoff = today - N days.
                        NO default — one of --before / --days is required, since
                        there is no safe silent age window (at ~15 entries/day a
                        30-day window retains ~450 entries). Prefer --before.

Usage:
  age-sweep-lessons.py <repo-root-or-lessons-path> [--before DATE | --days N]
                       [--archive-dir DIR] [--apply]
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_EXTRACTOR = _HERE / "extract-lessons.py"


def _load_extractor():
    spec = importlib.util.spec_from_file_location("extract_lessons", _EXTRACTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load entry parser from {_EXTRACTOR}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _resolve_lessons_path(arg: Path) -> Path:
    """Accept either a repo root (…/tasks/lessons.md appended) or a direct file."""
    if arg.is_file():
        return arg
    cand = arg / "tasks" / "lessons.md"
    if cand.is_file():
        return cand
    raise FileNotFoundError(f"no lessons.md at {arg} or {cand}")


def partition(lines: list[str], cutoff: str, el):
    """Return (preamble_lines, keep_spans, archive_entries, total_headers).

    keep_spans is a list of (start, end) index pairs into `lines`.
    archive_entries is a list of (source_line_1based, date, body_text).
    """
    header_idxs = [
        i for i, ln in enumerate(lines)
        if el._is_header(ln, lines[i - 1] if i > 0 else None)
    ]
    preamble = lines[: header_idxs[0]] if header_idxs else lines
    keep_spans: list[tuple[int, int]] = []
    archive_entries: list[tuple[int, str, str]] = []
    for n, start in enumerate(header_idxs):
        end = header_idxs[n + 1] if n + 1 < len(header_idxs) else len(lines)
        block = lines[start:end]
        body_lines = block[:]
        while body_lines and (el._HRULE.match(body_lines[-1]) or body_lines[-1].strip() == ""):
            body_lines.pop()
        body = "\n".join(body_lines)
        # Capture date = first ISO date AFTER the bold title span, NOT the first date
        # anywhere in the body. A title that references an older incident date —
        # e.g. `**lesson about the 2026-01-01 outage** ... 2026-05-26` — must be dated
        # by its CAPTURE date (the date that follows the title), or an in-title
        # reference would sweep it before it ever had a central-run promotion
        # opportunity, defeating the event-based-cutoff guarantee. (the Staff Engineer F0.)
        # Convention: the capture date follows the bold title (same line for holodeck/
        # addon formats, next line for the project-rag `## **title**\n  <date>` format);
        # dates inside the title sit within the bold span and are excluded.
        title_m = el._BOLD_SPAN.search(body)
        date_m = el._ISO_DATE.search(body, title_m.end() if title_m else 0)
        date = date_m.group(1) if date_m else None
        is_uni = "[universal]" in body
        if is_uni and date and date < cutoff:
            archive_entries.append((start + 1, date, body))
        else:
            keep_spans.append((start, end))
    return preamble, keep_spans, archive_entries, len(header_idxs)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", type=Path, help="repo root or path to tasks/lessons.md")
    # Cutoff is REQUIRED — there is no safe silent default. At observed capture rates
    # (~15 entries/day) a fixed age window is far too porous (a 30-day window retains
    # ~450 entries). The safe cutoff is event-based: the last completed central run
    # (those entries had a promotion opportunity). --days exists only as an explicit,
    # conservative floor for repos with no reachable central-run history.
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--before", default=None, help="cutoff YYYY-MM-DD (entries dated < this are swept) — PREFERRED: pass the last central-run date")
    g.add_argument("--days", type=int, default=None, help="explicit fallback: cutoff = today - N days (no default; --before preferred)")
    ap.add_argument("--archive-dir", type=Path, default=None,
                    help="archive dir (default <repo>/archive/lessons-archived)")
    ap.add_argument("--apply", action="store_true", help="write changes (default dry-run)")
    args = ap.parse_args(argv)

    try:
        lessons = _resolve_lessons_path(args.path)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Cutoff validation (the Staff Engineer F1): a blank --before satisfies argparse's required
    # group but is not a usable cutoff. Fail loud with a distinct exit code and a
    # clear message rather than crashing in timedelta(None) — the caller (skill) is
    # expected to SKIP the age-sweep, not invoke with an empty cutoff.
    if args.before is not None:
        cutoff = args.before.strip()
        if not cutoff:
            print("error: --before is empty — cutoff could not be determined. "
                  "The caller should SKIP the age-sweep (no completed central run "
                  "reachable), not invoke with a blank cutoff.", file=sys.stderr)
            return 2
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cutoff):
        print(f"error: cutoff '{cutoff}' is not a YYYY-MM-DD date", file=sys.stderr)
        return 2

    el = _load_extractor()
    mtime_at_read = lessons.stat().st_mtime  # TOCTOU guard (re-checked before write)
    lines = lessons.read_text(encoding="utf-8").splitlines()
    preamble, keep_spans, archive_entries, total = partition(lines, cutoff, el)

    out: list[str] = list(preamble)
    for (s, e) in keep_spans:
        out.extend(lines[s:e])
    # Collapse runs of 2+ blank lines (archived gaps leave them) to a single blank.
    collapsed: list[str] = []
    for ln in out:
        if ln.strip() == "" and collapsed and collapsed[-1].strip() == "":
            continue
        collapsed.append(ln)
    out = collapsed
    new_text = "\n".join(out).rstrip("\n") + "\n"
    orig_bytes = lessons.stat().st_size
    new_bytes = len(new_text.encode("utf-8"))
    pct = 100 * (orig_bytes - new_bytes) // max(orig_bytes, 1)

    print(f"age-sweep  {lessons}")
    print(f"  cutoff            : {cutoff}  ({'--before' if args.before else f'--days {args.days}'})")
    print(f"  entries seen      : {total}")
    print(f"  ARCHIVE (aged uni): {len(archive_entries)}")
    print(f"  KEEP              : {len(keep_spans)}")
    print(f"  lessons.md        : {orig_bytes} -> {new_bytes} bytes ({pct}% smaller)")

    if not archive_entries:
        print("  nothing aged out — no-op.")
        return 0
    # Guard the degenerate all-archived case (the Staff Engineer F5): refuse to write a file that
    # would be empty/whitespace-only — that only happens if every entry aged out AND
    # there is no preamble, which is never the intended flow (project-specific entries
    # are always kept). Abort rather than wipe the file.
    if not new_text.strip():
        print("  error: kept reconstruction is empty (all entries archived, no preamble) "
              "— refusing to write a near-empty lessons.md; aborting.", file=sys.stderr)
        return 2
    if not args.apply:
        print("  [DRY-RUN] no files written. Pass --apply to write.")
        return 0

    # TOCTOU guard (the Staff Engineer narrative): a concurrent session may have appended a lesson
    # between our read and this write; clean-tree discipline guards staged state, not a
    # mid-run append. Re-stat and abort if the file changed under us — the caller retries.
    if lessons.stat().st_mtime != mtime_at_read:
        print("  error: lessons.md changed on disk since read (concurrent edit) "
              "— aborting to avoid clobbering; re-run.", file=sys.stderr)
        return 3

    now = datetime.now(timezone.utc)  # one clock for filename, stamp, and cutoff fallback
    # Derive repo root for the archive dir: <repo>/tasks/lessons.md -> <repo>.
    repo_root = lessons.resolve().parent.parent
    adir = args.archive_dir or (repo_root / "archive" / "lessons-archived")
    adir.mkdir(parents=True, exist_ok=True)
    af = adir / (now.strftime("%Y-%m") + ".md")
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    buf: list[str] = []
    if not af.exists():
        buf.append(f"# Archived lessons — {now.strftime('%Y-%m')}\n")
    for (ln, date, body) in archive_entries:
        buf.append(
            f"\n# Age-swept by /learn-lessons on {stamp} from tasks/lessons.md:{ln} "
            f"(dated {date}, pre-{cutoff} [universal]; canonical home: central wikis)\n"
        )
        buf.append(body + "\n")
    with af.open("a", encoding="utf-8") as fh:
        fh.write("".join(buf))
    lessons.write_text(new_text, encoding="utf-8")
    print(f"  [APPLIED] kept {len(keep_spans)} entries in {lessons}")
    print(f"  [APPLIED] archived {len(archive_entries)} entries to {af}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
