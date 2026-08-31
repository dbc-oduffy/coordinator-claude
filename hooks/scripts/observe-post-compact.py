"""PostCompact hook — OBSERVE ONLY, payload-agnostic by hard constraint.

Purpose (docs/plans/2026-08-10-adopt-harness-native-hook-capabilities.md, chunk C2, AC A3):
`PostCompact` has never been empirically fired on any harness version — two headless probe
sessions failed to induce compaction, because real compaction is slow and expensive to force.
Its payload is INFERRED from adjacent bundle strings (a `compact_summary` field, a
`manual`/`auto` trigger), not measured. Reading a guessed field name that silently comes back
absent is exactly the failure this handler exists to avoid, so it does the opposite: it never
reads a named field out of the payload at all. It parses the JSON only to dump it back out
whole, verbatim, into the observation log. That makes it correct without knowing the real
shape, and it becomes the cheapest available instrument for the open reachability question:
riding real sessions, where real compaction actually happens, is the only way two headless
probes could not answer that a hook fire finally can. If it never fires, the empty log is
itself the measurement that has been missing.

Do NOT "fix" this handler later by adding `.get()` reads for the guessed summary or trigger
keys named above until a real fired payload has actually been captured and inspected. That is
precisely the guessed-field-name failure this shape is built to avoid.

Contract:
  stdin   — PostCompact JSON payload (shape unconfirmed — see above).
  stdout  — nothing (this hook injects no context; its only product is the log line).
  exit 0  — ALWAYS. Malformed stdin or an unwritable log directory must never raise or return
            non-zero — fail-open is the whole contract for an observer hook.

Where the record goes: `<git-common-dir>/coordinator-sessions/hook-observations/PostCompact.jsonl`
(one JSON object per line). This is DERIVED bookkeeping, not authored state, so it lives outside
`state/subagent-share/` (DR-091 — that namespace is authored-only). `<git-common-dir>` is found by
walking up from the payload's `cwd` (if present — since the payload shape is unconfirmed, this
handler does not assume `cwd` exists either) looking for `.git` (directory or gitdir-pointer
file), then resolving that git dir's own `commondir` file if one exists — the same resolution
`observe-config-change.py` and `track-dispatched-agents.py`'s canary helper use, chosen over
shelling out to `git rev-parse --git-common-dir` so this handler stays a pure stdlib read/write
with no child process to fail to spawn.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _git_common_dir import resolve_git_common_dir as _resolve_git_common_dir_str  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _git_common_dir.py
    # must still fail open (empty common dir -> caller returns None) rather
    # than crash on import.
    def _resolve_git_common_dir_str(git_root: str) -> str:
        return ""

_EVENT_NAME = "PostCompact"


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) — same pattern as
    track-dispatched-agents.py._read_stdin."""
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


def _resolve_git_common_dir(start: Path) -> Path | None:
    """Walk up from `start` to the nearest `.git` (directory or gitdir-pointer file), then
    resolve its `commondir` file if present via the shared `_git_common_dir` helper. Returns
    None on any failure — never raises."""
    try:
        probe = start.resolve()
    except Exception:
        return None

    git_root = None
    for candidate in (probe, *probe.parents):
        try:
            if (candidate / ".git").exists():
                git_root = candidate
                break
        except Exception:
            return None
    if git_root is None:
        return None

    common = _resolve_git_common_dir_str(str(git_root))
    return Path(common) if common else None


def _append_record(git_common_dir: Path, record: dict) -> None:
    try:
        log_dir = git_common_dir / "coordinator-sessions" / "hook-observations"
        log_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with (log_dir / f"{_EVENT_NAME}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        return


def main() -> int:
    raw = _read_stdin()

    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # No named-field access anywhere below — the whole point of this handler. `payload` is
    # dumped back out whole, or `raw` is recorded verbatim if it did not even parse as JSON.
    try:
        payload = json.loads(raw)
    except Exception:
        payload = None

    if payload is None:
        record = {
            "observed_at": observed_at,
            "hook_event_name": _EVENT_NAME,
            "parse_error": True,
            "raw_stdin": raw[:2000],
        }
        cwd_hint = Path.cwd()
    else:
        record = {
            "observed_at": observed_at,
            "hook_event_name": _EVENT_NAME,
            "payload": payload,
        }
        cwd_value = payload.get("cwd") if isinstance(payload, dict) else None
        cwd_hint = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()

    git_common_dir = _resolve_git_common_dir(cwd_hint)
    if git_common_dir is None:
        return 0  # fail-open — no resolvable git tree, nothing to write into

    _append_record(git_common_dir, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
