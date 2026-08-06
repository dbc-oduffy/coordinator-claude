"""backfill-chain-ancestry-waiver-paths.py — one-shot repo-relative rewrite
of `source_handoff` in already-minted chain-ancestry waiver records.

Purpose: `record_chain_ancestry_waiver` (coordinator_core/chain_ancestry_waivers.py)
now normalizes `source_handoff` to repo-relative at write time (see
`_repo_relative_source_handoff`), fixing every FUTURE mint. Records minted
before that fix still carry a machine-absolute path baked into a file
committed under `state/review-trail/chain-ancestry-waivers/`, which is wrong
the moment another host clones the repo. This script sweeps the existing
on-disk records and applies the SAME helper retroactively — imported, not
duplicated, so the two paths can never drift.

Reported by doe-claude-em (cross-repo/inbox/
2026-08-06-doe-claude-em-chain-ancestry-waiver-absolute-path.md).

Naked Python, no bash — this repo's runtime-conventions rule (CLAUDE.md).

Usage:
  backfill-chain-ancestry-waiver-paths.py [--repo-root PATH] [--apply]

Default is --dry-run (no writes); pass --apply to rewrite in place.
Idempotent: a record already repo-relative (or absolute-but-outside-root) is
left untouched on a second run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT_GUESS = os.path.dirname(os.path.dirname(_BIN_DIR))
if _REPO_ROOT_GUESS not in sys.path:
    sys.path.insert(0, _REPO_ROOT_GUESS)

from coordinator_core.chain_ancestry_waivers import (  # noqa: E402
    CHAIN_ANCESTRY_WAIVER_DIRNAME,
    repo_relative_source_handoff,
)


def _iter_waiver_files(repo_root: str) -> list:
    root = Path(repo_root) / "state" / "review-trail" / CHAIN_ANCESTRY_WAIVER_DIRNAME
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*.json"))


def _process_file(path: Path, repo_root: str, apply: bool) -> str:
    try:
        text = path.read_text(encoding="utf-8")
        record = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        return f"SKIP (unreadable: {exc}): {path}"

    original = record.get("source_handoff")
    normalized = repo_relative_source_handoff(repo_root, original)
    if normalized == original:
        return f"UNCHANGED: {path}"

    if apply:
        record["source_handoff"] = normalized
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
            fh.write("\n")
        return f"REWRITTEN: {path} ({original!r} -> {normalized!r})"
    return f"WOULD REWRITE: {path} ({original!r} -> {normalized!r})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=_REPO_ROOT_GUESS,
        help="Repo root under which state/review-trail/chain-ancestry-waivers/ lives "
        "(default: the repo this script lives in).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Print, do not write (default).")
    mode.add_argument("--apply", action="store_true", default=False, help="Rewrite records in place.")
    args = parser.parse_args()

    apply = args.apply
    repo_root = str(Path(args.repo_root).resolve())

    files = _iter_waiver_files(repo_root)
    if not files:
        print(f"No waiver records found under {repo_root}")
        return 0

    rewritten = 0
    for path in files:
        result = _process_file(path, repo_root, apply)
        print(result)
        if result.startswith("REWRITTEN") or result.startswith("WOULD REWRITE"):
            rewritten += 1

    print(f"\n{rewritten} of {len(files)} record(s) {'rewritten' if apply else 'would be rewritten'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
