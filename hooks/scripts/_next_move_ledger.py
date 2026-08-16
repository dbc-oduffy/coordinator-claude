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
  {obligation_id, seam, next_action, opened_at, discharged_at|null, fired}

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
from typing import Optional

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
            "discharged_at": None,
            "fired": False,
        }
    )
    return _write_records(session_id, records)


def discharge_obligation(session_id: str, obligation_id: str) -> bool:
    """Stamp `discharged_at` on the open record matching `obligation_id`.
    No-op (returns False) if no such open record exists."""
    records = read_records(session_id)
    changed = False
    for record in records:
        if record.get("obligation_id") == obligation_id and record.get("discharged_at") is None:
            record["discharged_at"] = _now_iso()
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


def find_undischarged_unfired(session_id: str) -> Optional[dict]:
    """Return the first record that is open (discharged_at is None) and
    not yet fired (fired is False/absent), or None. This is the ENTIRE
    read surface the Stop hook consults -- no other signal, per module
    docstring."""
    for record in read_records(session_id):
        if record.get("discharged_at") is None and not record.get("fired"):
            return record
    return None
