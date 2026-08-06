#!/usr/bin/env python3
"""review-coverage-gate.py — chain-end code-review coverage gate for
/workstream-complete Step 2.9 and /merge-to-main.

Purpose: verifies mechanically that every commit in a workstream's chain diff
is covered by at least one code-reviewer trail record. Closes the gap where
a confident EM substitutes handoff prose for per-commit review reconciliation.

Output (stdout): one line in the form:
  range=<range> chain_commits=N covered=M uncovered=K VERDICT={COVERED|UNCOVERED|INDETERMINATE}
On UNCOVERED: also emits one "uncovered: <sha> <subject>" line per gap to stderr.
On INDETERMINATE: emits "note: <reason>" lines to stderr.

Exit: 0 on COVERED or UNCOVERED (verdict-line shape, matching
review-brightline-gate.py). Exit 2 on INDETERMINATE — the calling skill
treats exit 2 as a halt; this gate never owns the COVERED/UNCOVERED halt.
Exit 1 on transport/engine failure or a malformed engine response.

Usage:
  review-coverage-gate.py [--scope-paths <pathspec>...] [--verbose] [<range>]

  <range>                  git rev-range; default: $(git merge-base origin/main HEAD)..HEAD
  --scope-paths <paths>... Scope the CHAIN set to commits touching these paths (via
                           `git rev-list --no-merges <range> -- <paths>`). The REVIEWED
                           set is NEVER path-filtered — any session's trail record that
                           covers a commit credits that commit, regardless of which paths
                           the record was scoped to.
  --verbose                Forwarded to coordinator_core.coverage.run_coverage_gate's
                           `verbose` kwarg — the bookkeeping-partition note includes the
                           full raw uncovered-bookkeeping SHA list instead of a count.
                           Default off.
  --mint-chain-waivers     Forwarded to `coverage.gate` as `mint_chain_waivers=true`
                           (docs/plans/2026-07-31-review-trail-chain-ancestry-discriminator.md
                           § C2b). Ceremony-close-only: only
                           `wsc-coverage-gate-runner.py`'s `coverage-gate` subcommand
                           passes this flag. Every ad-hoc/diagnostic invocation of this
                           CLI MUST omit it — the default (flag absent) stays read-only,
                           per AC2. Mints a per-SHA chain-ancestry waiver for each
                           uncovered chain commit on a DAG-mode UNCOVERED verdict; a
                           no-op on COVERED/INDETERMINATE or in flat mode (no
                           --from-handoff).

Missing/empty --scope-paths: falls back to unscoped whole-chain (not an error).
See Design § "Scope filtering — asymmetric by design" for the full rationale.

Native-transport note (debash campaign, 2026-07-19): this is the pure-Python shape-(b)
per-op trampoline. It calls `cc_invoke.route()` directly — NOT `route_mutation()`. `coverage.gate`'s exit_code
(0=COVERED, 1=UNCOVERED, 2=INDETERMINATE) is a domain verdict encoding, not a generic
mutation-refusal signal; UNCOVERED is an ordinary, expected outcome, not an op-level
refusal. Routing it through `route_mutation()` would raise `RouteMutationError` on every
UNCOVERED verdict, which is a correctness bug, not a transport hardening. Under the
campaign's big-bang mandate the `legacy_fn` passed to `route()` unconditionally raises —
there is no bash fallback leg.

Spec backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § C3
DR-215 backlink: docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § C5
Debash backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave 1b
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import cc_invoke  # noqa: E402  (sys.path mutated above)

_SAFE_RANGE_RE = re.compile(
    r"^[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*\.\.\.?[0-9A-Za-z_/.][0-9A-Za-z_/.~^]*$"
)


def _die(message: str, code: int = 1) -> "NoReturn":  # type: ignore[name-defined]
    print(message, file=sys.stderr)
    sys.exit(code)


def _parse_args(argv: list[str]) -> tuple[list[str], str, str, bool, bool]:
    """Mirrors the bash facade's argument loop exactly (--scope-paths, --from-handoff,
    optional positional range, `--` range-forcing separator), plus `--verbose` (D3)
    and `--mint-chain-waivers` (C2b).

    Returns (scope_paths, range_arg, from_handoff, verbose, mint_chain_waivers).
    """
    scope_paths: list[str] = []
    range_arg = ""
    from_handoff = ""
    verbose = False
    mint_chain_waivers = False

    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok == "--scope-paths":
            i += 1
            while i < n and argv[i] != "--" and not argv[i].startswith("--"):
                scope_paths.append(argv[i])
                i += 1
            continue
        if tok == "--from-handoff":
            i += 1
            if i >= n or not argv[i]:
                _die("review-coverage-gate.py: --from-handoff requires a path argument")
            from_handoff = argv[i]
            i += 1
            continue
        if tok == "--verbose":
            verbose = True
            i += 1
            continue
        if tok == "--mint-chain-waivers":
            mint_chain_waivers = True
            i += 1
            continue
        if tok == "--":
            i += 1
            if i < n:
                range_arg = argv[i]
                i += 1
            continue
        if tok.startswith("-"):
            _die(f"review-coverage-gate.py: unknown option: {tok}")
        range_arg = tok
        i += 1

    return scope_paths, range_arg, from_handoff, verbose, mint_chain_waivers


def main(argv: list[str]) -> int:
    scope_paths, range_arg, from_handoff, verbose, mint_chain_waivers = _parse_args(argv)

    # Review: code-reviewer F4 (bash oracle parity) — validate the caller-supplied range
    # against the same no-leading-dash pattern the core applies to untrusted trail-JSON
    # sha_range, hardening the direct-invocation path to parity with the trail-JSON path.
    if range_arg and not _SAFE_RANGE_RE.match(range_arg):
        _die(f"review-coverage-gate.py: unsafe range argument: {range_arg}")

    if from_handoff and scope_paths:
        print(
            "review-coverage-gate.py: WARNING: --scope-paths is ignored in DAG mode "
            "(chain_set derives from session-segment trailers, not path filter)",
            file=sys.stderr,
        )
    if from_handoff and range_arg:
        print(
            f"review-coverage-gate.py: WARNING: positional range argument ({range_arg}) "
            "is ignored when --from-handoff is set (DAG mode; coordinator_core receives "
            "from_handoff, not range)",
            file=sys.stderr,
        )

    if not range_arg and not from_handoff:
        try:
            merge_base = subprocess.run(
                ["git", "merge-base", "origin/main", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, OSError):
            _die(
                "review-coverage-gate.py: cannot resolve origin/main — pass a range explicitly"
            )
        range_arg = f"{merge_base}..HEAD"

    try:
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        _die("review-coverage-gate.py: cannot find git repo root")

    params: dict[str, object] = {}
    if from_handoff:
        # coverage.gate's wire contract (coordinator_core/ops/coverage_gate.py)
        # documents from_handoff as an ABSOLUTE path; coverage.py's
        # _derive_dag_chain_set resolves it via os.path.abspath(from_handoff),
        # which resolves against the *engine process's* cwd — now pinned to
        # CLAUDE_KLABAUTER_ROOT by cc_invoke.py, not necessarily repo_root. Anchor a
        # relative from_handoff on repo_root (already resolved above, the
        # same root every other git call in this gate uses) before forwarding,
        # rather than relying on cwd coincidence between this CLI and the
        # spawned engine process.
        if not os.path.isabs(from_handoff):
            from_handoff = os.path.join(repo_root, from_handoff)
        params["from_handoff"] = from_handoff
        # D3 case 3 (DAG mode): the closing handoff's segment may belong to the
        # currently-active session whose add-commit trailer does not exist yet
        # (unpublished handoff). coordinator_core reads this ONLY from the
        # closing_session_id param — it never consults the environment — so the
        # facade forwards $CLAUDE_CODE_SESSION_ID, matching the retired bash
        # gate's behaviour (vacuous-match guard AC14 depends on this reaching
        # the engine).
        closing_session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
        if closing_session_id:
            params["closing_session_id"] = closing_session_id
    else:
        if range_arg:
            params["range"] = range_arg
        if scope_paths:
            params["scope_paths"] = scope_paths
    if verbose:
        params["verbose"] = True
    if mint_chain_waivers:
        params["mint_chain_waivers"] = True

    def _legacy_fn() -> "NoReturn":  # type: ignore[name-defined]
        raise RuntimeError(
            "review-coverage-gate.py: coordinator_core seam absent — no bash fallback "
            "under the debash big-bang cutover. Install/repair coordinator_core "
            "(CLAUDE_KLABAUTER_ROOT) and retry."
        )

    try:
        result = cc_invoke.route("coverage.gate", params, repo_root, _legacy_fn)
    except RuntimeError as exc:
        print(
            f"review-coverage-gate.py: engine could not compute a verdict ({exc})",
            file=sys.stderr,
        )
        print(
            "  Verify CLAUDE_KLABAUTER_ROOT and coordinator_core installation (see diagnostics above)",
            file=sys.stderr,
        )
        return 1

    if not isinstance(result, dict):
        print(
            f"review-coverage-gate.py: malformed result from cc_invoke: not a dict ({result!r})",
            file=sys.stderr,
        )
        return 1

    verdict = result.get("verdict_line", "")
    notes = result.get("notes") or []
    if not isinstance(notes, list):
        notes = []

    exit_code_raw = result.get("exit_code", 1)
    try:
        exit_code = int(exit_code_raw)
    except (TypeError, ValueError):
        print(
            f"review-coverage-gate.py: unexpected exit_code type from coordinator_core: "
            f"{exit_code_raw!r}; treating as 1",
            file=sys.stderr,
        )
        exit_code = 1

    if exit_code not in (0, 1, 2):
        print(
            f"review-coverage-gate.py: unexpected exit_code from coordinator_core: "
            f"{exit_code}; treating as 1",
            file=sys.stderr,
        )
        exit_code = 1

    # INDETERMINATE (exit_code==2) must propagate even when verdict_line is empty — a
    # malformed INDETERMINATE result must not be silently demoted to exit 1. When the
    # engine DID supply a verdict_line (the normal case), it prints to stdout per the
    # frozen CLI contract — VERDICT=INDETERMINATE is part of the stdout verdict-line
    # shape (see module docstring), not a stderr-only outcome.
    if exit_code == 2:
        if verdict:
            print(verdict)
        for note in notes:
            print(note, file=sys.stderr)
        return 2

    if not verdict:
        print(
            "review-coverage-gate.py: coordinator_core returned empty verdict_line",
            file=sys.stderr,
        )
        return 1

    print(verdict)
    for note in notes:
        print(note, file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
