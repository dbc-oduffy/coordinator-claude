"""Per-session ledger of resolved-but-undischarged next moves.

Spec backlink: docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md
(chunk C3).

Store for `watchdog-undischarged-next-move.py`. An "obligation" is a
machine-resolved next action the EM has not yet invoked -- opened by a
PostToolUse observation of a seam-opening call, discharged by a PostToolUse
observation of the matching terminal call. Nothing here infers state from
timing, idle duration, or transcript shape; every mutation is triggered by a
concrete tool-call observation the caller already has in hand.

Record shape (one per obligation, JSON-serialised):
  {obligation_id, seam, next_action, opened_at, progressed_at|null, discharged_at|null, fired}

Storage: `state/subagent-share/<session-id>/next-move-ledger.jsonl`, the
existing per-session bookkeeping convention (see
`state/subagent-share/<session-id>/advisory-fire-counts.jsonl` for the same
shape used elsewhere) -- not a new path convention. The whole ledger is
rewritten on each mutation (open/discharge/mark-fired): per-session record
counts are tiny (at most three concurrent obligations, per the static seam
table), so this is not a hot-path cost concern.

Windows-safe throughout: paths built via `os.path.join`/`pathlib`, no `/tmp`
literal, home resolution via `os.path.expanduser("~")` where needed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from typing import Any, Optional

_LEDGER_FILENAME = "next-move-ledger.jsonl"

# Reuse the existing root-resolution PRIMITIVE (`_engine_root._session_repo_root`
# -- CLAUDE_PROJECT_DIR when set and real, else a zero-spawn upward walk for a
# `.git` entry) rather than writing a fourth copy of that walk. This is NOT
# the families-spanning shared READER/TRANSPORT module DR-047/DR-118 decline
# (see `_find_repo_root`'s own docstring below, kept verbatim) -- that ruling
# is about collapsing the three coordinator.local.md READERS into one shared
# transport, not about sharing the tiny root-finding primitive beneath them.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
try:
    from _engine_root import _session_repo_root as _resolve_consuming_repo_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its sibling
    # _engine_root.py (e.g. an isolated test harness, or a partial deploy)
    # must still fail-open (this rung simply never resolves) rather than
    # crash on import.
    _resolve_consuming_repo_root = None  # type: ignore[assignment]


def _find_repo_root() -> Optional[str]:
    """Anchor at the CONSUMING repo root: `CLAUDE_PROJECT_DIR` when set and a
    real directory, else a zero-spawn pure-Python upward walk for a `.git`
    entry (directory for a normal clone, file for a worktree). Mirrors
    `_posture._find_repo_root` (kept as a separate copy rather than a shared
    import: DR-047/DR-118 decline a families-spanning shared-transport
    module for this class of tiny, independently-failing-open helper).

    Delegates to `_engine_root._session_repo_root` for the actual walk (see
    the module-level comment above) -- reusing that shared root-resolution
    primitive is explicitly NOT the shared-transport merge DR-047/DR-118
    decline; only the READER stays a separate copy per those DRs.

    Previously walked upward from THIS FILE's own `__file__` looking for a
    directory containing `coordinator.local.md`, which only ever resolves
    this plugin's own checkout -- correct by accident in a dev repo where
    `--plugin-dir` points the plugin at the working tree itself, and a
    silent miss on a marketplace install where the plugin lives under
    `~/.claude/plugins/` and the consumer's `state/subagent-share/` tree
    lives somewhere `__file__` can never reach."""
    if _resolve_consuming_repo_root is None:
        return None
    try:
        root = _resolve_consuming_repo_root()
        return str(root) if root else None
    except Exception:
        return None


def ledger_path(session_id: str) -> Optional[str]:
    """Return the absolute ledger path for `session_id`, or None if the
    repo root cannot be resolved (fail-open caller contract: no repo root
    means no ledger, never a crash)."""
    if not isinstance(session_id, str) or not session_id:
        return None
    repo_root = _find_repo_root()
    if repo_root is None:
        return None
    return os.path.join(repo_root, "state", "subagent-share", session_id, _LEDGER_FILENAME)


def read_records(session_id: str) -> list:
    """Return the list of obligation records for `session_id`, oldest
    first. Missing/unreadable/malformed file -> []. Malformed individual
    lines are skipped rather than aborting the whole read."""
    path = ledger_path(session_id)
    if path is None or not os.path.isfile(path):
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if isinstance(record, dict):
                    records.append(record)
    except OSError:
        return []
    return records


def _write_records(session_id: str, records: list) -> bool:
    """Serialise `records` and atomically replace the ledger file.

    Writes to a temp file in the SAME directory as the ledger, then
    `os.replace()`s it onto the ledger path -- atomic on both POSIX and
    Windows (unlike `os.rename`, which raises on Windows if the
    destination already exists). This closes a read-modify-write race
    between concurrent hook processes: a reader never observes a
    partially-written file, and a losing writer's obligation record is at
    worst a missed fire (Anti-scope: cheaper than a repeat fire), never a
    corrupted ledger. No cross-process lock -- see module docstring; a
    lock file would add a wedged-lock risk this defect class does not
    justify. `_write_records` itself does not decide who "won" a race
    between two racing read-modify-write callers -- `mark_fired` below
    layers its own post-replace confirmation read on top for that.
    """
    path = ledger_path(session_id)
    if path is None:
        return False
    directory = os.path.dirname(path)
    tmp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=".next-move-ledger-", suffix=".tmp", dir=directory
        )
        try:
            try:
                handle = os.fdopen(tmp_fd, "w", encoding="utf-8")
            except Exception:
                # `os.fdopen` failing (fd exhaustion, odd encoding failure)
                # leaves `tmp_fd` unwrapped by any context manager -- close
                # it directly so the raw fd is never leaked.
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
                raise
            with handle:
                for record in records:
                    handle.write(json.dumps(record, sort_keys=True))
                    handle.write("\n")
            os.replace(tmp_path, path)
            tmp_path = None
        finally:
            if tmp_path is not None and os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    except (OSError, TypeError, ValueError):
        return False
    return True


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def open_obligation(session_id: str, obligation_id: str, seam: str, next_action: str) -> bool:
    """Append a new open obligation, UNLESS one with the same
    `obligation_id` is already open (never discharged, regardless of
    `fired`) -- idempotent against a re-observed seam-opening call.
    Returns True if a record was written, False on any failure or no-op."""
    records = read_records(session_id)
    for record in records:
        if record.get("obligation_id") == obligation_id and record.get("discharged_at") is None:
            return False  # already open -- do not duplicate
    records.append(
        {
            "obligation_id": obligation_id,
            "seam": seam,
            "next_action": next_action,
            "opened_at": _now_iso(),
            "progressed_at": None,
            "blocked_at": None,
            "blocked_on_session_id": None,
            "blocked_on_name": None,
            "discharged_at": None,
            "fired": False,
        }
    )
    return _write_records(session_id, records)


def block_obligation(
    session_id: str,
    obligation_id: str,
    blocked_on_session_id: str,
    blocked_on_name: Optional[str] = None,
) -> bool:
    """Stamp `blocked_at` and who this obligation is blocked ON.

    THE ONE SIGNAL NOT WRITTEN AT A BOUNDARY. Every other liveness signal
    either plane can read -- transcript mtime, subagent sidecar mtime,
    `receiver-state.json`, hook-write timestamps -- is written at the END of a
    unit of work, so they all go quiet together and cannot arbitrate between
    each other. A session waiting on a named peer therefore ages identically
    on every field to one that has stopped. This record is written at the
    moment of blocking, by the party that knows it is blocking, before the
    silence starts; that is the whole reason it can say something the others
    cannot. It is not an inference and nothing here derives it from timing.

    This precision holds for a first, uninterrupted fold. It does NOT hold
    across a crash-and-replay of the intake drain: a "blocked" row's
    `emitted_at` is provenance only (never used for ordering, per the intake
    schema table), so a replay after a partially-committed fold re-stamps
    `blocked_at` with the moment of the REPLAY, which can be several drain
    cycles later than the producer's original blocking moment. Callers doing
    precise arbitration against other liveness signals should treat
    `blocked_at` as "blocked, as of at least this stamp" rather than an exact
    original timestamp.

    THE ADDRESS IS A SESSION ID, NEVER A BARE PEER NAME. A name re-points to a
    new session with no event and no visible difference, so a `blocked_on`
    name read an hour later can name a session that has exited or, worse, a
    different one that now answers to it -- the hazard
    `read_pass.resolve_addressee` refuses on the send path, arriving here in a
    stored field instead. `blocked_on_name` rides along for a human reading
    the row; only the id identifies. Tripwire:
    `A-PEER-NAME-IS-NOT-A-STABLE-ADDRESS`.

    Cleared by the next `progress` or `discharge`: a stale block reads as a
    live one, which is the confirming-direction failure this field exists to
    remove.

    NO READER ON THIS PLANE, BY DESIGN -- NOT DEAD CODE. This op family has
    zero consumers under `coordinator/`: no rendered surface in this repo
    reads `blocked_at`/`blocked_on_session_id`/`blocked_on_name`. Its
    consumer is the engine plane: `claude-klabauter-em` requested this op by
    memo, and the folding/read side lives there, not here -- this repo is
    the ledger's sole WRITER for this op, the same relationship it already
    has with the intake side of `_next_move_ledger.py`. See
    `coordinator/docs/wiki/obligations-inbound-intake.md` for the contract.
    A future reader with a dead-code eye: check that wiki before deleting --
    a write-only field with no local consumer is the correct shape here, not
    a defect.
    """
    if not isinstance(blocked_on_session_id, str) or not blocked_on_session_id:
        return False
    records = read_records(session_id)
    changed = False
    for record in records:
        if record.get("obligation_id") == obligation_id and record.get("discharged_at") is None:
            record["blocked_at"] = _now_iso()
            record["blocked_on_session_id"] = blocked_on_session_id
            record["blocked_on_name"] = blocked_on_name
            changed = True
    return _write_records(session_id, records) if changed else False


def _clear_block(record: dict) -> None:
    """A block is cleared by the obligation moving, never by its own age."""
    record["blocked_at"] = None
    record["blocked_on_session_id"] = None
    record["blocked_on_name"] = None


def progress_obligation(session_id: str, obligation_id: str) -> bool:
    """Stamp `progressed_at` on the open record matching `obligation_id`.

    The state between opened and discharged, and the one the record could not express.
    `fired` is a boolean about the NUDGE -- whether anyone was told -- and carries nothing about
    the work, so a row whose seam dispatched and is an hour into recovery is shaped identically
    to one that never started. A reader cannot tell a stalled obligation from a moving one, which
    is exactly what a watch needs to know.

    A TIMESTAMP RATHER THAN A STATE ENUM, deliberately: it answers "is this moving" without two
    planes having to agree a state machine, and its absence degrades to the previous behaviour
    rather than to a wrong answer. Re-stamping is the point -- every leg of work moves it forward,
    so the field reads as "last seen moving", never as "started once".
    """
    records = read_records(session_id)
    changed = False
    for record in records:
        if record.get("obligation_id") == obligation_id and record.get("discharged_at") is None:
            record["progressed_at"] = _now_iso()
            _clear_block(record)
            changed = True
    return _write_records(session_id, records) if changed else False


def discharge_obligation(session_id: str, obligation_id: str) -> bool:
    """Stamp `discharged_at` on the open record matching `obligation_id`.
    No-op (returns False) if no such open record exists."""
    records = read_records(session_id)
    changed = False
    for record in records:
        if record.get("obligation_id") == obligation_id and record.get("discharged_at") is None:
            record["discharged_at"] = _now_iso()
            _clear_block(record)
            changed = True
    if not changed:
        return False
    return _write_records(session_id, records)


def mark_fired(session_id: str, obligation_id: str) -> bool:
    """Set `fired: true` on the record matching `obligation_id`. This is
    the ONE-FIRE-PER-OBLIGATION latch (A6): once set, a repeat Stop finds
    no undischarged-and-unfired record and stays silent.

    `_write_records`'s temp+`os.replace` makes ONE write atomic, but two
    Stop-hook processes racing on the same unfired obligation can both
    `read_records` before either replaces, both observe `fired: False`,
    and both would otherwise get a truthy latch result -- the exact
    repeat-fire the module docstring rejects. Closed here, without a
    cross-process lock, by tagging this call's write with a private
    one-shot token and immediately re-reading the just-replaced file: only
    the writer whose token survives the replace (i.e. no later racing
    writer's replace has landed since) is told it won the latch. The
    loser -- its own write clobbered by the winner's later replace --
    degrades to a silent miss, never a second fire.
    """
    records = read_records(session_id)
    changed = False
    token = uuid.uuid4().hex
    for record in records:
        if record.get("obligation_id") == obligation_id and not record.get("fired"):
            record["fired"] = True
            record["fire_token"] = token
            changed = True
    if not changed:
        return False
    if not _write_records(session_id, records):
        return False
    for record in read_records(session_id):
        if record.get("obligation_id") == obligation_id:
            return record.get("fire_token") == token
    return False


# ---------------------------------------------------------------------------
# Obligations-inbound intake -- the engine->doctrine-plane fold
# ---------------------------------------------------------------------------
#
# The doctrine plane is the SOLE WRITER of this ledger. The engine plane (`coordinator_core`)
# resolves obligations of its own and must not write these files: both planes
# writing the same peer's ledger on the same Stop event is a read-modify-
# whole-file-rewrite collision, the race `mark_fired` above already documents.
# So the engine APPENDS rows to a separate, append-only intake file and this plane
# folds them in. One writer, one rewrite path, no shared file.
#
#   producer (engine) --append--> obligations-inbound.jsonl
#   consumer (here)   --claim---> obligations-inbound.jsonl.draining
#                     --fold----> next-move-ledger.jsonl
#                     --delete--> (only after the fold committed)
#
# Row shape, one JSON object per line. The producing plane's copy of this
# table lives at `coordinator/docs/wiki/obligations-inbound-intake.md`:
#
#   schema         int, must be 1
#   session_id     str, the session the obligation belongs to; must equal the
#                  session directory the file sits in
#   op             "open" | "progress" | "blocked" | "discharge"
#   obligation_id  str, the producer's stable id for this obligation
#   emitted_at     str, ISO-8601 Z; provenance only, never used for ordering
#   seam           str, REQUIRED for op="open", ignored otherwise
#   next_action    str, REQUIRED for op="open", ignored otherwise
#   blocked_on_session_id
#                  str, REQUIRED for op="blocked" -- a SESSION ID, never a bare
#                  peer name (see `block_obligation`); ignored otherwise
#   blocked_on_name
#                  str, optional companion to the id, for a human reading the
#                  row; never used to identify anything
#   producer       str, optional free-form provenance
#
# Unknown keys are ignored, so the producer can add fields without a lockstep
# release here.
#
# THREE FAILURE-PATH RULES, each load-bearing:
#
# 1. A TRAILING partial line is tolerated; a malformed line MID-FILE is not.
#    A torn last line is a producer caught mid-append and costs one row. A
#    malformed line with rows after it is a producer BUG, and silently
#    skipping it would keep that bug invisible for as long as it kept
#    shipping. Such lines are quarantined verbatim to
#    `obligations-inbound.rejected.jsonl` and counted in the drain report --
#    visible on disk, without stalling the fold behind a row nobody is coming
#    to fix.
#
# 2. The claim uses a FIXED `.draining` suffix, drained on startup. A
#    timestamped or pid-stamped name would leave a fold that died partway
#    orphaning its rows under a name nothing ever looks for again; a fixed
#    name means the next drain finds them.
#
# 3. The drained file is deleted only AFTER the fold has committed. Deleting
#    first means a failed write loses the rows outright; deleting after costs
#    at worst a replay, and every fold op is idempotent -- `open_obligation`
#    dedupes on `obligation_id` and the stamps re-stamp.
#
# No cross-process lock. Concurrent drainers are safe by that same
# idempotence: the `O_EXCL` claim below serialises the common case, and a
# drainer that cannot claim defers to the next drain rather than replacing an
# unread `.draining` file.

_INTAKE_FILENAME = "obligations-inbound.jsonl"
_DRAINING_SUFFIX = ".draining"
_REJECTED_FILENAME = "obligations-inbound.rejected.jsonl"
_INTAKE_SCHEMA = 1
_INTAKE_OPS = ("open", "progress", "blocked", "discharge")


def intake_path(session_id: str) -> Optional[str]:
    """Absolute path of the append-only intake file the engine plane writes."""
    ledger = ledger_path(session_id)
    if ledger is None:
        return None
    return os.path.join(os.path.dirname(ledger), _INTAKE_FILENAME)


def _validate_intake_row(row: Any, session_id: str) -> Optional[str]:
    """None if `row` is foldable, else a short reason string."""
    if not isinstance(row, dict):
        return "not a JSON object"
    if row.get("schema") != _INTAKE_SCHEMA:
        return "unsupported schema"
    if row.get("session_id") != session_id:
        return "session_id does not match this file's session"
    op = row.get("op")
    if op not in _INTAKE_OPS:
        return "unknown op"
    obligation_id = row.get("obligation_id")
    if not isinstance(obligation_id, str) or not obligation_id:
        return "missing obligation_id"
    if op == "open":
        for field in ("seam", "next_action"):
            value = row.get(field)
            if not isinstance(value, str) or not value:
                return "op=open missing " + field
    if op == "blocked":
        blocked_on = row.get("blocked_on_session_id")
        if not isinstance(blocked_on, str) or not blocked_on:
            # A bare name is not accepted in its place. A row naming who it
            # waits on with an address that re-points says something wrong
            # later, which is worse than saying nothing now.
            return "op=blocked missing blocked_on_session_id"
    return None


def parse_intake(text: str, session_id: str) -> tuple:
    """Split raw intake text into (foldable rows, rejected raw lines).

    An unterminated final line that does not PARSE is the tolerated trailing
    partial -- dropped silently, per rule 1. A final line that parses is a
    whole line and a real record: position does not excuse it from
    validation. Every other bad line anywhere in the file is rejected.
    """
    if not text:
        return [], []
    lines = text.split("\n")
    has_trailing_partial = bool(lines[-1])
    if not has_trailing_partial:
        lines = lines[:-1]
    rows: list = []
    rejected: list = []
    last_index = len(lines) - 1
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            if has_trailing_partial and index == last_index:
                continue  # producer caught mid-append -- tolerated
            rejected.append(raw)
            continue
        if _validate_intake_row(row, session_id) is not None:
            rejected.append(raw)
            continue
        rows.append(row)
    return rows, rejected


def _apply_intake_row(session_id: str, row: dict) -> bool:
    """Apply one row; return whether it actually mutated the ledger.

    `open_obligation`/`progress_obligation`/`block_obligation`/
    `discharge_obligation` all return this already -- a no-op read (the
    referenced `obligation_id` isn't a currently-open record) is not a raise,
    so it must not be folded into a "committed" count silently.
    """
    op = row["op"]
    obligation_id = row["obligation_id"]
    if op == "open":
        return open_obligation(session_id, obligation_id, row["seam"], row["next_action"])
    elif op == "progress":
        return progress_obligation(session_id, obligation_id)
    elif op == "blocked":
        return block_obligation(
            session_id,
            obligation_id,
            row["blocked_on_session_id"],
            row.get("blocked_on_name"),
        )
    else:  # op == "discharge" -- the only value _validate_intake_row admits here
        return discharge_obligation(session_id, obligation_id)


def _quarantine(directory: str, rejected: list) -> bool:
    """Append rejected lines verbatim to the per-session rejected file.

    Idempotent against a replay of the SAME `.draining` file: if this exact
    block of rejected lines is already the tail of the rejected file, skip
    the write rather than doubling every rejected row. That replay is the
    one rule-3 promises -- a committed fold whose subsequent `os.remove`
    failed -- and nothing else appends to a given session's rejected file
    between one drain and the next, so a tail match is a safe, cheap proxy
    for "already quarantined this batch", not a general content dedupe.
    """
    if not rejected:
        return True
    path = os.path.join(directory, _REJECTED_FILENAME)
    block = "".join(line.rstrip("\n") + "\n" for line in rejected)
    try:
        os.makedirs(directory, exist_ok=True)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                existing = handle.read()
            if existing.endswith(block):
                return True
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(block)
    except OSError:
        return False
    return True


def _drain_one_file(session_id: str, draining: str) -> dict:
    """Fold one claimed `.draining` file, then delete it. Rule 3."""
    report = {"folded": 0, "noop": 0, "rejected": 0, "deleted": False}
    try:
        with open(draining, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return report
    rows, rejected = parse_intake(text, session_id)
    for row in rows:
        try:
            mutated = _apply_intake_row(session_id, row)
        except Exception:  # noqa: BLE001
            # A fold that cannot commit keeps the file (below): rows survive
            # to the next drain, where the replay is idempotent.
            # `drain_intake` promises never to raise, and its caller is a
            # Stop hook.
            return report
        if mutated:
            report["folded"] += 1
        else:
            report["noop"] += 1
    report["rejected"] = len(rejected)
    if not _quarantine(os.path.dirname(draining), rejected):
        # The fold committed but the quarantine did not. Keep the file: a
        # replay is idempotent, a silently dropped producer bug is not.
        return report
    try:
        os.remove(draining)
        report["deleted"] = True
    except OSError:
        pass
    return report


def _merge_drained(report: dict, drained: dict) -> bool:
    """Fold one `_drain_one_file` result into the running `drain_intake`
    report; return whether the drained file is actually gone.

    The one place both the orphan claim and the fresh claim decide what a
    fold outcome means for the caller-facing report -- written once so the
    two paths cannot drift the way primary/orphan handling did before (a
    `deleted` check present on one and missing on the other). Anything that
    is not `deleted` is `deferred`, no exceptions: a delete failure after a
    committed fold is exactly as undrained, from the next drain's point of
    view, as a fold that never committed at all.
    """
    report["folded"] += drained["folded"]
    report["noop"] += drained["noop"]
    report["rejected"] += drained["rejected"]
    if not drained["deleted"]:
        report["deferred"] = True
        return False
    return True


def drain_intake(session_id: str) -> dict:
    """Fold `obligations-inbound.jsonl` for `session_id` into the ledger.

    Drains any orphaned `.draining` file FIRST (rule 2), then claims the
    current intake file and drains that. Returns a report dict; never raises.
    """
    report = {"folded": 0, "noop": 0, "rejected": 0, "deferred": False}
    path = intake_path(session_id)
    if path is None:
        return report
    draining = path + _DRAINING_SUFFIX

    if os.path.isfile(draining):
        orphan = _drain_one_file(session_id, draining)
        if not _merge_drained(report, orphan):
            # Still there -- the fold could not commit, or a peer drainer owns
            # it. Leave the fresh intake for the next drain rather than
            # replacing a claim nobody has read.
            return report

    if not os.path.isfile(path):
        return report

    try:
        claim_fd = os.open(draining, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError:
        report["deferred"] = True
        return report
    try:
        os.close(claim_fd)
    except OSError:
        pass
    try:
        os.replace(path, draining)
    except OSError:
        try:
            os.remove(draining)
        except OSError:
            pass
        report["deferred"] = True
        return report

    drained = _drain_one_file(session_id, draining)
    _merge_drained(report, drained)
    return report


def drain_all_intakes(repo_root: Optional[str] = None) -> dict:
    """Drain every session's intake under `state/subagent-share/`.

    The Group EM's read is the one that matters for a peer whose turn has
    ended: that peer's own Stop hook is not going to fire again to fold its
    own rows, so a fold that only ever ran session-locally would leave exactly
    the sessions the watch exists to notice unfolded. No predicate here reads
    that state -- the sweep visits every session with an intake file, and it
    is the presence of the FILE, never any peer-state judgement, that selects.
    """
    totals = {"sessions": 0, "folded": 0, "noop": 0, "rejected": 0, "deferred": 0}
    root = repo_root if repo_root else _find_repo_root()
    if not root:
        return totals
    share = os.path.join(root, "state", "subagent-share")
    try:
        session_ids = sorted(os.listdir(share))
    except OSError:
        return totals
    for session_id in session_ids:
        directory = os.path.join(share, session_id)
        if not os.path.isfile(os.path.join(directory, _INTAKE_FILENAME)) and not os.path.isfile(
            os.path.join(directory, _INTAKE_FILENAME + _DRAINING_SUFFIX)
        ):
            continue
        report = drain_intake(session_id)
        totals["sessions"] += 1
        totals["folded"] += report["folded"]
        totals["noop"] += report["noop"]
        totals["rejected"] += report["rejected"]
        totals["deferred"] += 1 if report["deferred"] else 0
    return totals


def find_undischarged_unfired(session_id: str) -> Optional[dict]:
    """Return the first record that is open (discharged_at is None) and
    not yet fired (fired is False/absent), or None. This is the ENTIRE
    read surface the Stop hook consults -- no other signal, per module
    docstring."""
    for record in read_records(session_id):
        if record.get("discharged_at") is None and not record.get("fired"):
            return record
    return None
