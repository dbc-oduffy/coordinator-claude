#!/usr/bin/env python3
"""PostToolUse hook: warn a subagent that auto-compaction is near, early enough to write its log.

Hook payloads carry no token counts, so the subagent's context size is estimated from the last
`message.usage` row in its own transcript tail and compared with the compaction threshold from
`lib/compaction_defaults.py`. The warning fires once per agent per band, as `additionalContext`.
Main sessions (no `agent_id`) are skipped; the status line and PreCompact bridge cover them.

Contract: stdin PostToolUse JSON; stdout empty or one `hookSpecificOutput` JSON object; exit 0
on every path -- a broken advisory must never fail a tool call.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import compaction_defaults  # noqa: E402

#: Fractions of the threshold at which the warning fires (once each).
WARN_BANDS = (0.75, 0.90)
_TAIL_BYTES = 262144
_WINDOW_DEFAULT = 200000
_WINDOW_1M = 1000000

MESSAGE = (
    "Context compaction is near for this subagent (~{pct}% of the way to auto-compaction, "
    "~{tokens} tokens; estimated from your transcript). Write your forward log now -- decisions, "
    "files touched, what remains -- before continuing, so the work survives a compaction."
)


def _settings_home() -> Path:
    raw = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(raw) if raw else Path.home() / ".coordinator-claude-settings"


def _safe(value: str) -> str:
    return "".join(c for c in value if c.isalnum() or c in "-_")


def context_tokens(transcript: Path) -> tuple[int | None, str | None]:
    """(tokens, model) from the last usage row with a non-zero total in the transcript tail."""
    try:
        with transcript.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - _TAIL_BYTES))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None, None
    for line in reversed(lines):
        try:
            message = json.loads(line).get("message")
        except (ValueError, AttributeError):
            continue
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        total = sum(
            v for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            if isinstance(v := usage.get(k), (int, float)) and not isinstance(v, bool)
        )
        if total > 1:
            model = message.get("model")
            return int(total), model if isinstance(model, str) else None
    return None, None


def _window(model: str | None, tokens: int = 0) -> int:
    """Transcript model ids rarely say "1m", so a context already past the default window proves
    the larger one; otherwise assume the default."""
    if (model and "1m" in model.lower()) or tokens > _WINDOW_DEFAULT:
        return _WINDOW_1M
    return _WINDOW_DEFAULT


def _reap_old_markers(directory: Path, max_age_s: float = 86400.0) -> None:
    """Drop markers a day old; an agent's bands never outlive its session."""
    cutoff = time.time() - max_age_s
    for entry in directory.iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def evaluate(payload: dict) -> str | None:
    """The warning text when a new band has been crossed, else None."""
    agent_id = payload.get("agent_id")
    transcript = payload.get("agent_transcript_path") or payload.get("transcript_path")
    if not isinstance(agent_id, str) or not agent_id or not isinstance(transcript, str):
        return None
    tokens, model = context_tokens(Path(transcript))
    if tokens is None:
        return None
    threshold, _why = compaction_defaults.threshold_tokens(_window(model, tokens))
    if not threshold:
        return None
    ratio = tokens / threshold
    band = max((i + 1 for i, edge in enumerate(WARN_BANDS) if ratio >= edge), default=0)
    if not band:
        return None
    marker = _settings_home() / "state" / "compaction-warned" / f"{_safe(agent_id)}.{band}"
    if marker.exists():
        return None
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        _reap_old_markers(marker.parent)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        return None
    return MESSAGE.format(pct=min(100, round(ratio * 100)), tokens=f"{tokens / 1000:.0f}k")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        text = evaluate(payload) if isinstance(payload, dict) else None
    except Exception:
        return 0
    if text:
        sys.stdout.write(json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
