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

Governed-plan guard on the same fall-through: an orphan whose `deliverable_id` joins a
plan already stamped `status: implemented` did not merely lose its holder — its work
shipped, and releasing it back to open+ready_to_fire re-advertises finished work as a
live pickup target. `_unclaim` refuses those writes already (handoff_transition.py ::
`_find_implemented_governing_plan`), so this is a REPORTING fix, not a safety one: the
refusal surfaced as `release attempt(s) FAILED`, indistinguishable from a broken tool,
and `--dry-run` promised a release that could not happen. Same join, imported not
re-derived (`build_implemented_plan_index`), built once per run — the per-lookup form
cost 406ms of process time for 16 orphans against a 533-plan corpus, over the whole
run's 500ms budget on its own.
Disposition is `skip`, NOT auto-ship. An implemented plan can still govern a handoff
with genuinely open work, so plan status is a sufficient oracle for "do not release"
and an insufficient one for "ship" — shipping on it would be the stealth-skip
disposition in costume. Ship-or-discharge on these is an operator call.

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
    authored_by == the dead consumed_by session id. Zero means no terminal ceremony
    ran; two+ is ambiguous. Either fails closed. This is the ONLY ship-signal source;
    no claude-klabauter/ceremony coupling. Served from a completion index built ONCE per run
    (_resolve_completion_index) — this used to spawn `query-completions.py` TWICE per
    orphan, which was 9 of the 11.6s this script cost; see that resolver's docstring.
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
coordinator_core.session.liveness.session_live() (in-process import via the engine root, no
subprocess, no bash re-exec). Does NOT mutate frontmatter directly — every mutation is
delegated to bin/archive-stamp-cli's stamp-shipped-in / ship-handoff / unconsume-handoff
verbs (a Python trampoline into claude-klabauter coordinator_core.archive_stamp — no node spawn),
single-writer invariant, AC5.
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from handoff_lifecycle import is_claimed_status  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags  # noqa: E402

_ARCHIVE_STAMP_CLI = os.path.join(_SCRIPT_DIR, "archive-stamp-cli.py")


def _resolve_session_live():
    """Import coordinator_core.session.liveness.session_live via the engine root.

    In-process import (no subprocess, no bash) — mirrors the direct-import
    trampoline shape used by aggregate-chain-loe.py / query-completions.py.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.session.liveness import session_live
    return session_live


def _resolve_find_archived_twin_by_handoff_id():
    """Import coordinator_core.handoff_creation_guard.find_archived_twin_by_handoff_id
    via the engine root.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    Shares the archived-twin match predicate with the creation-side guard
    (``coordinator_core.handoff_creation_guard.assert_no_archived_twin``) so
    the two guards — this reaper's SKIP path and the creation guard's RAISE
    path — cannot silently drift apart on what counts as a "twin". See
    ``_handoff_id_archived_twin`` below for the thin wrapper that preserves
    this script's own str-path-or-"" return shape.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.handoff_creation_guard import find_archived_twin_by_handoff_id
    return find_archived_twin_by_handoff_id


def _resolve_claim_state():
    """Import coordinator_core.claim_state.resolve_claim_state via
    the engine root.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    C1 (commit 1194eb3f4) landed this as the canonical ledger-first claim
    accessor — ledger wins whenever it holds a LIVE claim (regardless of
    what the frontmatter mirror says); a dead ledger holder degrades to
    ``source: "mirror"``/``"none"``, never ``"ledger"``. See
    ``_claim_holder`` below for how this reaper consumes it.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.claim_state import resolve_claim_state
    return resolve_claim_state


def _resolve_handoff_has_live_children():
    """Import coordinator_core.ops.handoff_children._handoff_has_live_children
    and coordinator_core.git.repo_root.git_common_dir via the engine root.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    Amplification burn-down (state/ledgers/amp-wave4-worklist.md W2):
    ``_has_live_children_exit_code`` previously spawned
    ``handoff-has-live-children.py`` as a subprocess per orphan, and that
    script itself spawns a SECOND subprocess (``cc_invoke.route()`` into
    ``coordinator_core.invoke``) to reach this exact op — two spawns per
    orphan for a pure read (``handoff.has_live_children`` is
    ``OpClass.COMPUTE_ONLY``). This resolver goes straight to the op
    function, mirroring how this file already reaches ``session_live`` /
    ``resolve_claim_state`` / ``canonical_kind`` in-process rather than via
    a CLI veneer — zero spawns per orphan instead of two, and no per-item
    register entry, per the ledger's own guidance to check the walking
    seams before exempting a primitive-absence claim.

    ``git_common_dir`` (``coordinator_core.git.repo_root``) resolves the op's
    expected ``repo_root`` param (the git COMMON dir — see that op's own
    ``main_worktree_root`` derivation) purely by filesystem walk, never a
    subprocess — the CLI veneer got this for free from its router; calling
    the op directly means resolving it ourselves.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.git.repo_root import git_common_dir
    from coordinator_core.ops.handoff_children import has_live_children_many
    return has_live_children_many, git_common_dir


def _resolve_completion_index():
    """Import coordinator_core.ops.ceremony.records_query.query_records via
    the engine root and return a builder for the completion-log index.

    Same in-process import trampoline as ``_resolve_session_live`` above, and
    the same amplification burn-down that already moved ``session_live`` /
    ``canonical_kind`` / ``handoff_has_live_children`` off their CLI veneers.
    P3 (the completion-entry oracle) was the last per-orphan spawn site in
    this script: it ran ``query-completions.py --where authored_by=<id>``
    TWICE per orphan (once for ``--format paths``, once for ``--format
    json``), each a fresh interpreter at ~175ms. Measured on this box before
    the change: **11,640ms process time across 53 processes** for a
    26-orphan dry-run, against DR-344's 500ms bar — the spawns were ~9s of
    it. `query-completions.py` is the SAME op behind that CLI
    (`coordinator_core.ops.query_completions` forwards to `query_records`),
    so this reaches the oracle directly rather than through two interpreter
    starts per orphan.

    The whole completion log is read ONCE (546 records, 62ms process time)
    and grouped by ``authored_by``, so P3 becomes a dict lookup. This is the
    same fix shape C13 already applied to P4's ``git show`` — that chunk
    batched the git-spawning leg and left this one per-orphan.

    `limit=0` is unbounded. The CLI path this replaces passed no `--limit`
    and so inherited `query_completions._DEFAULT_LIMIT = 50`; that cap never
    changed a verdict, because P3 fails closed on anything other than
    EXACTLY one entry and a capped result is still `!= 1`. Unbounded here
    keeps the same verdict while removing a silent truncation from the read.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.ceremony.records_query import query_records

    def build(repo_root: str) -> dict:
        index: dict = {}
        records = query_records("completion", Path(repo_root), where=None, since=None, limit=0)
        for record in records:
            if not isinstance(record, dict):
                continue
            frontmatter = record.get("frontmatter")
            if not isinstance(frontmatter, dict):
                continue
            authored_by = frontmatter.get("authored_by")
            if not isinstance(authored_by, str) or not authored_by.strip():
                continue
            index.setdefault(authored_by.strip(), []).append(record)
        return index

    return build


def _resolve_implemented_plan_index():
    """Import coordinator_core.ops.handoff_transition.build_implemented_plan_index
    via the engine root.

    Same in-process import trampoline as ``_resolve_session_live`` above. This
    is the SAME join `_unclaim` itself consults before refusing a release
    (`handoff_transition._find_implemented_governing_plan` is a lookup over
    this index), imported rather than re-derived so the reaper's pre-check and
    the writer's refusal can never disagree about which handoffs are governed
    by an implemented plan.

    The index is built ONCE per run and shared across every orphan: the
    per-lookup form measured 406ms of process time for 16 orphans against a
    533-plan corpus, which alone exceeds the 500ms end-to-end budget for the
    whole run. Built: 78ms; each lookup is then a dict hit.
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.ops.handoff_transition import build_implemented_plan_index
    return build_implemented_plan_index


def _resolve_canonical_kind():
    """Import coordinator_core.frontmatter.baton_class.canonical_kind via
    the engine root.

    Same in-process import trampoline as ``_resolve_session_live`` above.
    De-aliases a still-live PRE-rename `kind` value (e.g. `spinoff-roadmap`)
    to its D1 successor (`roadmap-baton`) — the single canonical normaliser,
    not a hand-rolled retired/canonical pair (see that module's own
    "Vocabulary bridge" section).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.frontmatter.baton_class import canonical_kind
    return canonical_kind


# ---------------------------------------------------------------------------
# Field-extraction helper — same single-key frontmatter-scan idiom as the
# retired bash's awk-based _fm_field (mirrors sweep-shipped-handoffs.sh
# process_file).
# ---------------------------------------------------------------------------
def _fm_fields(path: str, keys: "tuple") -> dict:
    """Read SEVERAL frontmatter keys from ONE file open.

    Byte-for-byte the same single-key scan `_fm_field` does — same
    frontmatter delimiting, same `startswith(key + ":")` match, same
    single-matched-quote-pair strip, same "" for a missing key — just not
    reopening the file once per key. Pass 1 reads five keys per handoff, so
    the per-key open was four opens of avoidable I/O on every node in the
    corpus.

    Deliberately NOT switched to `dag._read_meta`: that returns PARSED YAML,
    where this file's comparisons (`is_claimed_status`, `== "in_flight"`,
    `canonical_kind`) are all written against the raw scanned string. Swapping
    the reader would quietly change value shapes (a YAML-parsed date or number
    is not the string this scan yields) on the corpus's own liveness path.
    Fewer opens, identical strings.
    """
    remaining = set(keys)
    out = {k: "" for k in keys}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            in_fm = False
            for line in fh:
                if not remaining:
                    break
                stripped_line = line.rstrip("\n").rstrip("\r")
                if not in_fm:
                    if stripped_line.strip() == "---":
                        in_fm = True
                    continue
                if stripped_line.strip() == "---":
                    break
                for key in tuple(remaining):
                    prefix = key + ":"
                    if stripped_line.startswith(prefix):
                        val = stripped_line[len(prefix):].strip()
                        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                            val = val[1:-1]
                        out[key] = val
                        remaining.discard(key)
                        break
    except OSError:
        return {k: "" for k in keys}
    return out


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



def _build_holder_census(handoffs_dir: str, repo_root: str) -> dict:
    """One walk of state/handoffs/ + archive/handoffs/ returning
    ``{claim_holder: count}`` -- P2's bounded-scan oracle.

    P2 asks a per-session question ("did this dead holder claim EXACTLY one
    handoff?"), but answering it inside the per-orphan predicate meant
    re-walking the whole corpus once per orphan: 18 orphans against ~950
    handoffs measured 17,133 ``_claim_holder`` calls and 6.3s of an 8.3s run.
    The census is the same walk done once; the predicate becomes a lookup.

    Verdict-preserving, not merely faster: ``_claim_holder`` is the same
    ledger-first accessor the per-orphan scan used, applied to the same two
    directories in the same order, so a session's count here is exactly the
    ``match_count`` that scan produced. Sessions with no claim never enter the
    census, and ``.get(sid, 0) != 1`` fails closed for them exactly as
    ``match_count != 1`` did.
    """
    census: dict = {}
    for h in glob.glob(os.path.join(handoffs_dir, "*.md")):
        if not os.path.isfile(h):
            continue
        holder = _claim_holder(h, repo_root=repo_root)
        if holder:
            census[holder] = census.get(holder, 0) + 1

    archive_handoffs_dir = os.path.join(repo_root, "archive", "handoffs")
    if os.path.isdir(archive_handoffs_dir):
        for h in glob.glob(os.path.join(archive_handoffs_dir, "**", "*.md"), recursive=True):
            if not os.path.isfile(h):
                continue
            holder = _claim_holder(h, repo_root=repo_root)
            if holder:
                census[holder] = census.get(holder, 0) + 1
    return census


def _shipped_orphan_candidate(
    consumed_by: str,
    this_handoff: str,
    handoffs_dir: str,
    repo_root: str,
    completion_index: Optional[dict] = None,
    holder_census: Optional[dict] = None,
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
    # Served from the caller's one-shot holder census (see _build_holder_census).
    # Counted per-orphan, this walked state/handoffs/ + archive/handoffs/ in full
    # and called `_claim_holder` on every file EACH TIME -- 18 orphans against
    # ~950 handoffs was 17,133 calls / 6.3s of the run. The census answers the
    # same question ("how many handoffs did this session claim?") from one walk.
    # `None` (a standalone caller with no prebuilt census) walks it here, so
    # this predicate stays callable on its own; `main()` passes one built once.
    if holder_census is None:
        holder_census = _build_holder_census(handoffs_dir, repo_root)
    if holder_census.get(consumed_by, 0) != 1:
        return None

    # P3 — completion-entry oracle (DoE-local ONLY; no claude-klabauter/ceremony coupling).
    # Exactly one completion-log entry authored by the dead session. Zero means
    # no terminal ceremony ran; two+ is ambiguous. Either fails closed.
    # Served from the caller's one-shot index (see _resolve_completion_index)
    # rather than two `query-completions.py` spawns per orphan. The predicate
    # is unchanged: EXACTLY one entry authored by the dead session, zero or
    # two-plus fails closed.
    matched = (completion_index or {}).get(consumed_by) or []
    if len(matched) != 1:
        return None

    entry = matched[0] if isinstance(matched[0], dict) else {}
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
    completion_index: Optional[dict] = None,
    holder_census: Optional[dict] = None,
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
    candidates = _shipped_orphan_candidate(
        consumed_by, this_handoff, handoffs_dir, repo_root, completion_index, holder_census
    )
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


def _has_live_children_exit_code(handoff_path: str, repo_root: str) -> int:
    """Reverse-membership crash-orphan guard for the clean release fall-through.

    The ordinary crash shape this guards against: a session runs /handoff under
    context pressure and dies before /workstream-complete, so its predecessor
    node's completion-log entry never lands (P3 above returns ""), and the
    orphan falls through to claim-release — resurrecting into the ready_to_fire
    pool a node whose own successor already exists. Delegates to the same
    handoff.has_live_children reverse-membership predicate the /handoff
    chain-archival path and fleet.archive_completed_handoffs already consult;
    this reaper was the one lifecycle writer that didn't. Fail-closed: any
    resolution/import/op failure returns 2 (indeterminate), never 1 (safe to
    release).

    Calls the op in-process (see ``_resolve_handoff_has_live_children``) —
    zero subprocess spawns, not a CLI veneer. ``repo_root`` is this script's
    own resolved worktree root (``resolve_checked_repo_root``'s
    ``_show_toplevel``-derived value); the op itself expects the git COMMON
    dir, so it is re-derived here via ``git_common_dir`` rather than
    threading the worktree root straight through.
    """
    return _has_live_children_exit_codes([handoff_path], repo_root).get(handoff_path, 2)


def _has_live_children_exit_codes(handoff_paths: list, repo_root: str) -> dict:
    """``{path: exit_code}`` for the whole fall-through set, from ONE corpus pass.

    Delegates to ``handoff_children.has_live_children_many`` — the same guards
    and the same verdicts as the singular op, with the reverse-edge index built
    once instead of per candidate. Asking per orphan cost 36,638 ``_read_meta``
    calls (19 orphans x ~950 handoffs) and was the entire remaining 3.1s of this
    script's process time; the index primitive it now routes through
    (``dag.build_reverse_edge_index``) already existed and was already in
    production behind ``fleet.archive_terminal_handoffs``.

    Fail-closed per path exactly as before: 2 (indeterminate) on any resolution,
    import, or op failure, never 1 (safe to release).
    """
    if not handoff_paths:
        return {}
    try:
        has_live_children_many, git_common_dir = _resolve_handoff_has_live_children()
    except (RuntimeError, ImportError):
        return {p: 2 for p in handoff_paths}

    common_dir = git_common_dir(cwd=repo_root)
    if not common_dir:
        return {p: 2 for p in handoff_paths}

    try:
        return asyncio.run(
            has_live_children_many(list(handoff_paths), repo_root=Path(common_dir))
        )
    except Exception:
        return {p: 2 for p in handoff_paths}


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
        # applied to _resolve_session_live() above (same engine-root
        # sys.path trampoline); a stale sibling checkout predating this
        # migration must fail loud with a clean message, not a raw
        # traceback. See _PRE_RENAME_ALIASES's module docstring: a
        # half-migrated fleet is the normal state, not a hypothetical.
        print(f"reap-orphaned-in-flight-handoffs.py: canonical-kind resolver not importable: {exc}", file=sys.stderr)
        return 2

    # P2's oracle: one walk of state/ + archive/handoffs/, shared by every
    # orphan (see _build_holder_census).
    holder_census = _build_holder_census(handoffs_dir, repo_root)

    # Both indexes are built ON FIRST USE, not up front: they cost 109ms and
    # 78ms of whole-corpus reading, and neither is consulted at all unless an
    # orphan actually reaches its gate. A clean corpus — the steady state once
    # the backlog is drained, and the overwhelmingly common case for a sweep
    # that runs on a cadence — should not pay 187ms to answer nothing. Each
    # still builds at most once per run.
    _index_cache: dict = {}

    def _completion_index() -> dict:
        if "completion" not in _index_cache:
            try:
                _index_cache["completion"] = _resolve_completion_index()(repo_root)
            except (RuntimeError, ImportError) as exc:
                # Fail CLOSED to an empty index. P3 then matches nothing, every
                # ship-check fails closed, and each orphan falls through to the
                # release path — the same disposition an unreadable completion
                # log already produced. Never a wrong ship.
                print(
                    f"reap-orphaned-in-flight-handoffs.py: completion-log index not importable: {exc}; "
                    "ship-check disabled for this run (every orphan falls through to release)",
                    file=sys.stderr,
                )
                _index_cache["completion"] = {}
        return _index_cache["completion"]

    def _implemented_plan_index() -> dict:
        if "plans" not in _index_cache:
            try:
                _index_cache["plans"] = _resolve_implemented_plan_index()(Path(repo_root))
            except (RuntimeError, ImportError) as exc:
                # Same fail-loud posture. Fail CLOSED to an empty index rather
                # than exiting: an unresolvable index means the governed-plan
                # pre-check below can't fire, which restores exactly the
                # pre-fix behaviour (attempt the release, let `_unclaim` refuse
                # it) — degraded reporting, never a wrong write.
                print(
                    f"reap-orphaned-in-flight-handoffs.py: implemented-plan index not importable: {exc}; "
                    "governed-plan pre-check disabled for this run",
                    file=sys.stderr,
                )
                _index_cache["plans"] = {}
        return _index_cache["plans"]

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
    skipped_plan_implemented = 0
    would_skip_plan_implemented = 0
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

            # One open serves every key pass 1 needs off this node.
            fm = _fm_fields(f, ("status", "deployment_state", "handoff_id", "kind", "deliverable_id"))
            status = fm["status"]
            deployment_state = fm["deployment_state"]

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
            handoff_id = fm["handoff_id"]
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
            kind = fm["kind"]
            deliverable_id = fm["deliverable_id"]
            candidates = None
            if not (canonical_kind(kind) == "roadmap-baton" and deliverable_id):
                candidates = _shipped_orphan_candidate(
                    claim_holder, f, handoffs_dir, repo_root, _completion_index(), holder_census
                )
                if candidates:
                    all_candidate_shas.update(candidates)

            pending.append(
                {
                    "path": f,
                    "claim_holder": claim_holder,
                    "candidates": candidates,
                    # Carried for the governed-plan pre-check in pass 2 — read
                    # here rather than re-read there so the disposition and the
                    # ship-check's P1 gate see the SAME frontmatter snapshot.
                    "kind": kind,
                    "deliverable_id": deliverable_id,
                }
            )

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
    # One corpus pass answers the live-children guard for every fall-through
    # candidate (see _has_live_children_exit_codes). `sha` is pure in-memory
    # selection against the already-batched timestamp map, so the release-path
    # set is knowable up front; a sha-truthy orphan takes the ship path and
    # never consults the guard.
    #
    # This set is a mild SUPERSET -- an orphan that short-circuits later in the
    # disposition loop is answered here anyway. That was a real cost when each
    # answer re-walked the corpus, and is now a dict lookup against an index
    # built once, so the superset is free where it used to be the defect.
    guard_codes = _has_live_children_exit_codes(
        [
            item["path"]
            for item in pending
            if not (_best_shipped_sha(item["candidates"], sha_ct) if item["candidates"] else "")
        ],
        repo_root,
    )

    for item in pending:
        f = item["path"]
        claim_holder = item["claim_holder"]
        candidates = item["candidates"]
        orphan_kind = item["kind"]
        orphan_deliverable_id = item["deliverable_id"]
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
            guard_exit = guard_codes.get(f, 2)
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

        # Governed-plan pre-check — release is the WRONG verb for an orphan
        # whose governing plan is already stamped `implemented`. That plan
        # shipped, so returning its handoff to open+ready_to_fire re-advertises
        # finished work as a live pickup target: the exact defect this reaper
        # exists to clear. `_unclaim` already refuses these writes, so nothing
        # was ever corrupted — but the refusal surfaced as `release attempt(s)
        # FAILED`, which reads as a tool error rather than as "these need a
        # different verb", and `--dry-run` promised a release that could not
        # happen. Checking here makes both honest.
        #
        # NOT auto-shipped. Plan status alone is not a sufficient oracle: an
        # implemented plan can still have a handoff carrying genuinely open
        # work (`state/handoffs/2026-08-25_193508_the-scoped-commit-rebuilt-
        # from-first-principles.md` declares two open P1s and a blocking PM
        # decision under an implemented plan). Shipping on plan status would
        # be the stealth-skip disposition in costume, so the disposition is
        # `skip` — counted, named, non-terminal — matching the live-children
        # guard above and the 2026-07-20 PM ruling that no automated writer in
        # this family resolves a handoff a session never resolved.
        #
        # Kind exemption mirrors `_unclaim`'s own (C3, docs/plans/2026-08-18-a-
        # spinoff-is-not-its-parents-deliverable.md): a `kind: spinoff`
        # record's `deliverable_id` is an inherited id, not a true join onto
        # the plan it matches.
        if not sha and orphan_deliverable_id and canonical_kind(orphan_kind) != "spinoff":
            governing_plan = _implemented_plan_index().get(orphan_deliverable_id)
            if governing_plan is not None:
                reason = (
                    f"governing plan {governing_plan['title']!r} ({governing_plan['path']}) is "
                    "stamped implemented — needs ship-or-discharge adjudication, not release"
                )
                if dry_run:
                    print(f"reap-orphaned-in-flight-handoffs.py: [dry-run] would skip {f} ({reason})")
                    would_skip_plan_implemented += 1
                else:
                    print(f"reap-orphaned-in-flight-handoffs.py: skip: {f} — {reason}", file=sys.stderr)
                    skipped_plan_implemented += 1
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
        if would_skip_plan_implemented > 0:
            print(
                f"{would_skip_plan_implemented} orphaned in_flight handoffs would be skipped "
                "(governing plan implemented — ship or discharge, never release; dry-run)"
            )
    else:
        if skipped_by_guard > 0:
            print(f"{skipped_by_guard} orphaned in_flight handoffs skipped (live-children guard)")
        if skipped_plan_implemented > 0:
            print(
                f"{skipped_plan_implemented} orphaned in_flight handoffs skipped "
                "(governing plan implemented — ship or discharge, never release)"
            )
        if skipped_archived_duplicate > 0:
            print(
                f"{skipped_archived_duplicate} orphaned in_flight handoffs skipped "
                "(archived-twin guard)"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
