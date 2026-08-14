"""ConfigChange hook — OBSERVE ONLY. Records a JSONL line per fire; blocks nothing, mutates
nothing outside its own log file.

Purpose (docs/plans/2026-08-10-adopt-harness-native-hook-capabilities.md, chunk C2, AC A3):
`ConfigChange` is first-class in the 2.1.226 catalog and CAN block a config change (verbatim
strings confirmed live: "ConfigChange hook blocked change to ", "...blocked deletion of ",
"...blocked skill reload ("). A first registration that both observes and enforces gives no
way to tell a false positive from a correct block, on a file every session on every host boots
through — so this pass lands the signal only. Earning enforcement is a successor's job, gated
by the NAMED EXIT CONDITION in the C2 chunk body: after 50 observed payloads or 2026-09-10,
whichever comes first, the EM reads the accumulated records and either files the enforcement
successor or retires this hook.

Payload shape used below (`session_id`, `transcript_path`, `cwd`, `hook_event_name`,
`prompt_id`, `source`, `file_path`) is EMPIRICALLY MEASURED on harness 2.1.220, not inferred
from vendored docs — see `state/reference/anthropic-docs/_hook-frontmatter-reachability.md`.
Confirmed coverage is narrower than "watches config": tool-caused writes to
`.claude/settings.local.json` only. Do not widen this handler's assumed coverage without a new
measurement.

Contract:
  stdin   — ConfigChange JSON payload.
  stdout  — nothing (this hook injects no context; its only product is the log line).
  exit 0  — ALWAYS. Malformed stdin, an unwritable log directory, or a missing key must never
            raise or return non-zero — fail-open is the whole contract for an observer hook.

Where the record goes: `<git-common-dir>/coordinator-sessions/hook-observations/ConfigChange.jsonl`
(one JSON object per line). This is DERIVED bookkeeping, not authored state, so it lives outside
`state/subagent-share/` (DR-091 — that namespace is authored-only). `<git-common-dir>` is found by
walking up from the payload's `cwd` looking for `.git` (directory or gitdir-pointer file), then
resolving that git dir's own `commondir` file if one exists — the same resolution
`track-dispatched-agents.py`'s canary helper uses, chosen over shelling out to
`git rev-parse --git-common-dir` so this handler stays a pure stdlib read/write with no child
process to fail to spawn.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

_EVENT_NAME = "ConfigChange"

# Fields measured live on harness 2.1.220 for this event (see module docstring). Recorded by
# name, not dumped verbatim, because — unlike PostCompact — this event's payload shape is
# confirmed, not guessed.
_KNOWN_FIELDS = (
    "session_id",
    "transcript_path",
    "cwd",
    "hook_event_name",
    "prompt_id",
    "source",
    "file_path",
)


# Review: coordinator:code-reviewer (Finding 2) — `_read_stdin`, `_resolve_git_common_dir`, and
# `_append_record` below are duplicated verbatim in `observe-post-compact.py` and again (as
# `track-dispatched-agents.py`'s canary helper). This is deliberate: both observer scripts must
# run standalone through the fail-open site-packages seam, and a shared-module import is a real
# risk to that seam. A fix to any one copy MUST be mirrored to the other two.
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
    resolve its `commondir` file if present. Returns None on any failure — never raises."""
    try:
        probe = start.resolve()
    except Exception:
        return None

    git_dir = None
    for candidate in (probe, *probe.parents):
        try:
            marker = candidate / ".git"
            if marker.is_dir():
                git_dir = marker
                break
            if marker.is_file():
                raw_pointer = marker.read_text(encoding="utf-8", errors="replace")
                if not raw_pointer.startswith("gitdir:"):
                    return None
                pointer = raw_pointer[len("gitdir:") :].strip()
                if not pointer:
                    return None
                pointer_path = Path(pointer)
                if not pointer_path.is_absolute():
                    pointer_path = (candidate / pointer_path).resolve()
                git_dir = pointer_path
                break
        except Exception:
            return None
    if git_dir is None:
        return None

    try:
        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            raw_common = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
            if not raw_common:
                return git_dir
            common_path = Path(raw_common)
            if not common_path.is_absolute():
                common_path = (git_dir / common_path).resolve()
            return common_path
        return git_dir
    except Exception:
        return git_dir


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

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = None
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
        record: dict[str, object] = {
            "observed_at": observed_at,
            "hook_event_name": _EVENT_NAME,
        }
        for key in _KNOWN_FIELDS:
            if key in payload:
                record[key] = payload.get(key)
        cwd_value = payload.get("cwd")
        cwd_hint = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()

    git_common_dir = _resolve_git_common_dir(cwd_hint)
    if git_common_dir is None:
        return 0  # fail-open — no resolvable git tree, nothing to write into

    _append_record(git_common_dir, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
