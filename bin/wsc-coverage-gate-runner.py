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
      policy. This subcommand owns that policy.

      The `tier` field this line used to carry, and the `if tier == "A"`
      hard-stop branch that read it, are REMOVED (state/kill-ledger.md
      K-004, 2026-08-16, Verdict A — measured across 151 records: tier=B
      135, tier=none 16, tier=A zero; tier=B fell through to a plain
      communicate-only exit 0, changing only a `basis` substring, so
      removing it changes nothing observable). Communicate the full
      BRIGHTLINE line loudly (all three oracle numbers + basis) and prompt
      for a RECORDED EM reviewer-count decision
      (COORDINATOR_BRIGHTLINE_REVIEWER_COUNT), cross-checked against the
      count of matching artifacts under state/review-trail/findings/ when
      set. Never a hard stop on its own — the EM's judgment call, not the
      gate's:

                 C13 (docs/plans/2026-08-05-coverage-gate-planning-artifact-
                 class.md, AC20/AC21; narrowed 2026-08-08 by
                 docs/plans/2026-08-08-vouch-free-review-coverage-gates.md):
                 ONE narrow exception carved out of the "never a hard stop"
                 posture above. When `verdict=PARTITION-MANDATORY` AND the
                 on-disk review-trail carries no record whose resolved range
                 shares at least one commit with the chain's own DAG
                 (membership, an intersection test — see
                 `directives_review.chain_partition_verdict_discharged`'s own
                 docstring) and whose code-bearing intersection covers every
                 one of the chain's code-review obligations, the uncovered
                 set is partitioned (`_partition_foreign_uncovered_shas`)
                 into `own_shas` (this session's own code commits — no
                 discharging verdict yet, but recordable: nothing refuses a
                 review-trail write naming them) and `foreign_shas`
                 (ancestor/predecessor commits the foreign-session guard on
                 trail-record writes refuses to let this session record,
                 regardless of verdict):
                   - `own_shas` non-empty => this subcommand REFUSES (HALT,
                     exit 1) — a session cannot be told "four reviewers
                     required," run zero, and still reach a clean terminal
                     stamp (the verified 2026-08-05 DoE-claude incident this
                     closes) when the gap is one it could close itself. The
                     halt names the performable remedy: record a per-commit
                     review-trail verdict for each `own_shas` entry via
                     coordinator/bin/coordinator-write-review-trail.py.
                   - `own_shas` empty (every uncovered commit is
                     foreign/ancestor-only) => communicate-only, exit 0. No
                     record this session writes could discharge a commit the
                     foreign-session guard refuses to let it name, so
                     halting here would be unsatisfiable by any means this
                     gate documents — the diagnostic still prints the full
                     uncovered breakdown (code/planning/foreign counts, a
                     per-sha describe list) to stderr, it just does not stop
                     the close.
                   - When `chain_code_shas`/`chain_dag_shas` themselves fail
                     to resolve (diagnostics unavailable — a different
                     failure mode than "own commits lack a verdict," and one
                     where the own/foreign split cannot be computed at all),
                     this subcommand still REFUSES (HALT, exit 1)
                     unconditionally, conservative for lack of any basis to
                     know the gap is foreign-only; that path's message names
                     `/handoff` as the sanctioned exit.
                 Discharge is scoped by CHAIN MEMBERSHIP, not by tip
                 ancestry (2026-08-06 correction): a record whose range-tip
                 merely lands later on this fleet's ONE SHARED
                 `work/{machine}/{date}` branch than the chain tip is NOT
                 evidence it reviewed this chain — every concurrent peer
                 session's record satisfies that condition regardless of
                 what it actually reviewed, which live re-verification
                 proved trivially satisfiable by unrelated peer activity and
                 unsatisfiable-by-timing for a chain with no later peer
                 write yet. See `directives_review.chain_partition_verdict_
                 discharged`'s own docstring for the full incident writeup.
                 `single-reviewer-ok` and every ordinary communicate-only
                 case are UNCHANGED — this does not restore the pre-C10
                 hard-block posture, it adds one discharge check on top of it.

Spec backlink: docs/plans/2026-07-21-doe-skill-bash-to-claude-klabauter-python-port.md [DEAD-CITATION: plan file never committed to this repo]
  (M3 chunk WSC-2). Source: DoE-claude
  coordinator/skills/workstream-complete/SKILL.md §§ Step 2.4 "Plan-claim
  guard", Step 2.9 "Coverage gate (chain-end path)" + "Marker write".

Exit codes:
  claim-plan    — 0 (claimed/re-entrant/stale-takeover), 1 (contention or
                  infra error — both fail the same way; see docstring above)
  write-trail   — propagates coordinator-write-review-trail.py's own exit
                  code verbatim (0 success, 1 missing required arg, 2 native
                  op transport/refusal failure)
  brightline-gate — 0 (communicate-only, including — C13 —
                  verdict=PARTITION-MANDATORY whose uncovered set is
                  foreign/ancestor-only), 1 (the underlying gate could not
                  be reached / did not emit a parseable BRIGHTLINE line; or
                  — C13 — verdict=PARTITION-MANDATORY with no discharging
                  review-trail verdict on disk AND at least one uncovered
                  commit this session itself authored, or with diagnostics
                  unavailable)
"""
from __future__ import annotations

import argparse
import contextvars
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
    EXECUTION_BASIS_NOT_RECORDED,
    ChainAttributionWindow,
    build_chain_slices,
    chain_partition_execution_basis_report,
    chain_partition_uncovered_shas,
    classify_untrusted_trail_ranges,
    verify_trail_range_termination,
)
from coordinator_core.coverage import (  # noqa: E402
    SPEC_DISPATCH_EXEMPT_REASON,
    _UUID_RE,
    _classify_bookkeeping_shas,
    _commit_touched_paths,
    _derive_dag_chain_set,
    _resolve_numstat_row_path,
    _spec_dispatch_exempt_planning_shas,
)
from coordinator_core.ops.review_brightline_gate import (  # noqa: E402
    _is_prose_bearing_path,
)
from coordinator_core.workstream_complete.chain_partition_verdict_store import (  # noqa: E402
    write_verdict_record,
)
from coordinator_core.git.repo_root import show_toplevel as _show_toplevel  # noqa: E402
from coordinator_core import chain_attribution  # noqa: E402
from coordinator_core import session_attribution  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags  # noqa: E402


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


#: Plan C4 (docs/plans/2026-08-15-composition-invocation-budgets.md) —
#: per-run `_commit_touched_paths` cache, keyed by sha, shared across this
#: close's `_classify_bookkeeping_shas` call sites (`_resolve_dag_
#: candidates`, `_resolve_chain_planning_shas`, `_resolve_chain_spec_
#: dispatch_exempt_shas`, `_classify_uncovered_shas`) so a sha's touched-
#: paths batch is fetched at most once per close, not once per resolver.
#: A `contextvars.ContextVar` rather than a plain module-global: several
#: existing tests replace `_resolve_chain_code_shas`/`_resolve_chain_
#: planning_shas`/etc. wholesale via `monkeypatch.setattr(_mod,
#: "_resolve_chain_code_shas", lambda from_handoff: ...)`, so threading the
#: cache through an added call parameter would break every one of those
#: call sites' arity — the cache must reach the resolvers without widening
#: their signature.
#:
#: `_reset_touched_paths_cache` (called once, at the top of `cmd_
#: brightline_gate`'s PARTITION-MANDATORY block, before any of the four
#: sibling resolvers run) REPLACES this ContextVar's value with a brand
#: new empty dict — it does not need a `with`/`finally` teardown, because
#: every entry is a pure, content-addressed `sha -> touched-paths`
#: mapping: even if a stale dict from an EARLIER close in this same
#: process were consulted, no entry in it could ever be wrong for a
#: DIFFERENT close (same repo, same shas). The reset call still means the
#: cache does not, in practice, outlive one close: each new close's first
#: sibling call overwrites the ContextVar with its own fresh dict, so the
#: previous close's dict becomes unreachable (dropped) at that point,
#: never consulted again. It is also never shared across the ~16
#: concurrent sessions this tree carries — each is its own process with
#: its own ContextVar default. Outside any call to `_reset_touched_paths_
#: cache`, `.get()` returns `None` and every resolver falls back to its
#: own call-local `{}`, exactly as it did before C4.
_TOUCHED_PATHS_CACHE: contextvars.ContextVar[dict[str, "frozenset[str]"] | None] = (
    contextvars.ContextVar("_TOUCHED_PATHS_CACHE", default=None)
)


def _reset_touched_paths_cache() -> dict[str, "frozenset[str]"]:
    """Start a fresh, empty plan-C4 touched-paths cache for the close about
    to run, discarding whatever any prior close in this process left behind
    (see `_TOUCHED_PATHS_CACHE`'s own docstring for why no explicit
    teardown is needed). Returns the new dict for callers that also want a
    direct handle on it."""
    cache: dict[str, "frozenset[str]"] = {}
    _TOUCHED_PATHS_CACHE.set(cache)
    return cache


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
    refactor.

    Shares plan C4's per-close touched-paths cache via `_TOUCHED_PATHS_
    CACHE` (the ContextVar, not an added parameter — see that variable's
    own docstring for why: several existing tests replace this module's
    resolvers wholesale with single-argument lambdas, and widening the call
    signature would break every one of those call sites). Outside a
    `_reset_touched_paths_cache` call, falls back to a call-local `{}`,
    exactly as before C4."""
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
    cache = _TOUCHED_PATHS_CACHE.get()
    if cache is None:
        cache = {}
    exhaust_set, _planning_set, _note = _classify_bookkeeping_shas(dag_shas, repo_root, cache)
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
    credit available", never crash the gate.

    Shares plan C4's per-close touched-paths cache via `_TOUCHED_PATHS_
    CACHE` — see `_resolve_dag_candidates`'s docstring for why a ContextVar,
    not an added parameter."""
    resolved = _derive_dag_shas(from_handoff)
    if resolved is None:
        return []
    repo_root, dag_shas = resolved
    cache = _TOUCHED_PATHS_CACHE.get()
    if cache is None:
        cache = {}
    _exhaust_set, planning_set, _note = _classify_bookkeeping_shas(dag_shas, repo_root, cache)
    return [sha for sha in dag_shas if sha in planning_set]


def _resolve_chain_spec_dispatch_exempt_shas(
    from_handoff: str,
    uncovered_planning_shas: list[str],
) -> tuple[frozenset[str], dict[str, str]]:
    """The live-path twin of `coverage.run_coverage_gate`'s spec-dispatch
    PLANNING exemption (`coverage._spec_dispatch_exempt_planning_shas`),
    wired into THIS runner's own `_classify_bookkeeping_shas` call rather
    than `run_coverage_gate`'s — `run_coverage_gate` is not the live path
    for `cmd_brightline_gate`'s C13 PARTITION-MANDATORY HALT (that HALT
    reads `_resolve_chain_planning_shas`, not `run_coverage_gate`'s
    result), so the exemption must be re-derived here off the SAME two
    gates (route: the commit's plan carries `scope_mode: spec-dispatch`;
    compensating control: a qualifying non-waived/non-pending code-review
    trail record over a CODE commit in this chain) rather than imported
    as a precomputed set.

    `uncovered_planning_shas`, empty, or `_derive_dag_shas` failing,
    degrades to `(frozenset(), {})` — no exemption available — mirroring
    every other resolver in this module's fail-safe posture: this backs a
    discharge-widening leg that must never manufacture an exemption from
    incomplete data, only ever narrow toward "still owed".

    Shares plan C4's per-close touched-paths cache via `_TOUCHED_PATHS_
    CACHE` — see `_resolve_dag_candidates`'s docstring for why a ContextVar,
    not an added parameter."""
    if not uncovered_planning_shas:
        return frozenset(), {}
    resolved = _derive_dag_shas(from_handoff)
    if resolved is None:
        return frozenset(), {}
    repo_root, dag_shas = resolved
    cache = _TOUCHED_PATHS_CACHE.get()
    if cache is None:
        cache = {}
    bookkeeping_set, planning_set, _note = _classify_bookkeeping_shas(
        dag_shas, repo_root, cache
    )
    try:
        trail_paths = _list_review_trail_paths()
    except ReviewTrailListError:
        trail_paths = []
    return _spec_dispatch_exempt_planning_shas(
        uncovered_planning_shas,
        frozenset(dag_shas),
        bookkeeping_set,
        planning_set,
        cache,
        trail_paths,
        repo_root,
    )


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
    degrade toward "leg (b) unavailable", never crash the gate).

    Shares plan C4's per-close touched-paths cache via `_TOUCHED_PATHS_
    CACHE` — see `_resolve_dag_candidates`'s docstring for why a ContextVar,
    not an added parameter."""
    cache = _TOUCHED_PATHS_CACHE.get()
    if cache is None:
        cache = {}
    resolved = _resolve_dag_candidates(from_handoff)
    if resolved is None:
        return []
    repo_root, candidates = resolved
    touched_by_sha, _note = _commit_touched_paths(candidates, repo_root, cache)
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
            **no_console_creationflags(),
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
            **no_console_creationflags(),
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
                **no_console_creationflags(),
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
            **no_console_creationflags(),
        )
        return proc.returncode, proc.stdout.rstrip("\n"), proc.stderr
    except OSError as exc:
        return 1, "", str(exc)


def _resolve_foreign_session_shas(sha_range: str, session_id: str | None) -> frozenset[str]:
    """The `narrow_foreign_shas` callable `directives_review._record_
    membership_shas` injects for session/chain-scoped records (review-
    integrator finding W2).

    A2 (2026-08-08, N+1 git-spawn-class/amplification-gate plan): thin
    wrapper over `chain_attribution.unattributed_foreign_shas` (P2) —
    migrated onto that module's STRICTER, fail-closed posture rather than
    `session_attribution.trailer_foreign_shas` (P1) or
    `bulk_trailer_session_map`, both of which are EXCLUSION-based and would
    reintroduce the membership bypass this resolver was hand-written to
    close (a merge commit, or an untrailered commit, being creditable to
    ANY spanning record regardless of session). See
    `coordinator_core/chain_attribution.py`'s module and function
    docstrings for the full posture contract this delegates to: merges,
    ambiguous multi-valued trailers, and untrailered/non-grep-attributed
    commits are all foreign; only a commit whose trailer affirmatively
    equals `session_id`, or an untrailered commit the same-window grep leg
    (`--no-merges --grep=^Session-Id: <sid>$`) attributes to `session_id`,
    is not.

    Same signature and call shape as before this migration — callers
    (`_record_membership_shas`, `_partition_foreign_uncovered_shas`) are
    unaffected. `_FOREIGN_SHAS_CACHE` and `_git_run_for_session_attribution`
    are passed straight through as the `cache`/`run` DI seams
    `unattributed_foreign_shas` expects, so this file's Windows subprocess
    conventions (`CREATE_NO_WINDOW`, no shell) and existing test
    monkeypatch hooks keep working unchanged.

    Raises (propagates `session_attribution.GitLogFailed` — re-exported
    unchanged by `chain_attribution` — or a plain exception if the repo
    root is unresolvable) rather than degrading to an empty result on
    failure — `_record_membership_shas`'s own try/except around this
    callable already fails the record CLOSED on any exception, matching
    `coverage.build_reviewed_set`'s own fail-closed
    `_ForeignSessionLookupError` handling for this exact narrowing. Isolated
    for test monkeypatching."""
    repo_root = _resolve_repo_root()
    if not repo_root:
        raise RuntimeError("_resolve_foreign_session_shas: repo root unresolvable")
    return chain_attribution.unattributed_foreign_shas(
        sha_range,
        session_id,
        repo_root,
        _FOREIGN_SHAS_CACHE,
        _git_run_for_session_attribution,
    )


#: Module-level memo for `_resolve_vouched_shas`, keyed on `session_id`
#: (session-independent lookups are cheap, but memoized here anyway so a
#: repeat call for the same key, common across a chain's many trail records,
#: doesn't re-scan the waiver directory and re-resolve the closing session
#: id per record).
_VOUCHED_SHAS_CACHE: dict = {}


def _resolve_vouched_shas(session_id: str | None) -> frozenset[str]:
    """The `vouched_shas` callable `directives_review._record_membership_
    shas` injects. Formerly the gate-minted chain-ancestry waiver store
    (`coverage._chain_ancestry_waived_shas`, scoped to `session_id`) — that
    mechanism is removed outright (state/kill-ledger.md K-005, 2026-08-16 —
    "waiver system dies"). No waiver source remains, so this resolver
    always returns empty; the foreign-session strip in
    `_record_membership_shas` now proceeds unconditionally. Kept as a named
    seam (isolated for test monkeypatching) rather than inlined."""
    return frozenset()


#: Module-level memo for `_resolve_chain_attribution_window`, keyed on
#: `repo_root` — a chain-terminal close resolves the window exactly once
#: per process (see that function's own docstring). `False` (not present
#: in the dict) means "not yet attempted"; a present entry of `None` means
#: "attempted and failed" (merge-base unresolvable, or the bulk walk
#: raised) — memoized too, so a failing resolution is not retried once per
#: surviving trail record.
_CHAIN_ATTRIBUTION_WINDOW_CACHE: dict[str, "ChainAttributionWindow | None"] = {}


def _git_run_no_optional_locks(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """`chain_attribution.GitRunner`-shaped wrapper that inserts
    `--no-optional-locks` immediately after `git` for every read-only
    invocation this resolver makes (docs/wiki/machine-load-norm.md) —
    this fleet runs dozens of concurrent sessions against the same
    working tree, and an unguarded `git log`/`git merge-base` can block on
    (or be blocked by) a peer's index lock for no reason, since neither
    call here ever mutates the index. Delegates to
    `_git_run_for_session_attribution` for the actual Windows-safe
    subprocess shape (`CREATE_NO_WINDOW`, no shell, never raises)."""
    if cmd and cmd[0] == "git":
        cmd = [cmd[0], "--no-optional-locks", *cmd[1:]]
    return _git_run_for_session_attribution(cmd, cwd)


def _resolve_merge_base_head_range(repo_root: str) -> str | None:
    """`<merge-base(origin/main, HEAD)>..HEAD` — the same default range
    `coverage.run_coverage_gate`'s flat-mode fallback resolves (see that
    module's own `git merge-base origin/main HEAD` call), reused here as
    the ONE covering range C6a's `ChainAttributionWindow` is built over.
    Returns `None` on any git failure or empty merge-base output — never a
    partial/best-guess range; a caller failing to resolve this must fall
    back to the pre-window per-record path, never synthesize a narrower
    range that could fail to cover a sha in play."""
    rc, out, _err = _git_run_no_optional_locks(
        ["git", "merge-base", "origin/main", "HEAD"], repo_root,
    )
    if rc != 0:
        return None
    merge_base = out.strip()
    if not merge_base:
        return None
    return f"{merge_base}..HEAD"


def _resolve_chain_attribution_window(repo_root: str | None) -> "ChainAttributionWindow | None":
    """C6b wiring (docs/plans/2026-08-15-composition-invocation-budgets.md):
    resolves ONE `ChainAttributionWindow` over `merge-base(origin/main,
    HEAD)..HEAD` for this process, then hands it to
    `chain_partition_uncovered_shas` as `chain_window` at the PARTITION-
    MANDATORY call site in `cmd_brightline_gate`.

    WINDOW-COVERAGE PRECONDITION (see `ChainAttributionWindow`'s own
    docstring and `chain_attribution.foreign_shas_from_window`'s): this
    function's `commit_map` is built from ONE
    `chain_attribution.bulk_commit_attribution_map` walk over exactly the
    range `_resolve_merge_base_head_range` resolves — the SAME range
    `grep_attributed_for_session` (a closure over
    `chain_attribution.bulk_grep_attributed_shas`) is scoped to. Neither
    leg is widened, truncated, or lazily populated relative to the other:
    a sha this window's `commit_map` does not contain is a sha outside
    `merge-base..HEAD` entirely, never a sha inside that range this
    resolver merely chose not to fetch. `_record_membership_shas` (the
    window's only consumer) already treats a sha absent from `commit_map`
    as "the window fast path does not apply to this record" and falls
    back to the per-record `narrow_foreign_shas` spawn rather than reading
    absence as foreign — this resolver's job is only to make that fallback
    the exception, not the rule, for an ordinary close.

    Returns `None` (never raises) on an unresolvable `repo_root`, an
    unresolvable merge-base, or any exception from the underlying bulk
    walk (`session_attribution.GitLogFailed` on a non-zero `git log`, or
    any other failure) — every caller already treats `chain_window=None`
    as byte-identical to the pre-C6a/C6b behaviour (a per-record spawn
    fallback), so a failed resolution here degrades performance, never
    correctness.

    Memoized per `repo_root` in `_CHAIN_ATTRIBUTION_WINDOW_CACHE` for the
    lifetime of this process — one resolution (two git spawns: the
    merge-base lookup plus the bulk `git log` walk) per close, not one per
    surviving trail record, mirroring every other resolver cache in this
    file."""
    key = repo_root or ""
    if key in _CHAIN_ATTRIBUTION_WINDOW_CACHE:
        return _CHAIN_ATTRIBUTION_WINDOW_CACHE[key]
    result: "ChainAttributionWindow | None" = None
    if repo_root:
        sha_range = _resolve_merge_base_head_range(repo_root)
        if sha_range:
            try:
                commit_map = chain_attribution.bulk_commit_attribution_map(
                    sha_range, repo_root, _git_run_no_optional_locks,
                )
            except Exception:  # noqa: BLE001 - a broken window walk must fall back, never crash the gate
                commit_map = None
            if commit_map is not None:
                def _grep_attributed_for_session(
                    session_id: str | None,
                    _range: str = sha_range,
                    _repo_root: str = repo_root,
                ) -> frozenset[str]:
                    return chain_attribution.bulk_grep_attributed_shas(
                        _range, session_id, _repo_root, _git_run_no_optional_locks,
                    )

                result = ChainAttributionWindow(
                    commit_map=commit_map,
                    grep_attributed_for_session=_grep_attributed_for_session,
                )
    _CHAIN_ATTRIBUTION_WINDOW_CACHE[key] = result
    return result


def _clear_process_caches() -> None:
    """Test-only reset hook for every module-level, never-cleared-in-
    production process cache this file owns (`_RANGE_SHAS_CACHE`,
    `_DAG_SHAS_CACHE`, `_FOREIGN_SHAS_CACHE`, `_GREP_ATTRIBUTED_SHAS_CACHE`,
    `_VOUCHED_SHAS_CACHE`, `_CHAIN_ATTRIBUTION_WINDOW_CACHE`) —
    review-integrator finding N2. Each is a correct, intentional design for
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
    _CHAIN_ATTRIBUTION_WINDOW_CACHE.clear()


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
            **no_console_creationflags(),
        )
    except OSError:
        return list(shas)
    if proc.returncode != 0:
        return list(shas)
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return lines or list(shas)


def _classify_uncovered_shas(
    shas: list[str],
    repo_root: str | None,
) -> tuple[list[str], list[str]]:
    """Split `shas` into `(planning, code)`, in input order, using the SAME
    classifier the gate itself already applies to decide `chain_code_shas`
    membership (`coverage._classify_bookkeeping_shas`) — never a second
    classifier, and this never changes `chain_code_shas` membership or the
    denominator/verdict, only how the HALT message labels each entry
    (2026-08-07 audit, `state/audits/2026-08-07-wsc-chain-gate-counts-doc-
    only-commits.md` Q1: PLANNING commits stay IN the code-obligation set
    by design — AC9, "a planning artifact still owes a review, just not a
    code review" — the gate's own message calling them "chain code
    commit(s)" was the lie this splits apart).

    `repo_root=None`, or an empty `shas`, degrades to `([], list(shas))` —
    every sha reads as unclassified CODE, the message's prior behavior,
    rather than guessing at a classification this diagnostic couldn't
    resolve.

    Shares plan C4's per-close touched-paths cache via `_TOUCHED_PATHS_
    CACHE` — see `_resolve_dag_candidates`'s docstring for why a ContextVar,
    not an added parameter."""
    if not repo_root or not shas:
        return [], list(shas)
    cache = _TOUCHED_PATHS_CACHE.get()
    if cache is None:
        cache = {}
    _exhaust_set, planning_set, _note = _classify_bookkeeping_shas(shas, repo_root, cache)
    planning = [sha for sha in shas if sha in planning_set]
    code = [sha for sha in shas if sha not in planning_set]
    return planning, code


def _format_capped_overflow_note(total: int, cap: int) -> str:
    """AC12 (plan C3) — each uncovered-set listing's existing `cap = 10`
    truncates silently ("+N more" with no count context). Disclose the cap
    explicitly rather than leaving the reader to guess how many were hidden
    from what."""
    return f"    +{total - cap} more (only the first {cap} of {total} shown, cap={cap})"


def _group_code_shas_by_directory(
    shas: list[str], repo_root: str | None,
) -> tuple[dict[str, list[str]] | None, bool]:
    """AC4 (plan C3) — a suggested directory/subsystem grouping of `shas`
    (the already-capped `code_shas_only` slice `cmd_brightline_gate` is
    about to print), derived by the runner itself: the gate's only channel
    to this process is one regex-anchored stdout line carrying five
    integers, no file list, so the grouping cannot be carried on that line
    and must be computed here (CROSS-PROCESS SEAM CONSTRAINT). One batched
    `git show --numstat` spawn over the capped set — the same shape as the
    existing `_describe_uncovered_shas` batched `git log --no-walk` call.

    A touched path `_is_prose_bearing_path` classifies as prose (`.md`/
    `.yaml`/`.yml`) is excluded from the grouping signal — imported from the
    gate rather than re-derived, per the HARD REQUIREMENT that this file
    never author a second, independent code-vs-prose classifier.

    Groups genuinely spanning two top-level directories are NOT forced
    disjoint — a commit legitimately appears in both buckets when it
    touches both.

    Returns `(groups, undetermined)`. `groups` is `None` — never a
    one-item grouping — when the axis would not help: an empty input,
    fewer than two directories found, or the check could not run at all.
    `undetermined=True` marks the latter case (unresolved `repo_root`, a
    spawn failure, or a non-zero `git show` exit) — the check never ran,
    so the caller must not render this as "checked, they don't separate."
    `undetermined=False` with `groups=None` means the check ran and found
    fewer than two directories. A bad suggestion is worse than none."""
    if not shas:
        return None, False
    if not repo_root:
        return None, True
    try:
        proc = subprocess.run(
            ["git", "show", "--numstat", "--format=%H", *shas],
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
            **no_console_creationflags(),
        )
    except OSError:
        return None, True
    if proc.returncode != 0:
        return None, True
    groups: dict[str, list[str]] = {}
    current_sha: str | None = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"[0-9a-f]{40}", line):
            current_sha = line
            continue
        if current_sha is None:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        _added, _deleted, path = parts
        if _is_prose_bearing_path(path):
            continue
        path = _resolve_numstat_row_path(path)
        top_dir = path.split("/", 1)[0] if "/" in path else "(root)"
        bucket = groups.setdefault(top_dir, [])
        short_sha = current_sha[:7]
        if short_sha not in bucket:
            bucket.append(short_sha)
    if len(groups) < 2:
        return None, False
    return groups, False


def _basis_weighable_clause(fields: dict) -> str:
    """AC6 (plan C3) — a human-weighable clause APPENDED to (never
    replacing) the gate's own machine `basis` string: names WHICH oracle arm
    drove `reviewers_required`, not just the raw metric triple the
    BRIGHTLINE stdout line already carries. Must contain no `"` character —
    the persisted record's `basis` field is a bare string, and a caller
    parsing it as a delimited value would terminate on the first one."""
    oracles = {
        "plan_oracle": int(fields.get("plan_oracle") or 0),
        "chain_oracle": int(fields.get("chain_oracle") or 0),
        "session_oracle": int(fields.get("session_oracle") or 0),
    }
    driver = max(oracles, key=oracles.get)
    return (
        f"reviewers_required={fields.get('reviewers_required')} driven by "
        f"{driver}={oracles[driver]} (plan={oracles['plan_oracle']} "
        f"chain={oracles['chain_oracle']} session={oracles['session_oracle']})"
    )


def _resolve_broadly_reviewed_shas(
    trail_records: list[dict],
    chain_code_shas: frozenset[str] | list[str],
    chain_dag_shas: list[str],
    chain_planning_shas: list[str],
) -> frozenset[str]:
    """AC7 (plan C4) — an aiming aid, never a discount (PM ruling: prior
    review does not reduce what the closing EM owes). Re-runs the same
    verdict-consuming seam `chain_partition_uncovered_shas` uses for the
    displayed (narrow) uncovered set, a second time with
    `narrow_foreign_shas`/`vouched_shas` omitted — the broad membership
    test, unrestricted by THIS chain's foreign-session/vouching scope
    (`directives_review._record_membership_shas`). A sha this returns was
    NOT dropped from the narrow uncovered set here: it carries a real,
    non-pending/non-waived review-trail verdict recorded somewhere, just
    not one this chain's narrower rule credits toward discharge — exactly
    the case an EM benefits from seeing named. Doctrine:
    docs/wiki/review-scale.md — "consume verdicts, don't re-derive them";
    this reuses the existing seam rather than writing a second, independent
    coverage classifier.

    AC3 (plan C3) — `chain_code_shas` is deliberately the CALLER's already-
    capped, already-displayed sha set (<=30: 3 buckets x cap 10), not the
    full chain code-obligation set. `chain_partition_uncovered_shas` ->
    `_collect_discharging_range_shas` short-circuits its trail-record walk
    the moment `covered` names every entry of the sha set it was asked
    about — that ceiling is what this narrowing shrinks, bounding the
    number of records (and their `resolve_range_shas` git spawns) this
    walk pays for. Coverage credit stays capped at the queried set
    (`_record_membership_shas`'s contract), so narrowing never changes the
    answer for a sha actually in the query — it only stops crediting shas
    nobody asked about, which were never displayed anyway.

    Never read by `chain_partition_uncovered_shas`, `discharged`, or the
    verdict — this is a second, standalone call whose return value only
    feeds `_annotate_already_reviewed`'s rendering below. Best-effort:
    degrades to an empty set (no markers) on any failure rather than
    raising, mirroring `_describe_uncovered_shas`'s own fail-safe
    posture — this is a diagnostic amenity, never load-bearing."""
    try:
        broad_uncovered = chain_partition_uncovered_shas(
            trail_records, chain_code_shas, chain_dag_shas, _resolve_range_shas,
            narrow_foreign_shas=None,
            vouched_shas=None,
            chain_planning_shas=chain_planning_shas,
        )
    except Exception:
        return frozenset()
    return frozenset(chain_code_shas) - frozenset(broad_uncovered)


def _annotate_already_reviewed(lines: list[str], broadly_reviewed: frozenset[str]) -> list[str]:
    """AC7/AC8 (plan C4) — appends a terse, register-conformant marker to
    each `_describe_uncovered_shas` line (`<short-sha> <subject>`) whose
    leading short sha prefixes a full sha in `broadly_reviewed`. Text only:
    changes no list membership, no ordering, no count — the caller's
    `len()`s and downstream `reviewers_required`/verdict are computed
    before this function ever runs."""
    if not broadly_reviewed:
        return lines
    annotated = []
    for line in lines:
        short_sha = line.split(" ", 1)[0]
        if any(full.startswith(short_sha) for full in broadly_reviewed):
            annotated.append(f"{line} [already reviewed elsewhere — not credited to this chain]")
        else:
            annotated.append(line)
    return annotated


def _resolve_uncovered_commit_attribution_window(
    shas: list[str], repo_root: str,
) -> dict | None:
    """A3 (2026-08-08, N+1 git-spawn-class plan): the trailer signal for
    EXACTLY `shas`, in ONE `git log --no-walk` spawn — `--no-walk` is
    load-bearing: `git log sha1 sha2 ...` WITHOUT it walks each named
    commit's full ancestry (every sha's own history, not just the named
    commits), turning a bounded window into an unbounded one and
    reintroducing the very N+1-adjacent blowup this chunk exists to avoid.
    `chain_attribution.bulk_commit_attribution_map` cannot be reused
    directly here — its `range_str` parameter is ONE `git log` argv token,
    and `shas` is an arbitrary, generally discontiguous set with no single
    range expression that provably covers exactly (and only) its members;
    `--no-walk sha1 sha2 ... shaN` is that single-spawn cover.

    Reuses `chain_attribution`'s own record framing/parsing contract
    (`_LOG_FORMAT`, `_parse_log_records`) rather than re-deriving the
    `\\x1e`/`\\x1f` separators and multi-valued-trailer handling a second
    time — those are exactly the shape `bulk_commit_attribution_map`
    already gets right; this function only differs in accepting N explicit
    revs instead of one range expression, so the per-record value
    extraction below (parents -> `is_merge`, trailer lines ->
    `trailer_session_id`/`trailer_ambiguous`) mirrors that function's own
    body verbatim.

    Returns `None` on any git failure (non-zero rc, `OSError`) — the
    caller (`_partition_foreign_uncovered_shas`) treats `None` exactly as
    it treats an unresolvable repo root: whole-batch degrade to `own`,
    never a false foreign claim from a window this function could not
    positively build. A sha named in `shas` but genuinely absent from
    `--no-walk`'s output (e.g. a mistyped/garbage sha) is simply absent
    from the returned dict — the caller's own "every classified sha must
    be present in the window" check catches that, this function does not
    special-case it."""
    if not shas:
        return {}
    rc, out, _err = _git_run_for_session_attribution(
        ["git", "log", "--no-walk", f"--format={chain_attribution._LOG_FORMAT}", *shas],
        repo_root,
    )
    if rc != 0:
        return None
    window: dict[str, chain_attribution.CommitAttribution] = {}
    for sha, parents, trailer in chain_attribution._parse_log_records(out):
        parent_shas = [p for p in parents.split(" ") if p]
        is_merge = len(parent_shas) > 1
        trailer_values = [v for v in trailer.split("\n") if v.strip()]
        if not trailer_values:
            trailer_session_id: str | None = None
            ambiguous = False
        elif len(trailer_values) == 1:
            trailer_session_id = trailer_values[0].strip()
            ambiguous = False
        else:
            trailer_session_id = trailer_values[0].strip()
            ambiguous = True
        window[sha] = chain_attribution.CommitAttribution(
            sha=sha,
            trailer_session_id=trailer_session_id,
            is_merge=is_merge,
            trailer_ambiguous=ambiguous,
        )
    return window


def _resolve_uncovered_grep_attribution(
    shas: list[str], session_id: str, repo_root: str,
) -> frozenset[str] | None:
    """A3: the grep signal for EXACTLY `shas`, in ONE `git log --no-walk
    --no-merges` spawn — mirrors `chain_attribution.bulk_grep_attributed_
    shas`'s `--no-merges` posture (load-bearing there, and here: a merge
    commit's own message matching the grep must never be grep-attributed,
    since it is already unconditionally foreign via `is_merge` and
    `foreign_shas_from_window`'s merge-is-foreign rule would otherwise be
    bypassed) and its `_UUID_RE` shape-validation (an unvalidated
    `session_id` — an arbitrary on-disk record field — interpolated raw
    into `--grep=` could collapse the pattern to match every commit).
    `--no-walk` is load-bearing for the identical reason it is in
    `_resolve_uncovered_commit_attribution_window`: without it this walks
    each sha's ancestry, not just the named commits.

    Callers only reach this when at least one sha in the window needs the
    grep signal at all (an untrailered, non-merge, non-ambiguous commit —
    see `_partition_foreign_uncovered_shas`'s `needs_grep` guard); a window
    fully resolved by trailers alone skips this spawn entirely, which is
    the 2N-not-N fix the plan names.

    Returns the empty frozenset immediately, without spawning, on a
    malformed `session_id` — fail-closed, matching `bulk_grep_attributed_
    shas`. Returns `None` on any git failure — distinct from the empty
    frozenset, so the caller can tell "confirmed nothing" from "could not
    ask" and whole-batch degrade on the latter."""
    if not _UUID_RE.match(session_id):
        return frozenset()
    rc, out, _err = _git_run_for_session_attribution(
        [
            "git", "log", "--no-walk", "--no-merges",
            f"--grep=^Session-Id: {session_id}$",
            "--format=%H",
            *shas,
        ],
        repo_root,
    )
    if rc != 0:
        return None
    return frozenset(line.strip() for line in out.splitlines() if line.strip())


def _partition_foreign_uncovered_shas(
    shas: list[str], session_id: str | None,
) -> tuple[list[str], list[str]]:
    """Split `shas` into `(foreign, own)`, in input order — the
    "unrecordable-by-construction" distinction (`state/audits/2026-08-07-
    wsc-chain-gate-counts-doc-only-commits.md` Q2/Q5): a FOREIGN commit's
    coverage can never be discharged by an ordinary review-trail write,
    because `coordinator_core.ops.review_trail_write._guard_foreign_
    session_range` refuses any range naming a commit attributed to
    another session, while the chain-terminal discharge path
    (`directives_review._record_membership_shas`) narrows a record by the
    WRITING session's id — so a record correctly naming a predecessor's
    commit is emptied to `set()` and credits nothing. Both mechanisms are
    individually correct; jointly they make a foreign uncovered commit
    unsatisfiable by any write this session could make.

    A3 (2026-08-08, N+1 git-spawn-class plan): answers from ONE window
    covering exactly `shas` (`_resolve_uncovered_commit_attribution_
    window`, one spawn) plus, ONLY when at least one sha in that window is
    untrailered/non-merge/non-ambiguous and therefore needs the grep
    signal at all, a second window-scoped grep spawn
    (`_resolve_uncovered_grep_attribution`) — replacing the prior per-sha
    `X^..X` loop (2 spawns * N shas, no dedup possible: every sha yields a
    distinct range so the module-level memo never hits). NOT sized as the
    N+1 win here (measured 1.04s/22 spawns on real 11-sha input, not the
    39.7s figure that belongs to a different call site); this migration is
    correctness-bearing — the P1/P2 posture (`chain_attribution`'s
    fail-closed treatment of merges/ambiguous trailers, see that module's
    docstring), and the window-coverage contract below.

    `session_id=None`, an empty `shas`, an unresolvable repo root, a
    window-build failure, a sha `shas` names but the window walk did not
    return (absence must never be read as "untrailered" — a window that
    does not provably cover every classified sha is not trusted at all),
    or a grep-leg failure when the grep leg was actually needed: ALL
    degrade the WHOLE BATCH to `own`, never per-sha. This is a deliberate
    change from the prior per-sha degrade-to-own posture — this diagnostic
    must never assert ANY commit is foreign from a partially-failed
    resolution; silence beats a false foreign claim across the entire
    batch, not just the one sha that happened to fail."""
    if not session_id or not shas:
        return [], list(shas)
    repo_root = _resolve_repo_root()
    if not repo_root:
        return [], list(shas)
    try:
        window = _resolve_uncovered_commit_attribution_window(shas, repo_root)
    except Exception:
        window = None
    if window is None or any(sha not in window for sha in shas):
        return [], list(shas)
    needs_grep = any(
        not window[sha].is_merge
        and not window[sha].trailer_ambiguous
        and window[sha].trailer_session_id is None
        for sha in shas
    )
    grep_attributed: frozenset[str] = frozenset()
    if needs_grep:
        try:
            grep_result = _resolve_uncovered_grep_attribution(shas, session_id, repo_root)
        except Exception:
            grep_result = None
        if grep_result is None:
            return [], list(shas)
        grep_attributed = grep_result
    foreign_set = chain_attribution.foreign_shas_from_window(
        shas, session_id, window, grep_attributed,
    )
    foreign = [sha for sha in shas if sha in foreign_set]
    own = [sha for sha in shas if sha not in foreign_set]
    return foreign, own


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
        **no_console_creationflags(),  # popup-safe-env-suppressed
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
    if args.reviewer_evidence:
        argv += ["--reviewer-evidence", args.reviewer_evidence]

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

# tier= field removed from the frozen line (state/kill-ledger.md K-004,
# 2026-08-16, Verdict A — "waiver system dies" sibling cut, the tier branch).
_BRIGHTLINE_RE = re.compile(
    r"^BRIGHTLINE reviewers_required=(?P<reviewers_required>\d+) "
    r"reviewers_suggested=(?P<reviewers_suggested>\d+) "
    r"reviewers_low=(?P<reviewers_low>\d+) "
    r"plan_oracle=(?P<plan_oracle>\d+) "
    r"chain_oracle=(?P<chain_oracle>\d+) "
    r"session_oracle=(?P<session_oracle>\d+) "
    r"verdict=(?P<verdict>single-reviewer-ok|PARTITION-MANDATORY) "
    r'basis="(?P<basis>[^"]*)"$'
)


#: op_latency `op=` label for the whole `--from-handoff` chain (K-004,
#: 2026-08-16 — "No stage of it is instrumented ... one timing span in
#: cmd_brightline_gate makes this decidable"). Deliberately a single span
#: over the subprocess boundary — `d-run-chain-plan-brightline-gate` →
#: this function → `review-brightline-gate.py` → `_from_handoff_main` →
#: `_compute_chain_oracle` → `coverage.py::_derive_dag_chain_set` — rather
#: than four separate op rows, since the child process is opaque to this
#: caller and the ONE number K-004 needs is end-to-end wall-clock against
#: DISPATCH_TIMEOUT_SECS, not a stage breakdown. Distinct from `coverage.
#: gate`'s op rows (K-004 Verdict B: "a DIFFERENT handler ... deliberately
#: not substituted as a proxy") — this label must never be conflated with
#: that one when reading op-latency.jsonl.
_OP_LATENCY_LABEL = "review_brightline_gate.from_handoff"


def _run_review_brightline_gate(argv: list[str]) -> tuple[int, str, str]:
    """Invoke the sibling review-brightline-gate.py in --from-handoff mode and
    return (returncode, stdout, stderr). Isolated for test monkeypatching.

    Records one op_latency span (op=`_OP_LATENCY_LABEL`) over the whole
    subprocess call — see that constant's docstring for why this is the
    single instrumentation point for the K-004 `chain_oracle` walk. Same
    fail-open contract as `coordinator_core.telemetry.op_latency` itself:
    a telemetry failure here must never fail the gate, so both the started
    and completed recordings are wrapped in their own swallow-all
    try/except, independent of the subprocess call they bracket."""
    cmd = [
        sys.executable,
        os.path.join(_SCRIPT_DIR, "review-brightline-gate.py"),
        "--from-handoff",
        *argv,
    ]

    import time as _time

    from coordinator_core.telemetry.op_latency import (
        new_correlation_id,
        record_op_latency,
        record_op_started,
    )

    repo_root_str = _resolve_repo_root()
    repo_root = Path(repo_root_str) if repo_root_str else None

    t_start = _time.time()
    perf_start = _time.perf_counter()
    corr_id = new_correlation_id()
    try:
        record_op_started(
            op=_OP_LATENCY_LABEL, t_start=t_start, corr_id=corr_id, repo_root=repo_root,
        )
    except Exception:
        pass

    outcome = "ok"
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            **no_console_creationflags(),  # popup-safe-env-suppressed
        )
        if proc.returncode != 0:
            outcome = "error"
        return proc.returncode, proc.stdout, proc.stderr
    except BaseException:
        outcome = "error"
        raise
    finally:
        elapsed_ms = (_time.perf_counter() - perf_start) * 1000.0
        try:
            record_op_latency(
                op=_OP_LATENCY_LABEL,
                t_start=t_start,
                elapsed_ms=elapsed_ms,
                outcome=outcome,
                repo_root=repo_root,
                corr_id=corr_id,
            )
        except Exception:
            pass


def _parse_brightline_line(stdout: str) -> dict | None:
    """Return the last BRIGHTLINE line's fields as a dict, or None if the gate
    did not emit one (transport failure, malformed compute — treat as a
    fail-loud infra error, never a silent pass)."""
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
    env vars, then an epoch fallback; the `.current-session-id` sentinel
    tier was removed, KS-3/KS-4, 2026-08-07), so the verdict record this
    subcommand writes is keyed by the
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
    chain_slices: list[dict] | None = None,
) -> None:
    """Write the just-computed brightline verdict to the persistence seam
    (`chain_partition_verdict_store`) so the NEXT `wsc.brief()`/`wsc.apply()`
    call can read it without an EM re-typing `decisions["chain_partition_
    verdict"]` (root cause: cross-repo/inbox/2026-08-04-project-rag-em-
    brightline-partition-mandatory-does-not-halt.md, "mechanism 2").

    `chain_slices` (AC4, Seam 2/3): C7's slate, already decorated by the
    caller. `None` (the default) omits the key entirely — `write_verdict_
    record`'s own contract (absent means "not computed for this call",
    never confused with a resolved-and-empty `[]`). `cmd_brightline_gate`
    calls this function twice for EVERY PARTITION-MANDATORY verdict that
    reaches the point of computing an owed set — whether that set turns
    out non-empty (undischarged) or empty (discharged/vacuous): once here,
    unconditionally and BEFORE the owed-set is known (so every early-return
    path still gets a persisted record exactly as before this parameter
    existed), and again once the slate is resolved,
    passing `chain_slices` — a non-empty list in the undischarged case, or
    `[]` in the discharged case — either way the second call overwrites
    the same on-disk record (same session-keyed path) with `chain_slices`
    added. Both calls target the SAME record; this is not two competing
    verdicts, only two writes of one.

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
            chain_slices=chain_slices,
        )
    except OSError as exc:
        print(
            f"WARNING: could not persist brightline verdict to disk: {exc}. "
            "decisions[\"chain_partition_verdict\"] remains the only path "
            "forward this run.",
            file=sys.stderr,
        )


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

    basis = fields["basis"]

    # AC6 (plan C3) — append a human-weighable clause to the machine basis
    # BEFORE persistence, so the appended text flows into the persisted
    # record and `wsc.brief()`/`wsc.apply()` read back. APPENDED, never a
    # replacement: the existing metric-triple substring stays intact and is
    # still the first thing in the string.
    # `_basis_weighable_clause` always returns a non-empty string — no
    # guard needed here; a conditional would read as if the clause could
    # legitimately be absent, which it can't (Review: code-reviewer).
    weighable_clause = _basis_weighable_clause(fields)
    basis = f"{basis} {weighable_clause}".strip()
    fields["basis"] = basis

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

    # tier=A hard-stop branch (declared-but-unwalked-repo halt, with its
    # COORDINATOR_OVERRIDE_BRIGHTLINE/autonomous-sentinel escape hatch and
    # the state/review-trail/findings/-name-match lift) is REMOVED
    # (state/kill-ledger.md K-004, 2026-08-16, Verdict A — measured across
    # 151 records: tier=A never fired). See
    # docs/wiki/cost-budgets-and-the-kill-disposition.md.

    # C13 (docs/plans/2026-08-05-coverage-gate-planning-artifact-class.md,
    # AC20/AC21): the ONE narrow refusal carved out of the "never
    # hard-stops" communicate-only posture below. Checked BEFORE the
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
        # 2026-08-07 through 2026-08-15: this branch folded a chain-ancestry
        # waiver mint (`_run_review_coverage_gate(..., mint_chain_waivers=
        # True)`) in here so `brightline-gate` was self-sufficient without
        # requiring `coverage-gate` to have run first. Removed outright
        # (state/kill-ledger.md K-005, 2026-08-16 — "waiver system dies"):
        # the whole chain-ancestry-waiver mechanism, including the mint this
        # call fed, is gone. See docs/wiki/cost-budgets-and-the-kill-
        # disposition.md.
        dag_resolved = _derive_dag_shas(args.from_handoff)
        trail_records = _load_trail_records()
        # Per-run touched-paths cache (plan C4, docs/plans/2026-08-15-
        # composition-invocation-budgets.md): reset the shared `_TOUCHED_
        # PATHS_CACHE` ContextVar to a fresh dict for THIS close, so the
        # four sibling resolvers below (`_resolve_chain_code_shas`,
        # `_resolve_chain_planning_shas`, `_resolve_chain_spec_dispatch_
        # exempt_shas`, `_classify_uncovered_shas`) share one `git log
        # --no-walk --name-only` batch per sha instead of one each. See
        # `_TOUCHED_PATHS_CACHE`'s own docstring for why a reset (not a
        # `with`/`finally` scope) is sufficient: the cache is a pure,
        # content-addressed sha->paths map, so it never needs explicit
        # teardown, and the reset here means it cannot outlive this close
        # in practice — the previous close's dict, if any, becomes
        # unreachable at this line. Never module-global: a ContextVar, not
        # a plain module attribute, and this tree carries ~16 concurrent
        # sessions, each its own process with its own ContextVar default.
        _reset_touched_paths_cache()
        chain_code_shas = _resolve_chain_code_shas(args.from_handoff)
        chain_dag_shas = _resolve_chain_dag_shas(args.from_handoff)
        dag_resolution_failed = dag_resolved is None
        chain_owes_no_code_review = not dag_resolution_failed and not chain_code_shas
        # Resolved once, reused by both the uncovered-shas computation
        # below and the execution-basis-report companion below it — same
        # `from_handoff` input, same repo state (Review: code-reviewer).
        chain_planning_shas = _resolve_chain_planning_shas(args.from_handoff)
        # C6b wiring (docs/plans/2026-08-15-composition-invocation-budgets.md):
        # the ONE `merge-base(origin/main, HEAD)..HEAD` window this close's
        # `narrow_foreign_shas` fan-out can answer from, in-memory, instead of
        # per surviving trail record. `chain_repo_root` is `dag_resolved`'s
        # own `repo_root` half (already resolved above, same process, same
        # cwd) — never re-derived. `None` (an unresolvable merge-base, or any
        # failure in the underlying bulk walk) degrades byte-identically to
        # every pre-C6a/C6b caller: `chain_partition_uncovered_shas` below
        # takes the per-record `narrow_foreign_shas` spawn path unchanged.
        chain_repo_root = dag_resolved[0] if dag_resolved is not None else _resolve_repo_root()
        chain_window = _resolve_chain_attribution_window(chain_repo_root)
        if chain_owes_no_code_review:
            uncovered: list[str] = []
            discharged = True
        else:
            uncovered = (
                chain_partition_uncovered_shas(
                    trail_records, chain_code_shas, chain_dag_shas, _resolve_range_shas,
                    narrow_foreign_shas=_resolve_foreign_session_shas,
                    vouched_shas=_resolve_vouched_shas,
                    chain_planning_shas=chain_planning_shas,
                    chain_window=chain_window,
                )
                if chain_code_shas and chain_dag_shas
                else []
            )
            # Conditional spec-dispatch PLANNING exemption (see
            # `_resolve_chain_spec_dispatch_exempt_shas`'s docstring) — the
            # live-path twin of `coverage.run_coverage_gate`'s own
            # exemption, which this HALT does not otherwise reach (it reads
            # `_resolve_chain_planning_shas`/`_classify_bookkeeping_shas`
            # directly, not `run_coverage_gate`'s result). Fully discharges
            # a qualifying sha — subtracted from `uncovered` itself, not
            # merely relabeled — because a genuine compensating code review
            # stands in for the plan review this HALT would otherwise
            # demand.
            spec_dispatch_exempt_shas, _spec_dispatch_exempt_reasons = (
                _resolve_chain_spec_dispatch_exempt_shas(
                    args.from_handoff,
                    [sha for sha in uncovered if sha in chain_planning_shas],
                )
            )
            if spec_dispatch_exempt_shas:
                uncovered = [
                    sha for sha in uncovered if sha not in spec_dispatch_exempt_shas
                ]
            discharged = bool(chain_code_shas) and bool(chain_dag_shas) and not uncovered
            if spec_dispatch_exempt_shas:
                # SPEC_DISPATCH_EXEMPT_REASON is the distinguishable token a
                # reader (or a test) greps to tell this apart from an
                # ordinary trail-record discharge or the still-owed
                # PLANNING label below.
                print(
                    "NOTE: "
                    f"{len(spec_dispatch_exempt_shas)} PLANNING commit(s) "
                    f"{SPEC_DISPATCH_EXEMPT_REASON} — discharged, not "
                    f"counted in UNCOVERED: {sorted(spec_dispatch_exempt_shas)!r}",
                    file=sys.stderr,
                )
        # Read-only narration companion (chunk C4b, docs/plans/2026-08-11-
        # review-trail-carries-execution-basis.md, AC4). Never read by
        # `discharged`/`uncovered` above or by any HALT/return-code decision
        # below — informational only, mirrors the same inputs the
        # `chain_partition_uncovered_shas` call above already assembled.
        # Wrapped defensively: `chain_partition_execution_basis_report` is a
        # C4 companion this call site did not author, so a malformed trail
        # record must degrade to omitting this line rather than take the
        # gate down.
        try:
            basis_report = chain_partition_execution_basis_report(
                trail_records, chain_code_shas, chain_dag_shas, _resolve_range_shas,
                narrow_foreign_shas=_resolve_foreign_session_shas,
                vouched_shas=_resolve_vouched_shas,
                chain_planning_shas=chain_planning_shas,
            )
        except Exception:
            basis_report = None
        if basis_report:
            _basis_total = sum(basis_report.values())
            if _basis_total:
                _basis_parts = ", ".join(
                    f"{basis_report.get(_label, 0)} {_label}"
                    for _label in ("executed", "read-only", EXECUTION_BASIS_NOT_RECORDED)
                )
                print(
                    f"EXECUTION-BASIS: chain discharged on {_basis_total} "
                    f"record(s): {_basis_parts}",
                    file=sys.stderr,
                )
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
            if chain_code_shas and chain_dag_shas:
                # 2026-08-07 rendering fix (state/audits/2026-08-07-wsc-
                # chain-gate-counts-doc-only-commits.md): a rendering-only
                # change — `uncovered`/`chain_code_shas` themselves, the
                # denominator below, and the verdict are untouched. Two
                # things this message used to get wrong: (1) it called
                # every entry a "chain code commit" when PLANNING commits
                # (docs/plans/, docs/research/, docs/problems/, state/plan-
                # sidecars/) stay in the obligation set by design but are
                # not code; (2) it stayed silent when an uncovered commit
                # is foreign to the closing session, which is frequently
                # uncovered BY CONSTRUCTION (Q2/Q5) rather than because no
                # one reviewed it.
                repo_root = _resolve_repo_root()
                planning_shas, code_shas_only = _classify_uncovered_shas(uncovered, repo_root)
                closing_session_id = _resolve_closing_session_id(repo_root) if repo_root else None
                foreign_shas, own_shas = _partition_foreign_uncovered_shas(
                    uncovered, closing_session_id,
                )
                # AC4/Seam 2/3 — the recordable partition on the SAME
                # evidence source the write guard consults
                # (`_resolve_vouched_shas`), computed ONCE here and reused
                # by both `build_chain_slices` below and the waived/
                # unwaived narration further down (never re-derived a
                # second time — the defect class this plan exists to
                # stop). `vouched` is only resolved when there is a
                # foreign sha to test it against; an empty `foreign_shas`
                # needs no waiver lookup at all.
                vouched = _resolve_vouched_shas(closing_session_id) if foreign_shas else frozenset()
                waived_foreign = [s for s in foreign_shas if s in vouched]
                unwaived_foreign = [s for s in foreign_shas if s not in vouched]
                recordable_shas = frozenset(own_shas) | frozenset(waived_foreign)
                # AC7 (plan C4) / AC3 (plan C3) — an aiming aid only: which
                # of the shas about to be listed below already carry a
                # discharging review-trail verdict recorded outside this
                # chain's narrower (foreign/vouched-scoped) credit rule.
                # Computed once, read-only, and never fed back into
                # `uncovered`, `discharged`, `code_shas_only`, or any other
                # count above. Narrowed to the <=30 shas the three buckets
                # below actually display (cap=10 x 3) — NOT the full
                # `chain_code_shas` — because `_resolve_broadly_reviewed_
                # shas`'s own short-circuit
                # (`_collect_discharging_range_shas`'s `covered >=
                # chain_code_sha_set` break) fires on the SIZE OF THE QUERY
                # SET, so a smaller query set here directly bounds the
                # number of trail records (and their `resolve_range_shas`
                # git spawns) this walk pays for. Coverage credit is capped
                # at the queried set (`_record_membership_shas`'s "coverage
                # credit capped at chain_code_shas" contract), so narrowing
                # the query never changes the answer FOR A QUEUED SHA — it
                # only stops crediting shas nobody asked about, which are
                # never displayed anyway.
                cap = 10
                _displayed_shas = (
                    frozenset(code_shas_only[:cap])
                    | frozenset(planning_shas[:cap])
                    | frozenset(unwaived_foreign[:cap])
                )
                broadly_reviewed = _resolve_broadly_reviewed_shas(
                    trail_records, _displayed_shas, chain_dag_shas,
                    chain_planning_shas,
                )
                # No waiver source remains (state/kill-ledger.md K-005,
                # 2026-08-16 — "waiver system dies") — every chain_slices
                # entry's certifies_review is now unconditionally False.
                chain_slices = build_chain_slices(
                    uncovered,
                    recordable_shas=recordable_shas,
                    waiver_records={},
                )
                _persist_brightline_verdict(
                    args.from_handoff, args.git_range, fields, chain_slices=chain_slices,
                )
                if own_shas:
                    print(
                        "HALT: brightline verdict=PARTITION-MANDATORY and "
                        "the on-disk review-trail carries no verdict that "
                        "is both non-pending and non-waived for at least "
                        "one commit this session itself authored — the "
                        "review this chain mandates has not been run. "
                        "This session cannot reach a terminal stamp in "
                        "this state.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "NOTE: brightline verdict=PARTITION-MANDATORY and "
                        "the on-disk review-trail carries no verdict that "
                        "is both non-pending and non-waived, but every "
                        "uncovered commit is an ancestor/foreign-session "
                        "commit — none of them are recordable by this "
                        "session. This is a communicate-only gate here, "
                        "not a halt.",
                        file=sys.stderr,
                    )
                print(
                    f"UNCOVERED: {len(uncovered)} of {len(chain_code_shas)} "
                    "chain code commit(s) carry no discharging review-trail "
                    "verdict (no record's range names them):",
                    file=sys.stderr,
                )
                if code_shas_only:
                    print(f"  {len(code_shas_only)} code commit(s):", file=sys.stderr)
                    for line in _annotate_already_reviewed(
                        _describe_uncovered_shas(code_shas_only[:cap], repo_root),
                        broadly_reviewed,
                    ):
                        print(f"    {line}", file=sys.stderr)
                    if len(code_shas_only) > cap:
                        print(
                            _format_capped_overflow_note(len(code_shas_only), cap),
                            file=sys.stderr,
                        )
                    # AC4/AC5 (plan C3) — a suggested directory/subsystem
                    # split of THIS bucket only, grouped over the same
                    # (already-capped) slice just printed above — never
                    # spanning planning/waived/unwaived, and reusing `cap`
                    # rather than adding a second display limit. Advisory:
                    # the division is the EM's call, not a prescription.
                    reviewers_required = fields.get("reviewers_required")
                    split_groups, split_undetermined = _group_code_shas_by_directory(
                        code_shas_only[:cap], repo_root
                    )
                    if split_groups:
                        print(
                            f"  SUGGESTED SPLIT (advisory — division is your "
                            f"call, groups may overlap): {len(split_groups)} "
                            f"directory group(s), {reviewers_required} "
                            f"reviewer(s) required:",
                            file=sys.stderr,
                        )
                        for directory in sorted(split_groups):
                            print(
                                f"    {directory}/: "
                                f"{', '.join(split_groups[directory])}",
                                file=sys.stderr,
                            )
                    elif split_undetermined:
                        print(
                            f"  SUGGESTED SPLIT: could not determine — "
                            f"directory data unavailable; "
                            f"{reviewers_required} reviewer(s), undivided.",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"  SUGGESTED SPLIT: none — these commits do not "
                            f"separate along a directory axis; "
                            f"{reviewers_required} reviewer(s), undivided.",
                            file=sys.stderr,
                        )
                if planning_shas:
                    print(
                        f"  {len(planning_shas)} planning-artifact "
                        "commit(s) (owe a plan review, not a code review):",
                        file=sys.stderr,
                    )
                    for line in _annotate_already_reviewed(
                        _describe_uncovered_shas(planning_shas[:cap], repo_root),
                        broadly_reviewed,
                    ):
                        print(f"    {line}", file=sys.stderr)
                    if len(planning_shas) > cap:
                        print(
                            _format_capped_overflow_note(len(planning_shas), cap),
                            file=sys.stderr,
                        )
                if foreign_shas:
                    # `waived_foreign`/`unwaived_foreign` are already
                    # computed above (same `vouched` evidence source the
                    # write guard consults, `_resolve_vouched_shas`) — never
                    # re-derived here, matching Seam 2's "recordable is
                    # supplied by the caller" contract.
                    #
                    # AC5 register rewrite (docs/wiki/guard-messaging.md
                    # § Register): the waived-foreign fact is stated once,
                    # plus a terse alternative — no self-legitimacy
                    # (asserting what the waiver "really" permits), no
                    # restatement of the waiver's own mechanism, no DR
                    # citation. The uncapped per-sha list now lives on the
                    # persisted `chain_slices` record (this call's own
                    # `_persist_brightline_verdict` above) instead of being
                    # enumerated a second time in prose here.
                    if waived_foreign:
                        print(
                            f"  {len(waived_foreign)} of these "
                            f"{len(uncovered)} commit(s) are foreign-session "
                            "and recordable via a chain-ancestry waiver for "
                            "this chain — not evidence anyone reviewed them "
                            "(see gates.review_scale.chain_slices for the "
                            "full list). Record only commits this session "
                            "reviewed: coordinator-write-review-trail "
                            '--sha-range "<sha>^..<sha>" --scope chain '
                            "(concrete endpoints only — a `..HEAD` range is "
                            "dropped before the waiver is consulted).",
                            file=sys.stderr,
                        )
                    if unwaived_foreign:
                        print(
                            f"  {len(unwaived_foreign)} of these "
                            f"{len(uncovered)} commit(s) are unrecordable by "
                            "an ordinary review-trail write: authored by a "
                            "predecessor session, carrying no chain-ancestry "
                            "waiver for this chain, and the foreign-session "
                            "guard refuses any range naming them, so no "
                            "record this session writes can discharge them. "
                            "The review is still OWED, not waived away: "
                            "naming this gap and its cause in the "
                            "workstream-complete narration IS the discharge "
                            "for it — do not read this refusal as license "
                            "to leave the ancestry silently uncovered.",
                            file=sys.stderr,
                        )
                        for line in _annotate_already_reviewed(
                            _describe_uncovered_shas(unwaived_foreign[:cap], repo_root),
                            broadly_reviewed,
                        ):
                            print(f"    {line}", file=sys.stderr)
                        if len(unwaived_foreign) > cap:
                            print(
                                _format_capped_overflow_note(len(unwaived_foreign), cap),
                                file=sys.stderr,
                            )
                if own_shas:
                    print(
                        f"REMEDY: record a per-commit review-trail verdict "
                        f"for each of the remaining {len(own_shas)} via "
                        "coordinator/bin/coordinator-write-review-trail.py.",
                        file=sys.stderr,
                    )
            else:
                print(
                    "HALT: brightline verdict=PARTITION-MANDATORY and the "
                    "on-disk review-trail carries no verdict that is both "
                    "non-pending and non-waived — the review this chain "
                    "mandates has not been run. This session cannot reach a "
                    "terminal stamp in this state.",
                    file=sys.stderr,
                )
                print(
                    "UNCOVERED: union-coverage diagnostics unavailable — "
                    "the chain's code-bearing commit set could not be "
                    "resolved, so no uncovered-commit list can be shown.",
                    file=sys.stderr,
                )
                print(
                    "ACTION: sanctioned exit is /handoff — hand the review "
                    "to a fresh session rather than proceeding here.",
                    file=sys.stderr,
                )
                print(f'basis: "{basis}"', file=sys.stderr)
                return 1
            if own_shas:
                print(
                    "ACTION: record a review-trail verdict for the "
                    "commit(s) named above via "
                    "coordinator/bin/coordinator-write-review-trail.py "
                    "— sanctioned exits: that, or /handoff.",
                    file=sys.stderr,
                )
            print(f'basis: "{basis}"', file=sys.stderr)
            return 1 if own_shas else 0
        else:
            # AC4/Seam 3 — the gate RAN and resolved the owed set to empty
            # (vacuous "owes no code review", or an ordinary discharge
            # with nothing uncovered). Persist `chain_slices=[]`
            # explicitly rather than leaving the key absent: absent means
            # "did not compute a slate for this close"
            # (`write_verdict_record`'s own None-vs-`[]` contract); a
            # clean, fully-reviewed close is the resolved-and-empty case,
            # not the not-run case, and must render as such on read-back.
            _persist_brightline_verdict(
                args.from_handoff, args.git_range, fields, chain_slices=[],
            )

    # Communicate loudly, never hard-stop. The EM (not this script) decides
    # reviewers_required; this only cross-checks a recorded decision against
    # findings already on disk when one is given.
    print(
        f"BRIGHTLINE verdict={fields['verdict']} — "
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

    p_trail = sub.add_parser("write-trail")
    p_trail.add_argument("--sha-range", required=True, dest="sha_range")
    p_trail.add_argument("--reviewer", required=True)
    p_trail.add_argument("--scope", required=True)
    p_trail.add_argument("--verdict", required=True)
    p_trail.add_argument("--diff-loc", required=True, dest="diff_loc")
    p_trail.add_argument("--scope-kind", default=None, dest="scope_kind")
    p_trail.add_argument("--workstream", default=None, dest="workstream")
    p_trail.add_argument(
        "--reviewer-evidence", default=None, dest="reviewer_evidence",
        help="Evidence correlating --reviewer with an artifact showing a review "
        "occurred (optional; forwarded verbatim when supplied). See "
        "coordinator_core/ops/review_trail_write.py's reviewer_evidence design.",
    )
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
