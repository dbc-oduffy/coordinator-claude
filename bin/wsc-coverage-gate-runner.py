#!/usr/bin/env python3
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

  coverage-gate --from-handoff <path>
      Step 2.9 "Coverage gate (chain-end path)". Wraps
      review-coverage-gate.py's DAG-mode VERDICT line (`--from-handoff`) and
      applies the halt-or-override policy: `VERDICT=INDETERMINATE` halts
      (exit 2) UNLESS `COORDINATOR_OVERRIDE_COVERAGE_GATE=1` is set in the
      environment (a PM-authorized bypass — there is no CLI flag for this,
      matching the SKILL's env-var-only override convention), in which case
      a warning is printed and the subcommand exits 0.

      C10 (docs/plans/2026-08-05-coverage-gate-planning-artifact-class.md,
      AC14): the pre-C10 binary `VERDICT=UNCOVERED` token no longer exists.
      Below the code-partition coverage ratio threshold the underlying gate
      now reports `VERDICT=WARN`, which never halts — for ORDINARY coverage
      nothing hard-blocks, ever (see coordinator_core.coverage's module-level
      hard-block decision note for the deliberate, named scope of that
      ruling — it does NOT extend to the partition-mandatory chain-verdict
      case, tracked separately at
      state/sizings/2026-08-06-partition-mandatory-must-refuse-the-chai.yaml).
      On `VERDICT=WARN` this subcommand relays the underlying gate's stderr,
      prints the `coordinator:review-code` remediation OFFER, and exits 0 —
      the underlying gate's own exit code for WARN. `COORDINATOR_OVERRIDE_
      COVERAGE_GATE` is still read and its use is noted on the WARN path for
      backward compatibility, but it is now a no-op (there is nothing left
      to override on this path) — this subcommand does NOT gain a new
      override surface, per the plan's Anti-scope. `VERDICT=COVERED` always
      exits 0. This subcommand owns the halt policy; review-coverage-gate.py
      itself deliberately does not (see its own docstring) — mirrors the
      sibling merge-gate-and-pr.py's `coverage-gate` subcommand shape for
      /merging-to-main, one halt-policy wrapper per ceremony caller.

      On `VERDICT=COVERED`, this subcommand additionally runs SKILL.md's
      trail-range-termination disbelief predicate
      (`coordinator_core.workstream_complete.directives_review.
      verify_trail_range_termination`) over the on-disk review-trail
      records: a COVERED verdict is corroborated only if at least one
      record's range-tip is at or after the current chain tip. An
      uncorroborated COVERED verdict (every record's tip is an unterminated
      `..HEAD` range, unparseable, or simply absent) prints a fail-loud
      `NOTE:` diagnostic to stderr naming every rejected record's reason —
      it never changes the exit code (still 0), matching the
      advisory-not-blocking contract every other verdict in this
      subcommand already honors.

      Negative-spec (F2, carried from the ported SKILL comment): `--from-handoff`
      selects DAG mode, in which `--scope-paths` is flat-range-only and is
      silently ignored by the underlying gate — this subcommand therefore does
      NOT expose a `--scope-paths` flag; do not add one without re-reading
      review-coverage-gate.py's DAG-mode branch first.

      Side effect (C2b, docs/plans/2026-07-31-review-trail-chain-ancestry-
      discriminator.md § C2b): this subcommand always invokes
      review-coverage-gate.py with `--mint-chain-waivers` — on a DAG-mode
      UNCOVERED verdict, the underlying `coverage.gate` op mints a per-SHA
      chain-ancestry waiver for each uncovered chain commit, from the
      ancestry it already derived. This subcommand is the SOLE
      ceremony-close caller of review-coverage-gate.py in this codebase; no
      other invocation of that CLI passes the flag, so no other caller takes
      on this side effect.

  write-trail --sha-range <A..B> --reviewer <name> --scope <chain|session>
              --verdict <ok|warn|blocked|waived|pending> --diff-loc <N>
              [--scope-kind <diff|plan|integration>] [--workstream <slug>]
      Step 2.9 "Marker write". A thin argv-forwarding passthrough to the
      sibling coordinator-write-review-trail.py (already the single
      authorized review_trail.write trampoline — see that file's own
      docstring) so the whole Step 2.9 ceremony sequence (claim → gate →
      trail) is reachable from one CLI surface. No branching logic of its
      own beyond argument assembly + exit-code/output passthrough.

  brightline-gate --from-handoff <path> [<git-range>]
      Enforcement wrapper over review-brightline-gate.py's `--from-handoff`
      (chain+plan two-oracle) mode. The gate itself
      (coordinator_core/ops/review_brightline_gate.py) is PURE COMPUTE+EMIT —
      it always exits 0 on a successful compute and never encodes halt
      policy. This subcommand owns that policy, distinct from and never
      merged with the `coverage-gate` verdict above:
        tier=A  (a deferred:false code-bearing plan row declares a repo the
                 chain walk saw zero commits in, or was indeterminate on) =>
                 HARD STOP (nonzero exit) UNLESS COORDINATOR_OVERRIDE_BRIGHTLINE=1
                 AND the /autonomous sentinel (see
                 coordinator_core.session.autonomous_sentinel.sentinel_path
                 — platform-resolved, NOT a hardcoded /tmp path) exists, OR
                 a recorded reviewer-findings artifact under
                 state/review-trail/findings/ already names the unwalked
                 repo. The override is REFUSED (tier=A still halts) when the
                 sentinel is absent — an interactive EM cannot self-override.
        tier=B/none => communicate the full BRIGHTLINE line loudly (all
                 three oracle numbers + basis) and prompt for a RECORDED EM
                 reviewer-count decision (COORDINATOR_BRIGHTLINE_REVIEWER_COUNT),
                 cross-checked against the count of matching artifacts under
                 state/review-trail/findings/ when set. Never a hard stop —
                 the EM's judgment call, not the gate's.

                 C13 (docs/plans/2026-08-05-coverage-gate-planning-artifact-
                 class.md, AC20/AC21): ONE narrow exception carved out of the
                 "never a hard stop" posture above. When `verdict=
                 PARTITION-MANDATORY` AND the on-disk review-trail carries no
                 record whose resolved range shares at least one commit with
                 the chain's own DAG (membership, an intersection test — see
                 `directives_review.chain_partition_verdict_discharged`'s own
                 docstring) and whose code-bearing intersection covers every
                 one of the chain's code-review obligations,
                 this subcommand REFUSES (HALT, nonzero exit) instead of
                 communicating and returning 0 — a session cannot be told
                 "four reviewers required," run zero, and still reach a
                 clean terminal stamp (the verified 2026-08-05 DoE-claude
                 incident this closes). Discharge is scoped by CHAIN
                 MEMBERSHIP, not by tip ancestry (2026-08-06 correction): a
                 record whose range-tip merely lands later on this fleet's
                 ONE SHARED `work/{machine}/{date}` branch than the chain tip
                 is NOT evidence it reviewed this chain — every concurrent
                 peer session's record satisfies that condition regardless of
                 what it actually reviewed, which live re-verification
                 proved trivially satisfiable by unrelated peer activity and
                 unsatisfiable-by-timing for a chain with no later peer
                 write yet. See `directives_review.chain_partition_verdict_
                 discharged`'s own docstring for the full incident writeup.
                 `single-reviewer-ok` and every ordinary tier=B/none case are
                 UNCHANGED — this does not restore the pre-C10 hard-block
                 posture, it adds one discharge check on top of it. The
                 refusal message names `/handoff` as the sanctioned exit.

Spec backlink: docs/plans/2026-07-21-doe-skill-bash-to-claude-klabauter-python-port.md
  (M3 chunk WSC-2). Source: DoE-claude
  coordinator/skills/workstream-complete/SKILL.md §§ Step 2.4 "Plan-claim
  guard", Step 2.9 "Coverage gate (chain-end path)" + "Marker write".

Exit codes:
  claim-plan    — 0 (claimed/re-entrant/stale-takeover), 1 (contention or
                  infra error — both fail the same way; see docstring above)
  coverage-gate — 0 (covered, warn — C10: warn never halts, see above — or
                  indeterminate-but-overridden), 2 (indeterminate halt —
                  propagated from the underlying gate's own INDETERMINATE
                  exit contract)
  write-trail   — propagates coordinator-write-review-trail.py's own exit
                  code verbatim (0 success, 1 missing required arg, 2 native
                  op transport/refusal failure)
  brightline-gate — 0 (tier=B/none communicate-only, or tier=A overridden),
                  1 (tier=A hard stop; the underlying gate could not be
                  reached / did not emit a parseable BRIGHTLINE line; or —
                  C13 — verdict=PARTITION-MANDATORY with no discharging
                  review-trail verdict on disk)
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

_CLAUDE_KLABAUTER_REPO_ROOT = Path(_SCRIPT_DIR).resolve().parents[1]
if str(_CLAUDE_KLABAUTER_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLAUDE_KLABAUTER_REPO_ROOT))

from coordinator_core.ops.list_review_trail_records import (  # noqa: E402
    ReviewTrailListError,
    list_paths as _list_review_trail_paths,
)
from coordinator_core.workstream_complete.directives_review import (  # noqa: E402
    CHAIN_VERDICT_PARTITION_MANDATORY as _CHAIN_VERDICT_PARTITION_MANDATORY,
    chain_partition_uncovered_shas,
    classify_untrusted_trail_ranges,
    verify_trail_range_termination,
)
from coordinator_core.coverage import (  # noqa: E402
    _UUID_RE,
    _chain_ancestry_waived_shas,
    _classify_bookkeeping_shas,
    _commit_touched_paths,
    _derive_dag_chain_set,
    _pm_vouched_waiver_shas,
)
from coordinator_core.session import review_trail_vouch  # noqa: E402
from coordinator_core.workstream_complete.chain_partition_verdict_store import (  # noqa: E402
    write_verdict_record,
)
from coordinator_core.git.repo_root import show_toplevel as _show_toplevel  # noqa: E402
from coordinator_core import session_attribution  # noqa: E402


# ---------------------------------------------------------------------------
# claim-plan
# ---------------------------------------------------------------------------

def _run_session_claim_cli(slug: str) -> tuple[int, str]:
    """Invoke the sibling session-claim-cli's claim-plan subcommand and return
    (returncode, combined_stdout_and_stderr) — combined the same way the ported
    bash captured `claim_out=$(... 2>&1)`. Isolated for test monkeypatching."""
    cmd = [sys.executable, os.path.join(_SCRIPT_DIR, "session-claim-cli"), "claim-plan", slug]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # popup-safe-env-suppressed
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
# coverage-gate
# ---------------------------------------------------------------------------

def _run_review_coverage_gate(from_handoff: str) -> tuple[int, str, str]:
    """Invoke the sibling review-coverage-gate.py in DAG mode and return
    (returncode, stdout, stderr). Isolated for test monkeypatching.

    Always passes `--mint-chain-waivers`: this subcommand IS the
    ceremony-close caller (docs/plans/2026-07-31-review-trail-chain-ancestry-
    discriminator.md § C2b) — the only caller of review-coverage-gate.py
    that may request minting (see that flag's own docstring for why every
    other/diagnostic invocation of review-coverage-gate.py must omit it).
    A no-op on COVERED/INDETERMINATE or in flat mode; this call is always
    DAG-mode (`--from-handoff` is required by this subcommand's own argparse
    definition below)."""
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "review-coverage-gate.py"),
        "--from-handoff",
        from_handoff,
        "--mint-chain-waivers",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # popup-safe-env-suppressed
    )
    return proc.returncode, proc.stdout, proc.stderr


def _resolve_repo_root() -> str | None:
    """The process cwd's repo toplevel — mirrors review-coverage-gate.py's
    own `repo_root` resolution (no explicit `cwd` is passed to that
    subprocess call either; both scripts assume the ceremony invokes them
    from the claude-klabauter repo root).

    Review-integrator finding B3/F3 (spawn-budget): delegates to
    `coordinator_core.git.repo_root.show_toplevel`, the process-lifetime,
    cwd-keyed memoized seam the 2026-08-06 spawn-elimination census built
    for exactly this — a chain-terminal gate run previously called this
    function once per trail record (~823 raw `git rev-parse
    --show-toplevel` spawns measured live), all resolving the SAME cwd.
    `show_toplevel` walks for the ordinary case (no spawn at all) and
    spawns only as a last-resort fallback, then memoizes that result for
    the rest of this process. Isolated for test monkeypatching."""
    return _show_toplevel()


#: Module-level memo for `_derive_dag_shas`, keyed on `from_handoff` — a
#: chain-terminal gate run calls this function twice independently
#: (`_resolve_chain_code_shas` via `_resolve_dag_candidates`, and
#: `_resolve_chain_dag_shas` directly), each triggering its own
#: `_derive_dag_chain_set` fixpoint walk over the SAME chain (review-
#: integrator finding B3/F3 — "two full `_derive_dag_chain_set` walks ...
#: no sharing"). `closing_session_id` is read from an env var that does not
#: change within one process, so `from_handoff` alone is a safe cache key.
#: A resolution FAILURE (`None`) is also memoized here — unlike
#: `coordinator_core.git.repo_root`'s negative-caching policy, a DAG
#: derivation failure for a given `from_handoff` cannot flip to success
#: later in the same short-lived, spawn-per-call process.
_DAG_SHAS_CACHE: dict[str, tuple[str, list[str]] | None] = {}


def _derive_dag_shas(from_handoff: str) -> tuple[str, list[str]] | None:
    """The chain's own UNFILTERED DAG sha set — every commit `_derive_dag_
    chain_set` places in this chain, ceremony bookkeeping and handoff-
    authoring commits included, no exclusion applied. Returns `(repo_root,
    dag_shas)`, or `None` on any resolution failure (indeterminate DAG
    derivation, empty chain, unresolvable repo root, git unavailable).
    Shared setup underneath `_resolve_dag_candidates` (which filters this
    down to code-review candidates) and `_resolve_chain_dag_shas` (which
    returns it unfiltered, for the C13 within-chain-MEMBERSHIP test — see
    `directives_review._record_membership_shas`'s "membership-vs-coverage
    split" docstring for why membership needs the unfiltered set while
    coverage needs the filtered one). Memoized per `from_handoff` in
    `_DAG_SHAS_CACHE` (review-integrator finding B3/F3) — see that cache's
    own docstring."""
    if from_handoff in _DAG_SHAS_CACHE:
        return _DAG_SHAS_CACHE[from_handoff]
    result: tuple[str, list[str]] | None = None
    repo_root = _resolve_repo_root()
    if repo_root:
        closing_session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
        try:
            dag_result = _derive_dag_chain_set(from_handoff, repo_root, closing_session_id)
        except Exception:  # noqa: BLE001 - diagnostics-only, must never be fatal
            dag_result = None
        if dag_result is not None and not dag_result.indeterminate and dag_result.shas:
            result = (repo_root, dag_result.shas)
    _DAG_SHAS_CACHE[from_handoff] = result
    return result


def _resolve_dag_candidates(from_handoff: str) -> tuple[str, list[str]] | None:
    """Shared setup both `_resolve_chain_tip_sha` and `_resolve_chain_code_
    shas` build on: `_derive_dag_shas`'s unfiltered chain DAG set, then
    exclude ceremony-bookkeeping commits via `_classify_bookkeeping_shas` —
    the same CODE-vs-bookkeeping partition the VERDICT itself already
    applies. Falls back to the full chain_set when every chain commit
    classifies as bookkeeping (never reports "no candidates at all").
    Returns `(repo_root, candidates)`, or `None` on any resolution failure —
    extracted verbatim from `_resolve_chain_tip_sha`'s prior body so that
    function's own behavior and return value are unchanged by this
    refactor."""
    resolved = _derive_dag_shas(from_handoff)
    if resolved is None:
        return None
    repo_root, dag_shas = resolved

    # Planning-only commits (planning_set) are deliberately NOT folded into
    # the exclusion here: PLANNING is not exempt from review (it owes a
    # *plan* review, not a code review — see docs/plans/2026-08-05-coverage-
    # gate-planning-artifact-class.md AC9), so a planning commit remains a
    # legitimate candidate exactly as it was before this class existed.
    # Only exhaust_set (today's bookkeeping semantics, unchanged) is
    # excluded.
    exhaust_set, _planning_set, _note = _classify_bookkeeping_shas(dag_shas, repo_root, {})
    candidates = [sha for sha in dag_shas if sha not in exhaust_set]
    if not candidates:
        # Every chain commit is bookkeeping-only — fall back to the full
        # chain_set rather than reporting "no candidates at all".
        candidates = dag_shas
    return repo_root, candidates


def _resolve_chain_dag_shas(from_handoff: str) -> list[str]:
    """The C13 MEMBERSHIP set — the chain's own UNFILTERED DAG sha set
    (`_derive_dag_shas`'s `dag_shas`, bookkeeping and handoff-authoring
    commits included), distinct from `_resolve_chain_code_shas`'s filtered
    COVERAGE set. `directives_review.chain_partition_verdict_discharged`
    tests a trail record's raw resolved range against THIS set to decide
    whether the record is even about this chain at all — see that
    function's own docstring, and `_record_membership_shas`'s, for why an
    honest whole-chain review range spanning one ceremony commit must not
    be rejected the way testing membership against the filtered
    `chain_code_shas` set alone used to reject it. Returns `[]` on any
    resolution failure (mirrors `_resolve_chain_code_shas`'s own fail-safe
    posture: this backs a diagnostics-only refusal check that must degrade
    toward "no membership evidence available", never crash the gate)."""
    resolved = _derive_dag_shas(from_handoff)
    if resolved is None:
        return []
    _repo_root, dag_shas = resolved
    return list(dag_shas)


def _resolve_chain_planning_shas(from_handoff: str) -> list[str]:
    """The PLANNING-classified subset of this chain's DAG — commits whose
    touched paths are entirely planning-artifact/bookkeeping paths with >=1
    planning-artifact path, and that do not introduce a `state/handoffs/`
    file (`coverage._classify_bookkeeping_shas`'s own PLANNING branch,
    `_PLANNING_ARTIFACT_PATH_PREFIXES`). Every PLANNING commit stays IN
    `_resolve_chain_code_shas`'s obligation set (AC9 — PLANNING owes a
    review, not exemption), so this resolver names the subset a
    `scope_kind: "plan"` trail record may discharge
    (`directives_review._record_membership_shas`'s `chain_planning_sha_set`
    parameter, 2026-08-07 correction,
    `state/audits/2026-08-07-wsc-chain-gate-counts-doc-only-commits.md`
    Q4's "second gap") — never a plain CODE commit, mirroring
    `coverage._credit_from_kind_partition`'s own kind-aware crediting for
    the session-oracle path. Returns `[]` on any resolution failure,
    mirroring `_resolve_chain_code_shas`'s own fail-safe posture: this
    backs a discharge-widening leg that must degrade toward "no planning
    credit available", never crash the gate."""
    resolved = _derive_dag_shas(from_handoff)
    if resolved is None:
        return []
    repo_root, dag_shas = resolved
    _exhaust_set, planning_set, _note = _classify_bookkeeping_shas(dag_shas, repo_root, {})
    return [sha for sha in dag_shas if sha in planning_set]


def _resolve_chain_code_shas(from_handoff: str) -> list[str]:
    """The set of chain commits that OWE a code review — `_resolve_dag_
    candidates`'s `candidates` list (dag shas minus `exhaust_set`, with the
    existing all-bookkeeping fallback), further MINUS any sha whose every
    touched path is under `state/handoffs/`.

    Why the further exclusion: `_classify_bookkeeping_shas` deliberately
    keeps a handoff-authoring commit (one that introduces a file under
    `state/handoffs/`) OUT of `exhaust_set` so it remains a chain-*tip*
    candidate for `_resolve_chain_tip_sha` — see that commit's own
    docstring, and the 87578a319 regression it guards against. But a commit
    of pure baton prose owes no *code* review; if it were left in this
    function's obligation set, the C13 union-coverage leg
    (`directives_review.chain_partition_verdict_discharged`) would demand a
    reviewer verdict naming a commit that touched no code, which no review
    ever could satisfy. `_resolve_chain_tip_sha` is UNCHANGED by this
    function's existence — it keeps using `_resolve_dag_candidates`'s
    unfiltered `candidates`, exactly as before this refactor, because a
    handoff-authoring commit remaining a valid TIP candidate is the whole
    point of that exclusion; this function answers a different question
    (what code-review obligations does the chain carry), not "what is the
    chain tip".

    Uses `coordinator_core.coverage._commit_touched_paths` — the same
    batched `git log --name-only` helper `_classify_bookkeeping_shas` uses
    internally — rather than hand-rolling a second one. Returns `[]` on any
    resolution failure (mirrors `_resolve_chain_tip_sha`'s own fail-safe
    posture: this backs a diagnostics-only union-coverage leg that must
    degrade toward "leg (b) unavailable", never crash the gate)."""
    resolved = _resolve_dag_candidates(from_handoff)
    if resolved is None:
        return []
    repo_root, candidates = resolved
    touched_by_sha, _note = _commit_touched_paths(candidates, repo_root, {})
    code_shas = []
    for sha in candidates:
        paths = touched_by_sha.get(sha) or frozenset()
        if paths and all(p.startswith("state/handoffs/") for p in paths):
            continue
        code_shas.append(sha)
    return code_shas


def _resolve_chain_tip_sha(from_handoff: str) -> str | None:
    """The chain's OWN tip — the newest ceremony-bookkeeping-EXCLUDED commit
    the coverage gate itself actually reasoned over — NOT raw `git rev-parse
    HEAD`.

    Re-derives the identical DAG-mode chain_set the gate's own verdict
    computation produced, via `coordinator_core.coverage._derive_dag_chain_set`
    (the same canonical fixpoint the gate calls — never a second, hand-rolled
    reimplementation of "what is in this chain"), then excludes ceremony-
    bookkeeping commits via `_classify_bookkeeping_shas` — the same CODE-vs-
    bookkeeping partition the VERDICT itself already applies (state/,
    archive/, tasks/-only commits don't gate COVERED/UNCOVERED, so they
    should not gate this disbelief check either: a trailing bookkeeping-only
    commit — completion entry, trail-record write, shipped_in stamp —
    authored AFTER the last reviewable code commit cannot possibly be what a
    review-trail record was reviewing). The newest remaining candidate (by
    committer date, one batched `git log --no-walk` call) is the chain tip.

    Why not raw HEAD (the prior behavior this replaces): this fleet's
    documented norm is ONE SHARED `work/{machine}/{date}` branch with many
    concurrent sessions on it (DoE-claude's
    coordinator/docs/wiki/concurrent-em-hazards.md § The model — a shared bus,
    not a workspace, for the many-sessions-one-branch fact, and
    coordinator/docs/wiki/daily-branch-discipline.md for the branch-name norm;
    coordinator/CLAUDE.md § Concurrent-EM Git Operations retired 2026-07-27) —
    HEAD accrues every peer session's unrelated commits between
    this chain's own tip and gate-run time, so demanding a trail record reach
    raw HEAD is structurally unsatisfiable outside a single-session repo.
    Observed live: 155 peer commits (from ~14 concurrent unrelated sessions)
    landed between a real review-trail record's tip and HEAD in one DoE-claude
    run, and the disbelief check printed "could not be corroborated" for a
    verdict that was, in fact, fully corroborated.

    Isolated for test monkeypatching. Returns None on any resolution failure
    (indeterminate DAG derivation, empty chain, unresolvable repo root, git
    unavailable) rather than raising — the disbelief check this backs is
    diagnostics-only and must never crash the gate."""
    resolved = _resolve_dag_candidates(from_handoff)
    if resolved is None:
        return None
    repo_root, candidates = resolved

    try:
        proc = subprocess.run(
            ["git", "log", "--no-walk", "--format=%H %ct", *candidates],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None

    newest_sha: str | None = None
    newest_ts = -1
    for line in proc.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        sha, ts_str = parts
        try:
            ts = int(ts_str)
        except ValueError:
            continue
        if ts > newest_ts:
            newest_ts = ts
            newest_sha = sha
    return newest_sha


def _git_is_ancestor(ancestor_sha: str, descendant_sha: str) -> bool:
    """True iff `ancestor_sha` is an ancestor of (or identical to)
    `descendant_sha`, via `git merge-base --is-ancestor`. Isolated for test
    monkeypatching; any subprocess failure resolves to False (never trusts
    a range this check could not positively confirm)."""
    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return False
    return proc.returncode == 0


#: Module-level memo for `_resolve_range_shas` — a chain-terminal close may
#: ask the same `sha_range` more than once (e.g. the C13 union leg followed
#: by the uncovered-set diagnostic re-deriving it), and `git rev-list` cost
#: scales with range size; memoizing avoids paying that twice per process.
_RANGE_SHAS_CACHE: dict[str, frozenset[str]] = {}


def _resolve_range_shas(sha_range: str) -> frozenset[str]:
    """`git rev-list <sha_range>` from the repo root, as the full sha set
    the C13 union-coverage leg (`directives_review.chain_partition_verdict_
    discharged`'s `resolve_range_shas` callable) treats a trail record as
    having reviewed. Memoized per `sha_range` string in `_RANGE_SHAS_CACHE`
    for the lifetime of this process. Any non-zero rc, unresolvable repo
    root, or `OSError` returns the empty frozenset — fail-safe toward
    refusal, mirroring `_git_is_ancestor`'s own posture: a range this
    function could not positively resolve must never silently count toward
    coverage. Windows-safe subprocess shape (`CREATE_NO_WINDOW`), matching
    every other git shell-out in this module — no console flash on a
    Windows EM's box."""
    if sha_range in _RANGE_SHAS_CACHE:
        return _RANGE_SHAS_CACHE[sha_range]
    result: frozenset[str] = frozenset()
    repo_root = _resolve_repo_root()
    if repo_root:
        try:
            proc = subprocess.run(
                ["git", "rev-list", sha_range],
                capture_output=True,
                text=True,
                check=False,
                cwd=repo_root,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            proc = None
        if proc is not None and proc.returncode == 0:
            result = frozenset(line.strip() for line in proc.stdout.splitlines() if line.strip())
    _RANGE_SHAS_CACHE[sha_range] = result
    return result


#: Module-level memo for `_resolve_foreign_session_shas`, mirroring
#: `_RANGE_SHAS_CACHE`'s own per-process-lifetime shape. Keyed by this
#: module on `(sha_range, own_session_id)` — B2/B3 (2026-08-06): this cache
#: now backs `_resolve_foreign_session_shas`'s own inclusive walk, not a
#: delegation to `session_attribution.trailer_foreign_shas`.
_FOREIGN_SHAS_CACHE: dict = {}

#: Module-level memo for `_grep_attributed_session_shas`, keyed identically
#: to `_FOREIGN_SHAS_CACHE` on `(sha_range, session_id)` — review R1
#: (2026-08-06, chain-close review-integration round). Same per-process-
#: lifetime idiom as every other cache in this file; a chain-terminal close
#: may ask the same `(sha_range, session_id)` pair more than once across
#: several trail records.
_GREP_ATTRIBUTED_SHAS_CACHE: dict = {}


def _grep_attributed_session_shas(sha_range: str, session_id: str | None) -> frozenset[str]:
    """The SAME message-line `--grep=^Session-Id: <sid>$` attribution
    `coverage._derive_dag_chain_set` step 3 uses to decide CHAIN MEMBERSHIP
    (that call is `git log HEAD --no-merges --format=%H --grep=^Session-Id:
    <sid>$`; this one scopes the same grep to `sha_range` instead of `HEAD`,
    since only commits within `sha_range` are ever relevant to the caller).

    Review R1 (2026-08-06): `_resolve_foreign_session_shas`'s trailer-block
    walk (`%(trailers:key=Session-Id,valueonly)`) and the chain-membership
    grep are TWO DIFFERENT attribution mechanisms. Git's trailer parser only
    reads a commit message's final paragraph, so a commit whose
    `Session-Id:` line is followed by any non-trailer line (e.g. a
    "--- end Step N blocks ---" footer) is a chain member BY GREP that the
    trailers atom can never attribute — permanently foreign, uncreditable by
    any record, making a PARTITION-MANDATORY verdict on a chain containing
    one unsatisfiable. This resolver lets the caller subtract those shas
    back out of `foreign` so the two mechanisms agree on every commit the
    chain walk itself already considers this session's own, without
    softening the trailer walk's own (still stricter) treatment of merges
    and genuinely-unattributable commits.

    Returns the empty frozenset on any git failure or unresolvable repo
    root — fail-safe toward the CALLER's existing posture: an unresolvable
    grep leg must leave `foreign` unchanged (today's behaviour: treat as
    foreign, refuse coverage), never silently credit a commit this leg
    could not positively confirm. Memoized per `(sha_range, session_id)` in
    `_GREP_ATTRIBUTED_SHAS_CACHE` — one extra spawn per cache key, the same
    memoized-per-process shape every other resolver in this file uses.

    Review F3 (2026-08-06): `session_id` arrives from `record.get(
    "session_id")` — an arbitrary string out of an on-disk review-trail
    record, including the archive union whose shape is not guaranteed — and
    is interpolated raw into the `--grep=` pattern below. Unvalidated, a
    value like `.*` collapses the pattern to match every commit, silently
    over-crediting a peer session's range. Mirrors `coverage._UUID_RE`'s own
    guard on the identical interpolation in `_derive_dag_chain_set`: shape-
    validate before interpolating, and return the empty frozenset (i.e. no
    subtraction — the caller's existing foreign-by-default posture) rather
    than fail-open on a malformed value."""
    key = (sha_range, session_id)
    if key in _GREP_ATTRIBUTED_SHAS_CACHE:
        return _GREP_ATTRIBUTED_SHAS_CACHE[key]
    result: frozenset[str] = frozenset()
    if session_id and _UUID_RE.match(session_id):
        repo_root = _resolve_repo_root()
        if repo_root:
            rc, out, _err = _git_run_for_session_attribution(
                [
                    "git", "log", "--no-merges", "--format=%H",
                    f"--grep=^Session-Id: {session_id}$",
                    sha_range,
                ],
                repo_root,
            )
            if rc == 0:
                result = frozenset(line.strip() for line in out.splitlines() if line.strip())
    _GREP_ATTRIBUTED_SHAS_CACHE[key] = result
    return result


def _git_run_for_session_attribution(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """`session_attribution.GitRunner`-shaped subprocess wrapper — never
    raises, matches `coverage.py`'s own `_run` shape so this module's
    Windows-safe subprocess conventions (`CREATE_NO_WINDOW`, no shell) stay
    consistent with the rest of this file rather than importing a second,
    differently-shaped runner.

    Review F1 (2026-08-06, pre-existing): `str.strip()` treats `\\x1f`
    (Python's `.isspace()` says so) as whitespace, so a whole-output
    `.strip()` here would eat a trailing `\\x1f` off the LAST line of a
    `%H%x1f%(trailers:...)`-formatted log — the exact separator
    `_resolve_foreign_session_shas`'s `"\\x1f" not in line` guard depends on
    to recognize that line at all. That silently drops the oldest commit in
    every range from `foreign` whenever it carries an empty trailer. Strip
    only the trailing newline `proc.stdout` always carries, not arbitrary
    trailing whitespace, so no line position is privileged."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode, proc.stdout.rstrip("\n"), proc.stderr
    except OSError as exc:
        return 1, "", str(exc)


def _resolve_foreign_session_shas(sha_range: str, session_id: str | None) -> frozenset[str]:
    """The `narrow_foreign_shas` callable `directives_review._record_
    membership_shas` injects for session/chain-scoped records (review-
    integrator finding W2).

    Review: review-integrator — B2/B3 (2026-08-06, brightline-discharge
    round4). `session_attribution.trailer_foreign_shas` is deliberately
    EXCLUSION-based: it runs `git log --no-merges` and only flags a commit
    foreign when its OWN trailer AFFIRMATIVELY names a different session,
    leaving a merge commit (never enumerated at all) and an untrailered
    commit (enumerated but never flagged) creditable to ANY spanning record
    regardless of session. That posture was safe when membership also
    required range-containment; under this predicate's intersection-based
    membership it is a bypass — a peer session's wide range can credit a
    merge or untrailered chain commit that owes review. This wrapper does
    NOT delegate to `trailer_foreign_shas` for that reason: it walks
    `sha_range` WITH merges included and treats every commit whose trailer
    does not affirmatively equal `session_id` (no trailer, a different
    trailer, or a merge with no attributable trailer) as foreign —
    inclusion-based with respect to what it can positively attribute, never
    crediting a commit this session cannot be shown to have authored.

    Review R1 (2026-08-06): the trailer-block atom this function reads
    (`%(trailers:key=Session-Id,valueonly)`) disagrees with the message-line
    `--grep=^Session-Id: <sid>$` `coverage._derive_dag_chain_set` uses to
    decide CHAIN MEMBERSHIP — git's trailer parser only reads a commit
    message's final paragraph, so a chain-member commit whose `Session-Id:`
    line is followed by any non-trailer line becomes permanently foreign
    here while the chain walk still counts it as a member, making a
    PARTITION-MANDATORY verdict on such a chain unsatisfiable by any record.
    Before returning, this function subtracts `_grep_attributed_session_
    shas(sha_range, session_id)` — the SAME grep the chain walk uses,
    scoped to `sha_range` — from `foreign`. This subtracted set can be a
    STRICT SUPERSET of what the membership derivation itself attributes to
    this walked node (`_derive_dag_chain_set` unions this leg with a
    stricter `legacy_leg` that excludes grep matches stamped for a
    different walked deliverable) — reviewed and traced (F5, 2026-08-06):
    every commit the over-subtraction can reach still carries this
    session's own `Session-Id` trailer, inside `sha_range`, and inside
    `chain_code`, so crediting it to this record is the correct outcome,
    not an over-credit; the discrepancy is only about which walked node
    owns it, a distinction no credit path here reads. This does not soften
    the merge/untrailered tightening: `--no-merges` means a merge commit is
    never returned by the grep leg either, so it stays foreign exactly as
    before.

    Raises (propagates `session_attribution.GitLogFailed`, or a plain
    exception if the repo root is unresolvable) rather than degrading to an
    empty result on failure — `_record_membership_shas`'s own try/except
    around this callable already fails the record CLOSED on any exception,
    matching `coverage.build_reviewed_set`'s own fail-closed
    `_ForeignSessionLookupError` handling for this exact narrowing. Isolated
    for test monkeypatching."""
    repo_root = _resolve_repo_root()
    if not repo_root:
        raise RuntimeError("_resolve_foreign_session_shas: repo root unresolvable")
    key = (sha_range, session_id)
    if key in _FOREIGN_SHAS_CACHE:
        return _FOREIGN_SHAS_CACHE[key]
    rc, out, err = _git_run_for_session_attribution(
        ["git", "log", "--format=%H%x1f%(trailers:key=Session-Id,valueonly)", sha_range],
        repo_root,
    )
    if rc != 0:
        raise session_attribution.GitLogFailed(
            f"git log failed while resolving foreign-session commits for "
            f"sha_range={sha_range!r}: {err.strip() or 'unknown error'}"
        )
    foreign: set[str] = set()
    for line in out.splitlines():
        if "\x1f" not in line:
            continue
        sha, trailer = line.split("\x1f", 1)
        sha = sha.strip()
        trailer = trailer.strip()
        if not sha:
            continue
        if trailer != session_id:
            foreign.add(sha)
    foreign -= _grep_attributed_session_shas(sha_range, session_id)
    result: frozenset[str] = frozenset(foreign)
    _FOREIGN_SHAS_CACHE[key] = result
    return result


#: Module-level memo for `_resolve_vouched_shas`, keyed on
#: `(session_id, live_vouch_candidate_shas)` (the `_pm_vouched_waiver_shas`
#: half is session-independent and re-reads the same directory for every
#: key — cheap, but memoized here anyway so a repeat call for the same key,
#: common across a chain's many trail records, doesn't re-scan two
#: directories and re-resolve the closing session id per record).
_VOUCHED_SHAS_CACHE: dict = {}


def _live_review_trail_vouch_shas(
    repo_root: str, candidate_shas: frozenset[str],
) -> frozenset[str]:
    """Consult the LIVE, per-session PM-granted review-trail vouch
    (`review_trail_vouch.check_review_trail_vouch`) directly, on the
    coverage READ side, for the CURRENT closing session — the exact same
    predicate `review_trail_write._guard_foreign_session_range` consults at
    write time before minting a permanent `pm-vouches/<sha>.json` waiver
    (`_pm_vouched_waiver_shas` reads that store).

    That write-side guard is gated to `scope_kind == "diff"` only
    (`write_review_trail_entry` — `if scope_kind == "diff" and
    caller_worktree is not None: _guard_foreign_session_range(...)`); a
    `scope_kind == "plan"` record NEVER runs it, so a foreign commit
    credited by a plan-scoped record never gets a waiver file minted no
    matter how live the covering grant was. `_pm_vouched_waiver_shas`
    alone is therefore permanently blind to a plan-scoped vouch — this
    function closes that gap by consulting the grant directly instead of
    depending on an artifact `scope_kind == "plan"` structurally never
    produces (root cause: 2026-08-07, `state/subagent-share/*/
    coordinatorexecutor-74e8304a.md`). This does not touch, weaken, or
    duplicate the write-side guard itself — same predicate, same module,
    called at read time instead of relying on its write-time side effect.

    Scoped to `candidate_shas` (the caller's own chain-relevant sha
    universe) — `check_review_trail_vouch` returns only the intersection of
    `candidate_shas` and the grant's own named `shas` list, so this can
    never credit a sha the grant does not explicitly name, and a
    request naming nothing returns nothing rather than resolving the
    session for no reason.

    Fail-safe toward narrowing: no candidate shas, no resolvable closing
    session id, or `check_review_trail_vouch` raising, all return an empty
    set — mirrors `_resolve_vouched_shas`'s own posture, never toward
    silently manufacturing coverage."""
    if not candidate_shas:
        return frozenset()
    session_id = _resolve_closing_session_id(repo_root)
    if not session_id:
        return frozenset()
    try:
        vouched, _record = review_trail_vouch.check_review_trail_vouch(
            candidate_shas, cwd=repo_root, session_id=session_id,
        )
    except Exception:  # noqa: BLE001 - a broken live-vouch lookup must narrow, never crash
        return frozenset()
    return vouched


def _resolve_vouched_shas(
    session_id: str | None, *, live_vouch_candidate_shas: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """The `vouched_shas` callable `directives_review._record_membership_
    shas` injects (2026-08-06, read-side vouch-honouring fix): unions the
    write-side PM-vouch waiver store (`coverage._pm_vouched_waiver_shas`,
    presence-only, honoured for ANY record regardless of which session wrote
    it) with the gate-minted chain-ancestry waiver store
    (`coverage._chain_ancestry_waived_shas`, scoped to `session_id` — the
    reading trail record's own session_id, i.e. the chain identity that
    would have minted a matching waiver) — the exact same union
    `coverage._narrow_foreign_session_scope` already performs for
    `build_reviewed_set`'s own read path. A sha named here is exempted from
    the foreign-session strip by `_record_membership_shas`, honouring a PM
    vouch (or gate-minted waiver) on the coverage read side the way the
    write side's `ForeignSessionRangeRefused` guard already names as the
    sanctioned remedy.

    2026-08-07: also unions `_live_review_trail_vouch_shas`, scoped to
    `live_vouch_candidate_shas` (the caller's chain-relevant sha universe,
    bound once via `functools.partial` at the `cmd_brightline_gate` call
    site — the SAME callable signature `directives_review` injects, `(sha)
    -> shas`, unaffected). This is the ONLY source that can credit a
    `scope_kind == "plan"` record's foreign shas: `_pm_vouched_waiver_shas`
    never sees them (no waiver file is ever minted for a plan-scope write —
    see `_live_review_trail_vouch_shas`'s own docstring), and
    `_chain_ancestry_waived_shas` is a gate-minted HALT artifact, not a
    PM-grant one. `live_vouch_candidate_shas` defaults to the empty
    frozenset — a caller that omits it (there are none left in this file,
    but any future direct caller) sees byte-identical pre-2026-08-07
    behavior, since an empty candidate set always resolves to nothing.

    Fail-safe toward narrowing, never toward crediting: an unresolvable repo
    root, or either underlying reader raising, returns an empty set — the
    caller (`_record_membership_shas`) treats that identically to "no vouch
    exists," so the foreign strip proceeds exactly as before this resolver
    existed. Both underlying readers (`_pm_vouched_waiver_shas`,
    `_chain_ancestry_waived_shas`) already degrade an unreadable/absent
    waiver directory to an empty set on their own (never raise), but this
    wrapper does not rely on that alone — any other exception (e.g. repo
    root resolution) is caught here too. Isolated for test monkeypatching."""
    key = (session_id, live_vouch_candidate_shas)
    if key in _VOUCHED_SHAS_CACHE:
        return _VOUCHED_SHAS_CACHE[key]
    result: frozenset[str] = frozenset()
    try:
        repo_root = _resolve_repo_root()
        if repo_root:
            result = (
                _pm_vouched_waiver_shas(repo_root)
                | _chain_ancestry_waived_shas(repo_root, session_id)
                | _live_review_trail_vouch_shas(repo_root, live_vouch_candidate_shas)
            )
    except Exception:  # noqa: BLE001 - a broken vouch lookup must narrow, never crash
        result = frozenset()
    _VOUCHED_SHAS_CACHE[key] = result
    return result


def _clear_process_caches() -> None:
    """Test-only reset hook for every module-level, never-cleared-in-
    production process cache this file owns (`_RANGE_SHAS_CACHE`,
    `_DAG_SHAS_CACHE`, `_FOREIGN_SHAS_CACHE`, `_GREP_ATTRIBUTED_SHAS_CACHE`,
    `_VOUCHED_SHAS_CACHE`) — review-integrator finding N2. Each is a correct,
    intentional design for
    production (spawn-per-call, one short-lived process per gate run —
    nothing outlives it to be poisoned), but a cross-test contamination
    hazard for any test suite that calls the real resolvers more than once
    against the SAME cache key (e.g. the literal `from_handoff`/`sha_range`
    strings this test module reuses across dozens of scenarios with
    different monkeypatched git-layer doubles). Not called automatically by
    this module — a test fixture (see
    `coordinator/bin/tests/test_wsc_coverage_gate_runner.py`) calls it
    between tests."""
    _RANGE_SHAS_CACHE.clear()
    _DAG_SHAS_CACHE.clear()
    _FOREIGN_SHAS_CACHE.clear()
    _GREP_ATTRIBUTED_SHAS_CACHE.clear()
    _VOUCHED_SHAS_CACHE.clear()


def _describe_uncovered_shas(shas: list[str], repo_root: str | None) -> list[str]:
    """`<short-sha> <subject>` lines for the C13 brightline HALT's
    uncovered-set diagnostic — the caller (`cmd_brightline_gate`) already
    caps `shas` to the display limit before calling this. One batched
    `git log --no-walk` call; any failure or an unresolved `repo_root`
    degrades to the bare (uncapped-format) sha rather than raising —
    this is a diagnostic amenity, never load-bearing for the refusal
    itself."""
    if not shas:
        return []
    if not repo_root:
        return list(shas)
    try:
        proc = subprocess.run(
            ["git", "log", "--no-walk", "--format=%h %s", *shas],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return list(shas)
    if proc.returncode != 0:
        return list(shas)
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return lines or list(shas)


def _load_trail_records() -> list[dict]:
    """Load every on-disk review-trail record (live + archive) as parsed
    JSON dicts, via `coordinator_core.ops.list_review_trail_records`.
    Isolated for test monkeypatching. Never raises: a state-root resolution
    failure or a malformed record file yields a shorter (possibly empty)
    list rather than crashing the coverage-gate CLI over a diagnostics-only
    sanity check — the caller treats "cannot corroborate" identically to
    "checked and found nothing", never as an error."""
    try:
        paths = _list_review_trail_paths()
    except ReviewTrailListError:
        return []
    records: list[dict] = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                records.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    return records


_MAX_REJECTED_REASONS_SHOWN = 10


def _warn_if_covered_verdict_unterminated(verdict_line: str, from_handoff: str) -> None:
    """Step 2.9's disbelief predicate, wired: a `VERDICT=COVERED` line is
    trustworthy only if at least one on-disk review-trail record's
    range-tip reaches the CHAIN'S OWN TIP at gate-run time — the newest
    substantive commit the coverage gate actually reasoned over, resolved
    by `_resolve_chain_tip_sha` (NOT raw `git rev-parse HEAD` — see that
    function's docstring for why raw HEAD is structurally unsatisfiable on
    this fleet's shared `work/*` branches), via
    `coordinator_core.workstream_complete.directives_review.
    verify_trail_range_termination` — see that module for the verified
    2026-07-25 `work/machine-a/2026-07-21` incident this closes: 8 stale
    `<sha>..HEAD` records reading as COVERED 12 commits past the newest
    concrete-range record).

    Prints a fail-loud diagnostic naming every rejected record's reason
    when the predicate cannot corroborate the verdict. Deliberately never
    changes `cmd_coverage_gate`'s return code — this subcommand's own
    halt policy already resolves COVERED to exit 0 unconditionally (see
    module docstring); this check qualifies what the verdict line means,
    it does not turn COVERED into a second halt path. Any failure inside
    this function (git unavailable, trail records unreadable) is caught
    and reported as its own diagnostic note — a broken disbelief check
    must never crash the gate it backs."""
    if "VERDICT=COVERED" not in verdict_line:
        return
    try:
        chain_tip_sha = _resolve_chain_tip_sha(from_handoff)
        if not chain_tip_sha:
            print(
                "NOTE: trail-range-termination disbelief check skipped — "
                "could not resolve the chain's own tip (DAG chain-set "
                "derivation indeterminate/empty, or git unavailable).",
                file=sys.stderr,
            )
            return
        records = _load_trail_records()
        if verify_trail_range_termination(records, chain_tip_sha, _git_is_ancestor):
            return
        rejected = classify_untrusted_trail_ranges(records)
        reasons = [reason for _record, reason in rejected[:_MAX_REJECTED_REASONS_SHOWN]]
        remainder = len(rejected) - len(reasons)
        reason_text = "; ".join(reasons) if reasons else "no review-trail records on disk"
        if remainder > 0:
            reason_text += f"; +{remainder} more"
        print(
            f"NOTE: VERDICT=COVERED could not be corroborated — no on-disk "
            f"review-trail record's range-tip reaches chain tip "
            f"{chain_tip_sha}. {len(rejected)} record(s) rejected: {reason_text}",
            file=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics-only, must never be fatal
        print(
            f"NOTE: trail-range-termination disbelief check could not run: {exc}",
            file=sys.stderr,
        )


def cmd_coverage_gate(args: argparse.Namespace) -> int:
    returncode, stdout, stderr = _run_review_coverage_gate(args.from_handoff)

    # Review: F9 (carried from the ported SKILL comment) — parse the VERDICT
    # token out of stdout; do NOT rely on the gate's exit code (it exits 0 on
    # both COVERED/UNCOVERED, matching review-brightline-gate.py's shape).
    verdict_line = stdout.strip()
    if verdict_line:
        print(verdict_line)

    override = os.environ.get("COORDINATOR_OVERRIDE_COVERAGE_GATE", "0") == "1"

    # A malformed INDETERMINATE result can carry an empty verdict_line (see
    # review-coverage-gate.py's own "must propagate even when verdict_line is
    # empty" comment) — fall back to the underlying exit code so that case
    # still halts as INDETERMINATE rather than silently falling through to
    # the COVERED passthrough at the bottom of this function.
    if "VERDICT=INDETERMINATE" in verdict_line or returncode == 2:
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
        if override:
            print(
                "WARNING: COORDINATOR_OVERRIDE_COVERAGE_GATE=1 — INDETERMINATE "
                "gate bypassed by PM override.",
                file=sys.stderr,
            )
            return 0
        print(
            "HALT: coverage gate INDETERMINATE — DAG derivation failed; check "
            "handoff DAG integrity before proceeding.",
            file=sys.stderr,
        )
        print(
            "Override (PM-authorized only): set COORDINATOR_OVERRIDE_COVERAGE_GATE=1 "
            "to bypass.",
            file=sys.stderr,
        )
        return 2

    if "VERDICT=WARN" in verdict_line:
        # C10 (docs/plans/2026-08-05-coverage-gate-planning-artifact-class.md,
        # AC14): the pre-C10 binary UNCOVERED halt-or-override path is
        # retired. WARN is an offer, never a refusal — ordinary coverage
        # never hard-blocks (see coordinator_core.coverage's module-level
        # hard-block decision note). The uncovered commits are already
        # surfaced on stderr by the gate itself; no re-run needed here, just
        # relay, then print the remediation offer and exit 0.
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
        print(
            "WARN: coverage gate below threshold — dispatch coordinator:review-code "
            "on the listed commits, then re-run the gate. This is an offer, not a "
            "halt — the gate does not block on it.",
            file=sys.stderr,
        )
        if override:
            print(
                "NOTE: COORDINATOR_OVERRIDE_COVERAGE_GATE=1 was set but has no "
                "effect — the coverage gate no longer halts on WARN (C10), so "
                "there is nothing to override.",
                file=sys.stderr,
            )
        return 0

    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    _warn_if_covered_verdict_unterminated(verdict_line, args.from_handoff)

    # VERDICT=COVERED, or the underlying gate could not be reached at all —
    # propagate its own exit code rather than reinterpreting it.
    return returncode


# ---------------------------------------------------------------------------
# write-trail
# ---------------------------------------------------------------------------

def _run_write_review_trail(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the sibling coordinator-write-review-trail.py and return
    (returncode, stdout, stderr). Isolated for test monkeypatching."""
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "coordinator-write-review-trail.py"),
        *argv,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # popup-safe-env-suppressed
    )
    return proc.returncode, proc.stdout, proc.stderr


def cmd_write_trail(args: argparse.Namespace) -> int:
    argv = [
        "--sha-range", args.sha_range,
        "--reviewer", args.reviewer,
        "--scope", args.scope,
        "--verdict", args.verdict,
        "--diff-loc", str(args.diff_loc),
    ]
    if args.scope_kind:
        argv += ["--scope-kind", args.scope_kind]
    if args.workstream:
        argv += ["--workstream", args.workstream]

    returncode, stdout, stderr = _run_write_review_trail(argv)
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
    return returncode


# ---------------------------------------------------------------------------
# brightline-gate
# ---------------------------------------------------------------------------

#: The verbatim `verdict=` literal `review-brightline-gate.py::_from_handoff_
#: main` emits on its BRIGHTLINE line — imported as
#: `directives_review.CHAIN_VERDICT_PARTITION_MANDATORY` (review-integrator
#: finding, P3, 2026-08-06: that module now exports it publicly, so this
#: file no longer needs its own duplicate literal). The other copy of this
#: value, inside this file's own `_BRIGHTLINE_RE` alternation below, is
#: unrelated (a regex fragment matching the raw stdout token, not a
#: comparison constant) and is out of scope for this dedup.

_BRIGHTLINE_RE = re.compile(
    r"^BRIGHTLINE reviewers_required=(?P<reviewers_required>\d+) "
    r"reviewers_suggested=(?P<reviewers_suggested>\d+) "
    r"reviewers_low=(?P<reviewers_low>\d+) "
    r"plan_oracle=(?P<plan_oracle>\d+) "
    r"chain_oracle=(?P<chain_oracle>\d+) "
    r"session_oracle=(?P<session_oracle>\d+) "
    r"tier=(?P<tier>none|A|B) "
    r"verdict=(?P<verdict>single-reviewer-ok|PARTITION-MANDATORY) "
    r'basis="(?P<basis>[^"]*)"$'
)

_UNWALKED_REPOS_RE = re.compile(r"tier=A declared-but-unwalked repo\(s\)=(?P<repos>[^ ]*)")


def _run_review_brightline_gate(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the sibling review-brightline-gate.py in --from-handoff mode and
    return (returncode, stdout, stderr). Isolated for test monkeypatching."""
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "review-brightline-gate.py"),
        "--from-handoff",
        *argv,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # popup-safe-env-suppressed
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_brightline_line(stdout: str) -> dict | None:
    """Return the last BRIGHTLINE line's fields as a dict, or None if the gate
    did not emit one (transport failure, malformed compute — treat as a
    fail-loud infra error, never a silent tier=none pass)."""
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        return None
    m = _BRIGHTLINE_RE.match(lines[-1])
    if not m:
        return None
    return m.groupdict()


def _resolve_closing_session_id(repo_root: str) -> str | None:
    """Resolve the closing session id via the SAME algorithm `workstream_
    complete.compute_session_shape_gate` uses (`wsc-session-disposition.py::
    resolve_session_id` — em_sid / CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID
    env vars, then the `.current-session-id` sentinel, then an epoch
    fallback), so the verdict record this subcommand writes is keyed by the
    EXACT id `brief()`'s `gate.sid` will resolve to on read-back. Loaded by
    file path (hyphenated bin script, not a package) — see
    `workstream_complete.__init__._load_bin_module`'s own docstring for why
    this is the correct seam. Returns None on any load/resolution failure
    (diagnostics-only path — the verdict write this backs is itself
    non-fatal, per this subcommand's advisory contract)."""
    import importlib.util

    script_path = Path(_SCRIPT_DIR) / "wsc-session-disposition.py"
    try:
        spec = importlib.util.spec_from_file_location("wsc_session_disposition", script_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.resolve_session_id(Path(repo_root))
    except Exception:  # noqa: BLE001 - diagnostics-only, must never be fatal
        return None


def _persist_brightline_verdict(
    from_handoff: str,
    git_range: str | None,
    fields: dict,
) -> None:
    """Write the just-computed brightline verdict to the persistence seam
    (`chain_partition_verdict_store`) so the NEXT `wsc.brief()`/`wsc.apply()`
    call can read it without an EM re-typing `decisions["chain_partition_
    verdict"]` (root cause: cross-repo/inbox/2026-08-04-project-rag-em-
    brightline-partition-mandatory-does-not-halt.md, "mechanism 2").

    Best-effort and NON-FATAL: any failure (session id unresolvable, repo
    root unresolvable, disk write error) is reported loudly on stderr and
    swallowed — this function must never change `cmd_brightline_gate`'s
    exit code or turn this advisory gate into a halt."""
    repo_root = _resolve_repo_root()
    if not repo_root:
        print(
            "WARNING: could not persist brightline verdict — repo root "
            "unresolvable. decisions[\"chain_partition_verdict\"] remains "
            "the only path forward this run.",
            file=sys.stderr,
        )
        return
    session_id = _resolve_closing_session_id(repo_root)
    if not session_id:
        print(
            "WARNING: could not persist brightline verdict — closing "
            "session id unresolvable. decisions[\"chain_partition_verdict\"] "
            "remains the only path forward this run.",
            file=sys.stderr,
        )
        return
    try:
        write_verdict_record(
            Path(repo_root),
            session_id=session_id,
            verdict=fields["verdict"],
            from_handoff=from_handoff,
            git_range=git_range,
            basis=fields["basis"],
            tier=fields["tier"],
        )
    except OSError as exc:
        print(
            f"WARNING: could not persist brightline verdict to disk: {exc}. "
            "decisions[\"chain_partition_verdict\"] remains the only path "
            "forward this run.",
            file=sys.stderr,
        )


def _autonomous_sentinel_exists() -> bool:
    """The /coordinator:autonomous sentinel — path resolution is delegated to
    coordinator_core.session.autonomous_sentinel.sentinel_path(), the single
    shared resolver both the writer (misc-session-and-guards.py) and every
    reader use, so writer and reader can never drift onto different tmp-dir
    conventions again (see that module's docstring for the incident this
    fixes)."""
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not session_id:
        return False
    from coordinator_core.session.autonomous_sentinel import sentinel_path

    return sentinel_path(session_id).exists()


def _findings_name_unwalked_repo(basis: str) -> bool:
    """Finding-6-adjacent escape hatch: a tier=A halt is also lifted when a
    reviewer has already recorded findings under state/review-trail/findings/
    that name the declared-but-unwalked repo from the gate's own basis text —
    the repo was reviewed by other means, just not walked by the chain DAG."""
    m = _UNWALKED_REPOS_RE.search(basis)
    if not m:
        return False
    repos = [r for r in m.group("repos").split(",") if r]
    if not repos:
        return False
    findings_dir = Path("state") / "review-trail" / "findings"
    if not findings_dir.is_dir():
        return False
    for path in findings_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if any(repo in text for repo in repos):
            return True
    return False


def _findings_count_for_chain() -> int:
    """Count of reviewer-findings artifacts on disk under
    state/review-trail/findings/ (Finding 4 discharge: "N reviewers findings
    exist on disk", not merely "EM typed N"). Flat count over the whole
    findings tree — the caller cross-checks this against a recorded decision,
    it does not itself decide chain scope."""
    findings_dir = Path("state") / "review-trail" / "findings"
    if not findings_dir.is_dir():
        return 0
    return sum(1 for path in findings_dir.rglob("*") if path.is_file())


def cmd_brightline_gate(args: argparse.Namespace) -> int:
    gate_argv = [args.from_handoff]
    if args.git_range:
        gate_argv.append(args.git_range)

    returncode, stdout, stderr = _run_review_brightline_gate(gate_argv)
    if stdout.strip():
        print(stdout.strip())
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    fields = _parse_brightline_line(stdout)
    if fields is None:
        print(
            "STOP: brightline gate produced no parseable BRIGHTLINE line — "
            "infra error, not a tier verdict.",
            file=sys.stderr,
        )
        return 1

    tier = fields["tier"]
    basis = fields["basis"]

    # Producer/consumer seam (2026-08-03 plan
    # docs/plans/2026-08-03-chain-end-review-scale-wiring.md, C5; persistence
    # half landed 2026-08-04 per cross-repo/inbox/2026-08-04-project-rag-em-
    # brightline-partition-mandatory-does-not-halt.md "mechanism 2"). This is
    # the ONLY place `verdict=` is available to a caller of this script.
    # Persist it (chain_partition_verdict_store) so the NEXT
    # `wsc.brief()`/`wsc.apply()` call on this chain reads it automatically
    # when `decisions` doesn't supply an explicit override — an explicit
    # `decisions["chain_partition_verdict"]` always wins over the persisted
    # record (see that module + `brief()`'s own read-site docstrings).
    # Printed/persisted regardless of tier — tier gates whether THIS gate run
    # halts, not whether the verdict it already resolved is worth carrying
    # forward.
    _persist_brightline_verdict(args.from_handoff, args.git_range, fields)
    print(
        f'ACTION: the chain-scoped verdict "{fields["verdict"]}" has been '
        "persisted and will be read automatically by the NEXT "
        "wsc.brief()/wsc.apply() call on this chain (if this close's chain "
        "disposition canonicalizes to a chain terminal) — no manual "
        "carry-forward required. An explicit "
        f'decisions["chain_partition_verdict"] = "{fields["verdict"]}" '
        "remains available as an override, e.g. when the persisted record "
        "cannot be trusted for the upcoming close. (This script does not "
        "itself check the close's disposition; decide_review_scale ignores "
        "both the persisted record and this value on a non-chain-terminal "
        "close.)",
        file=sys.stderr,
    )

    if tier == "A":
        override_env = os.environ.get("COORDINATOR_OVERRIDE_BRIGHTLINE", "0") == "1"
        sentinel_present = _autonomous_sentinel_exists()
        findings_cover_repo = _findings_name_unwalked_repo(basis)

        if findings_cover_repo:
            print(
                "NOTE: tier=A unwalked-repo halt lifted — a recorded reviewer "
                "finding under state/review-trail/findings/ already names the "
                "declared-but-unwalked repo.",
                file=sys.stderr,
            )
            return 0

        if override_env and sentinel_present:
            print(
                "WARNING: COORDINATOR_OVERRIDE_BRIGHTLINE=1 — tier=A "
                "declared-but-unwalked-repo halt bypassed under /autonomous "
                "sentinel.",
                file=sys.stderr,
            )
            return 0

        if override_env and not sentinel_present:
            print(
                "STOP: COORDINATOR_OVERRIDE_BRIGHTLINE=1 set but no /autonomous "
                "sentinel present — override REFUSED (interactive EM, PM must "
                "decide).",
                file=sys.stderr,
            )
        print(
            "HALT: brightline tier=A — a deferred:false code-bearing plan row "
            "declares a repo the chain walk never touched (or was "
            "indeterminate on). Dispatch coordinator:review-code on that repo, "
            "or record findings under state/review-trail/findings/ naming it, "
            "before proceeding.",
            file=sys.stderr,
        )
        print(f'basis: "{basis}"', file=sys.stderr)
        return 1

    # C13 (docs/plans/2026-08-05-coverage-gate-planning-artifact-class.md,
    # AC20/AC21): the ONE narrow refusal carved out of the "tier in {B,
    # none} never hard-stops" posture below. Checked BEFORE the
    # communicate-only branch — a PARTITION-MANDATORY verdict with nothing
    # discharging it on the review-trail must never fall through to a
    # relay-and-exit-0 path. Does NOT fire on `single-reviewer-ok` or any
    # other verdict — that ordinary case is untouched by this chunk.
    if fields["verdict"] == _CHAIN_VERDICT_PARTITION_MANDATORY:
        # Scoped to THIS chain by WITHIN-CHAIN MEMBERSHIP, not by tip
        # ancestry (2026-08-06 chain-scoping correction — see
        # `directives_review.chain_partition_verdict_discharged`'s own
        # docstring for the live re-verification this replaces: "record's
        # tip is later on the shared branch than the chain tip" is
        # satisfiable by any concurrent peer session's own review on this
        # fleet's one-shared-branch-many-sessions norm, and is therefore not
        # evidence the record reviewed THIS chain at all). Membership and
        # coverage are two different sets (2026-08-06 membership-vs-coverage
        # split, review-integrator P1): `chain_dag_shas` (unfiltered — every
        # chain DAG commit, bookkeeping and handoff-authoring included)
        # gates whether a record's range is even about this chain at all;
        # `chain_code_shas` (filtered — code-review obligation set) gates
        # what a membership-passing record actually discharges.
        # `_resolve_chain_tip_sha` is no longer consulted here.
        #
        # `uncovered` is computed exactly ONCE here (2026-08-06,
        # review-integrator P3) and `discharged` is derived from it rather
        # than calling `chain_partition_verdict_discharged` AND
        # `chain_partition_uncovered_shas` separately — both previously
        # walked `_collect_discharging_range_shas` a second time over the
        # same inputs for no additional information.
        # `_derive_dag_shas` is called directly (not merely through
        # `_resolve_chain_code_shas`/`_resolve_chain_dag_shas`, both of which
        # hit the SAME memoized result via `_DAG_SHAS_CACHE`) so this branch
        # can tell "DAG derivation itself failed" (`dag_resolved is None`)
        # apart from "DAG derivation succeeded but every chain commit is
        # ceremony bookkeeping / handoff-authoring-only, so `chain_code_shas`
        # is legitimately empty" — review-integrator finding W3. Before this
        # distinction, both collapsed to the same "diagnostics unavailable"
        # HALT with no REMEDY line, so a pure-ceremony/handoff chain that
        # reached PARTITION-MANDATORY had no discharge path at all short of
        # `/handoff`. The honest answer: a chain that owes no code review
        # cannot fail to discharge one.
        dag_resolved = _derive_dag_shas(args.from_handoff)
        trail_records = _load_trail_records()
        chain_code_shas = _resolve_chain_code_shas(args.from_handoff)
        chain_dag_shas = _resolve_chain_dag_shas(args.from_handoff)
        dag_resolution_failed = dag_resolved is None
        chain_owes_no_code_review = not dag_resolution_failed and not chain_code_shas
        if chain_owes_no_code_review:
            uncovered: list[str] = []
            discharged = True
        else:
            uncovered = (
                chain_partition_uncovered_shas(
                    trail_records, chain_code_shas, chain_dag_shas, _resolve_range_shas,
                    narrow_foreign_shas=_resolve_foreign_session_shas,
                    # `chain_dag_shas` (the chain's unfiltered DAG sha
                    # universe) bounds the live-vouch candidate set — the
                    # largest set any trail record's membership check could
                    # ever need narrowed, so this can never credit a sha
                    # outside this chain even when the PM grant names one.
                    vouched_shas=functools.partial(
                        _resolve_vouched_shas,
                        live_vouch_candidate_shas=frozenset(str(s).lower() for s in chain_dag_shas),
                    ),
                    chain_planning_shas=_resolve_chain_planning_shas(args.from_handoff),
                )
                if chain_code_shas and chain_dag_shas
                else []
            )
            discharged = bool(chain_code_shas) and bool(chain_dag_shas) and not uncovered
        if chain_owes_no_code_review:
            print(
                "NOTE: PARTITION-MANDATORY code-discharge check vacuously "
                "satisfied — this chain's DAG resolved but carries zero "
                "code-review obligations (every chain commit is ceremony "
                "bookkeeping or handoff-authoring-only). A chain with no "
                "code-bearing commits owes no code review.",
                file=sys.stderr,
            )
        if not discharged:
            print(
                "HALT: brightline verdict=PARTITION-MANDATORY and the "
                "on-disk review-trail carries no verdict that is both "
                "non-pending and non-waived — the review this chain "
                "mandates has not been run. This session cannot reach a "
                "terminal stamp in this state.",
                file=sys.stderr,
            )
            if chain_code_shas and chain_dag_shas:
                cap = 10
                descs = _describe_uncovered_shas(uncovered[:cap], _resolve_repo_root())
                print(
                    f"UNCOVERED: {len(uncovered)} of {len(chain_code_shas)} "
                    "chain code commit(s) carry no discharging review-trail "
                    "verdict (no record's range names them):",
                    file=sys.stderr,
                )
                for line in descs:
                    print(f"  {line}", file=sys.stderr)
                if len(uncovered) > cap:
                    print(f"  +{len(uncovered) - cap} more", file=sys.stderr)
                print(
                    "REMEDY: record a per-commit review-trail verdict for "
                    "each via coordinator/bin/coordinator-write-review-"
                    "trail.py.",
                    file=sys.stderr,
                )
            else:
                print(
                    "UNCOVERED: union-coverage diagnostics unavailable — "
                    "the chain's code-bearing commit set could not be "
                    "resolved, so no uncovered-commit list can be shown.",
                    file=sys.stderr,
                )
            print(
                "ACTION: sanctioned exit is /handoff — hand the review to a "
                "fresh session rather than proceeding here.",
                file=sys.stderr,
            )
            print(f'basis: "{basis}"', file=sys.stderr)
            return 1

    # tier in {B, none} — communicate loudly, never hard-stop. The EM (not
    # this script) decides reviewers_required; this only cross-checks a
    # recorded decision against findings already on disk when one is given.
    print(
        f"BRIGHTLINE tier={tier} verdict={fields['verdict']} — "
        f"reviewers_suggested={fields['reviewers_suggested']} "
        f"reviewers_low={fields['reviewers_low']} "
        f"plan_oracle={fields['plan_oracle']} chain_oracle={fields['chain_oracle']} "
        f"session_oracle={fields['session_oracle']}",
        file=sys.stderr,
    )
    print(f'basis: "{basis}"', file=sys.stderr)

    recorded = os.environ.get("COORDINATOR_BRIGHTLINE_REVIEWER_COUNT")
    if recorded is None:
        print(
            "ACTION: no recorded EM reviewer-count decision "
            "(COORDINATOR_BRIGHTLINE_REVIEWER_COUNT) — record one before "
            "dispatching review; this is a communicate-only gate, not a halt.",
            file=sys.stderr,
        )
    else:
        found = _findings_count_for_chain()
        try:
            recorded_n = int(recorded)
        except ValueError:
            print(
                f"WARNING: COORDINATOR_BRIGHTLINE_REVIEWER_COUNT={recorded!r} "
                "is not an integer — skipping cross-check.",
                file=sys.stderr,
            )
        else:
            if found < recorded_n:
                print(
                    f"WARNING: recorded reviewer decision N={recorded_n} but only "
                    f"{found} findings artifact(s) exist under "
                    "state/review-trail/findings/ — discharge is disk findings, "
                    "not the recorded count alone.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"OK: recorded reviewer decision N={recorded_n} covered by "
                    f"{found} findings artifact(s) on disk.",
                    file=sys.stderr,
                )

    return 0


# ---------------------------------------------------------------------------
# argv plumbing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wsc-coverage-gate-runner.py")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_claim = sub.add_parser("claim-plan")
    p_claim.add_argument("slug")
    p_claim.set_defaults(func=cmd_claim_plan)

    p_gate = sub.add_parser("coverage-gate")
    p_gate.add_argument("--from-handoff", required=True, dest="from_handoff")
    p_gate.set_defaults(func=cmd_coverage_gate)

    p_trail = sub.add_parser("write-trail")
    p_trail.add_argument("--sha-range", required=True, dest="sha_range")
    p_trail.add_argument("--reviewer", required=True)
    p_trail.add_argument("--scope", required=True)
    p_trail.add_argument("--verdict", required=True)
    p_trail.add_argument("--diff-loc", required=True, dest="diff_loc")
    p_trail.add_argument("--scope-kind", default=None, dest="scope_kind")
    p_trail.add_argument("--workstream", default=None, dest="workstream")
    p_trail.set_defaults(func=cmd_write_trail)

    p_brightline = sub.add_parser("brightline-gate")
    p_brightline.add_argument("--from-handoff", required=True, dest="from_handoff")
    p_brightline.add_argument("git_range", nargs="?", default=None)
    p_brightline.set_defaults(func=cmd_brightline_gate)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
