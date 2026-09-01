# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""freeze-review-diff.py — materialize a frozen review diff to disk by name.

Purpose: coordinator:code-reviewer's Bash is allowlist-confined by
coordinator_core.bash_guards.block_reviewer_bash_outside_allowlist (fail-closed,
no escape hatch, correctly so) — it cannot run `git show` / `git diff` / `git
log` itself. Every non-weekly review-dispatch gate therefore needs the diff
frozen to a file BEFORE dispatch, with the reviewer pointed at the path. Five
DoE-claude skill surfaces landed this as a hand-written `git diff > file`
fenced shell block — a command payload the EM reads out of a markdown fence
and retypes into a shell (unlintable, untestable, invisible to the coverage
gate, because a fence is not a file — PM ruling, 2026-07-22). This CLI is the
op those fences collapse into: a skill LINKS to this entrypoint by name
instead of carrying the payload.

Writes `<repo-root>/state/review-trail/diffs/<slice-id>.diff` (the diff of
`--range`, restricted to `--paths` when given) and
`<repo-root>/state/review-trail/diffs/<slice-id>.head.sha` (the freeze-time
HEAD sha, so drift between freeze and synthesis is detectable rather than
silent — parity with `coordinator/skills/parallel-code-review/SKILL.md`'s own
`head.sha`, the pre-existing pattern this CLI generalizes). Prints the
resolved `.diff` path to stdout; callers capture it and inject it into a
reviewer's dispatch brief.

--range is REQUIRED and is NEVER defaulted (not to `origin/main...HEAD`, not
to anything else). `/workstream-complete` resolves a *session-scoped* range
(`--session-id`, matching the `Session-Id:` git trailer — see
review-brightline-gate.py) precisely so a shared `work/*` branch's concurrent-
session commits are NOT swept into a review; a defaulted range here would
silently reintroduce the 2026-06-15 multi-EM-brightline-noise failure at every
caller. The caller owns range resolution; this tool only owns freezing it.

Usage:
    freeze-review-diff.py --range <RANGE> --slice-id <ID>
                           [--paths <pathspec> ...] [--repo-root <path>]

No open-loop trail record (RETIRED 2026-09-01)
---------------------------------------------
This CLI used to write a ``verdict: pending`` ``state/review-trail/*.json``
record on every freeze, routed through the ``review_trail.write`` op, with
``--print-trail-record`` / ``--no-trail-record`` / ``--reviewer`` / ``--scope``
attached to it. ``review_trail.write`` is a gravestone (kill-ledger K-060,
2026-08-27) with ``_no_fallback`` by design, so the write could not succeed
under any configuration and the leg emitted only stderr noise — or, for the
one caller that asked for the record path, an unconditional exit 3.

The record was never the binding. ``artifact-shape-contract.schema.json`` says
of ``reviewed_range``, verbatim, that it "ADMITS, NEVER REPLACES" a
``state/review-trail/*.json`` record and "does not credit coverage, does not
duplicate or re-implement the trail record" — the reviewer's own attestation
was always the binding, and a retired writer leaves nothing to admit. DR-372's
receipt stamped on the reviewer's sidecar is the replacement; K-060's
``Returns-when`` is "Not applicable". So the leg and its four flags came out
together, in sequence behind DoE-claude's ``compose-review-wave`` dropping the
``trailRecord`` key it fed (DoE f3d3128c8, closed b427d44b1) — that repo held
the only live caller, and removing our half first would have broken theirs.

The four flags are GONE, not accepted no-ops: an unrecognized-argument exit 2
tells a caller carrying a stale invocation that the mechanism is retired,
where a silently-tolerated flag would document one that does not exist.

STDOUT is exactly one line — the ``.diff`` path.
``parallel-review-orthogonality-guard.py``'s ``snapshot`` subcommand
(``_cmd_snapshot``) consumes it as ``proc.stdout.strip()``, a whole-stdout
slurp treated as one path from which it derives the ``.head.sha`` sibling by
suffix substitution; DoE-claude's fences slurp the same way via ``$(...)``. A
second stdout line would silently corrupt those derived paths while still
exiting 0.

--slice-id is a filename component, not a path: a value containing a path
separator or `..` is rejected (exit 1, nothing written) rather than silently
escaping `state/review-trail/diffs/`.

--repo-root defaults to the git root resolved from cwd (mirrors the
`git -C "$PWD" rev-parse --show-toplevel` idiom already used by
coordinator-write-review-trail.py / append-goal-event.py's own
`_resolve_repo_root`, re-derived locally per that convention rather than via
a shared helper).

An empty diff is a VALID outcome (e.g. a range with no net change under
`--paths`): both files are still written, exit 0, with a note on stderr — this
is deliberately NOT the die-silent-on-zero-match gate review-brightline-gate.py
reproduces from its bash oracle; that gate's negative-spec is a faithfully-
carried-over bash quirk, not a contract this new tool inherits.

Exit codes:
    0 — the freeze succeeded (diff, possibly empty, plus head.sha written;
        `.diff` path printed as the single stdout line).
    1 — the FREEZE failed: missing/empty --range, invalid --slice-id,
        unresolvable repo root, unresolvable HEAD, or `git diff` itself
        failing over --range (that failure's own stderr is surfaced verbatim,
        never swallowed).
    2 — argparse usage error (unrecognized argument, e.g. a stray `--`, a
        typo'd flag, or one of the four retired trail-record flags above).
        This is `parser.parse_args` fail-loud by design, NOT
        `parse_known_args` — an unrecognized argument must never be silently
        dropped: a dropped `--paths` restriction would freeze the WRONG
        (over-broad) diff while still reporting exit 0, the exact
        silent-wrong-artifact failure this CLI exists to prevent.
    There is no exit 3. It meant "freeze succeeded, trail record refused, and
    the caller asked for the record path", and it retired with the record —
    stated affirmatively so its absence from this matrix reads as the
    retirement it is rather than as a dropped row.

Spec backlink: cross-repo/inbox/2026-07-23-claude-central-em-review-diff-freeze-op-wanted.md
Prior pattern: coordinator/skills/parallel-code-review/SKILL.md (DoE-claude) — the
existing frozen-diff + head.sha shape this CLI generalizes to the other five
non-weekly review-dispatch gates.

Composing algorithm: the actual git-diff-and-write sequence (rev-parse HEAD,
git diff <range> [-- <paths>], write the two output files) now lives in
`coordinator_core.ops.review_freeze_diff.freeze_diff` — the same op the
`review.freeze_diff` JSON-RPC handler calls — imported directly below rather
than re-implemented, so the algorithm exists exactly once. This CLI owns only
argv parsing and the exit-code/stdout/stderr contract; it does not re-derive
the write.

Negative-spec:
    - Does NOT resolve or validate `--range` beyond passing it to `git diff`
      verbatim — range resolution (session-scoping, merge-base defaulting,
      etc.) is entirely the caller's responsibility, by design (see above).
    - Does NOT re-implement the git-diff-and-write sequence — see "Composing
      algorithm" above; a second copy of that logic here would be exactly the
      drift risk this tool's own docstring warns the five shell fences created.
    - Does NOT delete or rotate prior diffs under the same slice-id — a
      second freeze under the same id silently overwrites the prior pair.
    - Does NOT emit a second stdout line under any flag — see the
      stdout-slurping callers named above.
    - Does NOT write, route to, or name any `state/review-trail/*.json`
      record. `review_trail.write` is a gravestone and this CLI is no longer
      one of its callers; a freeze asserts nothing about an open review loop.
      The only `state/review-trail/` path it touches is the `diffs/`
      subdirectory it writes its own two artifacts into.
    - Does NOT accept `--print-trail-record`, `--no-trail-record`,
      `--reviewer`, or `--scope`. They existed only to shape the retired
      record and are refused as unrecognized arguments (exit 2), never
      tolerated as no-ops.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROG = "freeze-review-diff.py"
_SCRIPT_DIR = Path(__file__).resolve().parent
_CLAUDE_KLABAUTER_REPO_ROOT = Path(__file__).resolve().parents[2]

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put the claude-klabauter repo root on ``sys.path`` before ``coordinator_core``
    is imported.

    Idempotent; safe to call more than once. Moved out of module scope
    (2026-08-28) -- unconditionally mutating `sys.path` at import time made
    every import of this file mutate the `sys.path` of a warm server ~50
    sessions share. Only the trigger moved; the effect is byte-for-byte the
    same.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_CLAUDE_KLABAUTER_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_CLAUDE_KLABAUTER_REPO_ROOT))
    _BOOTSTRAP_DONE = True

#: The .cmd launcher's own basename — used by `recover_windows_argv` to locate
#: where this invocation's own arguments begin within the raw `%CMDCMDLINE%`
#: capture (see `raw_cmdline_recovery` module docstring). `--range` is a git
#: rev/range this CLI's caller types directly (never defaulted — see module
#: docstring), and git revision syntax leans on a literal `^` (`sha^..sha`,
#: the per-commit predecessor-range shape a chain-scoped caller types) --
#: exactly the character cmd.exe's `%*` batch-parameter population strips
#: silently. Refuses on an unvouchable capture (coordinator-write-review-
#: trail.py's C2 posture, not scoped-git-commit's C2b detect-and-record --
#: this is a low-traffic per-review CLI, not a ~40-concurrent-session commit
#: hot path, so a false refusal does not carry C2b's fleet-break risk).
_LAUNCHER_CMD_NAME = "freeze-review-diff.cmd"

def _resolve_repo_root(explicit: str) -> Path | None:
    """Resolve the repo root: --repo-root verbatim if supplied, else the git
    root from cwd (mirrors coordinator-write-review-trail.py's
    `_resolve_repo_root` / the `git -C "$PWD" rev-parse --show-toplevel`
    idiom used across this tree's other standalone bin/*.py entrypoints)."""
    if explicit:
        return Path(explicit)
    _bootstrap_engine()
    from coordinator_core.git.repo_root import show_toplevel

    root = show_toplevel(os.getcwd())
    if not root:
        print(f"{_PROG}: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return None
    return Path(root)


def main(argv: list[str]) -> int:
    _bootstrap_engine()
    from coordinator_core.cli_entry import recording_declared_writes
    from coordinator_core.ops.review_freeze_diff import _validate_slice_id, freeze_diff

    parser = argparse.ArgumentParser(prog=_PROG, add_help=False)
    parser.add_argument("--range", dest="range_", default="")
    parser.add_argument("--slice-id", dest="slice_id", default="")
    parser.add_argument("--paths", dest="paths", nargs="*", default=[])
    parser.add_argument("--repo-root", dest="repo_root", default="")
    args = parser.parse_args(argv)

    # OUTLIVED the retired trail record rather than depending on it: a range
    # that never reaches the reviewer's frozen payload can never be attested
    # by anyone, whatever else is or is not written alongside it. That is what
    # the 2026-06-15 multi-EM-brightline-noise failure was, and it is still
    # live.
    if not args.range_:
        print(
            f"{_PROG}: --range is required and is never defaulted — the caller "
            "owns range resolution (e.g. a --session-id-scoped range); pass it "
            "explicitly.",
            file=sys.stderr,
        )
        return 1

    slice_err = _validate_slice_id(args.slice_id)
    if slice_err:
        print(f"{_PROG}: {slice_err}", file=sys.stderr)
        return 1

    repo_root = _resolve_repo_root(args.repo_root)
    if repo_root is None:
        return 1

    # DR-276: freeze_diff() is a plain function called directly (not an op
    # main(argv)), so its declared writes are claimed via
    # recording_declared_writes rather than run_op_main.
    with recording_declared_writes(cwd=str(repo_root)):
        result = freeze_diff(repo_root, args.range_, args.slice_id, args.paths or None)
    if result["error"] is not None:
        print(f"{_PROG}: {result['error']}", file=sys.stderr)
        return 1

    if result["empty"]:
        print(
            f"{_PROG}: note: diff is empty for range {args.range_!r} "
            f"(paths={args.paths or 'all'}) — froze an empty diff, not an error",
            file=sys.stderr,
        )
    print(result["diff_path"])
    return 0


if __name__ == "__main__":
    # `import lib` is what bootstraps `sys.path` for `raw_cmdline_recovery`
    # below -- an undocumented dependency on a sibling module's import side
    # effect, named explicitly here rather than left implicit.
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from raw_cmdline_recovery import UnsoundRawCmdlineTransport, recover_windows_argv

    try:
        _argv = recover_windows_argv(sys.argv[1:], _LAUNCHER_CMD_NAME)
    except UnsoundRawCmdlineTransport:
        # Remediation names a runnable command line, not a slash command and not
        # a bare basename: this fires before argv is trustworthy, so it cannot
        # assume a cwd. `_SCRIPT_DIR` resolves to wherever this file is actually
        # installed. → CLAUDE.md § Runtime conventions (cold-path remediation).
        print(
            f"{_PROG}: the invoking shell stripped characters from this command "
            f'line before this process started — run `python "{_SCRIPT_DIR / "freeze-review-diff.py"}" '
            "...` instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(main(_argv))
