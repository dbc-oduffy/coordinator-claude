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
                           [--reviewer <name>]
                           [--scope <chain|session|workstream-close-auto>]
                           [--print-trail-record | --no-trail-record]

Open-loop record (ON BY DEFAULT)
--------------------------------
A freeze that never gets a verdict leaves no trace: the review-trail record is
written separately, after the review, by whoever dispatched it, so a session
that ends mid-round emits nothing and the chain coverage gate reads that
silence identically to a session that never reviewed at all
(docs/plans/2026-08-03-open-review-loops-are-a-named-gap.md § Problem).
EVERY freeze therefore writes a ``verdict: pending`` review-trail record for
the SAME range it resolved, routed through the native ``review_trail.write``
op via ``cc_invoke.route_mutation()`` — the same seam
``coordinator-write-review-trail.py`` uses (never a shell-out to that CLI,
never an open-coded record write). Record fields: ``sha_range`` = ``--range``,
``verdict`` = ``pending``, ``scope_kind`` = ``diff``, ``reviewed_paths`` =
``--paths`` when supplied, ``diff_loc`` = the frozen diff's line count,
``reviewer``/``scope`` from the two flags above.

Emission is unconditional BY DESIGN, per that plan's discharge test: a
mechanism that only fires when a caller remembers a flag has discharged
nothing, and the callers that would have to remember are a sibling repo's
prose fences (DoE-claude's mise ``PIPELINE.md``, ``review-wave.mjs``) — which
relocates the obligation instead of discharging it.

``pending`` is the open state — no new record field exists for it, and no
canonical filter credits a pending record with coverage
(``review_coverage_core._classify``, ``coverage._verdict_counts``).

STDOUT stays exactly one line by default (the ``.diff`` path), record or no
record. ``parallel-review-orthogonality-guard.py``'s ``snapshot`` subcommand
(``_cmd_snapshot``) consumes this CLI's stdout as ``proc.stdout.strip()`` — a
whole-stdout slurp treated as one path, from which it derives the
``.head.sha`` sibling by suffix substitution; DoE-claude's fences slurp the
same way via ``$(...)`` command substitution. A second unconditional stdout
line would silently corrupt those derived paths while still exiting 0. So
what is opt-in is the PRINTING, never the writing: ``--print-trail-record``
adds the record path as a second stdout line (``.diff`` path first).

``--no-trail-record`` is the opt-OUT, and exists for the narrow class of
caller that must freeze a diff WITHOUT asserting an open review loop: a probe
or dry-run that freezes only to measure (the orthogonality guard's snapshot is
the shape in question), and a test harness exercising the freeze contract
itself, for which a real trail record would be fixture pollution the chain
coverage gate later reads as truth. It is deliberately not a
convenience — suppressing the record re-opens the silence AC1 exists to close.

Exit 3 (record refused) is reserved for a caller that ASKED for the record
path: a refused write on the default path leaves a successful freeze
successful (exit 0 + stderr warning), because the write-side foreign-session
guard legitimately refuses ranges a freeze may still validly want (e.g.
commits carrying no attributable ``Session-Id:`` trailer), and turning those
freezes into failures would break callers that pass today.

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

Exit codes (the full matrix — freeze outcome x record outcome x flags):
    0 — the freeze succeeded (diff, possibly empty, plus head.sha written;
        `.diff` path printed). Covers all four record outcomes that leave a
        successful freeze successful:
          * record written, path NOT printed (the default: one stdout line);
          * record written, path printed as stdout line 2
            (--print-trail-record);
          * record write REFUSED and the caller did not ask for the path —
            refusal reason on stderr as a warning, stdout still one line;
          * record suppressed by --no-trail-record.
    1 — the FREEZE failed: missing/empty --range, invalid --slice-id,
        unresolvable repo root, unresolvable HEAD, or `git diff` itself
        failing over --range (that failure's own stderr is surfaced verbatim,
        never swallowed). No record is attempted.
    2 — argparse usage error (unrecognized argument, e.g. a stray `--` /
        typo'd flag; or --print-trail-record together with --no-trail-record,
        which are mutually exclusive). This is `parser.parse_args` fail-loud
        by design, NOT `parse_known_args` — an unrecognized argument must
        never be silently dropped: a dropped `--paths` restriction would
        freeze the WRONG (over-broad) diff while still reporting exit 0, the
        exact silent-wrong-artifact failure this CLI exists to prevent.
    3 — the freeze SUCCEEDED (both files written, `.diff` path printed) but
        the record write was refused (e.g. the foreign-session scope guard,
        an unresolvable session_id, an absent native seam) AND
        --print-trail-record was passed. Distinct from 1 so a caller can tell
        "no frozen diff" from "frozen diff, no open-loop record". Gated on the
        flag because a caller that asked for the record path and did not get
        one deserves the nonzero, while a default-path caller's freeze must
        not start failing merely because record emission became automatic.

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
    - Does NOT add a stdout line for the record unless --print-trail-record
      is passed — see the stdout-slurping callers named above. The WRITE is
      not gated on any flag; only the printing is.
    - Does NOT make the record write a precondition of the freeze. A refused
      record never unwrites the frozen diff and never fails the freeze on the
      default path.
    - Does NOT weaken or bypass `review_trail_write._guard_foreign_session_range`
      to make automatic emission succeed more often. A refused range is a
      correct refusal; the CLI degrades to a warning rather than arguing with
      it.
    - Does NOT open-code the record write or shell out to
      coordinator-write-review-trail.py — the native `review_trail.write` op
      via cc_invoke.route_mutation() is the only path, so the write-side
      foreign-session scope guard, symbolic-ref concretization, and
      never-clobber filename reservation all still apply to a pending record.
    - Does NOT invent an open/closed record field. `verdict: pending` IS the
      open state (docs/plans/2026-08-03-open-review-loops-are-a-named-gap.md
      § Anti-scope); a parallel `loop_state` key would be a second source of
      truth for the same fact.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PROG = "freeze-review-diff.py"

_CLAUDE_KLABAUTER_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_CLAUDE_KLABAUTER_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLAUDE_KLABAUTER_REPO_ROOT))

from coordinator_core.cli_entry import recording_declared_writes  # noqa: E402
from coordinator_core.ops.review_freeze_diff import (  # noqa: E402
    _validate_slice_id,
    freeze_diff,
)

def _resolve_repo_root(explicit: str) -> Path | None:
    """Resolve the repo root: --repo-root verbatim if supplied, else the git
    root from cwd (mirrors coordinator-write-review-trail.py's
    `_resolve_repo_root` / the `git -C "$PWD" rev-parse --show-toplevel`
    idiom used across this tree's other standalone bin/*.py entrypoints)."""
    if explicit:
        return Path(explicit)
    from coordinator_core.git.repo_root import show_toplevel

    root = show_toplevel(os.getcwd())
    if not root:
        print(f"{_PROG}: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return None
    return Path(root)


_PENDING_VERDICT = "pending"
_DEFAULT_RECORD_REVIEWER = "code-reviewer"
_DEFAULT_RECORD_SCOPE = "session"


def _diff_loc(diff_path: str) -> int:
    """Line count of the frozen diff, for the record's ``diff_loc`` field.

    Derived here rather than taken from ``freeze_diff``'s envelope: that op
    returns only a boolean ``empty``, never a count (its contract is fixed and
    shared with the ``review.freeze_diff`` JSON-RPC handler, so widening it is
    not this CLI's call). Reads the file the freeze just wrote instead of
    re-running git — the bytes on disk are the artifact the record attests.

    An unreadable file yields 0: a record whose LOC count is 0 is honest-ish
    and still fully usable as the open-loop marker, whereas failing the whole
    freeze over a count would be a worse trade.
    """
    try:
        return len(Path(diff_path).read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError as exc:
        print(f"{_PROG}: note: could not count diff lines for diff_loc ({exc}) — using 0", file=sys.stderr)
        return 0


def _no_fallback() -> None:
    """No bash legacy body exists for ``review_trail.write`` — a missing seam
    fails loud (finish-strangler cutover, parity with
    coordinator-write-review-trail.py's own ``_no_fallback``)."""
    raise RuntimeError(
        "review_trail.write: native seam required (no legacy fallback — finish-strangler cutover)"
    )


def _open_pending_trail_record(
    repo_root: Path,
    range_: str,
    reviewer: str,
    scope: str,
    paths: list[str],
    diff_path: str,
) -> str | None:
    """Write the ``verdict: pending`` open-loop record for the frozen range and
    return its path, or None (diagnostic already on stderr) on refusal.

    Routes through the native ``review_trail.write`` op via
    ``cc_invoke.route_mutation()`` — the seam
    ``coordinator/bin/coordinator-write-review-trail.py`` uses. ``cc_invoke``
    is imported here rather than at module scope so a ``--no-trail-record``
    invocation keeps the narrower import surface and cannot be broken by a
    transport-module import failure it never needed.

    Every refusal path returns None after printing its reason; the caller
    decides whether that is fatal (see the module docstring's exit matrix).
    """
    lib_dir = Path(__file__).resolve().parent / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    try:
        import cc_invoke
    except ImportError as exc:
        print(f"{_PROG}: open-loop trail record: cannot import cc_invoke transport: {exc}", file=sys.stderr)
        return None

    params: dict[str, object] = {
        "sha_range": range_,
        "reviewer": reviewer,
        "scope": scope,
        "verdict": _PENDING_VERDICT,
        "diff_loc": _diff_loc(diff_path),
        "scope_kind": "diff",
    }
    if paths:
        params["reviewed_paths"] = list(paths)

    try:
        result = cc_invoke.route_mutation(
            "review_trail.write", params, str(repo_root), _no_fallback
        )
    except cc_invoke.RouteMutationError as exc:
        payload = exc.result if isinstance(exc.result, dict) else {"error": str(exc)}
        print(f"{_PROG}: open-loop trail record refused: {json.dumps(payload)}", file=sys.stderr)
        return None
    except RuntimeError as exc:
        print(f"{_PROG}: open-loop trail record failed: {exc}", file=sys.stderr)
        return None

    out_path = result.get("out_path") if isinstance(result, dict) else None
    if not out_path:
        print(
            f"{_PROG}: open-loop trail record: review_trail.write returned no out_path: {result!r}",
            file=sys.stderr,
        )
        return None
    return str(out_path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=_PROG, add_help=False)
    parser.add_argument("--range", dest="range_", default="")
    parser.add_argument("--slice-id", dest="slice_id", default="")
    parser.add_argument("--paths", dest="paths", nargs="*", default=[])
    parser.add_argument("--repo-root", dest="repo_root", default="")
    # Mutually exclusive so "print it" and "do not write it" cannot both be
    # asserted — argparse rejects the pair as a usage error (exit 2) rather
    # than this CLI silently ranking one over the other.
    record_group = parser.add_mutually_exclusive_group()
    record_group.add_argument(
        "--print-trail-record", dest="print_trail_record", action="store_true",
    )
    record_group.add_argument(
        "--no-trail-record", dest="no_trail_record", action="store_true",
    )
    parser.add_argument("--reviewer", dest="reviewer", default=_DEFAULT_RECORD_REVIEWER)
    parser.add_argument("--scope", dest="scope", default=_DEFAULT_RECORD_SCOPE)
    args = parser.parse_args(argv)

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
    # recording_declared_writes rather than run_op_main. The separate
    # review_trail.write RPC-routed record below already reaches the engine
    # via cc_invoke.route_mutation() dispatch and needs no wrapping here.
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

    if args.no_trail_record:
        return 0

    record_path = _open_pending_trail_record(
        repo_root,
        args.range_,
        args.reviewer,
        args.scope,
        args.paths or [],
        str(result["diff_path"]),
    )
    if record_path is None:
        if args.print_trail_record:
            return 3
        print(
            f"{_PROG}: warning: the freeze SUCCEEDED but no open-loop trail "
            "record was written (reason above) — this review round is not "
            "recorded as open. Exit 0 because the frozen diff is the "
            "requested artifact; pass --print-trail-record to make a refused "
            "record exit 3 instead.",
            file=sys.stderr,
        )
        return 0
    if args.print_trail_record:
        print(record_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
