# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""reap-orphaned-in-flight-handoffs.py — crash-orphan CLAIM-RELEASER for consumed+in_flight
handoffs.

Purpose: find handoffs stuck at status:consumed + deployment_state:in_flight whose
claiming session (consumed_by:) is no longer live. A dead HOLDER is not a dead
DELIVERABLE — the handoff itself may still be entirely live work. This script therefore
RELEASES the claim (via bin/archive-stamp-cli's unconsume-handoff verb, a Python
trampoline into claude-klabauter coordinator_core.archive_stamp — handoff-transition.js was the prior
DEC-3 bash/JS parity oracle, deleted 2026-07-22 once claude-klabauter's parity suites froze to
committed goldens) rather than terminating the
handoff: status->active, deployment_state->ready_to_fire, consumed_at/consumed_by stripped,
a single-line park_note: stamped explaining the release. The handoff returns to the pool
for the NEXT session to pick up via /pickup — nothing about the deliverable itself is
judged abandoned. Some dead-holder orphans, however, actually SHIPPED before the session
died — their /workstream-complete Step 2.7 shipped-stamp was simply never run. Before
releasing the claim, this script runs a FAIL-CLOSED ship-check (see _shipped_orphan_sha
below) that upgrades a genuinely-shipped orphan to terminal `shipped` (via
archive-stamp-cli's `stamp-shipped-in` + `ship-handoff` verbs) instead of returning it to
the pool as if unfinished. This
script is otherwise a DETECTOR, not a free writer: every frontmatter mutation is delegated
to a tested CLI verb (archive-stamp-cli's stamp-shipped-in / ship-handoff /
unconsume-handoff) — single-writer invariant, AC5. `unconsume` (not `repark`) is used for the
release path: repark leaves `status: consumed` in place (an intentional-pause shape for a
session that will resume itself) and would block the next `/pickup` on its `consumed_by`
idempotency gate — a dead holder can never resume to clear that gate, so `repark` would
strand the handoff forever. `unconsume` fully clears the claim (status->active) so any
session can pick it up next.

Only a session that runs a terminal completion ceremony RESOLVES a handoff — that is the
only path to a terminal `deployment_state` (shipped/abandoned). A crashed holder that
never ran that ceremony has not resolved anything; it has merely stopped holding the
claim. Automated resolution-by-default was the bug: treating "holder died" as
equivalent to "work is abandoned" silently destroyed 30 live handoff records between
2026-07-04 and 2026-07-20 once sweep-shipped-handoffs.sh archived the `abandoned`-stamped
nodes this script produced. This REVERSES the 2026-07-13 decline of the claude-klabauter
`reaper-defensive-repark` proposal (which argued for keeping the abandon-by-default
behavior with a defensive repark carve-out) — that decision is superseded by the
2026-07-20 PM ruling: "We shouldn't have automated resolution to abandoned and then
archive those; we should only have handoffs get archived when they are resolved by a
session."

Reverse-membership (live-children) guard on the clean release fall-through (see
_has_live_children_exit_code): the ordinary crash shape is a session dying mid-/handoff,
before /workstream-complete writes a completion-log entry — exactly when P3 above returns
"" and this script would otherwise release the claim. If a successor handoff already
exists for that node, releasing it resurrects an ancestor into the ready_to_fire pool.
The guard's disposition is `skip` (counted, logged, non-terminal) — never `abandoned`;
per the same 2026-07-20 PM ruling, no automated writer in this family produces that
deployment_state.

Companion to the `repark` verb (archive-stamp-cli's repark-handoff) — repark is the INTENTIONAL-pause
path for a LIVE session choosing to step away; this reaper is the crash-orphan path for a
DEAD one, and now shares repark's non-terminal spirit (return to the pool) rather than
repark's `status: consumed` shape. They solve different sub-problems, not alternatives to
pick between.

The `kind: recovery` handoff mechanism (docs/wiki/multi-session-crash-recovery.md:107-113)
already provides the SUCCESSOR-path exit out of a crashed in_flight state. This reaper
closes the separate gap: the ORIGINAL crashed consumed+in_flight node itself, which the
recovery handoff bypasses but never sweeps/reaps/transitions state on — it would
otherwise stay orphaned and invisible to `/pickup` forever, permanently locked out of the
pool by its own dead consumed_by claim.

Spec backlink: state/handoffs/2026-07-20_114653_revive-lost-capabilities-triage.md § Part 1

Anti-scope (RAW-PID-LIVENESS tripwire): the orphan predicate gates on session liveness
ONLY — coordinator_core.session.liveness.session_live (the shared cs_live_session_ids /
cs_claim_holder_live liveness key, ported natively) — NEVER mtime/pid of the handoff file
itself. A slow-but-live in_flight session is never reaped; liveness is decided by the
session-claim layer, not filesystem staleness.

Ship-check predicate (P1-P4, unambiguous 1:1-binding, fail-closed to release on ANY
failure — see _shipped_orphan_sha):
  P1 (population split, NOT overlap) — kind:spinoff-roadmap + non-empty deliverable_id
    nodes belong to promote-shipped-in-flight-stubs.py's deliverable-spine join
    (rollup-derive.py); this reaper's ship-check does NOT run for them — falls through
    to the claim-release path unchanged. The two scripts partition the orphan
    population disjointly by this gate; they are not two passes over the same set.
  P2 (bounded scan) — the dead consumed_by session must have consumed EXACTLY ONE
    handoff across state/handoffs/ + archive/handoffs/. More than one is ambiguous
    (which consumption does a completion-log entry attest to?) and fails closed.
  P3 (completion-entry oracle, DoE-local) — exactly one completion-log entry with
    authored_by == the dead consumed_by session id (via query-completions.py --where
    "authored_by=<id>"). Zero means no terminal ceremony ran; two+ is ambiguous. Either
    fails closed. This is the ONLY ship-signal source; no claude-klabauter/ceremony coupling.
  P4 (terminal SHA selection) — from that single completion entry's commits[], pick the
    SHA with the MAX committer timestamp (git show -s --format=%ct), mirroring the
    best_sha/best_ct idiom in promote-shipped-in-flight-stubs.py:137-151. No resolvable
    SHA fails closed.
DoE-local / no-claude-klabauter-coupling constraint: every P2-P4 signal is a DoE-repo-local file
(state/handoffs, archive/handoffs, the completion log) — never state/ceremony/wsc/* or
any claude-klabauter-owned receipt shape.
Fail-closed contract: _shipped_orphan_sha returns a SHA iff P1 passed (this node is
in-scope) AND P2 AND P3 AND P4 all hold; on ANY failure it returns "" and the caller
falls through to the claim-release (unconsume) path unchanged. The ship path itself
re-asserts status:consumed + deployment_state:in_flight (TOCTOU guard) before mutating,
and asserts shipped_in actually landed after stamping — if the stamp silently no-ops,
the script WARNs and still falls through to claim-release rather than leaving the
handoff shipped-but-unstamped.

Usage:
    python3 reap-orphaned-in-flight-handoffs.py [--dry-run]

--dry-run: report orphan/ship-reclaim candidates on stdout without mutating anything.

Exit codes:
    0 — normal (including zero orphans found; claim-release is best-effort)
    2 — internal error (not inside a git repo, or state/handoffs/ unresolvable)

Spec backlink: DoE-claude:pln-handoff-spinoff-machinery-robu-0d0f15 § C5a
Spec backlink: DoE-claude:pln-reaper-ships-not-abandons-ship-6ce32a
Port of: reap-orphaned-in-flight-handoffs.sh (DoE e991362e, 2026-07-21,
de-bash campaign chunk A2-c)
Spec backlink: DoE-claude:pln-de-polyglot-the-coordinator-mi-119303 § chunk B1
(node-spawn call sites repointed onto archive-stamp-cli; handoff-transition.js /
stamp-shipped-in.js deleted 2026-07-22 — claude-klabauter's parity suites froze to committed
goldens, dissolving the DEC-3 keep-as-oracle hold)

Negative-spec: does NOT reimplement session-liveness logic — the orphan predicate calls
coordinator_core.session.liveness.session_live() (in-process import via CLAUDE_KLABAUTER_ROOT, no
subprocess, no bash re-exec). Does NOT mutate frontmatter directly — every mutation is
delegated to bin/archive-stamp-cli's stamp-shipped-in / ship-handoff / unconsume-handoff
verbs (a Python trampoline into claude-klabauter coordinator_core.archive_stamp — no node spawn),
single-writer invariant, AC5.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402
from handoff_lifecycle import is_claimed_status  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags  # noqa: E402

_ARCHIVE_STAMP_CLI = os.path.join(_SCRIPT_DIR, "archive-stamp-cli.py")
_QUERY_CLI_DEFAULT = os.path.join(_SCRIPT_DIR, "query-completions.py")
_HAS_LIVE_CHILDREN_CLI = os.path.join(_SCRIPT_DIR, "handoff-has-live-children.py")


def _resolve_session_live():
    """Import coordinator_core.session.liveness.session_live via CLAUDE_KLABAUTER_ROOT.

    In-process import (no subprocess, no bash) — mirrors the direct-import
    trampoline shape used by aggregate-chain-loe.py / query-completions.py.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.session.liveness import session_live
    return session_live


def _resolve_find_archived_twin_by_handoff_id():
    """Import coordinator_core.handoff_creation_guard.find_archived_twin_by_handoff_id
    via CLAUDE_KLABAUTER_ROOT.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    Shares the archived-twin match predicate with the creation-side guard
    (``coordinator_core.handoff_creation_guard.assert_no_archived_twin``) so
    the two guards — this reaper's SKIP path and the creation guard's RAISE
    path — cannot silently drift apart on what counts as a "twin". See
    ``_handoff_id_archived_twin`` below for the thin wrapper that preserves
    this script's own str-path-or-"" return shape.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.handoff_creation_guard import find_archived_twin_by_handoff_id
    return find_archived_twin_by_handoff_id


def _resolve_claim_state():
    """Import coordinator_core.claim_state.resolve_claim_state via
    CLAUDE_KLABAUTER_ROOT.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    C1 (commit 1194eb3f4) landed this as the canonical ledger-first claim
    accessor — ledger wins whenever it holds a LIVE claim (regardless of
    what the frontmatter mirror says); a dead ledger holder degrades to
    ``source: "mirror"``/``"none"``, never ``"ledger"``. See
    ``_claim_holder`` below for how this reaper consumes it.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.claim_state import resolve_claim_state
    return resolve_claim_state


def _resolve_canonical_kind():
    """Import coordinator_core.frontmatter.baton_class.canonical_kind via
    CLAUDE_KLABAUTER_ROOT.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    De-aliases a still-live PRE-rename `kind` value (e.g. `spinoff-roadmap`)
    to its D1 successor (`roadmap-baton`) — the single canonical normaliser,
    not a hand-rolled retired/canonical pair (see that module's own
    "Vocabulary bridge" section).
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.frontmatter.baton_class import canonical_kind
    return canonical_kind


# ---------------------------------------------------------------------------
# Field-extraction helper — same single-key frontmatter-scan idiom as the
# retired bash's awk-based _fm_field (mirrors sweep-shipped-handoffs.sh
# process_file).
# ---------------------------------------------------------------------------
def _fm_field(path: str, key: str) -> str:
    prefix = key + ":"
    val = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            in_fm = False
            for line in fh:
                stripped_line = line.rstrip("\n").rstrip("\r")
                if not in_fm:
                    if stripped_line.strip() == "---":
                        in_fm = True
                    continue
                if stripped_line.strip() == "---":
                    break
                if stripped_line.startswith(prefix):
                    val = stripped_line[len(prefix):].strip()
                    break
    except OSError:
        return ""

    # Review: review-integrator B-F4 — strip a single matched pair of surrounding
    # quotes. serializeYamlScalar (coordinator/bin/lib/schema.js) single-quotes
    # all-digit values (e.g. a synthetic all-digit session-id); an unstripped quoted
    # consumed_by would read as not-live below and could mis-reap a live handoff.
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1]
    return val


def _claim_holder(path: str, *, repo_root: str = "") -> str:
    """Ledger-first claim-holder read: prefer the branch-independent claim
    ledger's LIVE holder, fall back to the tracked-frontmatter mirror
    (`claimed_by`, then legacy `consumed_by`).

    Thin wrapper over `coordinator_core.claim_state.resolve_claim_state` (C1,
    commit 1194eb3f4) — the canonical ledger-first accessor. This replaces
    this file's prior mirror-only dual-read
    (coordinator/bin/lib/handoff_lifecycle.claim_holder): that accessor could
    never see a claim the ledger still held once the mirror reverted (e.g. a
    shared-worktree branch switch away from the commit that stamped
    `claimed_by`) — a LIVE ledger holder would read as "no holder" here and
    either wrongly disappear into `skipped_no_holder`, or worse, let a STALE
    mirror value (a different, dead session id left over from a prior claim)
    stand in as the tested holder and get reaped out from under the true,
    still-live claimant. `resolve_claim_state` closes both: `.holder`
    resolves to the ledger's holder whenever the ledger holds a live claim
    (source == "ledger"), regardless of the mirror; only when the ledger has
    no live claim does `.holder` fall back to the mirror value (source ==
    "mirror"/"none"). A dead ledger holder is never surfaced as `.holder`
    with source == "ledger" (see that module's own fail-closed-to-mirror
    degrade) — this reaper's downstream `session_live()` re-check therefore
    still governs whether the RESOLVED holder (ledger-live or mirror
    fallback) is itself alive; this wrapper only fixes WHICH holder gets
    tested, never removes that liveness test.

    `repo_root` threads through to `resolve_claim_state`'s own
    `git_common_dir` resolution (lru_cache'd — see that module's docstring),
    so passing it here costs a cached-dict lookup, not a subprocess.

    A resolution failure (e.g. a malformed ledger record for this one
    handoff) degrades to "" — this reaper's existing "no claim holder
    recorded, skip, do not reap" path — rather than aborting the whole
    batch. Defense-in-depth at this boundary even though the ledger-record
    accessor itself is expected to degrade rather than raise; this script
    destroys claim state, so it stays fail-closed-and-skip per handoff on
    its own terms.
    """
    resolve_claim_state = _resolve_claim_state()
    try:
        state = resolve_claim_state(path, repo_root=(repo_root or None))
    except Exception:
        return ""
    return state.holder or ""


def _handoff_id_archived_twin(handoff_id: str, repo_root: str) -> str:
    """Return the path of an `archive/handoffs/` record sharing `handoff_id`,
    or "" if none exists.

    Defensive guard against the DR-084 C8 incident (DoE-claude commit
    `339b269a`, cleaned up in `073b6b1f`): a live-path handoff that shares its
    `handoff_id` with an already-archived record is residue from an upstream
    archival-flow bug, never a legitimate live baton -- a handoff cannot
    correctly be both "already archived, terminal" and "currently in flight"
    at once. This reaper previously had no such check and, on exactly this
    incident's data, read one such residue as a real orphan and flipped it
    from a correctly-closed archived state back to open/ready_to_fire
    (`a33f3598`, "fleet: async reaper released stale claims on crash-orphaned
    handoffs"), resurrecting already-completed work as a live pickup
    candidate. See also `bin/dr084-migrate-handoff-vocabulary.py`'s
    `find_live_duplicate_ids()`, which closes the same collision shape at the
    migration-tool layer -- this is the same guard at the reaper layer, since
    a fresh residue could in principle reappear from a different upstream bug
    and this reaper is the point where residue becomes destructive (claim
    release / resurrection), not merely stale.

    Thin wrapper over the shared match predicate,
    `coordinator_core.handoff_creation_guard.find_archived_twin_by_handoff_id`
    -- this reaper (SKIP-on-match) and `handoff_creation_guard.
    assert_no_archived_twin` (RAISE-on-match) defend the same invariant at
    two different moments (resurrection-prevention here, creation-prevention
    there) and must never disagree on what counts as a "twin". Only the
    reaction to a match differs, and that reaction stays local to each call
    site -- this wrapper exists solely to preserve this script's own
    str-path-or-"" return shape (vs. the shared helper's `Path | None`) so
    every existing call site below is untouched.
    """
    if not handoff_id:
        return ""
    find_archived_twin_by_handoff_id = _resolve_find_archived_twin_by_handoff_id()
    twin = find_archived_twin_by_handoff_id(handoff_id, repo_root)
    return str(twin) if twin is not None else ""


def _run_query_cli(query_cli: str, where: str, fmt: str) -> str:
    if query_cli.endswith(".py"):
        cmd = [sys.executable, query_cli, "--where", where, "--format", fmt]
    else:
        cmd = [query_cli, "--where", where, "--format", fmt]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, **no_console_creationflags())
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _shipped_orphan_candidate(
    consumed_by: str,
    this_handoff: str,
    handoffs_dir: str,
    repo_root: str,
    query_cli: str = _QUERY_CLI_DEFAULT,
) -> Optional[list]:
    """Ship-check predicate P2+P3 (P1 is checked by the caller; P4's SHA
    selection is DEFERRED — see ``_batch_commit_timestamps`` /
    ``_best_shipped_sha`` below). Returns the single matched completion
    entry's raw ``commits[]`` list iff P2 AND P3 hold; returns ``None`` on
    ANY failure (fail-closed — caller treats this identically to a P4 "no
    resolvable SHA", i.e. falls through to the claim-release (unconsume)
    path unchanged).

    Neither P2 nor P3 spawns git — this function does zero subprocess calls.
    Splitting P4 out is what lets the caller batch the one genuinely
    git-spawning leg (committer-timestamp resolution) across every orphan in
    the in-flight set in a single call, instead of one ``git show`` per
    commit per orphan.
    """
    # Reserved for the documented future chain-join extension
    # (docs/plans/2026-07-13-reaper-ship-not-abandon-shipped-orphans.md
    # § Design decision, "Explicitly out of scope"); genuinely unused today,
    # not dead-code cruft — do not delete.
    _this_handoff_reserved_for_chain_join = this_handoff  # noqa: F841

    # P2 — bounded scan: the dead consumed_by session must have consumed EXACTLY
    # ONE handoff (across state/handoffs/ + archive/handoffs/). More than one is
    # ambiguous (a completion-log entry can't be disambiguated to a specific
    # consumption) and fails closed.
    match_count = 0
    for h in glob.glob(os.path.join(handoffs_dir, "*.md")):
        if not os.path.isfile(h):
            continue
        if _claim_holder(h, repo_root=repo_root) == consumed_by:
            match_count += 1

    archive_handoffs_dir = os.path.join(repo_root, "archive", "handoffs")
    if os.path.isdir(archive_handoffs_dir):
        for h in glob.glob(os.path.join(archive_handoffs_dir, "**", "*.md"), recursive=True):
            if not os.path.isfile(h):
                continue
            if _claim_holder(h, repo_root=repo_root) == consumed_by:
                match_count += 1

    if match_count != 1:
        return None

    # P3 — completion-entry oracle (DoE-local ONLY; no claude-klabauter/ceremony coupling).
    # Exactly one completion-log entry authored by the dead session. Zero means
    # no terminal ceremony ran; two+ is ambiguous. Either fails closed.
    where = f"authored_by={consumed_by}"
    completion_paths = _run_query_cli(query_cli, where, "paths")
    completion_path_count = len([ln for ln in completion_paths.splitlines() if ln.strip()])
    if completion_path_count != 1:
        return None

    completion_json = _run_query_cli(query_cli, where, "json")
    if not completion_json.strip():
        return None
    try:
        parsed = json.loads(completion_json)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None

    entry = parsed[0] if isinstance(parsed[0], dict) else {}
    frontmatter = entry.get("frontmatter") if isinstance(entry, dict) else None
    commits = frontmatter.get("commits") if isinstance(frontmatter, dict) else None
    if not isinstance(commits, list):
        return None

    return [sha.strip() for sha in commits if isinstance(sha, str) and sha.strip()]


def _batch_commit_timestamps(shas: list, repo_root: str) -> dict:
    """Resolve committer-timestamp (``%ct``) for a batch of commit SHAs in
    ONE ``git log`` call.

    Mirrors ``emit/sections/handoffs._resolve_shipped_in_dates``'s
    ``--no-walk --ignore-missing`` shape exactly (the in-tree reconciliation
    reference this chunk was told to cite, not re-derive): this is an OBJECT
    question (commit metadata at a caller-supplied SHA), not a RANGE
    question, so it batches unconditionally — ``git log --no-walk`` resolves
    each argv SHA independently; it never merges them into one
    ancestry/reachability set expression the way ``git rev-list A..B C..D``
    would (the forbidden shape for a DIFFERENT git-spawn class entirely; see
    ``docs/wiki/coverage-gate-perf.md``).

    ``--ignore-missing`` makes an unresolvable SHA silently ABSENT from
    stdout (exit 0) rather than an error — never read that absence as "this
    SHA resolved to nothing meaningful, treat it as ineligible and move on"
    without accounting for it explicitly: the prefix-match loop below only
    ever POPULATES ``sha_ct`` for a SHA it can positively match against
    stdout, so a requested SHA absent from the return value is simply absent
    from ``sha_ct`` — the caller (``_best_shipped_sha``) already treats a
    candidate sha missing from this dict as unresolved and skips it, which
    is exactly the fail-closed behaviour the old per-sha
    ``returncode != 0: continue`` path had.
    """
    if not shas:
        return {}
    ordered = sorted(set(shas))
    try:
        proc = subprocess.run(
            [
                "git", "-C", repo_root, "log",
                "--no-walk=unsorted", "--ignore-missing",
                "--format=%H %ct",
                *ordered,
            ],
            capture_output=True, text=True, check=False,
            **no_console_creationflags(),
        )
    except (OSError, ValueError):
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}

    sha_ct: dict = {}
    matched: set = set()
    for line in proc.stdout.replace("\r", "").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        full, ct_str = parts[0], parts[1]
        try:
            ct = int(ct_str)
        except ValueError:
            continue
        for raw in ordered:
            if raw not in matched and full[: len(raw)] == raw:
                sha_ct[raw] = ct
                matched.add(raw)
                break
    return sha_ct


def _best_shipped_sha(candidates: list, sha_ct: dict) -> str:
    """P4 — terminal SHA selection: MAX committer timestamp across a single
    completion entry's ``commits[]`` (best_sha/best_ct idiom mirroring
    ``promote-shipped-in-flight-stubs.py:137-151`` — do NOT positional-trust
    array order), resolved against the batched ``sha_ct`` map produced by
    ``_batch_commit_timestamps``. A candidate sha absent from ``sha_ct``
    (unresolvable, or dropped by ``--ignore-missing``) is never treated as
    resolved. No resolvable SHA -> "" (fail-closed, same contract as the
    prior per-sha-spawning ``_shipped_orphan_sha``).
    """
    best_sha = ""
    best_ct = -1
    for sha in candidates:
        ct = sha_ct.get(sha)
        if ct is None:
            continue
        if ct > best_ct:
            best_ct = ct
            best_sha = sha
    return best_sha


def _shipped_orphan_sha(
    consumed_by: str,
    this_handoff: str,
    handoffs_dir: str,
    repo_root: str,
    query_cli: str = _QUERY_CLI_DEFAULT,
) -> str:
    """Ship-check predicate P2-P4 for a SINGLE orphan (P1 is checked by the
    caller — see module docstring). Returns a landing SHA iff P2 AND P3 AND
    P4 all hold; returns "" on ANY failure (fail-closed — caller falls
    through to the claim-release (unconsume) path unchanged).

    Composes ``_shipped_orphan_candidate`` + ``_batch_commit_timestamps`` +
    ``_best_shipped_sha``. Retained for any single-orphan caller (e.g.
    tests exercising the predicate directly); ``main()`` below calls the
    three primitives directly so it can batch the ``_batch_commit_timestamps``
    leg across every in-flight orphan in ONE git call instead of once per
    orphan.
    """
    candidates = _shipped_orphan_candidate(consumed_by, this_handoff, handoffs_dir, repo_root, query_cli)
    if candidates is None:
        return ""
    sha_ct = _batch_commit_timestamps(candidates, repo_root)
    return _best_shipped_sha(candidates, sha_ct)


def _run_archive_stamp_cli(args: list) -> tuple:
    """Invoke bin/archive-stamp-cli (a Python trampoline into claude-klabauter
    coordinator_core.archive_stamp) as a subprocess, mirroring the retired
    _run_node's success-boolean contract (returncode == 0). Preserves the
    same success/failure handling the reaper previously got from
    _run_node(handoff-transition.js / stamp-shipped-in.js) — only the
    process target changed (no node spawn, no bash re-exec).

    Returns ``(ok, diagnostic)``. The diagnostic is empty on success and
    otherwise carries the exit code plus the child's stderr/stdout tail, so a
    caller can name WHY a verb failed. Negative-spec: callers must not collapse
    this back to a bare boolean — an unnamed "error releasing <path>; skipping"
    line is indistinguishable from a released-nothing run and sent two sibling
    repos chasing the wrong hypothesis (2026-08-12 cross-repo memos).
    """
    try:
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        result = subprocess.run(
            [sys.executable, _ARCHIVE_STAMP_CLI] + args,
            capture_output=True, text=True, check=False, env=child_env(), **no_console_creationflags(),
        )
    except OSError as exc:
        return False, f"could not spawn {_ARCHIVE_STAMP_CLI}: {exc}"
    if result.returncode == 0:
        return True, ""
    detail = (result.stderr or "").strip() or (result.stdout or "").strip() or "(no output)"
    return False, f"{os.path.basename(_ARCHIVE_STAMP_CLI)} {args[0]} exit {result.returncode}: {detail}"


def _has_live_children_exit_code(handoff_path: str) -> int:
    """Reverse-membership crash-orphan guard for the clean release fall-through.

    The ordinary crash shape this guards against: a session runs /handoff under
    context pressure and dies before /workstream-complete, so its predecessor
    node's completion-log entry never lands (P3 above returns ""), and the
    orphan falls through to claim-release — resurrecting into the ready_to_fire
    pool a node whose own successor already exists. Delegates to the same
    handoff.has_live_children reverse-membership predicate the /handoff
    chain-archival path and fleet.archive_completed_handoffs already consult;
    this reaper was the one lifecycle writer that didn't. Fail-closed: any
    transport/subprocess failure returns 2 (indeterminate), never 1 (safe to
    release).
    """
    try:
        from cc_invoke import child_env  # noqa: E402 (path injected at module top)

        result = subprocess.run(
            [sys.executable, _HAS_LIVE_CHILDREN_CLI, handoff_path],
            capture_output=True, text=True, check=False, env=child_env(), **no_console_creationflags(),
        )
    except OSError:
        return 2
    return result.returncode


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dry-run", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        print(f"reap-orphaned-in-flight-handoffs.py: unknown argument: {argv}", file=sys.stderr)
        return 2
    dry_run = args.dry_run

    # ---------------------------------------------------------------------
    # Repo root / handoffs dir resolution — via repo_identity's checked
    # resolver (memoized, gates on session identity; not a direct git
    # rev-parse call in this module): this reaper needs to run from a
    # cold session-init-hook shell like sweep-shipped-handoffs.sh, and scans
    # state/handoffs/ directly (session-claim liveness is itself keyed off
    # this same git root's .git/coordinator-sessions/).
    # ---------------------------------------------------------------------
    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if not repo_root:
        print("reap-orphaned-in-flight-handoffs.py: not inside a git repo", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277: this is a READER (no write into resolved root) -- warn
        # and proceed. UNRESOLVED never refuses either (AC4).
        print(verdict["message"], file=sys.stderr)

    handoffs_dir = os.path.join(repo_root, "state", "handoffs")

    try:
        session_live = _resolve_session_live()
    except (RuntimeError, ImportError) as exc:
        print(f"reap-orphaned-in-flight-handoffs.py: session liveness engine not importable: {exc}", file=sys.stderr)
        return 2

    try:
        canonical_kind = _resolve_canonical_kind()
    except (RuntimeError, ImportError) as exc:
        # Review: code-reviewer (P2, Finding 3) — matches the guard already
        # applied to _resolve_session_live() above (same CLAUDE_KLABAUTER_ROOT
        # sys.path trampoline); a stale sibling checkout predating this
        # migration must fail loud with a clean message, not a raw
        # traceback. See _PRE_RENAME_ALIASES's module docstring: a
        # half-migrated fleet is the normal state, not a hypothetical.
        print(f"reap-orphaned-in-flight-handoffs.py: canonical-kind resolver not importable: {exc}", file=sys.stderr)
        return 2

    released = 0
    would_release = 0
    reclaimed = 0
    would_reclaim = 0
    skipped_live = 0
    skipped_no_holder = 0
    skipped_by_guard = 0
    would_skip_by_guard = 0
    skipped_archived_duplicate = 0
    would_skip_archived_duplicate = 0
    failed_release = 0

    # -----------------------------------------------------------------
    # Pass 1 (read-only): walk the corpus once, evaluate every gate up to
    # (but not including) P4's git-spawning SHA selection, and — for every
    # dead-holder orphan whose ship-check reaches P2/P3 — collect its raw
    # candidate commits[] WITHOUT resolving any commit's timestamp yet.
    # This defers the one genuinely git-spawning leg (_batch_commit_timestamps
    # below) so it can run ONCE, batched over every candidate SHA across the
    # WHOLE in-flight set, instead of once per commit per orphan (the
    # C13 target: "batches _shipped_orphan_sha across the in-flight set").
    # -----------------------------------------------------------------
    pending: list = []
    all_candidate_shas: set = set()

    if os.path.isdir(handoffs_dir):
        for f in sorted(glob.glob(os.path.join(handoffs_dir, "*.md"))):
            # TOCTOU guard — a concurrent archival/consume can vanish or
            # rewrite the file between glob-enumeration and per-file
            # processing.
            if not os.path.isfile(f):
                continue

            status = _fm_field(f, "status")
            deployment_state = _fm_field(f, "deployment_state")

            # Orphan candidate shape: (status:consumed OR status:claimed) +
            # deployment_state:in_flight. DR-084 dual-read: field/value
            # renamed status:consumed->claimed, consumed_by->claimed_by at
            # P2; corpus is mixed during the P1..P4 migration window. Prefer
            # claimed_by, fall back to consumed_by, below — see
            # coordinator/skills/workstream-complete/SKILL.md Step 0 for the
            # canonical reference shape. is_claimed_status is the shared
            # handoff_lifecycle.py accessor for the status-value half of this
            # dual-read (mirrors _claim_holder for the holder-field half) —
            # collapse to a bare `status == "claimed"` check only once the
            # migration window closes and no repo's corpus can carry the old
            # vocabulary.
            if not (is_claimed_status(status) and deployment_state == "in_flight"):
                continue

            # Review: code-reviewer — Finding 3. Renamed from `consumed_by`
            # to `claim_holder`: post-DR-084 this holds a claimed_by-
            # preferred value, and the old name misled a reader skimming
            # just the variable name (not the assignment) into assuming
            # old-vocab-only.
            claim_holder = _claim_holder(f, repo_root=repo_root)

            # No claim holder recorded — cannot evaluate liveness; skip
            # (fail-closed, do not reap).
            if not claim_holder:
                skipped_no_holder += 1
                continue

            # Liveness gate: session_live ONLY (the shared cs_live_session_ids
            # / cs_claim_holder_live liveness key) — NEVER mtime/pid of the
            # handoff file (RAW-PID-LIVENESS).
            if session_live(claim_holder, cwd=repo_root):
                skipped_live += 1
                continue

            # Archived-twin guard (post DR-084 C8 incident, 339b269a/073b6b1f/
            # a33f3598 — see _handoff_id_archived_twin docstring). A live
            # in_flight candidate whose handoff_id ALSO exists under
            # archive/handoffs/ is residue, not a real orphan — a handoff
            # cannot legitimately be both terminal-archived and currently in
            # flight. Fail closed: skip, never claim-release/resurrect it.
            handoff_id = _fm_field(f, "handoff_id")
            archived_twin = _handoff_id_archived_twin(handoff_id, repo_root)
            if archived_twin:
                msg = (
                    f"reap-orphaned-in-flight-handoffs.py: SKIP {f} -- handoff_id "
                    f"{handoff_id!r} already exists in archive/handoffs "
                    f"({archived_twin}); refusing to treat live copy as a real "
                    "orphan (see DR-084 C8 incident)"
                )
                if dry_run:
                    print(f"[dry-run] {msg}")
                    would_skip_archived_duplicate += 1
                else:
                    print(msg)
                    skipped_archived_duplicate += 1
                continue

            # Dead holder — orphan confirmed. Before defaulting to
            # claim-release, run the ship-check's non-spawning legs (P1-P3 —
            # see module docstring) to catch orphans that actually shipped
            # before the session died. P4 (SHA selection) is deferred to the
            # batched resolution after this loop.
            #
            # P1 — population split (NOT overlap) with
            # promote-shipped-in-flight-stubs.py: kind:spinoff-roadmap +
            # non-empty deliverable_id nodes belong to that script's
            # deliverable-spine join; skip the ship-check for them entirely
            # and fall through to the unmodified claim-release path.
            kind = _fm_field(f, "kind")
            deliverable_id = _fm_field(f, "deliverable_id")
            candidates = None
            if not (canonical_kind(kind) == "roadmap-baton" and deliverable_id):
                candidates = _shipped_orphan_candidate(claim_holder, f, handoffs_dir, repo_root)
                if candidates:
                    all_candidate_shas.update(candidates)

            pending.append({"path": f, "claim_holder": claim_holder, "candidates": candidates})

    # -----------------------------------------------------------------
    # ONE batched git call resolves every candidate SHA's committer
    # timestamp across the ENTIRE in-flight set (object question — batches
    # unconditionally; see _batch_commit_timestamps' docstring). Zero spawns
    # here when no orphan reached P2/P3.
    # -----------------------------------------------------------------
    sha_ct = _batch_commit_timestamps(sorted(all_candidate_shas), repo_root)

    # -----------------------------------------------------------------
    # Pass 2 (mutating): P4 selection against the batched map, then the
    # unchanged ship / release disposition per orphan.
    # -----------------------------------------------------------------
    for item in pending:
        f = item["path"]
        claim_holder = item["claim_holder"]
        candidates = item["candidates"]
        sha = _best_shipped_sha(candidates, sha_ct) if candidates else ""

        if sha:
            # SHIP path — P1 and P2 and P3 and P4 all held: this dead
            # holder ran a terminal completion ceremony for exactly one
            # handoff (this one).
            #
            # TOCTOU re-read (mirrors
            # promote-shipped-in-flight-stubs.py:158-160): a concurrent
            # writer could have moved status/deployment_state between the
            # earlier read and now.
            now_status = _fm_field(f, "status")
            now_dstate = _fm_field(f, "deployment_state")
            if not (is_claimed_status(now_status) and now_dstate == "in_flight"):
                continue

            if dry_run:
                print(
                    f"reap-orphaned-in-flight-handoffs.py: [dry-run] would SHIP (reclaim) {f} "
                    f"(dead holder: {claim_holder}; shipped_in {sha[:8]})"
                )
                would_reclaim += 1
                continue

            _stamp_ok, _stamp_diag = _run_archive_stamp_cli(["stamp-shipped-in", f, "--sha", sha])
            if not _stamp_ok:
                print(
                    f"reap-orphaned-in-flight-handoffs.py: WARNING {f} — {_stamp_diag}",
                    file=sys.stderr,
                )

            # ASSERT shipped_in landed (mirrors
            # promote-shipped-in-flight-stubs.py:168-176) — UNCONDITIONAL,
            # not gated on this handoff's created date. If the stamp
            # silently no-op'd, fail closed: WARN and fall through to
            # claim-release rather than leaving a handoff
            # shipped-but-unstamped.
            landed = _fm_field(f, "shipped_in")
            if not landed or landed == "null":
                print(
                    f"reap-orphaned-in-flight-handoffs.py: WARNING {f} — shipped_in did not land "
                    "after stamp; falling through to claim-release",
                    file=sys.stderr,
                )
            else:
                ship_ok, ship_diag = _run_archive_stamp_cli(["ship-handoff", f])
                if ship_ok:
                    print(
                        f"reap-orphaned-in-flight-handoffs.py: reclaimed (shipped): {f} "
                        f"(dead holder {claim_holder} ran a terminal ceremony; shipped_in {sha[:8]})"
                    )
                    reclaimed += 1
                    continue
                else:
                    # A ship-verb failure after a successful stamp must
                    # fall through to claim-release like the WARN branch
                    # above, not strand the handoff at shipped_in-populated
                    # + status:consumed/deployment_state:in_flight forever
                    # (invisible to /pickup, never retried).
                    print(
                        f"reap-orphaned-in-flight-handoffs.py: error shipping {f} — {ship_diag}; "
                        "falling through to claim-release",
                        file=sys.stderr,
                    )

        # Reverse-membership (live-children) guard — reachable ONLY from
        # the clean fall-through (sha never populated, i.e. the ship-check
        # returned "" and no stamp was ever attempted for this node). The
        # WARN-degraded ship path above (sha truthy, stamp-shipped-in
        # already landed, ship-handoff then failed or shipped_in didn't
        # land) keeps falling through to release unchanged — it must not
        # be re-gated here.
        if not sha:
            guard_exit = _has_live_children_exit_code(f)
            if guard_exit == 0:
                reason = "has a live succession child; releasing would resurrect an ancestor"
            elif guard_exit == 2:
                reason = "live-children guard indeterminate; fail-closed"
            else:
                reason = None  # guard_exit == 1 (childless) -> proceed to release

            if reason is not None:
                if dry_run:
                    print(f"reap-orphaned-in-flight-handoffs.py: [dry-run] would skip {f} ({reason})")
                    would_skip_by_guard += 1
                else:
                    print(f"reap-orphaned-in-flight-handoffs.py: skip: {f} — {reason}", file=sys.stderr)
                    skipped_by_guard += 1
                continue

        # Dispatch the `unconsume` claim-release transition (this script
        # never writes frontmatter itself — single-writer invariant,
        # AC5). Returns the handoff to the pool (status:active,
        # deployment_state:ready_to_fire) rather than terminating it — a
        # dead HOLDER is not a dead DELIVERABLE.
        if dry_run:
            print(
                f"reap-orphaned-in-flight-handoffs.py: [dry-run] would release {f} "
                f"(dead holder: {claim_holder})"
            )
            would_release += 1
            continue

        note = (
            f"claim released by crash-orphan reaper — holder {claim_holder} died without "
            "resolving; returned to pool"
        )
        release_ok, release_diag = _run_archive_stamp_cli(
            ["unconsume-handoff", f, note, "--reaped-from", claim_holder]
        )
        if release_ok:
            print(
                f"reap-orphaned-in-flight-handoffs.py: released {f} "
                f"(dead holder: {claim_holder} — returned to pool)"
            )
            released += 1
        else:
            print(
                f"reap-orphaned-in-flight-handoffs.py: error releasing {f} — {release_diag}; skipping",
                file=sys.stderr,
            )
            failed_release += 1

    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------
    if dry_run:
        if would_release == 0:
            print("no orphaned in_flight handoffs would be released (dry-run)")
        else:
            print(f"{would_release} orphaned in_flight handoffs would be released (dry-run)")
        if would_reclaim > 0:
            print(f"{would_reclaim} orphaned in_flight handoffs would be reclaimed as shipped (dry-run)")
    elif released == 0 and failed_release == 0:
        print("no orphaned in_flight handoffs released")
    elif released == 0 and failed_release > 0:
        print(
            f"0 orphaned in_flight handoffs released — {failed_release} release attempt(s) FAILED "
            "(see error lines above)"
        )
    elif failed_release > 0:
        print(
            f"{released} orphaned in_flight claims released (returned to pool); "
            f"{failed_release} release attempt(s) FAILED (see error lines above)"
        )
    else:
        print(f"{released} orphaned in_flight claims released (returned to pool)")

    if reclaimed > 0:
        print(f"{reclaimed} orphaned in_flight handoffs reclaimed as shipped")

    if skipped_live > 0:
        print(f"{skipped_live} in_flight handoffs retained (live holder)")

    if skipped_no_holder > 0:
        print(f"{skipped_no_holder} consumed+in_flight handoffs retained (no claimed_by/consumed_by recorded)")

    if dry_run:
        if would_skip_by_guard > 0:
            print(f"{would_skip_by_guard} orphaned in_flight handoffs would be skipped (live-children guard, dry-run)")
        if would_skip_archived_duplicate > 0:
            print(
                f"{would_skip_archived_duplicate} orphaned in_flight handoffs would be "
                "skipped (archived-twin guard, dry-run)"
            )
    else:
        if skipped_by_guard > 0:
            print(f"{skipped_by_guard} orphaned in_flight handoffs skipped (live-children guard)")
        if skipped_archived_duplicate > 0:
            print(
                f"{skipped_archived_duplicate} orphaned in_flight handoffs skipped "
                "(archived-twin guard)"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
