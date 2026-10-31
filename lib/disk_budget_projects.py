"""Projects pruner for the disk-budget enforcer: bounds ~/.claude/projects by size AND age.

`disk_budget.prune_projects` delegates to `prune_projects` here. One `os.scandir` walk builds
`Unit`s (subagent transcript + meta pair, workflow run, tool-results entry, non-live main
transcript, repo `scratch/warp/*.workflow.mjs` script) and sizes the whole tree; the pass then

1. deletes what is stale regardless of cap: resolved workflow runs and the scripts naming them,
   subagent transcripts older than `subagent_max_age_hours`, non-live main transcripts older than
   `transcript_max_age_days`;
2. applies the per-session ceiling, then the global cap, deleting eligible units oldest-first.

Never deleted: a live session's main transcript (registered live or mtime inside `min_age_hours`),
a non-live main transcript younger than `transcript_max_age_days` (age only, never size), anything
under a `memory/` dir, any path named `pm_turns*`, any workflow run whose state is non-terminal,
unreadable or unrecognised (fail closed) until its newest file passes `min_age_hours`.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

from disk_budget import (
    TERMINAL_RUN_STATUSES,
    FreeProbe,
    Policy,
    Roots,
    SweepReport,
    Unit,
    resolve_roots,
    under_volume_pressure,
)

__all__ = ["prune_projects"]

HOUR = 3600.0
DAY = 24 * HOUR
_MAX_STATE_BYTES = 8 * 1024 * 1024
_PRUNABLE_DIRS = ("subagents", "workflows", "tool-results")
_ID_KEYS = ("run_id", "runId", "id")


def _protected(name: str) -> bool:
    return name == "memory" or "pm_turns" in name


def _scan(path: str):
    """(total bytes, newest mtime) of a file or directory tree; unreadable entries count as zero."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0.0
    if not stat.S_ISDIR(st.st_mode):
        return st.st_size, st.st_mtime
    size, newest = 0, st.st_mtime
    try:
        with os.scandir(path) as it:
            for entry in it:
                s, m = _scan(entry.path)
                size += s
                newest = max(newest, m)
    except OSError:
        pass
    return size, newest


def _read_run_state(path: str):
    """(status or None, ids) from a workflow run file; any failure yields (None, set())."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_MAX_STATE_BYTES)
        text = raw.decode("utf-8", errors="replace").lstrip()
        obj, _ = json.JSONDecoder().raw_decode(text)
    except (OSError, ValueError):
        return None, set()
    if not isinstance(obj, dict):
        return None, set()
    status = obj.get("status")
    status = status.strip().lower() if isinstance(status, str) else None
    ids = {str(obj[k]) for k in _ID_KEYS if isinstance(obj.get(k), (str, int))}
    return status, ids


def _run_ids(name: str, ids: set) -> set:
    stem = name.split(".")[0]
    out = set(ids) | {stem}
    if stem.startswith("wf_"):
        out.add(stem[3:])
    return out


def _workflow_units(sess_dir: str, session: str, policy: Policy, now: float, terminal_ids: set, running_ids: set):
    units = []
    try:
        entries = list(os.scandir(sess_dir))
    except OSError:
        return units
    for entry in entries:
        if _protected(entry.name):
            continue
        size, newest = _scan(entry.path)
        status, ids = None, set()
        if entry.is_file(follow_symlinks=False):
            status, ids = _read_run_state(entry.path)
        else:
            for cand in (entry.name + ".json", "state.json", "run.json"):
                p = os.path.join(entry.path, cand)
                if os.path.isfile(p):
                    status, ids = _read_run_state(p)
                    break
        run_ids = _run_ids(entry.name, ids)
        terminal = status in TERMINAL_RUN_STATUSES
        (terminal_ids if terminal else running_ids).update(run_ids)
        age_ok = now - newest > policy.min_age_hours * HOUR
        units.append(
            (
                Unit(
                    "workflow",
                    (entry.path,),
                    size,
                    newest,
                    session,
                    eligible=terminal or age_ok,
                    reason="resolved" if terminal else "",
                ),
                terminal,
            )
        )
    return units


def _wf_dir_protected(entry, policy: Policy, now: float, running_ids: set) -> bool:
    """True when a nested `wf_<id>` dir belongs to a running run or holds non-terminal state still young."""
    status, ids = None, set()
    for cand in (entry.name + ".json", "state.json", "run.json"):
        p = os.path.join(entry.path, cand)
        if os.path.isfile(p):
            status, ids = _read_run_state(p)
            break
    if _run_ids(entry.name, ids) & running_ids:
        return True
    if status in TERMINAL_RUN_STATUSES:
        return False
    if status is None and not ids:
        return False
    newest = _scan(entry.path)[1]
    return now - newest <= policy.subagent_max_age_hours * HOUR


def _subagent_units(sub_dir: str, session: str, policy: Policy, now: float, running_ids: Optional[set] = None):
    """Units under `<session>/subagents`, recursing into every nested directory (e.g. `workflows/wf_<id>`)."""
    running_ids = running_ids if running_ids is not None else set()
    groups: dict = {}
    out = []
    try:
        entries = list(os.scandir(sub_dir))
    except OSError:
        return []
    for entry in entries:
        if _protected(entry.name):
            continue
        if entry.is_dir(follow_symlinks=False):
            if entry.name.startswith("wf_") and _wf_dir_protected(entry, policy, now, running_ids):
                size, newest = _scan(entry.path)
                out.append((Unit("subagent", (entry.path,), size, newest, session, eligible=False), False))
            else:
                out.extend(_subagent_units(entry.path, session, policy, now, running_ids))
            continue
        key = entry.name.split(".")[0]
        size, newest = _scan(entry.path)
        g = groups.setdefault(key, [[], 0, 0.0])
        g[0].append(entry.path)
        g[1] += size
        g[2] = max(g[2], newest)
    for paths, size, newest in groups.values():
        aged = now - newest > policy.subagent_max_age_hours * HOUR
        out.append(
            (
                Unit(
                    "subagent",
                    tuple(sorted(paths)),
                    size,
                    newest,
                    session,
                    eligible=now - newest > policy.min_age_hours * HOUR,
                    reason="aged" if aged else "",
                ),
                aged,
            )
        )
    return out


def _tool_result_units(tr_dir: str, session: str, policy: Policy, now: float):
    out = []
    try:
        entries = list(os.scandir(tr_dir))
    except OSError:
        return out
    for entry in entries:
        if _protected(entry.name):
            continue
        size, newest = _scan(entry.path)
        out.append(
            (Unit("tool_result", (entry.path,), size, newest, session, eligible=now - newest > policy.min_age_hours * HOUR), False)
        )
    return out


def _script_units(roots: Roots, policy: Policy, now: float, terminal_ids: set, running_ids: set):
    out = []
    for repo in roots.repos:
        warp = Path(repo) / "scratch" / "warp"
        try:
            entries = [e for e in os.scandir(warp) if e.name.endswith(".workflow.mjs")]
        except OSError:
            continue
        for entry in entries:
            try:
                st = entry.stat()
            except OSError:
                continue
            stem = entry.name[: -len(".workflow.mjs")]

            def matches(ids):
                return any(i == stem or (len(i) >= 6 and (i in stem or stem in i)) for i in ids)

            if matches(running_ids):
                continue
            if matches(terminal_ids):
                reason = "resolved"
            elif now - st.st_mtime > policy.min_age_hours * HOUR:
                reason = "unmatched-aged"
            else:
                continue
            out.append(Unit("workflow_script", (entry.path,), st.st_size, st.st_mtime, "", True, reason))
    return out


def _on_rm_error(func, path, exc_info=None):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except OSError:
        pass


def _delete(path: str) -> bool:
    """Remove a file or tree, retrying read-only entries (Windows); True when it is gone."""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=lambda f, p, e: _on_rm_error(f, p))
            else:
                shutil.rmtree(path, onerror=lambda f, p, e: _on_rm_error(f, p))
        else:
            try:
                os.remove(path)
            except PermissionError:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                os.remove(path)
    except OSError:
        pass
    return not os.path.lexists(path)


def prune_projects(
    policy: Policy,
    deadline: float,
    *,
    roots: Optional[Roots] = None,
    now: Optional[float] = None,
    live_sessions: Sequence[str] = (),
    apply: bool = True,
    free_probe: Optional[FreeProbe] = None,
) -> SweepReport:
    """Prune ~/.claude/projects under `policy`; `deadline` is an absolute time.monotonic() value.

    Returns a SweepReport whose `freed_bytes` counts every deleted unit (`apply=False` counts what
    would be deleted) and whose `still_over` is true only when the remaining total exceeds the cap
    AND the volume's free bytes are below `policy.volume_free_floor` (`free_probe(path) -> bytes`).
    """
    roots = roots or resolve_roots()
    now = time.time() if now is None else now
    live = set(live_sessions)
    report = SweepReport()

    total = 0
    pairs = []  # (unit, forced)
    terminal_ids: set = set()
    running_ids: set = set()
    try:
        projects = [e.path for e in os.scandir(roots.projects) if e.is_dir(follow_symlinks=False)]
    except OSError:
        projects = []

    for proj in projects:
        try:
            entries = list(os.scandir(proj))
        except OSError:
            continue
        for entry in entries:
            if entry.is_file(follow_symlinks=False):
                size, newest = _scan(entry.path)
                total += size
                if entry.name.endswith(".jsonl") and not _protected(entry.name):
                    session = entry.name[: -len(".jsonl")]
                    is_live = session in live or now - newest <= policy.min_age_hours * HOUR
                    if not is_live and now - newest > policy.transcript_max_age_days * DAY:
                        pairs.append((Unit("main_transcript", (entry.path,), size, newest, session, False, "aged"), True))
                continue
            if _protected(entry.name) or not entry.is_dir(follow_symlinks=False):
                total += _scan(entry.path)[0]
                continue
            session = entry.name
            try:
                children = list(os.scandir(entry.path))
            except OSError:
                continue
            children.sort(key=lambda c: c.name != "workflows")
            for child in children:
                if child.name not in _PRUNABLE_DIRS or not child.is_dir(follow_symlinks=False):
                    total += _scan(child.path)[0]
                    continue
                if child.name == "subagents":
                    found = _subagent_units(child.path, session, policy, now, running_ids)
                elif child.name == "tool-results":
                    found = _tool_result_units(child.path, session, policy, now)
                else:
                    found = _workflow_units(child.path, session, policy, now, terminal_ids, running_ids)
                for unit, forced in found:
                    total += unit.size
                    pairs.append((unit, forced))

    for script in _script_units(roots, policy, now, terminal_ids, running_ids):
        pairs.append((script, True))

    deleted: set = set()
    state = {"total": total, "stopped": False}

    def remove(unit: Unit, counts_to_total: bool) -> None:
        if state["stopped"]:
            return
        if time.monotonic() >= deadline:
            state["stopped"] = True
            report.log.append("deadline reached; resumes next sweep")
            return
        if apply and not all(_delete(p) for p in unit.paths):
            report.log.append("could not delete " + unit.paths[0])
            return
        deleted.add(unit.paths)
        report.record("projects" if counts_to_total else "workflow_scripts", unit.size)
        report.deleted.append((unit.kind, unit.paths[0], unit.size, unit.reason))
        if counts_to_total:
            state["total"] -= unit.size

    # Stale regardless of cap, oldest first.
    for unit, forced in sorted(pairs, key=lambda p: p[0].newest_mtime):
        if forced:
            remove(unit, unit.kind != "workflow_script")

    # Size pressure over prunable, non-protected units: per-session ceiling, then global cap.
    pressure = [
        u
        for u, _ in sorted(pairs, key=lambda p: p[0].newest_mtime)
        if u.kind in ("subagent", "workflow", "tool_result") and u.eligible and u.paths not in deleted
    ]
    live_pool = [u for u, _ in pairs if u.kind in ("subagent", "workflow", "tool_result") and u.paths not in deleted]
    per_session: dict = {}
    for u in live_pool:
        per_session[u.session] = per_session.get(u.session, 0) + u.size
    for u in pressure:
        if per_session.get(u.session, 0) > policy.per_session_cap:
            remove(u, True)
            if u.paths in deleted:
                per_session[u.session] -= u.size
    for u in pressure:
        if state["total"] <= policy.projects_cap:
            break
        if u.paths not in deleted:
            remove(u, True)

    report.still_over = state["total"] > policy.projects_cap and under_volume_pressure(
        policy, [roots.projects], free_probe
    )
    return report
