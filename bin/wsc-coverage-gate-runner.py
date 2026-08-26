"""wsc-coverage-gate-runner.py — /workstream-complete Step 2.4/2.9 imperative
logic ported off the bash fences embedded in DoE-claude
coordinator/skills/workstream-complete/SKILL.md.

Subcommands (argv[1] selects):

  claim-plan <slug>
      Step 2.4 "Plan-claim guard" (spec backlink:
      docs/plans/2026-06-26-cs-claim-plan-execution-lock.md § C4). Invokes the
      sibling session-claim-cli's `claim-plan` subcommand and, on a non-zero
      exit, diagnoses whether the failure was **peer contention** (another
      live session already holds the plan-claim — the underlying claim
      machinery prints "... held by session <sid> ... concurrent /pickup
      detected" to stderr, coordinator_core/session/claims.py:268) or an
      **infra error** (any other failure shape). The SKILL body deliberately
      never conflates the two: reporting a transport failure as "a peer is
      driving this ceremony" would misdirect the operator into standing down
      when nothing is actually contending. On success (re-entrant, freshly
      acquired, or stale-takeover — all rc=0 per `claim_plan`'s bool
      contract), returns 0 silently; the ceremony proceeds.

  coverage-gate — REMOVED (state/kill-ledger.md K-005, 2026-08-16 — "waiver
      system dies"). This subcommand, its `review-coverage-gate.py` child,
      and the `coverage.gate` op it wrapped were the chain-ancestry-waiver
      mint's sole surviving consumer once the waiver system itself was
      killed; all three went with it. See
      docs/wiki/cost-budgets-and-the-kill-disposition.md.

  write-trail — REMOVED (PM ruling 2026-08-23, kill review_trail.write). Its
      whole job was an argv-forwarding passthrough to
      coordinator-write-review-trail.py, which was deleted along with the
      review_trail.write op it trampolined. See the removal comment above
      `_build_parser` (where the subcommand used to be registered).

  brightline-gate — REMOVED (state/kill-ledger.md K-007, 2026-08-19, PM
      ruling). The chain-terminal two-oracle gate: this subcommand, its
      nested `review-brightline-gate.py --from-handoff` child, the
      `--from-handoff` oracle half of
      coordinator_core/ops/review_brightline_gate.py, and
      `workstream_complete/chain_partition_verdict_store.py` all went with
      it. Measured 7.4s per chain-terminal close (~40 closes/day) to produce
      a review-scale verdict; the PM ruled the chain-wide oracle not worth
      that cost and will specify the replacement coverage separately.
      Partition decisions still fire on the cheap session-scoped brightline
      (`decide_review_scale` row 4) — only the chain-wide view is gone.

Spec backlink: docs/plans/2026-07-21-doe-skill-bash-to-claude-klabauter-python-port.md [DEAD-CITATION: plan file never committed to this repo]
  (M3 chunk WSC-2). Source: DoE-claude
  coordinator/skills/workstream-complete/SKILL.md §§ Step 2.4 "Plan-claim
  guard", Step 2.9 "Coverage gate (chain-end path)" + "Marker write".

Exit codes:
  claim-plan    — 0 (claimed/re-entrant/stale-takeover), 1 (contention or
                  infra error — both fail the same way; see docstring above)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_CLAUDE_KLABAUTER_REPO_ROOT = Path(_SCRIPT_DIR).resolve().parents[1]
if str(_CLAUDE_KLABAUTER_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLAUDE_KLABAUTER_REPO_ROOT))

_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from coordinator_core.win_portability import no_console_creationflags  # noqa: E402
from raw_cmdline_recovery import UnsoundRawCmdlineTransport, recover_windows_argv  # noqa: E402

#: The .cmd launcher's own basename — used by `recover_windows_argv` to locate
#: where this invocation's own arguments begin within the raw `%CMDCMDLINE%`
#: capture — see `coordinator/bin/lib/raw_cmdline_recovery.py`'s module
#: docstring. The `write-trail --sha-range` subcommand this originally guarded
#: (a git rev/range typed directly at the CLI, e.g. the `sha^..sha`
#: predecessor-range shape cmd.exe's `%*` batch-parameter population silently
#: strips a literal `^` from) was removed 2026-08-23 (PM ruling, kill
#: review_trail.write); kept for `claim-plan`'s own argv, refusing on an
#: unvouchable capture same as before.
_LAUNCHER_CMD_NAME = "wsc-coverage-gate-runner.cmd"


# ---------------------------------------------------------------------------
# claim-plan
# ---------------------------------------------------------------------------

def _run_session_claim_cli(slug: str) -> tuple[int, str]:
    """Invoke the sibling session-claim-cli's claim-plan subcommand and return
    (returncode, combined_stdout_and_stderr) — combined the same way the ported
    bash captured `claim_out=$(... 2>&1)`. Isolated for test monkeypatching."""
    cmd = [sys.executable, os.path.join(_SCRIPT_DIR, "session-claim-cli.py"), "claim-plan", slug]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        **no_console_creationflags(),  # popup-safe-env-suppressed
    )
    return proc.returncode, proc.stdout


def cmd_claim_plan(args: argparse.Namespace) -> int:
    returncode, combined = _run_session_claim_cli(args.slug)
    if returncode == 0:
        # Acquired, re-entrant, or stale takeover — no special handling required.
        return 0

    # Peer-contention vs infra-failure discrimination: the underlying claim
    # machinery (coordinator_core/session/claims.py) prints "... held by
    # session <sid> ..." to stderr ONLY on a live-holder collision. Any other
    # non-zero exit (unresolvable session id, bad baton root, mkdir failure)
    # is an infra error, never misreported as a phantom peer.
    if "held by session" in combined.lower():
        print("STOP: plan claim contention — workstream-complete halted.", file=sys.stderr)
    else:
        print("STOP: plan claim infra error — workstream-complete halted.", file=sys.stderr)
    if combined:
        print(combined, end="" if combined.endswith("\n") else "\n", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# coverage-gate subcommand and its `review-coverage-gate.py` child are
# REMOVED (state/kill-ledger.md K-005, 2026-08-16 — "waiver system dies"):
# the mint was `run_coverage_gate`'s/`coverage.gate`'s sole surviving
# consumer once the waiver system died, so both went with it — see
# docs/wiki/cost-budgets-and-the-kill-disposition.md.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# write-trail — REMOVED (PM ruling 2026-08-23, kill review_trail.write). This
# subcommand's entire job was an argv-forwarding passthrough to the sibling
# coordinator-write-review-trail.py, which was itself deleted along with the
# review_trail.write op it trampolined. Kill-means-kill, no successor built
# yet. See docs/wiki/cost-budgets-and-the-kill-disposition.md for the sibling
# removal precedents (coverage-gate/brightline-gate) this follows.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# argv plumbing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wsc-coverage-gate-runner.py")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_claim = sub.add_parser("claim-plan")
    p_claim.add_argument("slug")
    p_claim.set_defaults(func=cmd_claim_plan)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        _argv = recover_windows_argv(sys.argv[1:], _LAUNCHER_CMD_NAME)
    except UnsoundRawCmdlineTransport:
        print(
            "wsc-coverage-gate-runner.py: the invoking shell stripped "
            "characters from this command line before this process started — "
            f'run `python "{os.path.join(_SCRIPT_DIR, "wsc-coverage-gate-runner.py")}" '
            "...` instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(main(_argv))
