"""sweep_argv.py — shared leading-dash-argument guard for the sweep-*.py CLI trampolines.

Purpose: several sibling coordinator/bin/sweep-*.py trampolines
(sweep-actioned-memos.py, sweep-terminal-plans.py, sweep-boot.py,
sweep-consumed-handoffs.py) each grew their own ad hoc argv scan that either
(a) took `argv[0]` unconditionally as the repo-root positional -- so
`--help` or a mistyped flag was silently forwarded downstream as a bogus
"repo root" -- or (b) recognized its own flag vocabulary but fell through to
treating any OTHER leading-dash token as a legitimate positional. Both
shapes turn a usage mistake into a fail-silent success (the malformed value
reaches `coordinator_core.invoke`, the transport call fails, and the
trampoline's best-effort log-and-continue posture swallows the error and
still exits 0). This module centralizes the "reject an unrecognized
leading-dash token" scan exactly once, instead of re-copy-pasting it into
every trampoline.

Negative-spec: does NOT own any script's OWN flag vocabulary (`--dry-run`,
a second `state_common_dir` positional, etc) -- callers pass their own
`known_flags` set and interpret `flags_seen` themselves. This module only
answers "is this token a flag I must reject, or a legitimate positional?".
Does NOT print to stdout on error (usage/error text on --help goes to
stdout by convention -- matching prior per-script behavior; on an actual
error it goes to stderr) and does NOT call `sys.exit` itself -- it returns
an explicit exit code for the caller's own `main()` to return, so `main()`
stays a plain callable (important for the existing `_run_main_capturing`
test-harness shape used across this directory's test_sweep_*.py files).

Spec backlink: coordinator/bin/sweep-actioned-memos.py `--help`
fail-silent-success fix, 2026-07-25.
"""
from __future__ import annotations

import sys
from typing import FrozenSet


def parse_repo_root_argv(
    argv: list[str],
    *,
    prog: str,
    usage: str,
    known_flags: FrozenSet[str] = frozenset(),
    max_positional: int = 1,
) -> tuple[list[str], set[str], "int | None"]:
    """Scan argv for -h/--help, caller-known flags, unrecognized leading-dash
    tokens, and positional arguments.

    Returns (positional_args, flags_seen, early_exit_code).

    `early_exit_code` is None on success -- the caller proceeds using
    `positional_args`/`flags_seen`. When it is not None, usage/error text has
    ALREADY been printed to the correct stream (stdout for --help, stderr for
    everything else) and the caller MUST return that code immediately without
    doing any further work.
    """
    positional: list[str] = []
    flags_seen: set[str] = set()
    for arg in argv:
        if arg in ("-h", "--help"):
            print(usage)
            return [], flags_seen, 0
        if arg.startswith("-"):
            if arg in known_flags:
                flags_seen.add(arg)
                continue
            print(f"{prog}: unrecognized argument: {arg!r}", file=sys.stderr)
            print(usage, file=sys.stderr)
            return [], flags_seen, 2
        positional.append(arg)
    if len(positional) > max_positional:
        print(
            f"{prog}: too many positional arguments (expected at most "
            f"{max_positional}, got {len(positional)}: {positional!r})",
            file=sys.stderr,
        )
        print(usage, file=sys.stderr)
        return [], flags_seen, 2
    return positional, flags_seen, None
