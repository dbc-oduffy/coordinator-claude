"""async_hook_status.py — single shared failure-surfacing convention for LOAD-BEARING async hooks.

Spec: plugins/coordinator-claude/coordinator/docs/plans/2026-06-30-async-hook-failure-surfacing.md § Design

Producers (bootstrap-substrate.sh, platform-localize.sh) record failures via
record_failure; session-init.sh surfaces+clears them via surface_and_clear.
Markers live under ${CLAUDE_HOME:-$HOME}/.claude/.cache/async-hook-status/
(per-machine, boot-transient — NOT git-tracked state/).

This module is IMPORTED, not executed as a CLI — a naked-python port of the
former lib/async-hook-status.sh (2026-07-21 de-bash campaign,
docs/plans/2026-07-19-debash-coordinator-windows.md, chunk E3-e). No current
producer/consumer in THIS repo (bootstrap-substrate.sh / session-init.sh do
not exist here — they were already ported/relocated elsewhere), so this
module currently has no in-repo caller besides its own test — kept as the
canonical async-hook failure-surfacing primitive for any future producer.

Negative-spec:
  - record_failure MUST NOT raise out of the caller's control flow — producers
    run under best-effort conditions equivalent to bash's `set -e` / async ERR
    traps; all internal failures are swallowed and the function always returns.
  - Apply ONLY to load-bearing hooks with silent persistent harm AND no
    self-correction window before harm lands. Do NOT apply to fire-and-forget
    nudges or high-frequency hooks (coordinator-reminder, ue-knowledge-distrust,
    session-heartbeat, runtime-tripwire-stop-watcher). The discriminator is the
    value — see plan § Problem.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

_NOOP_SENTINEL = "/dev/null/async-hook-status-noop"


def status_dir() -> str:
    """Return the canonical marker directory, creating it if needed.

    Falls back to a sentinel path if .cache is unwritable (e.g. a regular file
    sits where the directory should be), so callers degrade to a silent no-op
    without raising.
    """
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    directory = os.path.join(home, ".claude", ".cache", "async-hook-status")
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        return directory
    except OSError:
        return _NOOP_SENTINEL


def record_failure(hook: str, exit_code, detail: str = "", logpath: str = "") -> int:
    """Write a single-line JSON failure marker for a load-bearing async hook.

    Latest-wins: overwrites any prior marker for the same hook name.

    Best-effort, never raises: mirrors the bash oracle's subshell + unconditional
    return-0 shape — an exception anywhere in the write path is swallowed and
    the function still returns 0.

    <hook> SHOULD be a simple slug [a-z0-9][a-z0-9-]* — no slashes/quotes/backslashes
    (not enforced here; callers own the value, matching the bash oracle which
    also did not validate on the write path).
    """
    try:
        directory = status_dir()
        if directory == _NOOP_SENTINEL or directory.startswith("/dev/null/"):
            return 0
        hook_name = hook or "unknown"
        record = {
            "hook": hook_name,
            "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "exit": int(exit_code) if exit_code not in (None, "") else 1,
            "detail": detail or "",
            "log": logpath or "",
            "remediation": "",
        }
        marker = os.path.join(directory, f"{hook_name}.json")
        with open(marker, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        # Best-effort: any failure on the write path is swallowed.
        pass
    return 0


_LINE_FMT = "[async-hook] {hook} failed last boot (exit {exit}): {detail} — {remediation}"


def surface_and_clear() -> str:
    """Surface any recorded load-bearing async hook failures, then clear them.

    Design: atomic claim via os.replace (rename(2)) before reading, so
    concurrent readers skip silently on a lost race rather than
    double-surfacing. A re-fail on the NEXT boot causes the producer to
    overwrite a fresh marker, which re-surfaces on the boot after that —
    correct "failed last boot" semantics.

    Returns the surfaced text (one line per marker, newline-joined; empty
    string when nothing to surface). Never raises.
    """
    directory = status_dir()
    if directory == _NOOP_SENTINEL or directory.startswith("/dev/null/"):
        return ""

    lines: list[str] = []
    try:
        markers = sorted(Path(directory).glob("*.json"))
    except OSError:
        return ""

    for marker in markers:
        claimed = marker.with_suffix(marker.suffix + f".claimed.{os.getpid()}")
        try:
            os.replace(marker, claimed)
        except OSError:
            continue  # lost the race to a concurrent reader — not an error
        try:
            content = claimed.read_text(encoding="utf-8")
        except OSError:
            try:
                claimed.unlink()
            except OSError:
                pass
            continue
        try:
            record = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            record = _parse_legacy_json_line(content)
        hook = record.get("hook") or "unknown"
        exit_code = record.get("exit", 1)
        detail = record.get("detail", "")
        remediation = record.get("remediation", "")
        lines.append(_LINE_FMT.format(hook=hook, exit=exit_code, detail=detail, remediation=remediation))
        try:
            claimed.unlink()
        except OSError:
            pass

    return "\n".join(lines)


_FIELD_RE = {
    "hook": re.compile(r'"hook"\s*:\s*"([^"]*)"'),
    "exit": re.compile(r'"exit"\s*:\s*(\d+)'),
    "detail": re.compile(r'"detail"\s*:\s*"([^"]*)"'),
    "remediation": re.compile(r'"remediation"\s*:\s*"([^"]*)"'),
}


def _parse_legacy_json_line(content: str) -> dict:
    """Best-effort field extraction for a malformed/foreign marker.

    Mirrors the bash oracle's sed-based per-field extraction (which never
    hard-failed on a garbled marker) — a no-match field falls back to a safe
    default rather than propagating a parse exception.
    """
    result = {"hook": "unknown", "exit": 1, "detail": "", "remediation": ""}
    for field, pattern in _FIELD_RE.items():
        m = pattern.search(content)
        if m:
            result[field] = int(m.group(1)) if field == "exit" else m.group(1)
    return result
