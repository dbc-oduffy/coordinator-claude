"""coordinator/bin/publish-resolve-target.py — thin CLI over
lib/percolate/resolve_target.resolve_publish_row.

Usage:
  publish-resolve-target.py <raw_row>

Port of: resolve-publish-target.sh (DoE 16302166, 2026-07-21) — preserves its
sourced-function contract exactly: one pipe-delimited row on stdout on
success, diagnostics on stderr, exit codes 0/1/2/3 (see
lib/percolate/resolve_target.py's module docstring for the full contract —
these codes are the CLI's return codes too).

Port: docs/plans/2026-07-21-percolate-python-port.md (chunk C-W0).

Cwd-independent: this script self-bootstraps its own `sys.path` (bin/../lib)
before importing `percolate.resolve_target`, so it requires no DOE_ROOT
injection or particular working directory from callers invoking it as a
subprocess.
"""

from __future__ import annotations

import os
import sys

def main(argv: list[str]) -> int:
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

    from percolate.resolve_target import ResolveError, resolve_publish_row

    if len(argv) != 2:
        print(
            f"usage: {os.path.basename(argv[0]) if argv else 'publish-resolve-target.py'} <raw_row>",
            file=sys.stderr,
        )
        return 2

    raw_row = argv[1]
    try:
        stdout_row = resolve_publish_row(raw_row)
    except ResolveError as exc:
        if exc.message:
            print(exc.message, file=sys.stderr)
        return exc.code

    print(stdout_row)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
