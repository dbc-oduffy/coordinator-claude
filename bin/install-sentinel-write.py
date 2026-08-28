# coordinator/bin/install-sentinel-write
#
# Separable sentinel-writer for the agentic install integrity primitive.
# Writes <path>/version.txt containing one line of 40-hex git SHA + LF.
#
# Paired with coordinator/bin/check-install-divergence.py (reader). See
# docs/wiki/agentic-install-integrity.md for the format spec and
# docs/wiki/cross-repo-handshake-doctrine.md § Carve-out for the
# doctrinal justification of the bare-SHA format.
#
# Usage:
#   install-sentinel-write --path <target-dir> [--source <git-root>] [--sha <40-hex>]
#
# Semantics:
#   - With --sha: validate matches ^[0-9a-f]{40}$ and write to <target>/version.txt.
#   - Without --sha: git -C <source> rev-parse HEAD (default --source .), validate, write.
#   - Idempotent: always overwrites; never reads-then-writes.
#   - File contents: ONE line of 40-hex SHA + trailing LF. UTF-8.
#
# Exit codes:
#   0  success
#   1  validation failure (non-hex --sha, malformed git HEAD), bad path, or git error

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

GENERATES = []  # writes <--path>/version.txt to a caller-supplied install-target directory outside claude-klabauter's own tracked tree

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _resolve_sha(source: Path, sha_arg: str | None) -> str:
    if sha_arg is not None:
        if not _SHA_RE.fullmatch(sha_arg):
            print(f"ERROR: --sha is not 40-hex: {sha_arg!r}", file=sys.stderr)
            sys.exit(1)
        return sha_arg

    if not source.is_dir():
        print(f"ERROR: --source path does not exist or is not a directory: {source}", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"ERROR: git rev-parse HEAD failed (exit {result.returncode}) in {source}\n"
            f"stderr: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)

    sha = result.stdout.strip()
    if not _SHA_RE.fullmatch(sha):
        print(f"ERROR: git HEAD did not produce a 40-hex SHA: {sha!r}", file=sys.stderr)
        sys.exit(1)
    return sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a 40-hex source-HEAD SHA into <path>/version.txt.",
    )
    parser.add_argument("--path", required=True, help="Target directory; version.txt is written at <path>/version.txt.")
    parser.add_argument("--source", default=".", help="Git repo root to read HEAD from (default: cwd).")
    parser.add_argument("--sha", default=None, help="Explicit 40-hex SHA; bypasses git rev-parse.")
    args = parser.parse_args(argv)

    target = Path(args.path)
    if not target.is_dir():
        print(f"ERROR: --path does not exist or is not a directory: {target}", file=sys.stderr)
        return 1

    sha = _resolve_sha(Path(args.source), args.sha)

    sentinel = target / "version.txt"
    sentinel.write_text(sha + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
