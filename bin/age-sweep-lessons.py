"""Age-archive aged [universal] entries from state/lessons/*.yaml.

WHY THIS EXISTS
---------------
`state/lessons/` is read by `/learn-lessons`, the central-mode strip-local pull-pass,
and the PM-invoked `/workstream-start` ceremony (it is NOT a Tier-0 boot read; see
the coordinator doctrine repo's coordinator/docs/wiki/tiered-context-loading.md § 2. The Five Tiers,
negative spec "`state/lessons/` is NOT Tier 0" — coordinator/CLAUDE.md § Session
Orientation retired 2026-07-27). It is a capture queue: local-mode
`/learn-lessons` folds recent lessons to wikis but historically had no step that
*bounds the directory's size*, so it grows unbounded and each consumer pays a
proportional listing tax.

A `[universal]` lesson's canonical home is the CENTRAL coordinator wikis (promoted
by central-mode `/learn-lessons`, surfaced to planners by the prior-art-checker
pre-flight). Once an entry is older than the central promotion window, keeping it
in `state/lessons/` is redundant: its durable home is central, and git history is
the recovery net. So we age-archive aged universals and KEEP everything else.

PARTITION (per YAML entry, per `scope` and `created` fields)
  ARCHIVE  iff  scope == universal  AND  has a `created` date  AND  date < cutoff
  KEEP     otherwise:
             - project-specific entries (no central home) — any age
             - entries without `created` (can't prove aged) — conservative keep
             - universals within the window (may not be promoted yet)

Archival is via `git mv` to `archive/lessons/<YYYY-MM>/` (one YAML file per entry,
preserving git history). Unlike the old monolithic-file approach, no file is rewritten
— only the aged entries are moved.

Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C3a

SAFETY
  - Default DRY-RUN. `--apply` is required to write.
  - Archive moves files to <repo>/archive/lessons/YYYY-MM/ via `git mv` (git-tracked).
  - Operates on one directory listing; each `git mv` is atomic per file.

CUTOFF
  --before YYYY-MM-DD   explicit cutoff (preferred: pass the last central-run
                        date so only entries that already had a promotion
                        opportunity are swept).
  --days N              explicit conservative floor: cutoff = today - N days.
                        NO default — one of --before / --days is required, since
                        there is no safe silent age window. Prefer --before.

Usage:
  age-sweep-lessons.py <repo-root-or-lessons-dir> [--before DATE | --days N]
                       [--archive-dir DIR] [--apply]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml  # PyYAML — available in coordinator venv

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

cc_invoke.ensure_engine_on_path(__file__)


def _resolve_lessons_dir(arg: Path) -> Path:
    """Accept either a repo root or a direct path to the lessons directory."""
    if arg.is_dir() and arg.name == "lessons":
        return arg
    cand = arg / "state" / "lessons"
    if cand.is_dir():
        return cand
    raise FileNotFoundError(
        f"no state/lessons/ directory at {arg} or {cand}; "
        f"pass a repo root or the state/lessons/ directory directly"
    )


def partition(
    lessons_dir: Path, cutoff: str
) -> tuple[list[tuple[Path, str]], list[Path], int]:
    """Partition YAML files into (archive_entries, keep_files, total_count).

    archive_entries: list of (yaml_path, date_str) — aged universal entries to archive
    keep_files:      list of yaml_path — entries that stay in state/lessons/
    total_count:     total YAML files scanned

    ARCHIVE iff scope=='universal' AND created date present AND date < cutoff.
    KEEP otherwise — conservative for missing scope, missing date, project-scoped entries.
    """
    yaml_files = sorted(lessons_dir.glob("*.yaml"))
    archive_entries: list[tuple[Path, str]] = []
    keep_files: list[Path] = []

    for f in yaml_files:
        try:
            fm = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"warning: skipping malformed YAML {f.name}: {e}", file=sys.stderr)
            keep_files.append(f)
            continue

        created = fm.get("created")
        # PyYAML parses `created: 2026-06-30` (unquoted) as a date object; normalise to str.
        date = str(created) if created is not None else None
        # The migration sentinel "0000-00-00" (undated legacy entry) means date-UNKNOWN, not
        # ancient. Treat it as missing so the conservative-keep path applies — an entry whose
        # date we cannot prove must not be auto-archived (matches this script's stated contract:
        # "entries without created (can't prove aged) — conservative keep").
        if date == "0000-00-00":
            date = None
        scope = str(fm.get("scope", "")).strip()
        is_uni = scope == "universal"

        if is_uni and date and date < cutoff:
            archive_entries.append((f, date))
        else:
            keep_files.append(f)

    return archive_entries, keep_files, len(yaml_files)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", type=Path,
                    help="repo root or path to state/lessons/ directory")
    # Cutoff is REQUIRED — there is no safe silent default.
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--before", default=None,
                   help="cutoff YYYY-MM-DD (entries dated < this are swept) — PREFERRED: pass the last central-run date")
    g.add_argument("--days", type=int, default=None,
                   help="explicit fallback: cutoff = today - N days (no default; --before preferred)")
    ap.add_argument("--archive-dir", type=Path, default=None,
                    help="archive dir (default <repo>/archive/lessons/<YYYY-MM>/)")
    ap.add_argument("--apply", action="store_true", help="move files (default dry-run)")
    args = ap.parse_args(argv)

    try:
        lessons_dir = _resolve_lessons_dir(args.path)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    # Cutoff validation: a blank --before satisfies argparse's required group but is
    # not a usable cutoff. Fail loud with a distinct exit code.
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

    archive_entries, keep_files, total = partition(lessons_dir, cutoff)

    print(f"age-sweep  {lessons_dir}")
    print(f"  cutoff                   : {cutoff}  ({'--before' if args.before else f'--days {args.days}'})")
    print(f"  entries seen             : {total}")
    print(f"  ARCHIVE (aged universal) : {len(archive_entries)}")
    print(f"  KEEP                     : {len(keep_files)}")

    if not archive_entries:
        print("  nothing aged out — no-op.")
        return 0

    if not args.apply:
        print("  [DRY-RUN] no files moved. Pass --apply to move.")
        for f, date in archive_entries:
            print(f"    would archive: {f.name} (dated {date})")
        return 0

    # Repo root: state/lessons/ → state/ → repo root
    repo_root = lessons_dir.resolve().parent.parent

    now = datetime.now(timezone.utc)
    ym = now.strftime("%Y-%m")
    adir = args.archive_dir or (repo_root / "archive" / "lessons" / ym)
    adir.mkdir(parents=True, exist_ok=True)

    from coordinator_core.win_portability import no_console_creationflags

    archived = _batched_git_mv_into_dir(
        [src for src, _date in archive_entries], adir, repo_root, no_console_creationflags()
    )
    if archived is None:
        return 1
    for src, _date in archive_entries:
        print(f"  [APPLIED] archived {src.name} -> {adir / src.name}")

    print(f"  [APPLIED] moved {archived} entries to {adir}")
    return 0


# Windows caps a process command line at 32767 characters (`CreateProcess`); a
# corpus of aged lessons can in principle exceed one batch. All sources share
# ONE destination directory here (same `adir` for the whole sweep), so `git mv
# src1 src2 ... dst/` is valid git syntax (basenames are preserved on a
# directory destination) and the batch just needs byte-budget chunking against
# the argv cap -- the idiom named in this plan's Safe-primitive map
# (discriminator 7), applied by hand here since the loop target is a `Path`
# list, not a raw argv splice.
_GIT_MV_BATCH_BUDGET = 20000


def _batched_git_mv_into_dir(
    srcs: list, dst_dir, repo_root, creationflags_kwargs: dict
) -> int | None:
    """`git mv` every `srcs` entry into `dst_dir` (same target for all, so
    basenames are preserved) using as few spawns as the argv-length budget
    allows: N -> ceil(N / batch) calls, never N -> N. Returns the count moved,
    or None (having already printed the ERROR) on any batch failure -- a
    batch failure aborts the sweep rather than guessing which entries in a
    failed batch actually moved."""
    if not srcs:
        return 0
    batches: list[list] = []
    current: list = []
    current_len = 0
    for src in srcs:
        entry_len = len(str(src)) + 1
        if current and current_len + entry_len > _GIT_MV_BATCH_BUDGET:
            batches.append(current)
            current = []
            current_len = 0
        current.append(src)
        current_len += entry_len
    if current:
        batches.append(current)

    moved = 0
    for batch in batches:
        result = subprocess.run(
            ["git", "mv", *[str(s) for s in batch], str(dst_dir)],
            capture_output=True,
            cwd=str(repo_root),
            **creationflags_kwargs,
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            print(f"  error: git mv failed for a {len(batch)}-entry batch: {err}", file=sys.stderr)
            return None
        moved += len(batch)
    return moved


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
