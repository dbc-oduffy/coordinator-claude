"""Print a file's modification time as a timezone-aware RFC3339 stamp.

Purpose: the deep-research drivers must pass `claims-emit --ran-at` the moment
the merge actually happened, and the only honest source for that is the mtime of
`merged-claims.json`. A synthesizer has no shell and no clock, so a timestamp it
offers in a completion message is an estimate; `claims-emit` validates RFC3339
*shape* only, so a confident guess lands in the durable sidecar looking exactly
like a measured value.

This exists as an entrypoint rather than an inline `python -c` because the
one-liner it replaces needed a shell assignment, a command substitution and two
statement separators to say this much -- a payload for an operator to retype,
invisible to every linter and to both test registries
(`NO-MULTI-LINE-SHELL-FENCE`). It lives beside the pipeline that calls it, not
under `coordinator/bin/`, because that tree is sourced wholly from the engine at
publish time and so reaches no OSS consumer; `pipelines/` publishes.

Negative spec: does not read, parse or validate the file's contents -- the
argument's only role is to carry an mtime, and a `merged-claims.json` that is
malformed still has an honest one. Does not invent a stamp for a missing file:
an unreadable path exits 1 naming it, because a driver that silently substituted
`now()` would write exactly the unmeasured value this script exists to prevent.

Contract:
  argv[1] -- path to the file whose mtime is the answer
  stdout  -- one RFC3339 UTC stamp (`2026-09-20T12:41:20.123456+00:00`)
  exit 0  -- stamp printed
  exit 1  -- no argument, or the path cannot be stat'd (reason on stderr)
"""

from __future__ import annotations

import datetime
import pathlib
import sys


def main(argv: "list[str]") -> int:
    if len(argv) != 2:
        print(f"usage: {pathlib.Path(argv[0]).name} <path>", file=sys.stderr)
        return 1
    target = pathlib.Path(argv[1])
    try:
        mtime = target.stat().st_mtime
    except OSError as exc:
        print(f"cannot stat {target}: {exc}", file=sys.stderr)
        return 1
    stamp = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc)
    print(stamp.isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
