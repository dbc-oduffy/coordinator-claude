"""regenerate-generator-content-cache.py — rebuild the shipped, git-committed
content-keyed cache `coordinator_core/ops/generator-content-cache.json`.

WHY THIS EXISTS
    `coordinator_core.ops.generator_scan_cache`'s (mtime_ns, size)-keyed
    stat cache makes a WARM `discover_generators` run ~150-350ms (measured,
    under the 500ms brightline). It is useless on a FIRST-EVER run: git
    stores no mtime metadata, so a fresh clone or install stamps a brand
    new `mtime_ns` on every file regardless of content, and the stat cache
    misses on every entry the moment it lands
    (state/bug-backlog/2026-08-22-generator-discovery-ast-parses-71mb-per-
    94a6779e1ad8.yaml's 2026-09-07 and 2026-09-09 notes; both independently
    re-derived the same finding). A cold run then pays the full
    scan/parse cost: ~46-60s of process time.

    The content cache is the fix: a SECOND store, keyed on each file's own
    content hash rather than its stat, committed to the repo so it ships
    with every clone. A stat-miss on a fresh checkout still gets a
    content-hash hit whenever the file's bytes are unchanged from what this
    script last recorded, at the cost of one blake2b hash (~609ms/79.4MB
    measured — over the 500ms PER-RUN bar by itself, but this is a ONE-TIME
    cost paid once against a ~46-60s alternative, not a per-run cost; see
    `docs/research/spike-verdicts/2026-08-31-generator-discovery-cache-
    rebuild.md` for why that refutation does not transfer here).

WHAT THIS SCRIPT DOES, PRECISELY
    Walks the same sweep directories `generator_provenance.discover_generators`
    walks (`_SWEEP_DIRS`: coordinator/bin, bin, coordinator_core), reads
    every `.py` file's raw bytes, hashes each with
    `generator_scan_cache.content_hash`, and — for each DISTINCT digest —
    parses the source once and records its `FileWrites` (the same shape the
    stat cache holds: `generates`/`mutates`/`write_sites`/`write_surface_paths`,
    NEVER a resolved tracked-set verdict — see `generator_scan_cache`'s own
    docstring on why resolution stays a per-run, live-tracked-set concern).
    Writes the result to `generator-content-cache.json` via
    `generator_scan_cache.save_content_cache`, atomically, sorted for a
    stable diff.

    Deliberately does NOT call `discover_generators` or resolve anything
    against `git ls-files` — the content cache holds pre-resolution write
    facts only, so this script needs no git state at all beyond a plain
    file walk. This also means running it never depends on `.git/index`
    being in any particular state, and its output is identical regardless
    of which branch or commit it is run from, as long as the swept files'
    CONTENT is unchanged.

REGENERATION — WHEN AND HOW SOMEONE FINDS OUT
    Run this whenever `_SCHEMA_VERSION` in `generator_scan_cache.py` is
    bumped (a scanner-semantics change) — that module's own comment beside
    `_SCHEMA_VERSION` names this script as the required next step, in the
    same commit as the scanner change, and the version-gate in
    `load_content_cache` means a forgotten regeneration degrades SAFELY
    (every entry in the stale-schema file is ignored, cold path reverts to
    the pre-cache ~46-60s cost — never a silently wrong record) rather than
    silently serving stale write facts. There is no other trigger: a change
    that only ADDS or EDITS swept .py files does not need this script run,
    because a fresh clone's stat cache always misses on new/changed content
    and the content cache simply has nothing to say for a digest it has
    never seen — it falls through to a full scan for exactly that file, same
    as it would with no content cache at all.

USAGE
    python3 coordinator/bin/regenerate-generator-content-cache.py [--repo-root PATH] [--dry-run]

    --repo-root PATH   sweep this repo instead of the one this script lives
                        in (default: resolved from this script's own path —
                        coordinator/bin/../.. — since this is a repo-local
                        maintenance script, not a cross-repo tool).
    --dry-run          report counts, write nothing.

Negative-spec:
    - Never invoked by `discover_generators` or any production path — this
      is a human/ceremony-run maintenance script, run deliberately and
      committed deliberately (see `generator_scan_cache.save_content_cache`'s
      own docstring on why the writer is not the sweep itself).
    - Does not resolve the claude-klabauter engine root cross-repo (no `cc_invoke`,
      no engine-root ladder) — this script's job is this repo's own
      checkout, always, so a plain path computation from `__file__` is the
      correct (and only) resolution it needs.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_REPO_ROOT_FROM_SELF = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT_FROM_SELF) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FROM_SELF))

from coordinator_core.ops import generator_provenance as gp  # noqa: E402
from coordinator_core.ops import generator_scan_cache as cache  # noqa: E402


def _iter_swept_files(repo_root: Path):
    """Yield every `.py` file under each of `gp._SWEEP_DIRS`, exactly the
    population `discover_generators` walks (minus its stat-cache and
    tracked-set machinery, neither of which this script needs)."""
    for sweep_dir in gp._SWEEP_DIRS:
        start = repo_root / sweep_dir
        if not start.is_dir():
            continue
        for path in sorted(start.rglob("*.py")):
            if path.is_file():
                yield path


def build_content_cache(repo_root: Path) -> tuple[dict[str, gp.FileWrites], int]:
    """Scan every swept file once per DISTINCT content digest.

    Returns (entries, file_count) — `file_count` is the number of files
    walked (for reporting); `len(entries)` is the number of distinct
    contents among them, which is what actually gets written.
    """
    entries: dict[str, gp.FileWrites] = {}
    file_count = 0
    for path in _iter_swept_files(repo_root):
        file_count += 1
        try:
            data = path.read_bytes()
        except OSError:
            continue
        digest = cache.content_hash(data)
        if digest in entries:
            continue  # already scanned this exact content under another path

        try:
            source = data.decode("utf-8")
            tree = ast.parse(source, filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            writes = gp.FileWrites(
                generates=None, mutates=None, write_sites=[], syntax_error=True
            )
        else:
            writes = gp._scan_file_writes(tree)
        entries[digest] = writes
    return entries, file_count


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_REPO_ROOT_FROM_SELF,
        help="repo root to sweep (default: this script's own repo)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report counts, write nothing",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    entries, file_count = build_content_cache(repo_root)

    if args.dry_run:
        print(
            f"[dry-run] {file_count} files walked, {len(entries)} distinct "
            f"content digests -- generator-content-cache.json NOT written"
        )
        return 0

    cache.save_content_cache(entries)
    written = cache._content_cache_path()
    size_bytes = written.stat().st_size if written.exists() else 0
    print(
        f"wrote {written} -- {file_count} files walked, {len(entries)} "
        f"distinct content digests, {size_bytes} bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
