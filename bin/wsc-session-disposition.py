# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# wsc-session-disposition — naked-Python port of the workstream-complete Step 0
# "Session-Shape Detection" block (DoE-claude
# coordinator/skills/workstream-complete/SKILL.md, the `<!-- VERBATIM -->`
# fence at its Step 0). No cc_invoke/IPC hop — this is pure resolution logic
# operating on git and the filesystem, plus one subprocess call out to the
# sibling `session-claim-cli` entrypoint for Detector C's liveness
# enumeration, and (as of the ledger-first authoritative-read plan, chunk C7)
# one `coordinator_core.claim_state.resolve_claim_state` import for the
# claim-holder reads below, plus (2026-08-20, `docs/plans/2026-08-20-wsc-
# identity-gates-key-on-the-deliverable.md` C1) `coordinator_core.
# workstream_complete.session_identity.session_deliverable_ids` — a pure,
# stdlib-only leaf module, the fourth sanctioned coordinator_core import; every
# other helper here stays self-contained by the same discipline the rest of
# this module's comments still describe.
#
# Ported under docs/plans/2026-07-23-skills-carry-no-code-extirpation.md
# (M3 chunk WSC-1) — moves the 5-way session-id resolution + 3-detector
# (live-consume / archive-provenance / crash-recovery scope-intersection)
# chain-terminal disposition resolver out of the DoE skill's bash fence and
# into a single naked-Python CLI the skill can call by name. The D2 repoint
# (a later plan wave) rewrites the DoE skill's Step 0 fence to invoke this
# CLI instead of running the resolver logic inline; this file lands first so
# that repoint has something to call.
#
# P6 (epoch-tail fabricated-id fallback) REMOVED — KS-5, 2026-08-07: a
# fabricated id is different on every invocation and indistinguishable from
# a real one downstream, which turned an unidentifiable session into a
# passing single-session disposition (the same false-clean failure mode the
# P4/.current-session-id sentinel removal fixed, reached by a different
# route). `resolve_session_id` now returns "" when no tier resolves, and
# `_cmd_resolve` refuses to run the detector chain against it — see
# `resolve_session_id` and `_cmd_resolve` below.
#
# Resolution stack this CLI replaces (see SKILL.md Step 0 for the full
# rationale prose, preserved here only where it disambiguates a corner case):
#   Session-id 5-way superset resolution (AC2b):
#     P1 em_sid env var, then P2 CLAUDE_SESSION_ID, then P3
#     CLAUDE_CODE_SESSION_ID, then P4 REMOVED (KS-3, 2026-08-07 — was the
#     .current-session-id sentinel; unsound under concurrency + its sole
#     writer deleted 2026-07-15, see resolve_session_id() below), falls
#     through directly to P5 the hex-timestamp fallback.
#   Disposition = chain-terminal iff ANY of:
#     - primary scan: a LIVE state/handoffs/ entry stamped
#       claimed_by/consumed_by: <this session> (DR-084 dual-read: both key
#       names are schema-legal through the P0-P3 migration window; first
#       match in file line order wins, not either name's "preference").
#     - Detector A: an ARCHIVED handoff (archive/handoffs/) naming this
#       session as claimed_by/consumed_by AND carrying a predecessor: field
#       (catches ship-then-archive / awaiting_gate / direct-ship / repark
#       churn / session-id skew / async-sweep-archival-between-consume-and-WSC,
#       i.e. cases where no LIVE claim stamp survived to be caught by the
#       primary scan).
#     - Detector B: git provenance — this session's own commits (matched by
#       the `Session-Id:` trailer) archived (A/R/C, --find-renames) a
#       `archive/handoffs/*.md` file THIS run, net of a foreign-consumer
#       spoof guard (a restoration/fix commit that re-ADDS another session's
#       archived handoff, e.g. recovering a file a stale shared-index commit
#       deleted, must not be misread as this session's own chain-terminal
#       ship — see `_foreign_consumer_guard`).
#     - Detector C: crash-recovery — a stale LIVE claim (its claiming session
#       died before it could ship/archive) whose handoff's `scope:` block
#       intersects (exact-file or directory-prefix) the set of paths THIS
#       session committed this run, disambiguated via
#       `session-claim-cli list-stale-claim-handoffs` liveness enumeration.
#       FAIL-LOUD on any resolution failure along this path (missing CLI,
#       non-zero exit, unresolvable merge-base) — such a failure means
#       liveness is INDETERMINATE, never "no stale batons": an infra failure
#       reading as a clean negative is the exact fail-open this detector
#       exists to close.
#
# Spec backlinks (rationale for individual corner cases, preserved from the
# ported bash — see SKILL.md Step 0 for the full inline commentary):
#   cross-repo/inbox/2026-07-21-claude-klabauter-em-wsc-chain-terminal-detection-fails-open.md
#   cross-repo/inbox/2026-07-22-claude-klabauter-em-dr084-skill-layer-raw-frontmatter-reads-break.md
#   cross-repo/inbox/2026-07-23-claude-klabauter-em-liveness-primitive-landed.md
#   cross-repo/inbox/2026-07-23-claude-klabauter-em-wsc-step0-fails-open-crash-recovery.md
#   DR-084 remainder baton: state/handoffs/2026-07-22_152437_dr084-skill-layer-dual-read.md
#   (DoE-claude repo; these inbox/state paths do not resolve in this repo —
#   quoted here only as provenance, not as a live citation).
#
# Exit codes: 0 on a completed resolution (chain-terminal OR single-session —
# both are valid answers, not failures). 2 usage error (bad/missing
# subcommand or flag). 3 transport failure — repo root unresolvable (no
# `--repo-root` and `git rev-parse --show-toplevel` failed). 4 session id
# unresolvable — no tier (em_sid/CLAUDE_SESSION_ID/CLAUDE_CODE_SESSION_ID)
# resolved (KS-5, 2026-08-07): refusing to run the detector chain against an
# unidentified session, rather than reporting a single-session disposition
# that would read as a clean chain-end coverage gate skip. Detector-level
# resolution failures (missing session-claim-cli, non-zero CLI exit,
# unresolvable merge-base) do NOT propagate to the process exit code — they
# print a WARN to stderr and resolve the disposition as best-effort
# single-session, exactly mirroring the ported bash's fail-loud-but-continue
# shape (a human/CI reads the WARN; the ceremony does not hard-stop).
from __future__ import annotations

"""wsc-session-disposition — see the # comment block above for the RAG-bait
purpose text (the polyglot shebang line above makes this triple-quoted
string a silently-discarded expression statement, not the module __doc__ —
same convention as archive-stamp-cli / session-claim-cli)."""

import argparse
import functools
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, NamedTuple

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")

# Bound by `_bootstrap_engine_imports()` -- keeps this module's own body
# import-purity clean (module-scope non-stdlib import) the same way every
# other allowlisted coordinator/bin/ CLI now does.
#
# THIS FILE HAS TWO ENTRY PATHS AND BOTH MUST BOOTSTRAP. `main()` is the CLI
# path. The other is in-process: coordinator_core.workstream_complete's
# `compute_session_shape_gate` loads this file by path and calls
# `resolve_disposition` directly, never touching `main()`. When only `main()`
# bootstrapped, that library path left every name below at None and
# `/workstream-complete` died for every session with `'NoneType' object is not
# callable` -- an error naming neither this file nor the unbound name. Any new
# entry point added here calls `_bootstrap_engine_imports()` first; it is
# idempotent, so calling it again costs a dict lookup.
resolve_claim_state = None
show_toplevel = None
rel_id = None
session_deliverable_ids = None

# Idempotence guard for `_bootstrap_engine_imports`, deliberately a DEDICATED
# sentinel rather than reusing one of the four names above (e.g.
# `resolve_claim_state is not None`). A name-keyed guard couples "which name
# the guard tests" to "which name is assigned last" invisibly — reorder the
# four assignments below (e.g. for readability) and the guard silently starts
# testing a name that is no longer assigned last, reintroducing the
# partial-bind failure mode this whole function exists to close (review:
# coordinator-code-reviewer, P2 finding on `_bootstrap_engine_imports`). This
# flag is set in exactly one place, after all four assignments succeed, so no
# reordering of the assignments above it can desync it from "all four are
# bound".
_ENGINE_IMPORTS_BOUND = False


def _bootstrap_engine_imports() -> None:
    """Bind this module's engine-side names. Idempotent by design -- every
    entry point calls it, and re-entry after a successful bind is a no-op."""
    global resolve_claim_state, show_toplevel, rel_id, session_deliverable_ids
    global _ENGINE_IMPORTS_BOUND

    if _ENGINE_IMPORTS_BOUND:
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    cc_invoke.ensure_engine_on_path(__file__)

    from coordinator_core.claim_state import resolve_claim_state as _resolve_claim_state
    from coordinator_core.git.repo_root import show_toplevel as _show_toplevel
    from coordinator_core.wire_paths import rel_id as _rel_id
    from coordinator_core.workstream_complete.session_identity import (
        session_deliverable_ids as _session_deliverable_ids,
    )

    resolve_claim_state = _resolve_claim_state
    show_toplevel = _show_toplevel
    rel_id = _rel_id
    session_deliverable_ids = _session_deliverable_ids
    _ENGINE_IMPORTS_BOUND = True


_TRANSPORT_FAIL = 3
_SESSION_ID_UNRESOLVED = 4


# ---------------------------------------------------------------------------
# Session-id 5-way superset resolution (AC2b)
# ---------------------------------------------------------------------------


def resolve_session_id(_repo_root: Path) -> str:
    """Resolve the current session id, first hit wins: the em_sid env var, then
    CLAUDE_SESSION_ID, then CLAUDE_CODE_SESSION_ID, then a hex-timestamp
    fallback (last 6 digits of the current epoch second, mirroring the
    ported bash's `date +%s | tail -c 7 | head -c 6`).

    `_repo_root` is unused by this env-var-only resolution — kept for call
    signature conformance with `_cmd_resolve`'s call site and this module's
    own test suite, both of which pass a repo root positionally.

    The `.current-session-id` sentinel tier that used to sit here was
    REMOVED (KS-3, 2026-08-07): unsound under concurrency (documented
    last-writer-wins across concurrent sessions sharing one worktree — see
    coordinator_core/bash_guards/guard_inprocess_search.py ~L84) AND its
    sole writer (session-init.py, the DoE-claude SessionStart hook) was
    deleted by PM directive 2026-07-15 — no production writer survives.

    The hex-timestamp fallback that used to sit BELOW the sentinel was
    REMOVED (KS-5, 2026-08-07): a fabricated id is different on every
    invocation and indistinguishable to a downstream reader from a real
    one — strictly worse than the sentinel it sat below, which at least
    named a session that once existed. Returns "" when no tier resolves;
    `_cmd_resolve` refuses to run the detector chain against an empty sid
    rather than let it silently resolve "single-session" (the same
    false-clean failure mode the sentinel removal fixed, reached by a
    different route)."""
    for var in ("em_sid", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


# ---------------------------------------------------------------------------
# Primary scan — live state/handoffs/ consume-stamp
# ---------------------------------------------------------------------------


class PrimaryScanResult(NamedTuple):
    """`primary_consumed_handoff_scan`'s two disjoint sets. `adopted` is what
    the live-consume leg may resolve against; `mirror_conflicts` is the
    ledger-vs-mirror HOLDER MISMATCH set — a claim the ledger says this
    session holds while the tracked frontmatter positively names a DIFFERENT
    session. Both repo-relative POSIX, both sorted."""

    adopted: list[str]
    mirror_conflicts: list[str]


def primary_consumed_handoff_scan(repo_root: Path, sid: str) -> PrimaryScanResult:
    """This bin script's OWN detector set: every file under state/handoffs/
    whose claim state — resolved ledger-first via
    `coordinator_core.claim_state.resolve_claim_state`, frontmatter mirror
    as fallback (C1, plan `2026-08-07-claim-state-ledger-first-authoritative-
    read.md`) — names `sid` as holder, collected and sorted. Was previously
    an UNANCHORED regex `(claimed_by|consumed_by):\\s*<sid>` scanned directly
    over file text, which only ever saw the frontmatter mirror; a claim held
    only in the branch-independent ledger (mirror desynced by a branch
    switch — see `claim_state.py`'s module docstring for the incident this
    closes) was invisible to it. Deliberately NOT the same computation as
    branch_resolution.py's anchored `step0_evidence["consumed_handoff_paths"]`
    one layer down — this is a self-contained local scan, not a cross-package
    agreement.

    HOLDER-MISMATCH PARTITION (2026-08-26). A ledger-resolved holder match
    whose frontmatter mirror positively names a DIFFERENT session is NOT
    evidence that this session consumed that baton — it is the residue of an
    INCOMPLETE takeover. `pickup_assemble.apply` promotes the ledger claim to
    `apply` stage BEFORE any directive runs; a run that then halts at
    `claim_grant` (or fails) leaves that durable ledger claim behind with
    `d2`'s frontmatter stamp never landed. The mirror still names the peer
    who actually holds the baton, and the ledger names a session that only
    ever read it. Adopting that as `predecessor-consumed` caps a PEER's
    workstream: the live incident (2026-08-26, session
    2f937280 vs. baton holder 24d63e82 on
    `state/handoffs/2026-08-22-warm-engine-and-door-install-from-published-
    root.md`) resolved predecessor-consumed against a peer's in_flight baton
    and stood `d-complete-entry` down as "already exists for chain", so the
    session's own work got no completion entry.

    Narrower than "any ledger/mirror disagreement", and deliberately the
    complement of `ClaimState.disagreement`: the branch-switch-revert case
    this whole ledger-first read exists for leaves the mirror EMPTY
    (`mirror_holder is None`), which stays in `adopted` untouched. Only a
    mirror that positively names somebody else is partitioned out — see
    `ClaimState.disagreement`'s own docstring, which records that a
    same-slot holder mismatch is left for callers to detect via
    `ledger_holder`/`mirror_holder`. This is that caller.

    Negative-spec: does NOT release, demote, or otherwise mutate the
    conflicting ledger claim — read-only, like every other leg here. The
    conflict is reported to the caller so the disposition can decline to
    rest on it; reaping it belongs to the claim-hygiene surface, not to a
    session-shape detector."""
    handoffs_dir = repo_root / "state" / "handoffs"
    if not handoffs_dir.is_dir():
        return PrimaryScanResult([], [])
    matches: list[Path] = []
    conflicts: list[Path] = []
    for f in handoffs_dir.rglob("*"):
        if not f.is_file():
            continue
        state = resolve_claim_state(f, repo_root=repo_root)
        if state.holder != sid:
            continue
        if state.mirror_holder and state.mirror_holder != sid:
            conflicts.append(f)
        else:
            matches.append(f)
    matches.sort()
    conflicts.sort()
    # POSIX separators, not the native ones: this value becomes the ceremony's
    # `consumed_handoff` wire-id — it is written into frontmatter, exported as
    # WSC_CONSUMED_HANDOFF, and string-compared against handoff paths recorded
    # by other sessions and other platforms. A backslashed form compares
    # unequal to the same handoff recorded anywhere else. `repo_root / value`
    # still resolves correctly on Windows, which accepts forward slashes.
    return PrimaryScanResult(
        [f.relative_to(repo_root).as_posix() for f in matches],
        [f.relative_to(repo_root).as_posix() for f in conflicts],
    )


def primary_consumed_handoff_paths(repo_root: Path, sid: str) -> list[str]:
    """The ADOPTABLE half of `primary_consumed_handoff_scan` — see that
    function for the holder-mismatch partition this excludes."""
    return primary_consumed_handoff_scan(repo_root, sid).adopted


def primary_consumed_handoff(repo_root: Path, sid: str) -> str | None:
    matches = primary_consumed_handoff_paths(repo_root, sid)
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Detector A — archived handoff naming this session as consumer
# ---------------------------------------------------------------------------


def detector_a(repo_root: Path, sid: str) -> str | None:
    """An ARCHIVED handoff whose claim state — resolved ledger-first via
    `coordinator_core.claim_state.resolve_claim_state`, frontmatter mirror as
    fallback (C1) — names this session as holder AND carries a
    `predecessor:` field. Was previously this function's own private
    UNANCHORED regex `^(claimed_by|consumed_by): +<sid> *$` read directly off
    file text — replaced for the same reason as
    `primary_consumed_handoff_paths` above (a mirror-only read misses a claim
    that survives only in the branch-independent ledger)."""
    archive_dir = repo_root / "archive" / "handoffs"
    if not archive_dir.is_dir():
        return None
    predecessor_re = re.compile(r"^predecessor:", re.MULTILINE)
    candidates = []
    for f in archive_dir.rglob("*"):
        if not f.is_file():
            continue
        state = resolve_claim_state(f, repo_root=repo_root)
        if state.holder == sid:
            candidates.append(f)
    for f in sorted(candidates):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if predecessor_re.search(text):
            # POSIX separators — same wire-id reasoning as the primary scan's
            # own return above.
            return f.relative_to(repo_root).as_posix()
    return None


# ---------------------------------------------------------------------------
# Git plumbing shared by Detector B and Detector C
# ---------------------------------------------------------------------------


def git_merge_base(repo_root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "origin/main", "HEAD"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    base = proc.stdout.strip()
    return base or None


def _git_log_trailer_lines(repo_root: Path, rev_range: str, extra_args: list[str]) -> list[str] | None:
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "log",
        rev_range,
        *extra_args,
        "--format=__SID__ %(trailers:key=Session-Id,valueonly)",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.splitlines()


def _session_scoped_lines(lines: Iterable[str], sid: str) -> list[str]:
    """Walk `__SID__ <sid>`-delimited git-log output, yielding every
    non-empty line that belongs to a commit whose Session-Id trailer equals
    `sid` — the shared state machine behind both Detector B's name-status
    scan and Detector C's committed-paths scan."""
    me = False
    out = []
    for line in lines:
        if line.startswith("__SID__ "):
            commit_sid = line[len("__SID__ "):]
            me = commit_sid == sid
            continue
        if me and line.strip():
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# Detector B — git provenance (this session archived a handoff this run)
# ---------------------------------------------------------------------------

_HANDOFF_PATH_RE = re.compile(r"^archive/handoffs/.*\.md$")

# Unit-separator byte (ASCII 0x1F) delimiting detector_b_shipped_by_me's
# marker-line fields — cannot occur in a commit subject or a Session-Id
# trailer value, unlike whitespace.
_FIELD_SEP = "\x1f"

# Commit-subject prefixes emitted by automated bulk/housekeeping archival
# machinery, never by a session's own targeted action on its own predecessor
# (2026-08-05 chain-terminal misattribution incident, this session's own
# reproduction — session 5bbc9cc8-4b1c-406b-9116-a04ed3692478: a
# `fleet.archive_completed_handoffs` sweep ran inside this session and
# archived ANOTHER session's `archive/handoffs/2026-07/2026-07-10_141606_
# roadmap-qsub-03.md`, and the resulting `fleet: archive 1 completed
# handoff(s)` commit carried THIS session's Session-Id trailer purely
# because the sweep ran inside it. Detector B read that trailer as "I did
# this" and misattributed the archival. Verified against the literal
# emitted text (DoE-claude coordinator_core/ops/fleet/archive_handoffs.py,
# archive_shipped_handoffs.py, session/boot_sweep.py), not paraphrased; no
# distinguishing automation trailer exists beyond the ambient Session-Id
# trailer already consulted above, so subject text is the only signal
# available at this layer.
_SWEEP_ATTRIBUTED_SUBJECT_PREFIXES: tuple = (
    "fleet: archive ",
    "session.boot_sweep: ",
)


def _is_sweep_attributed_subject(subject: str) -> bool:
    """True when `subject` (a commit's first-line message) matches a known
    automated bulk/housekeeping archival prefix — see
    _SWEEP_ATTRIBUTED_SUBJECT_PREFIXES above."""
    return any(subject.startswith(prefix) for prefix in _SWEEP_ATTRIBUTED_SUBJECT_PREFIXES)


def detector_b_shipped_by_me(
    repo_root: Path, sid: str, ship_base: str, diagnostics: list[str]
) -> str | None:
    """First `archive/handoffs/*.md` path this session's commits added,
    renamed, or copied in `ship_base..HEAD` (--diff-filter=ARC
    --find-renames --name-status), EXCLUDING commits whose subject matches a
    known automated bulk/housekeeping archival prefix
    (_SWEEP_ATTRIBUTED_SUBJECT_PREFIXES — see its docstring for the
    2026-08-05 incident this closes). A rejected sweep-attributed candidate
    is routed to `diagnostics` (not silently dropped) and scanning
    continues past it, so a genuinely session-authored archival commit
    elsewhere in the window is still found.

    Widens the shared `git log --format` marker-line shape with the commit
    subject (`%s`), carried ahead of the trailer field: git's
    `%(trailers:...,valueonly)` formatter appends its OWN trailing newline
    after the value (present even for a single trailer) — placing it
    anywhere but last in the format string silently truncates every field
    after it (verified live during this fix)."""
    cmd = [
        "git",
        "-C",
        str(repo_root),
        "log",
        f"{ship_base}..HEAD",
        "--diff-filter=ARC",
        "--find-renames",
        "--name-status",
        "--format=" f"__SID__{_FIELD_SEP}%s{_FIELD_SEP}%(trailers:key=Session-Id,valueonly)",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    commit_is_mine = False
    commit_subject = ""
    for line in proc.stdout.splitlines():
        if line.startswith("__SID__"):
            fields = line.split(_FIELD_SEP)
            # A malformed/truncated marker line (fewer than the expected 3
            # fields) degrades to empty-string here deliberately, rather
            # than being flagged as ambiguous — permissive by choice: git
            # always emits the expected shape for this format string, so
            # this is defense against a shape that shouldn't occur, not an
            # oversight.
            commit_subject = fields[1].strip() if len(fields) > 1 else ""
            trailer_sid = fields[2].strip() if len(fields) > 2 else ""
            commit_is_mine = bool(trailer_sid) and trailer_sid == sid
            continue
        if not commit_is_mine or "\t" not in line:
            continue
        last_field = line.split("\t")[-1].strip()
        if not _HANDOFF_PATH_RE.match(last_field):
            continue
        if _is_sweep_attributed_subject(commit_subject):
            diagnostics.append(
                f"NOTE: Detector B candidate {last_field} rejected — archiving commit "
                f"subject ({commit_subject!r}) matches a known automated bulk/housekeeping "
                "archival prefix, not evidence this session performed the archival itself "
                "(2026-08-05 chain-terminal misattribution incident: a nested fleet-archive/"
                "boot_sweep run carries this session's Session-Id trailer regardless of whose "
                "handoff it swept)"
            )
            continue
        return last_field
    return None


def _origin_session(path: Path) -> str:
    """Non-lifecycle frontmatter read: the record's own `origin_session:`
    scalar, when present — a UUID naming the session that ORIGINATED the
    record (schema rule C2-1c), directly comparable to a resolved session id,
    unlike `authoring_session` (observed path-shaped, not session-id-shaped,
    in this corpus — deliberately NOT consulted here for that reason).
    Returns "" when absent/unreadable. Bounded fence scan (first `---`/`---`
    pair only) — same idiom as handoff_lifecycle._fm_field; this local scan
    stays self-contained rather than routing through this module's one
    coordinator_core dependency (see module docstring)."""
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
                if stripped_line.startswith("origin_session:"):
                    val = stripped_line[len("origin_session:"):].strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                    return val
    except OSError:
        return ""
    return ""


def _foreign_consumer_guard(repo_root: Path, shipped_by_me: str, sid: str) -> tuple[bool, str]:
    """Returns (rejected, reason). `rejected=True` means shipped_by_me must
    NOT be read as this session's own chain-terminal ship, and `reason` is a
    human-readable explanation of which negative-evidence read rejected it.
    `rejected=False` means `reason` is instead `consumer` — the claim
    holder read from `shipped_by_me`'s frontmatter, possibly empty — unused
    by the current call site but carried for any future caller that wires
    it up. Two independent negative-evidence reads, EITHER of which rejects:

      - the ledger-first claim-holder read (`coordinator_core.claim_state.
        resolve_claim_state` — DR-084 dual-tolerant `claimed_by`/
        `consumed_by` mirror fallback, ledger-first when the ledger holds a
        live claim; was previously a mirror-only DR-084 preference read,
        which left this rung DISARMED whenever a claim survived only in the
        branch-independent ledger and the mirror had desynced — see
        `claim_state.py`'s module docstring for the incident this closes): a
        restoration-commit spoof, e.g. re-ADDing another session's archived
        handoff while recovering a file a stale shared-index commit deleted.
      - `origin_session:` (widened 2026-08-05 — chain-terminal
        misattribution incident, this session's own reproduction: a record
        with NO claim holder at all was accepted by the pre-fix guard
        because `consumer` was falsy, and origin_session — naming a
        different session — was never consulted; absence of a claim holder
        is absence of evidence, not evidence of THIS session's ownership,
        and must not fall through to acceptance by default).

    Ownership must be POSITIVELY evidenced (tightened 2026-08-10 — project-rag
    memo `2026-08-10-project-rag-em-wsc-archive-leg-infers-consumption-from-a-
    touch.md`): at least one of the two reads must NAME this session. Both
    reads coming back empty is the no-evidence case, and it now rejects rather
    than falling through to acceptance, because "no one is on record as owning
    this" is indistinguishable from "someone owns it and the record does not
    say so" — which is exactly what a live peer's baton looks like once its
    ledger claim is liveness-gated away and its frontmatter mirror carries no
    `claimed_by` (the observed shape: touching an archived handoff via a
    restore/rename/reformat commit was read as consuming it).

    Fails closed by design. The cost is a session that genuinely ships and
    archives its own predecessor while stamping NEITHER field — that now
    resolves single-session, which `resolve_disposition` already surfaces as a
    loud WARN ("archived a handoff this run but disposition resolved
    single-session"), with the escalate-only `WSC_DISPOSITION` override as the
    operator remedy. A skipped gate the operator is told about beats a
    chain-end review silently scoped over a peer's ancestry.

    Negative-spec: this is NOT a replacement for the sweep-subject filter in
    `detector_b_shipped_by_me`. That filter is deliberately independent — it
    rejects a bulk archival commit even when the swept record's claim holder
    DOES equal this session, which a positive-ownership match alone would
    wave through."""
    shipped_path = repo_root / shipped_by_me
    consumer = resolve_claim_state(shipped_path, repo_root=repo_root).holder or ""
    if consumer and consumer != sid:
        return True, f"claimed_by ({consumer}) is another session (restoration-commit spoof guard)"
    origin = _origin_session(shipped_path)
    if origin and origin != sid:
        return (
            True,
            f"no claim holder names this session, and origin_session ({origin}) names a "
            "different session (unproven ownership fails closed — absence of a claim holder "
            "is not evidence of this session's ownership; 2026-08-05 chain-terminal "
            "misattribution incident)",
        )
    if not consumer and not origin:
        return (
            True,
            "neither a claim holder nor origin_session names any session, so nothing "
            "positively attributes this record to this session — a commit touching an "
            "archived handoff (restore, rename, reformat, licence sweep) is not evidence "
            "of consuming it, and an ownerless-looking record is routinely a live peer's "
            "baton whose ledger claim is liveness-gated and whose mirror carries no "
            "claimed_by (2026-08-10 archive-leg touch-vs-consume incident)",
        )
    return False, consumer


# ---------------------------------------------------------------------------
# Detector C — crash-recovery (stale LIVE baton, scope-intersection match)
# ---------------------------------------------------------------------------


def _is_executable(path: Path) -> bool:
    """POSIX: the real `os.access(X_OK)` exec-bit check, guarded so it is
    reachable only off Windows (recognised by home-resolution-lint's guard
    exemption — see `coordinator/lib/home_resolution_lint.py`). Windows:
    `os.access(path, os.X_OK)` degrades to a meaningless existence-only
    check there anyway, and both call sites below already gate on their own
    `.is_file()` before calling this, so the Windows branch is a no-op on
    top of that already-passed check. Local rather than
    `coordinator_core.win_portability.is_executable` because this helper
    stays self-contained rather than reaching for this module's one
    coordinator_core dependency (see module docstring)."""
    if os.name != "nt":
        return os.access(path, os.X_OK)
    return True


def find_session_claim_cli() -> Path | None:
    """Self-resolve the sibling `session-claim-cli` entrypoint (same bin/
    directory, Path(__file__)-relative — no cwd dependence) first; fall back
    to the settings-home install shim (`${COORDINATOR_SETTINGS_HOME:-
    ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings}/bin`) for callers
    invoking an installed copy of this CLI from outside the claude-klabauter repo,
    mirroring the ported bash's resolution order."""
    sibling = Path(__file__).resolve().parent / "session-claim-cli.py"
    if sibling.is_file():
        return sibling
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or os.path.join(
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or "",
        ".coordinator-claude-settings",
    )
    candidate = Path(settings_home) / "bin" / "session-claim-cli"
    if candidate.is_file() and _is_executable(candidate):
        return candidate
    return None


def _session_claim_cli_argv(cli_path: Path) -> list[str]:
    """Build the invocation argv for ``session-claim-cli``.

    ``find_session_claim_cli`` resolves either the in-repo
    ``session-claim-cli.py`` sibling or the settings-home installed shim
    (the bare ``session-claim-cli`` name the install chain maps ``.py``
    sources onto) — neither carries a shebang or an exec bit post-C6/C4, so
    a bare-path launch fails on POSIX (no exec permission) exactly as it
    fails on Windows (CreateProcess WinError 193 — "%1 is not a valid Win32
    application", which also does not interpret ``#!`` lines). Route through
    this interpreter explicitly on both platforms; a ``.cmd`` sibling (never
    produced by ``find_session_claim_cli`` today, kept for forward
    compatibility) IS directly executable and stays bare. Mirrors
    ``workday-complete-reconcile.py``'s ``_cruft_sweep_argv`` — the same
    interpreter-invocation rung, not the ``.cmd``-sibling rung.

    Detector C reads this call's exit code as a real signal (a non-zero rc
    makes the disposition indeterminate), so an unrunnable CLI here does not
    fail open — it surfaced as a hard brief() crash before this fix.
    """
    if os.path.splitext(str(cli_path))[1] == ".cmd":
        return [str(cli_path)]
    return [sys.executable, str(cli_path)]


def list_stale_claim_handoffs(cli_path: Path, repo_root: Path) -> tuple[list[tuple[str, str]] | None, int]:
    proc = subprocess.run(
        [*_session_claim_cli_argv(cli_path), "list-stale-claim-handoffs", str(repo_root)],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        return None, proc.returncode
    entries = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        entries.append((parts[0], parts[1]))
    return entries, 0


def parse_scope_paths(handoff_path: str) -> list[str]:
    """Extract the `scope:` YAML list block's entries (quote-stripped) from
    a handoff file — same shape as the ported bash's awk state machine: scan
    for `^scope:`, then collect `- <entry>` lines until the block ends."""
    try:
        text = Path(handoff_path).read_text(errors="replace")
    except OSError:
        return []
    in_scope = False
    result: list[str] = []
    for line in text.splitlines():
        if not in_scope:
            if line.startswith("scope:"):
                in_scope = True
            continue
        m = re.match(r"^\s*-\s+(.*)$", line)
        if not m:
            break
        val = m.group(1).strip()
        val = re.sub(r"^['\"]", "", val)
        val = re.sub(r"['\"]$", "", val)
        result.append(val)
    return result


def all_committed_paths(repo_root: Path, sid: str, ship_base: str) -> list[str]:
    lines = _git_log_trailer_lines(repo_root, f"{ship_base}..HEAD", ["--name-only"])
    if lines is None:
        return []
    return _session_scoped_lines(lines, sid)


class ScopeEntryMatch(NamedTuple):
    """One `scope:` entry (as written in a candidate baton's handoff) that
    matched a path this session committed — "exact" (verbatim set
    membership) or "prefix" (directory-scope entry matching one or more
    committed paths underneath it, counted once regardless of how many
    committed paths fall under it — see `_resolve_crash_recovery`)."""

    scope_entry: str
    hit_path: str
    kind: str


class BatonMatch(NamedTuple):
    """A candidate stale baton and the FULL set of its `scope:` entries that
    matched this session's committed paths — `scope_size` is the baton's
    TOTAL scope-entry count, unchanged in meaning from before this widening;
    `matched_scope_entries` is the new fact C2b's coincidence-prone
    predicate needs (how many of those entries actually matched, not merely
    whether at least one did)."""

    handoff_path: str
    dead_sid: str
    matched_scope_entries: tuple[ScopeEntryMatch, ...]
    scope_size: int


class CrashRecoveryOutcome(tuple):
    """`_resolve_crash_recovery` / `detector_c`'s return: the historical
    2-tuple `(repo_relative_handoff_path_or_None, status)`, ITSELF, plus a
    `match_facts` dict hung off it as an attribute — same idiom as
    `DispositionResolution` above, and for the same reason: every call site
    (this module's `detector_c` crash-recovery leg, `resolve_disposition`,
    this file's own test suite, and `detector_c`'s test coverage) unpacks
    this return 2-wide; widening the arity would raise `ValueError: too many
    values to unpack` at every one of them on a tree siblings execute
    unversioned. `len()` stays 2, `tuple()` is the historical 2-tuple,
    iteration never yields `match_facts`.

    `match_facts` is `None` on every path except the clean single-match
    crash-recovery resolution, where it is exactly:
      {"matched_scope_entry_count": <int>, "scope_size": <int>,
       "single_match_kind": "exact" | "prefix", "exact_match_count": <int>}
    ("single_match_kind" is the sole matched entry's kind; the field only
    has a stable meaning when there is exactly one matched entry.
    "exact_match_count" is how many of `matched_scope_entries` were EXACT
    path matches rather than prefix hits — additive, derived from the same
    per-match kind data already in hand here, not a recomputation of the
    matching logic.)"""

    match_facts: dict[str, Any] | None

    def __new__(cls, path: str | None, status: str | None, match_facts: dict[str, Any] | None) -> "CrashRecoveryOutcome":
        self = super().__new__(cls, (path, status))
        self.match_facts = match_facts
        return self


def _resolve_crash_recovery(
    stale_entries: list[tuple[str, str]],
    committed_paths: list[str],
    repo_root: Path,
    diagnostics: list[str],
) -> "CrashRecoveryOutcome":
    """Pure scope-intersection resolver over already-fetched stale-baton and
    committed-path data — split out from `detector_c` so it is unit-testable
    without stubbing the `session-claim-cli` subprocess. Returns a
    `CrashRecoveryOutcome` (repo_relative_handoff_path_or_None, status)
    where status is one of None (true negative / no intersection),
    "ambiguous", or the caller sets "crash-recovery" itself on a clean
    single match — plus `.match_facts`, see `CrashRecoveryOutcome`.

    Accumulates ALL matching scope entries per candidate baton (not just the
    first) — a directory scope entry matching multiple committed paths
    underneath it still counts as ONE matched entry, since the `break` right
    after a prefix hit stops scanning committed_paths for THAT scope entry,
    not the scope_paths loop."""
    committed_set = set(committed_paths)
    matches: list[BatonMatch] = []
    for path, dead_sid in stale_entries:
        scope_paths = parse_scope_paths(path)
        entry_matches: list[ScopeEntryMatch] = []
        for sp in scope_paths:
            if sp in committed_set:
                entry_matches.append(ScopeEntryMatch(sp, sp, "exact"))
                continue
            prefix = sp.rstrip("/") + "/"
            hit = next((cp for cp in committed_paths if cp.startswith(prefix)), None)
            if hit:
                entry_matches.append(ScopeEntryMatch(sp, hit, "prefix"))
        # Dedupe by matched physical FILE (hit_path), not by scope entry —
        # overlapping scope entries (e.g. both `coordinator_core/` and
        # `coordinator_core/foo.py`) can each independently match the SAME
        # committed file, which would otherwise inflate
        # `matched_scope_entry_count` above the count of distinct files
        # actually touched. Prefer an "exact" match over a "prefix" match
        # for the same file — the exact entry is the more specific evidence,
        # so it is what `single_match_kind` should reflect when both are
        # present. Do not "restore" the double-count: the ratio below
        # counts distinct matched FILES, not raw scope entries.
        by_hit_path: dict[str, ScopeEntryMatch] = {}
        for em in entry_matches:
            existing = by_hit_path.get(em.hit_path)
            if existing is None or (existing.kind == "prefix" and em.kind == "exact"):
                by_hit_path[em.hit_path] = em
        deduped_matches = list(by_hit_path.values())
        if deduped_matches:
            matches.append(BatonMatch(path, dead_sid, tuple(deduped_matches), len(scope_paths)))

    if len(matches) == 1:
        baton = matches[0]
        rel_path = baton.handoff_path
        repo_root_str = str(repo_root)
        if baton.handoff_path.startswith(repo_root_str + os.sep):
            # POSIX separators — same wire-id reasoning as the primary scan's
            # own return above (primary_consumed_handoff_paths); this value
            # is returned as CrashRecoveryOutcome's path and flows out as
            # DispositionResolution's consumed-handoff identity.
            rel_path = Path(baton.handoff_path).relative_to(repo_root).as_posix()
        matched_count = len(baton.matched_scope_entries)
        exact_count = sum(1 for em in baton.matched_scope_entries if em.kind == "exact")
        first = baton.matched_scope_entries[0]
        hit_detail = first.hit_path if first.kind == "exact" else f"{first.hit_path} (under scope {first.scope_entry})"
        diagnostics.append(
            f"NOTE: chain-terminal resolved by Detector C (crash-recovery): this session "
            f"committed against the scope of {rel_path} (matched via {hit_detail}, "
            f"{matched_count} of {baton.scope_size} scope entries matched), whose claimer "
            f"{baton.dead_sid} is not live. "
            f"{matched_count}-of-{baton.scope_size} scope-entry match — sanity-check before "
            f"relying on it if that overlap could be coincidental (e.g. a widely-shared file)."
        )
        match_facts = {
            "matched_scope_entry_count": matched_count,
            "scope_size": baton.scope_size,
            "single_match_kind": first.kind if matched_count == 1 else None,
            "exact_match_count": exact_count,
        }
        return CrashRecoveryOutcome(rel_path, "crash-recovery", match_facts)

    if len(matches) > 1:
        diagnostics.append(
            f"WARN: Detector C found {len(matches)} stale batons whose scope this session "
            f"committed against — cannot disambiguate:"
        )
        for baton in matches:
            diagnostics.append(f"  {baton.handoff_path}\t{baton.dead_sid}")
        diagnostics.append(
            f"Detector C found {len(matches)} stale batons whose scope this session "
            f"committed against — cannot disambiguate. Export "
            f"WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also accepted) "
            f"and WSC_CONSUMED_HANDOFF=<the one you are continuing> before continuing."
        )
        return CrashRecoveryOutcome(None, "ambiguous", None)

    if stale_entries:
        diagnostics.append(
            f"WARN: Detector C found {len(stale_entries)} stale baton(s) whose scope did NOT "
            f"intersect this session's committed paths — disposition may still resolve "
            f"single-session and Step 2.9's chain-end coverage gate will be SKIPPED. Stale "
            f"batons considered:"
        )
        for path, dead_sid in stale_entries:
            diagnostics.append(f"  {path}\t{dead_sid}")
        diagnostics.append(
            "If one of these is the baton this session is continuing, export "
            "WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also accepted) "
            "and WSC_CONSUMED_HANDOFF=<path> before continuing."
        )
    return CrashRecoveryOutcome(None, None, None)


def _resolve_deliverable_id_join(
    repo_root: Path,
    sid: str,
    stale_entries: list[tuple[str, str]],
    diagnostics: list[str],
) -> "CrashRecoveryOutcome | None":
    """Session-shape attribution's PREFERRED leg (C5, 2026-08-20
    `wsc-identity-gates-key-on-the-deliverable.md`, item 1 AC2): join this
    session's own commit-trailer `deliverable_id` values (C1's
    `session_deliverable_ids` reader, already imported at module scope)
    against the candidate stale batons' `deliverable_id` frontmatter,
    preferring an exact unambiguous join over `_resolve_crash_recovery`'s
    scope-path heuristic below. Called from `detector_c` BEFORE the
    scope-path leg runs; scope-path matching is the fallback for when this
    returns `None`, not the primary any longer.

    Ambiguity is not a match, on either side of the join: a session whose
    commits carry more than one distinct `deliverable_id`, or more than one
    candidate baton carrying the SAME id, both fall through to the
    scope-path fallback rather than picking — each case is reported via a
    diagnostic, not silently swallowed.

    Returns `None` (never a status of its own) to signal "fall through to
    scope-path matching" for every non-match shape (no trailer resolved,
    ambiguous session-side, ambiguous baton-side, no baton carries a
    matching id) — the diagnostics list is where those shapes are told
    apart, not the return value. Returns a populated `CrashRecoveryOutcome`
    (status "crash-recovery") only on the single unambiguous match."""
    result = session_deliverable_ids(repo_root, sid)
    if not result.ok or not result.deliverable_ids:
        return None
    if len(result.deliverable_ids) != 1:
        diagnostics.append(
            f"NOTE: deliverable_id join skipped — this session's own commits carry "
            f"{len(result.deliverable_ids)} conflicting Deliverable-Id trailer values "
            f"({', '.join(sorted(result.deliverable_ids))}); falling back to Detector C's "
            f"scope-path matching."
        )
        return None
    session_deliverable_id = next(iter(result.deliverable_ids))

    matches: list[tuple[str, str]] = []
    for path, dead_sid in stale_entries:
        baton_deliverable_id = _read_fm_field_local(Path(path), "deliverable_id")
        if baton_deliverable_id and baton_deliverable_id == session_deliverable_id:
            matches.append((path, dead_sid))

    if not matches:
        return None
    if len(matches) > 1:
        diagnostics.append(
            f"NOTE: deliverable_id join found {len(matches)} stale batons carrying the same "
            f"Deliverable-Id ({session_deliverable_id}) as this session's own commits — "
            f"ambiguous, falling back to Detector C's scope-path matching:"
        )
        for path, dead_sid in matches:
            diagnostics.append(f"  {path}\t{dead_sid}")
        return None

    path, dead_sid = matches[0]
    rel_path = path
    repo_root_str = str(repo_root)
    if path.startswith(repo_root_str + os.sep):
        # POSIX separators — same wire-id reasoning as the primary scan's
        # own return above (primary_consumed_handoff_paths).
        rel_path = Path(path).relative_to(repo_root).as_posix()
    diagnostics.append(
        f"NOTE: chain-terminal resolved by the deliverable_id join (preferred over Detector "
        f"C's scope-path heuristic): this session's commits carry Deliverable-Id="
        f"{session_deliverable_id}, matching {rel_path} (claimer {dead_sid}, not live)."
    )
    return CrashRecoveryOutcome(rel_path, "crash-recovery", {"deliverable_id_join": True})


def detector_c(
    repo_root: Path,
    sid: str,
    ship_base: str | None,
    cli_path: Path | None,
    diagnostics: list[str],
) -> "CrashRecoveryOutcome":
    """Returns a `CrashRecoveryOutcome` (repo_relative_handoff_path_or_None,
    status) where status is one of None, "indeterminate", "ambiguous", or
    "crash-recovery" — plus `.match_facts` (see `CrashRecoveryOutcome`),
    `None` on every early-return path here, propagated unchanged from
    `_resolve_crash_recovery` on the crash-recovery path."""
    if cli_path is None:
        diagnostics.append(
            "WARN: Detector C (crash-recovery chain-terminal detection) could not resolve "
            "session-claim-cli — liveness INDETERMINATE, not \"no stale batons\". If this "
            "session recovered a crashed session's baton, export "
            "WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also accepted) "
            "and WSC_CONSUMED_HANDOFF=<path> before continuing."
        )
        return CrashRecoveryOutcome(None, "indeterminate", None)

    stale, rc = list_stale_claim_handoffs(cli_path, repo_root)
    if stale is None:
        diagnostics.append(
            f"WARN: Detector C (crash-recovery chain-terminal detection) — "
            f"list-stale-claim-handoffs exited {rc} — liveness INDETERMINATE, not "
            f"\"no stale batons\". If this session recovered a crashed session's baton, export "
            f"WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also accepted) "
            f"and WSC_CONSUMED_HANDOFF=<path> before continuing."
        )
        return CrashRecoveryOutcome(None, "indeterminate", None)

    if ship_base is None:
        # Detector B already WARNed about the unresolvable merge-base — don't re-WARN.
        return CrashRecoveryOutcome(None, "indeterminate", None)

    if not stale:
        return CrashRecoveryOutcome(None, None, None)  # true negative — no stale batons at all

    join_outcome = _resolve_deliverable_id_join(repo_root, sid, stale, diagnostics)
    if join_outcome is not None:
        return join_outcome

    committed = all_committed_paths(repo_root, sid, ship_base)
    return _resolve_crash_recovery(stale, committed, repo_root, diagnostics)


# ---------------------------------------------------------------------------
# Memo-predecessor leg — a cross-repo memo this session claimed (picked_up_by)
# names it as this workstream's predecessor, independent of any handoff/
# archive/git-provenance evidence. See resolve_disposition's docstring and
# the plan's "THE PRECEDENCE CONTRACT" for how this leg is sequenced against
# Detector C.
# ---------------------------------------------------------------------------


def _read_fm_field_local(path: Path, key: str) -> str:
    """Bounded frontmatter fence-scan for one `key:` scalar, one layer of
    surrounding quotes stripped — the same self-contained idiom
    `_origin_session` above uses (this module deliberately does not import
    `coordinator_core.frontmatter.primitives.read_fm_field_unquoted`; see
    module docstring), generalised to an arbitrary key name so it can read
    both `picked_up_by` and `picked_up_at` (both written by
    `coordinator_core.ops.memo_transition._claim_stamp_fields` with
    `numeric_quoting=True`, so a purely-numeric session id or timestamp is
    written QUOTED and a naive un-stripped read would fail the equality
    test). Returns "" when the key, the frontmatter fence, or the file
    itself is absent/unreadable — never raises."""
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
                if stripped_line.startswith(f"{key}:"):
                    val = stripped_line[len(key) + 1 :].strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                    return val
    except OSError:
        return ""
    return ""


def _run_git_local(repo_root: Path, args: list[str]) -> "subprocess.CompletedProcess | None":
    """Local mirror of `coordinator_core.workstream_complete.
    directives_memo_lifecycle._run_git`'s guard semantics — duplicated, not
    imported, keeping this helper self-contained rather than reaching for
    this module's one coordinator_core dependency (see module docstring).
    Same bounded `timeout` and the same
    `(OSError, subprocess.SubprocessError)` swallow-to-None: a stale git
    lock, a hung `git` process, or a missing `git` binary degrades this leg
    rather than hanging or crashing `resolve_disposition`. Review:
    coordinator-code-reviewer (Finding 1) — the original reimplementation
    omitted both the timeout and the exception guard the function it
    duplicates relies on."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _resolve_memo_session_start_time(repo_root: Path, sid: str) -> "datetime | None":
    """Local reimplementation of `coordinator_core.workstream_complete.
    directives_memo_lifecycle.resolve_session_start_time`'s resolution
    ladder — duplicated, not imported, per this module's "no
    coordinator_core import" contract (see module docstring): the mtime of
    `.git/coordinator-sessions/<sid>/` under the git COMMON dir, else the
    timestamp of the earliest commit not shared with `@{upstream}` /
    `origin/main` / `origin/master` / `main` / `master` (first one that
    resolves), else the repo's very first commit. Returns `None` when none
    of those resolve — the memo leg fails closed on that, it does not guess."""
    common_proc = _run_git_local(repo_root, ["rev-parse", "--git-common-dir"])
    if common_proc is not None and common_proc.returncode == 0 and common_proc.stdout.strip():
        common = Path(common_proc.stdout.strip())
        common_dir = common if common.is_absolute() else repo_root / common
        claim_dir = common_dir / "coordinator-sessions" / sid
        if claim_dir.is_dir():
            try:
                return datetime.fromtimestamp(claim_dir.stat().st_mtime, tz=timezone.utc)
            except OSError:
                pass

    for base in ("@{upstream}", "origin/main", "origin/master", "main", "master"):
        mb_proc = _run_git_local(repo_root, ["merge-base", "HEAD", base])
        if mb_proc is None or mb_proc.returncode != 0 or not mb_proc.stdout.strip():
            continue
        merge_base = mb_proc.stdout.strip()
        log_proc = _run_git_local(repo_root, ["log", "--reverse", "--format=%cI", f"{merge_base}..HEAD"])
        if log_proc is not None and log_proc.returncode == 0 and log_proc.stdout.strip():
            first_line = log_proc.stdout.strip().splitlines()[0]
            try:
                return datetime.fromisoformat(first_line)
            except ValueError:
                pass

    log_proc = _run_git_local(repo_root, ["log", "--reverse", "--format=%cI"])
    if log_proc is not None and log_proc.returncode == 0 and log_proc.stdout.strip():
        first_line = log_proc.stdout.strip().splitlines()[0]
        try:
            return datetime.fromisoformat(first_line)
        except ValueError:
            return None
    return None


def find_memo_predecessor(repo_root: Path, sid: str, diagnostics: list[str]) -> str | None:
    """Scans `cross-repo/inbox/*.md` and `cross-repo/archive/*.md` (flat,
    non-nested trees as of this writing — no `rglob` needed) for a memo
    whose frontmatter `picked_up_by` equals `sid` AND whose `picked_up_at`
    is at-or-before this session's own start time.

    The `picked_up_at` gate is load-bearing, not incidental:
    `picked_up_by` alone proves a CLAIM, not an ORIGIN — EMs claim memos
    mid-workstream routinely, and without this gate an incidental
    late-session memo claim would silently preempt a real resolution. If
    the session's start time cannot be resolved, the leg does NOT fire
    (fail closed) rather than skip the gate.

    Unreadable memos, memos with no frontmatter fence, and an unparseable
    `picked_up_at` are SKIPPED, never fatal. Several matches resolve
    deterministically: sort by repo-relative path, take the first.

    The filesystem scan for a `picked_up_by == sid` candidate runs FIRST,
    before the session-start git ladder is ever paid for — Review:
    coordinator-code-reviewer (Findings 2, 3). When zero candidates exist
    (the common case — this leg only matters for a session that opened on a
    memo), the git ladder never runs and no diagnostic is emitted, keeping
    `resolve_disposition`'s "byte-identical to pre-memo-leg HEAD when no
    memo matched" docstring claim true without exception. Only when at
    least one `picked_up_by` candidate is found does the ladder run to gate
    it against session start.

    Returns the matched memo's repo-relative path, or `None` if the leg did
    not fire or nothing matched."""
    candidates: list[tuple[Path, str, "datetime"]] = []
    for dirname in ("inbox", "archive"):
        memo_dir = repo_root / "cross-repo" / dirname
        if not memo_dir.is_dir():
            continue
        for f in memo_dir.glob("*.md"):
            if not f.is_file():
                continue
            picked_up_by = _read_fm_field_local(f, "picked_up_by")
            if not picked_up_by or picked_up_by != sid:
                continue
            picked_up_at_raw = _read_fm_field_local(f, "picked_up_at")
            if not picked_up_at_raw:
                continue
            try:
                picked_up_at = datetime.fromisoformat(picked_up_at_raw)
            except ValueError:
                continue
            if picked_up_at.tzinfo is None:
                picked_up_at = picked_up_at.replace(tzinfo=timezone.utc)
            candidates.append((f, picked_up_at_raw, picked_up_at))

    if not candidates:
        return None

    session_start = _resolve_memo_session_start_time(repo_root, sid)
    if session_start is None:
        diagnostics.append(
            "NOTE: memo-predecessor leg did not fire — could not resolve this session's start "
            "time (no .git/coordinator-sessions/<sid>/ claim dir under the git common dir, and "
            "no upstream/origin/main/master merge-base or first-commit fallback "
            "resolved), so a picked_up_by match cannot be gated to at-or-before session start; "
            "failing closed rather than risk an incidental late-session memo claim preempting a "
            "real resolution."
        )
        return None

    matches = [
        (f, picked_up_at_raw)
        for f, picked_up_at_raw, picked_up_at in candidates
        if picked_up_at <= session_start
    ]
    if not matches:
        return None
    matches.sort(key=lambda pair: pair[0])
    chosen, chosen_at_raw = matches[0]
    rel = rel_id(chosen, repo_root)
    diagnostics.append(
        f"NOTE: memo-predecessor candidate: {rel} (picked_up_by={sid}, "
        f"picked_up_at={chosen_at_raw} <= session-start {session_start.isoformat()})"
    )
    return rel


# ---------------------------------------------------------------------------
# Top-level disposition resolution
# ---------------------------------------------------------------------------


def _normalize_override_handoff(repo_root: Path, raw: str, diagnostics: list[str]) -> str:
    """Normalise a raw ``WSC_CONSUMED_HANDOFF`` override value to a
    repo-relative path (whitespace already stripped by the caller). NOTEs
    (never fails) when the resulting path does not exist on disk — the
    observed real case this override exists for includes already-archived
    handoffs, so a nonexistent path is worth surfacing but not worth
    blocking a ceremony over. No legacy-literal use here (kept out of
    ``resolve_disposition`` only to stay readable; see that function for the
    literal-carrying override checks themselves)."""
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            rel = rel_id(candidate.resolve(), repo_root.resolve())
        except (OSError, ValueError):
            rel = raw
    else:
        rel = raw
    if not (repo_root / rel).exists():
        diagnostics.append(
            f"NOTE: WSC_CONSUMED_HANDOFF={rel} does not exist on disk (e.g. an "
            f"already-archived handoff, or a stale path) — accepted anyway, the override "
            f"always wins."
        )
    return rel


#: The closed enum of legs `resolve_disposition` can decide on, carried out
#: on `DispositionResolution.detection["deciding_leg"]`. Six, not three:
#: "A/B/C detector" under-enumerates, because the escalate-only env override
#: and the primary live-claim scan both decide ahead of any detector, the
#: memo-predecessor leg decides independently of any detector (see THE
#: PRECEDENCE CONTRACT on `resolve_disposition`), and the terminal
#: fall-through decides nothing at all.
#:   env-override     — WSC_DISPOSITION escalated ahead of the whole chain
#:   live-consume     — `primary_consumed_handoff_paths` found a live claim stamp
#:   archive          — Detector A, or Detector B plus a `predecessor:` field
#:   detector-c       — crash-recovery scope intersection against a stale baton
#:   memo-predecessor — a claimed cross-repo memo, per `find_memo_predecessor`,
#:                      either because no archive/detector-c predecessor was
#:                      found or because it preempted a coincidence-prone
#:                      Detector C match
#:   none             — nothing resolved; disposition is single-session
DECIDING_LEGS = ("env-override", "live-consume", "archive", "detector-c", "memo-predecessor", "none")


class DispositionResolution(tuple):
    """`resolve_disposition`'s return: the historical 4-tuple, ITSELF, plus a
    structured `detection` record hung off it as an attribute.

    A `tuple` subclass rather than a NamedTuple, and deliberately so. Every
    call site in and out of this repo unpacks this return as exactly four
    values (`compute_session_shape_gate` in
    `coordinator_core/workstream_complete/__init__.py`, this module's own
    `_cmd_resolve`, two test suites); widening the arity would raise
    `ValueError: too many values to unpack` at every one of them the instant
    this file landed and before its consumers did — a live hazard on a
    working tree sibling sessions execute unversioned. Carrying the new fact
    as an attribute keeps the unpack arity frozen at four while making the
    structured signal available to any consumer that asks for it by name.

    Negative-spec: `detection` is NOT a tuple element. `len(result)` is 4,
    `tuple(result)` is the historical 4-tuple, and iteration never yields it.

    `detection` keys:
      deciding_leg — one of `DECIDING_LEGS`.
      detector_c_status — Detector C's own status (`None`, "indeterminate",
        "ambiguous", "crash-recovery"), or `None` when Detector C never ran.
        Kept as its own key rather than a generic "status" because Detector C
        is the only leg that has one; a leg-agnostic name would imply the
        others could populate it. Populated on a `memo-predecessor`
        resolution too when Detector C ran first — see `resolve_disposition`'s
        docstring — as a DIAGNOSTIC only, never a control signal for that
        resolution.
      matched_scope_entry_count / scope_size / single_match_kind /
        exact_match_count — Detector C's own match facts (see
        `CrashRecoveryOutcome`), merged in only when Detector C supplied
        them; same diagnostics-only status on a `memo-predecessor`
        resolution.
      memo_path — repo-relative path of the memo `find_memo_predecessor`
        matched, present only on a `deciding_leg == "memo-predecessor"`
        resolution.
    """

    detection: dict[str, Any]

    def __new__(
        cls,
        disposition: str,
        consumed_handoff: str,
        diagnostics: list[str],
        consumed_handoff_paths: list[str],
        detection: dict[str, Any],
    ) -> "DispositionResolution":
        self = super().__new__(cls, (disposition, consumed_handoff, diagnostics, consumed_handoff_paths))
        self.detection = detection
        return self

    @property
    def disposition(self) -> str:
        return self[0]

    @property
    def consumed_handoff(self) -> str:
        return self[1]

    @property
    def diagnostics(self) -> list[str]:
        return self[2]

    @property
    def consumed_handoff_paths(self) -> list[str]:
        return self[3]


def _detection(
    deciding_leg: str,
    detector_c_status: str | None = None,
    match_facts: dict[str, Any] | None = None,
    memo_path: str | None = None,
    mirror_conflicts: list[str] | None = None,
) -> dict[str, Any]:
    """Builds one `DispositionResolution.detection` record. A helper rather
    than one inline dict literal per return path so the key names cannot
    drift between the several return paths of `resolve_disposition`.
    `match_facts` (Detector C's `matched_scope_entry_count` / `scope_size` /
    `single_match_kind` / `exact_match_count`, see `CrashRecoveryOutcome`) is
    merged in when present — the detector-c leg, and a memo-predecessor
    resolution that preempted a coincidence-prone Detector C match, both
    supply it (see
    THE PRECEDENCE CONTRACT on `resolve_disposition`). `memo_path` is set
    only on a `deciding_leg == "memo-predecessor"` resolution.

    `mirror_conflicts` is set on EVERY leg the detector chain can reach after
    the primary scan ran (see `primary_consumed_handoff_scan`'s
    HOLDER-MISMATCH PARTITION): the paths whose ledger claim names this
    session while their frontmatter names somebody else. It is a REFUSAL
    fact, not a leg — whichever leg then decided, this key says a
    live-consume candidate was declined and why the shape may be wrong.
    Omitted entirely when there is no conflict, so its presence, not its
    value, is the signal — the same presence-vs-absence discipline
    `exact_match_count` already uses one layer up."""
    record = {"deciding_leg": deciding_leg, "detector_c_status": detector_c_status}
    if match_facts:
        record.update(match_facts)
    if memo_path is not None:
        record["memo_path"] = memo_path
    if mirror_conflicts:
        record["live_consume_mirror_conflicts"] = list(mirror_conflicts)
    return record


def _memo_predecessor_result(
    diagnostics: list[str],
    c_status: str | None,
    c_match_facts: dict[str, Any] | None,
    memo_path: str,
    mirror_conflicts: list[str] | None = None,
) -> "DispositionResolution":
    """The `memo-predecessor` `DispositionResolution` — factored out because
    `resolve_disposition` builds this identical five-argument shape from two
    return sites (the Detector-C-preemption path and the no-archive-match
    path). Review: coordinator-code-reviewer (Finding 4, nit) — keeps any
    future change to the memo-predecessor return shape in sync across both
    call sites by construction."""
    return DispositionResolution(
        "memo-predecessor",
        "",
        diagnostics,
        [],
        _detection(
            "memo-predecessor",
            c_status,
            c_match_facts,
            memo_path,
            mirror_conflicts=mirror_conflicts,
        ),
    )


def is_coincidence_prone_detection(match_facts: dict[str, Any]) -> bool:
    """The breadth-not-count corroboration predicate, called from
    `resolve_disposition`'s memo-preemption gate below.

    NOT the single shared home in practice, despite the intent: a SECOND
    copy of this exact rule lives inline in
    `coordinator_core.workstream_complete._session_shape_is_uncertain`'s
    Detector-C branch, duplicated rather than delegated here — a
    module-load delegation (`_load_session_disposition_module()`) was tried
    and reverted, because it forces `resolve_operator_config` to run as a
    side effect of what should be a pure predicate, breaking every test in
    that module that hand-constructs a `detection` dict with no repo_root /
    operator config in scope. This module's own "no coordinator_core
    import" contract (module docstring) blocks the delegation running the
    other direction. If this rule ever changes, change BOTH copies.

    The 2026-08-06 fix this function centralises went through two passes.
    Pass 1 replaced a count short-circuit (`matched_scope_entry_count != 1`
    -> not coincidence-prone) that read an all-prefix multi-match as MORE
    corroborated than a single exact match (the example-market-data-repo live
    false-positive: 2 prefix-only matches on a 7-entry scope read as
    settled). Pass 2 closed a near-neighbour miss in that first fix: gating
    the "one exact hit is weak" case on `matched_scope_entry_count == 1`
    meant adding worthless prefix hits alongside a lone exact hit SILENCED
    an already-flagged attribution (1 exact + 2 prefix in a 7-entry scope
    fell through `!= 1` to "not coincidence-prone", despite being no more
    corroborated than 1 exact alone). The rule below is keyed ENTIRELY on
    `exact_match_count`, which has neither hole; `matched_scope_entry_count`
    plays no role in the live rule, only in the stale-producer fallback.

    Two visibly separate branches, selected by PRESENCE of
    `exact_match_count` in `match_facts` (not by its value — an absent key
    must never be misread as `0`):

      - `exact_match_count` present — the live rule:
          - `== 0` -> coincidence-prone, at ANY match count (every matched
            entry was a prefix hit).
          - `== 1` with a `scope_size` of two or more — coincidence-prone
            (one exact hit against a multi-entry scope is weak whether or
            not prefix hits ride along).
          - two or more — NOT coincidence-prone (two or more exact matches
            is real corroboration, regardless of accompanying prefix hits).
          - `== 1` and `scope_size == 1` -> NOT coincidence-prone (the
            narrowest, most specific attribution possible).
      - `exact_match_count` absent — stale-producer fallback, replaying the
        pre-`exact_match_count` logic byte-for-byte:
        `matched_scope_entry_count == 1 and (scope_size >= 2 or
        single_match_kind == "prefix")`. `single_match_kind == "prefix"`
        earns its keep ONLY here — on the live path above it is redundant
        (a prefix-kind single match implies `exact_match_count == 0`,
        already caught by the first case)."""
    if "exact_match_count" in match_facts:
        exact_count = match_facts.get("exact_match_count")
        if exact_count == 0:
            return True
        if exact_count == 1:
            return match_facts.get("scope_size", 0) >= 2
        return False
    if match_facts.get("matched_scope_entry_count") != 1:
        return False
    return (
        match_facts.get("scope_size", 0) >= 2
        or match_facts.get("single_match_kind") == "prefix"
    )


# GRAVESTONE: `_note_session_deliverable_ids` (removed 2026-08-25).
#
# It called `session_deliverable_ids` unconditionally at the top of
# `resolve_disposition` and appended a NOTE naming this session's own
# `Deliverable-Id` trailer values. Its own docstring described it as
# "DIAGNOSTIC ONLY, never a control signal here", running "without changing
# `resolve_disposition`'s own returned disposition", and existing to "prove
# the plain import is wired and live".
#
# WHY IT WENT: that reader runs `git log --no-merges` from HEAD with no
# `--since`, no `-n`, and no pathspec -- a full-history walk measured at
# 296.9ms of process time on this repo, and one that grows with repo age
# forever, on every machine. Measured across a real `brief()`, it was the
# ONLY `session_deliverable_ids` call the close path reached, and roughly a
# fifth of the entire gate path's cost. A call that by its own contract
# cannot change what the ceremony decides is not worth an unbounded walk on
# a path ~50 concurrent sessions queue behind.
#   -> docs/plans/2026-08-25-the-close-ceremony-inside-the-brightline.md, C1
#   -> state/audits/2026-08-25-close-ceremony-gate-path-caller-census.md
#
# WHAT DISCHARGES ITS REQUIREMENT NOW (the job did not vanish with the code):
# proving the import is wired and live is a test's job, and the test already
# exists -- `TestSessionIdentityImport ::
# test_import_resolves_to_the_engine_leaf_module` in
# `coordinator/bin/tests/test_wsc_session_disposition.py` asserts the bound
# name IS the engine leaf function. The runtime call was redundant with it.
#
# NEGATIVE SPEC -- do not reintroduce this as a "cheap" diagnostic. There is
# no cheap shape: the cost is the unbounded history walk, not the NOTE. If an
# operator needs this session's Deliverable-Id values, resolve them from the
# already-computed disposition record rather than re-walking history here.
# The reader itself stays live and is still called from
# `_resolve_deliverable_id_join` (detector_c), where the value DOES gate a
# decision and therefore earns its cost.


def resolve_disposition(repo_root: Path, sid: str) -> "DispositionResolution":
    """Returns (disposition, consumed_handoff, diagnostics, consumed_handoff_paths)
    where disposition is one of "predecessor-consumed", "memo-predecessor",
    or "single-session" (three-valued, not two — see `find_memo_predecessor`
    and THE PRECEDENCE CONTRACT below), consumed_handoff is a repo-relative
    path (empty string on single-session AND on memo-predecessor — see
    below — kept for unmigrated callers as consumed_handoff_paths[0] or ""
    when empty), and consumed_handoff_paths is primary_consumed_handoff's
    own full sorted `matches` list — this bin script's OWN unanchored
    local-scan detector set, NOT a cross-package agreement with
    branch_resolution.py's anchored step0_evidence["consumed_handoff_paths"].

    THE PRECEDENCE CONTRACT (memo-predecessor leg vs. Detector C): Detector
    C always runs (its call is never skipped, and its status is never
    deleted from `.detection`). A clean Detector C match preempts the memo
    leg ONLY when it is NOT coincidence-prone, per the shared
    `is_coincidence_prone_detection` predicate above — the same predicate
    `coordinator_core.workstream_complete._session_shape_is_uncertain`
    already applies to Detector C's own output.
      - Clean + not coincidence-prone -> "predecessor-consumed", deciding_leg
        "detector-c" (memo loses; unchanged from before this leg existed).
      - Clean + coincidence-prone -> "memo-predecessor" if a memo matched
        (memo wins); otherwise (2026-08-20, wsc-identity-gates-key-on-the-
        deliverable C4) NOT adopted as "predecessor-consumed" -- falls
        through to the shared "single-session" return below.
        `deciding_leg` on that return stays "detector-c" (not "none") and
        still carries `detector_c_status`/the match facts, so a
        coincidence-prone crash-recovery attribution with no memo to
        corroborate it is a distinguishable single-session shape, not a
        silent discard of Detector C's own verdict -- see AMENDMENT
        BREADCRUMB below and this function's single-session return.
      - indeterminate/ambiguous, or nothing found via any detector -> "memo-
        predecessor" if a memo matched, else today's behaviour (unchanged).

      AMENDMENT BREADCRUMB (2026-08-20, wsc-identity-gates-key-on-the-
      deliverable C4, amending the ratified 2026-08-05-memo-predecessor-
      representable-outcome.md AC3 precedence contract above): this chunk
      edits the CALLER'S ADOPTION of Detector C's verdict here in
      `resolve_disposition` -- the fall-through that used to keep a
      coincidence-prone, memo-less crash-recovery match as
      "predecessor-consumed" regardless. It does NOT touch Detector C's own
      matching logic (`is_coincidence_prone_detection`,
      `_resolve_crash_recovery`, `detector_c` are unchanged) -- so do not
      score this against the 2026-08-05 plan's own anti-scope line ("do not
      fix Detector C again... if you find yourself editing `detector_c`'s
      matching logic, stop"); that line does not apply to this edit.
      - No memo matched at all -> every return path is byte-identical to
        pre-memo-leg HEAD, trailing WARNs included.
      - Detector A/B ("archive" leg) always wins over the memo leg
        unconditionally — the memo leg is only ever consulted when `arch` is
        falsy going into the Detector-C decision, or when Detector C itself
        decided and was coincidence-prone.
    On a "memo-predecessor" resolution, `consumed_handoff` is the EMPTY
    STRING and `consumed_handoff_paths` is `[]` — contractual:
    `consumed_handoff` is a HANDOFF path consumed by the chain, and
    `pipeline_context`'s emptiness invariant reads it that way; the memo
    path is carried ONLY on `.detection["memo_path"]`. Detector C's own
    `detector_c_status`/match-facts ride onto that same `.detection` record
    as DIAGNOSTICS ONLY when a memo-predecessor resolution preempted a
    Detector C match — "memo-predecessor" is a SETTLED FACT, not an
    uncertain one: `_session_shape_is_uncertain` returns `False` for it.

    ESCALATE-ONLY ENV OVERRIDE: before the detector chain runs, checks
    WSC_DISPOSITION / WSC_CONSUMED_HANDOFF (the exact remedy the diagnostics
    below tell the operator to export). This is a safety gate, so the
    override may only ESCALATE, never downgrade: a positive value
    (canonical "predecessor-consumed" or the legacy alias "chain-terminal",
    case-insensitive, whitespace-stripped) wins outright, ahead of every
    detector. "single-session" is refused as a downgrade — a positively
    detected consume is never suppressed by an env var — and the chain runs
    normally with a WARN explaining the refusal. An unrecognised non-empty
    value is ignored (WARN, chain runs normally). WSC_CONSUMED_HANDOFF alone,
    without a positive WSC_DISPOSITION, does not flip disposition (NOTE,
    ignored).

    STRUCTURED DETECTION RECORD: the return also carries
    `.detection` — `{"deciding_leg": <DECIDING_LEGS member>,
    "detector_c_status": <Detector C's own status or None>}`. This is the
    machine-readable answer to "which leg decided, and how sure was it";
    consumers gate on it directly instead of substring-matching the
    free-text `diagnostics` below, which stay prose for a human reader and
    are never a control signal (see `DispositionResolution`)."""
    # Library entry point: callers reach this without going through main(),
    # so it bootstraps its own engine imports. Idempotent.
    _bootstrap_engine_imports()

    diagnostics: list[str] = []

    override = os.environ.get("WSC_DISPOSITION", "").strip()
    override_norm = override.lower()
    handoff_raw = os.environ.get("WSC_CONSUMED_HANDOFF", "").strip()

    if override_norm in ("predecessor-consumed", "chain-terminal"):
        consumed = _normalize_override_handoff(repo_root, handoff_raw, diagnostics)
        diagnostics.append(
            f"NOTE: disposition resolved via WSC_DISPOSITION={override!r} override — "
            f"escalate-only, takes precedence ahead of the whole detector chain."
        )
        return DispositionResolution(
            "predecessor-consumed",
            consumed,
            diagnostics,
            ([consumed] if consumed else []),
            _detection("env-override"),
        )

    if override_norm == "single-session":
        diagnostics.append(
            "WARN: WSC_DISPOSITION=single-session cannot downgrade a positively-detected "
            "consume — this override only escalates, never suppresses. Running the detector "
            "chain normally."
        )
    elif override:
        diagnostics.append(
            f"WARN: unrecognised WSC_DISPOSITION={override!r} — accepted values are "
            "predecessor-consumed (canonical) or chain-terminal (legacy alias). Ignoring and "
            "running the detector chain normally."
        )
    elif handoff_raw:
        diagnostics.append(
            "NOTE: WSC_CONSUMED_HANDOFF is set without WSC_DISPOSITION — ignored; it alone "
            "cannot flip disposition."
        )

    consumed_paths, mirror_conflicts = primary_consumed_handoff_scan(repo_root, sid)
    if mirror_conflicts:
        diagnostics.append(
            f"WARN: {len(mirror_conflicts)} handoff(s) name this session as ledger claim holder "
            f"while their tracked frontmatter names a DIFFERENT holder — an incomplete takeover "
            f"(a pickup that promoted its ledger claim and then halted without landing d2's "
            f"frontmatter stamp), not a consume. NOT adopted as predecessor-consumed; the "
            f"detector chain continues below:"
        )
        for path in mirror_conflicts:
            diagnostics.append(f"  {path}")
        diagnostics.append(
            "If this session genuinely holds one of these batons, complete the pickup (so the "
            "frontmatter stamp lands) or export WSC_DISPOSITION=predecessor-consumed with "
            "WSC_CONSUMED_HANDOFF=<path>. If it does not, release the stale claim via "
            "`pickup-assemble drop <path>`."
        )

    # Bound once, above every return below, so a holder-mismatch conflict
    # reaches `.detection` on whichever leg ends up deciding — the refusal
    # moves the disposition, and this is the only fact that says WHY it
    # moved. `coordinator_core.workstream_complete._session_shape_is_
    # uncertain` reads this key to raise `jp-session-shape`, restoring the
    # correction channel a "certain" live-consume resolution had none of.
    # functools.partial rather than a hand-declared wrapper that re-lists
    # `_detection`'s first four parameters — Review: coordinator-code-reviewer
    # (Finding 1, nit). A hand-copied signature here would silently stop
    # forwarding any future parameter added to `_detection` unless this
    # wrapper were edited in lockstep; partial forwards every positional/
    # keyword argument through by construction, so that drift is structurally
    # impossible rather than merely unlikely.
    _det = functools.partial(_detection, mirror_conflicts=mirror_conflicts or None)

    if consumed_paths:
        return DispositionResolution(
            "predecessor-consumed",
            consumed_paths[0],
            diagnostics,
            consumed_paths,
            _det("live-consume"),
        )

    arch = detector_a(repo_root, sid)

    ship_base = git_merge_base(repo_root)
    if ship_base is None:
        diagnostics.append(
            "WARN: could not resolve origin/main merge-base — Detector B (git-provenance "
            "chain-terminal detection) skipped; if this session shipped/archived a handoff, "
            "chain-terminal may be missed — verify manually or export "
            "WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also accepted)"
        )
        shipped_by_me = None
    else:
        shipped_by_me = detector_b_shipped_by_me(repo_root, sid, ship_base, diagnostics)

    arch_via = None
    if not arch and shipped_by_me:
        rejected, reason = _foreign_consumer_guard(repo_root, shipped_by_me, sid)
        if rejected:
            diagnostics.append(f"NOTE: Detector B hit {shipped_by_me} rejected — {reason}")
        else:
            shipped_path = repo_root / shipped_by_me
            try:
                text = shipped_path.read_text(errors="replace")
            except OSError:
                text = ""
            if re.search(r"^predecessor:", text, re.MULTILINE):
                arch = shipped_by_me

    # Gated behind `not arch` — Review: coordinator-code-reviewer (Finding
    # 2). Detector A/B ("archive" leg) always wins over the memo leg
    # unconditionally per THE PRECEDENCE CONTRACT, so when `arch` is already
    # truthy the memo scan (and the session-start git ladder it can pay for)
    # would only be discarded work, plus a diagnostics-leak: an
    # archive-resolved session would otherwise show an unrelated memo
    # candidate note. Resolved BEFORE the Detector C call below so it is
    # available for the precedence decision after it — Detector C's own
    # call is never made conditional on this.
    memo_path: str | None = None
    c_status: str | None = None
    c_match_facts: dict[str, Any] | None = None
    if not arch:
        memo_path = find_memo_predecessor(repo_root, sid, diagnostics)
        c_outcome = detector_c(repo_root, sid, ship_base, find_session_claim_cli(), diagnostics)
        c_result, c_status = c_outcome
        c_match_facts = c_outcome.match_facts
        if c_status not in ("indeterminate", "ambiguous") and c_result:
            arch = c_result
            arch_via = "crash-recovery"

    if arch:
        if arch_via == "crash-recovery":
            matched_count = c_match_facts.get("matched_scope_entry_count") if c_match_facts else None
            scope_size = c_match_facts.get("scope_size") if c_match_facts else None
            single_match_kind = c_match_facts.get("single_match_kind") if c_match_facts else None
            # This is ONE of TWO copies of this rule, not a shared home:
            # `coordinator_core.workstream_complete._session_shape_is_
            # uncertain`'s Detector-C branch duplicates this exact predicate
            # inline rather than calling `is_coincidence_prone_detection` —
            # see that function's own docstring for why delegation was
            # tried and reverted. If this rule ever needs to change, change
            # BOTH copies.
            coincidence_prone = is_coincidence_prone_detection(c_match_facts or {})
            if coincidence_prone and memo_path:
                diagnostics.append(
                    f"NOTE: memo-predecessor ({memo_path}) preempts a coincidence-prone "
                    f"Detector C match ({arch}: {matched_count} of {scope_size} scope entries "
                    f"matched, single_match_kind={single_match_kind!r}) — see THE PRECEDENCE "
                    f"CONTRACT on resolve_disposition."
                )
                return _memo_predecessor_result(
                    diagnostics, c_status, c_match_facts, memo_path, mirror_conflicts or None
                )
            if coincidence_prone:
                # AMENDMENT BREADCRUMB (2026-08-20, wsc-identity-gates-key-on-the-
                # deliverable C4): this is the caller's ADOPTION of Detector C's
                # verdict giving way here, not a change to Detector C's own
                # matching logic (is_coincidence_prone_detection/detector_c/
                # _resolve_crash_recovery are untouched) — see THE PRECEDENCE
                # CONTRACT above. With no memo to corroborate a weak match, do
                # NOT set `arch` — let control fall through to the shared
                # single-session return below, which keeps `deciding_leg`
                # "detector-c" (not "none") and carries `detector_c_status` plus
                # the match facts on `.detection`, so this coincidence-prone
                # crash-recovery shape stays distinguishable from a genuine
                # "nothing found" single-session close rather than silently
                # discarding Detector C's own verdict.
                diagnostics.append(
                    f"NOTE: Detector C's crash-recovery match ({arch}: {matched_count} of "
                    f"{scope_size} scope entries matched, single_match_kind={single_match_kind!r}) "
                    f"is coincidence-prone and no memo-predecessor corroborated it — NOT adopted "
                    f"as predecessor-consumed. Falling through to single-session; "
                    f"detection.deciding_leg stays 'detector-c' with the match facts intact, "
                    f"not discarded."
                )
                arch = None
                arch_via = None
        if arch:
            if arch_via != "crash-recovery":
                diagnostics.append(
                    f"NOTE: chain-terminal resolved from archive (shipped/archived without a live "
                    f"consume): {arch}"
                )
            return DispositionResolution(
                "predecessor-consumed",
                arch,
                diagnostics,
                [arch],
                _det(
                    "detector-c" if arch_via == "crash-recovery" else "archive",
                    c_status if arch_via == "crash-recovery" else None,
                    c_match_facts if arch_via == "crash-recovery" else None,
                ),
            )

    if memo_path:
        diagnostics.append(
            f"NOTE: disposition resolved memo-predecessor ({memo_path}) — no archive/"
            f"detector-c predecessor was found (Detector C status: {c_status!r})."
        )
        if shipped_by_me:
            # The single-session WARN below is unreachable once the memo leg
            # decides, but its operator-facing fact survives the new outcome
            # unchanged: d-coverage-gate is built only for PREDECESSOR_CONSUMED
            # with a non-empty consumed_handoff, and memo-predecessor is neither.
            # Dropping the warning here would silently cost a session that
            # archived a handoff the one signal telling it the gate was skipped.
            diagnostics.append(
                f"WARN: session {sid} archived a handoff this run ({shipped_by_me}) but "
                f"disposition resolved memo-predecessor — Step 2.9's chain-end coverage gate "
                f"will be SKIPPED. If this session actually consumed that handoff, export "
                f"WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also "
                f"accepted) and WSC_CONSUMED_HANDOFF={shipped_by_me} before continuing."
            )
        return _memo_predecessor_result(
            diagnostics, c_status, c_match_facts, memo_path, mirror_conflicts or None
        )

    if shipped_by_me:
        diagnostics.append(
            f"WARN: session {sid} archived a handoff this run ({shipped_by_me}) but disposition "
            f"resolved single-session — Step 2.9's chain-end coverage gate will be SKIPPED. If "
            f"chain-terminal, export WSC_DISPOSITION=predecessor-consumed (chain-terminal "
            f"legacy alias also accepted) and WSC_CONSUMED_HANDOFF={shipped_by_me} before "
            f"continuing."
        )
    if c_status == "indeterminate":
        diagnostics.append(
            "WARN: disposition resolved single-session with Detector C (crash-recovery "
            "liveness) INDETERMINATE — Step 2.9's chain-end coverage gate will be SKIPPED and "
            "that skip may be wrong. If this session recovered a crashed session's baton, "
            "export WSC_DISPOSITION=predecessor-consumed (chain-terminal legacy alias also "
            "accepted) and WSC_CONSUMED_HANDOFF=<path> before continuing."
        )
    if c_status == "ambiguous":
        diagnostics.append(
            "WARN: disposition resolved single-session despite Detector C finding multiple "
            "candidate stale batons — Step 2.9's chain-end coverage gate will be SKIPPED and "
            "that skip may be wrong. Export WSC_DISPOSITION=predecessor-consumed "
            "(chain-terminal legacy alias also accepted) and "
            "WSC_CONSUMED_HANDOFF=<the one you are continuing> before continuing."
        )
    # `c_status == "crash-recovery"` reaching this final fallback happens
    # ONLY via the coincidence-prone-with-no-memo reroute above (every other
    # path that produces a "crash-recovery" status either adopts it as
    # predecessor-consumed or is preempted by a memo and returns earlier) —
    # keep `deciding_leg` "detector-c" (not "none") and carry the match
    # facts forward in that one case, so this shape stays distinguishable
    # from a genuine "nothing found" single-session close on `.detection`.
    return DispositionResolution(
        "single-session",
        "",
        diagnostics,
        [],
        _det(
            "detector-c" if c_status == "crash-recovery" else "none",
            c_status,
            c_match_facts if c_status == "crash-recovery" else None,
        ),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _shq(s: str) -> str:
    """Single-quote a value for safe consumption by a bash `eval` caller."""
    return "'" + s.replace("'", "'\\''") + "'"


def _git_show_toplevel() -> Path | None:
    top = show_toplevel()
    return Path(top) if top else None


def _cmd_resolve(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _git_show_toplevel()
    if repo_root is None:
        print(
            "wsc-session-disposition: could not resolve repo root (git rev-parse "
            "--show-toplevel failed) — pass --repo-root explicitly",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    sid = resolve_session_id(repo_root)
    if not sid:
        # KS-5: never run the detector chain against an unresolved sid — an
        # empty sid would either (a) spuriously match unclaimed handoffs
        # (resolve_claim_state's holder is also "" for those, so `"" == sid`
        # would false-positive), or (b) fall through to "single-session",
        # which reads as a clean chain-end coverage gate skip identical to
        # the false clean the fabricated-epoch fallback produced. Fail loud
        # instead.
        print(
            "wsc-session-disposition: session id could not be resolved via any tier "
            "(em_sid/CLAUDE_SESSION_ID/CLAUDE_CODE_SESSION_ID) — refusing to classify "
            "chain-terminal disposition against an unidentified session (KS-5: the "
            "fabricated-epoch fallback that used to paper over this was removed as "
            "strictly worse than reporting unresolved)",
            file=sys.stderr,
        )
        return _SESSION_ID_UNRESOLVED
    disposition, consumed, diagnostics, _consumed_paths = resolve_disposition(repo_root, sid)

    for msg in diagnostics:
        print(msg, file=sys.stderr)

    if args.format == "json":
        print(json.dumps({"WSC_SID": sid, "WSC_DISPOSITION": disposition, "WSC_CONSUMED_HANDOFF": consumed}))
    else:
        print(f"WSC_SID={_shq(sid)}")
        print(f"WSC_DISPOSITION={_shq(disposition)}")
        print(f"WSC_CONSUMED_HANDOFF={_shq(consumed)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wsc-session-disposition")
    sub = p.add_subparsers(dest="subcommand", required=True)

    resolve_p = sub.add_parser(
        "resolve",
        help="Resolve WSC_SID / WSC_DISPOSITION / WSC_CONSUMED_HANDOFF for the current session",
    )
    resolve_p.add_argument(
        "--repo-root",
        default=None,
        help="Repo root to resolve against (default: `git rev-parse --show-toplevel`)",
    )
    resolve_p.add_argument(
        "--format",
        choices=("eval", "json"),
        default="eval",
        help="eval (default): bash-eval-safe KEY='value' lines on stdout. "
        "json: a single JSON object.",
    )
    resolve_p.set_defaults(func=_cmd_resolve)
    return p


def main(argv: list[str]) -> int:
    _bootstrap_engine_imports()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
