#!/usr/bin/env python3
"""subagent-statusline — render `who · what · model · effort · elapsed · tokens · status` per row.

WHAT THIS IS FOR. The harness's `subagentStatusLine` setting renders a custom row per visible
subagent task, replacing the default `name · description · token count` row -- this script is that
renderer, ported from DoE-claude for the same reason every other consumer-blocking `coordinator/bin`
CLI moved (`docs/plans/2026-09-18-doe-holds-no-scripts.md`).

INVOCATION SHAPE, NOT A TOOL CALL. Per `statusline.md:202-223`, the harness runs this command once
per refresh tick, handing it all visible subagent rows as a single JSON object on stdin, and reads
zero or more `{"id": ..., "content": ...}` JSON lines back from stdout.

OUTPUT CONTRACT: an omitted `id` keeps the harness's own default render for that row. An EMPTY
`content` HIDES the row entirely -- so a degraded render must still emit SOME non-empty content,
never an empty string, or a live worker silently vanishes from the panel.

VERSION-GATED FIELDS DEGRADE, THEY NEVER CRASH. `model` and `contextWindowSize` require harness
v2.1.205+; `effort` requires v2.1.214+ and is additionally ABSENT whenever the subagent inherits
the session's effort level, which is a normal, expected state today even though most agent
definitions do set `effort:` explicitly. Each absent field simply drops its segment from the row
rather than rendering a placeholder -- and an absent `contextWindowSize` renders the percentage as
a dash, never `0%`, for the same reason the main `statusline.py` never renders a false zero: a
gauge reading empty while the window is actually full is the exact failure this mechanism exists
to remove.

FAILURE MODE IS BLANK, NEVER LOUD. Malformed or non-object stdin, a non-list `tasks`, or any
per-row surprise all degrade to emitting nothing for that case -- this process must exit 0 on
every path, because a broken subagent statusline command must never be able to take the panel
render down with it.

Naked Python, single process, zero subprocess fan-out or filesystem I/O: this is a pure
stdin-to-stdout transform, run on a machine already busy with concurrent sessions. No DoE-relative
path is used anywhere in this module, so the move here is byte-for-byte mechanical apart from the
`main(argv)` arity fix (§ Path resolution / warm-servability,
`coordinator_core.warm.serve_classifier`).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C4.
"""
from __future__ import annotations

import json
import sys
import time

_UNKNOWN_PCT = "-"
_SEP = " · "
_ELLIPSIS = "…"
_GENERIC_KINDS = {"local_agent"}
_IDENTITY_CAP = 32


def _identity(task: dict) -> str | None:
    """The row's leading segment: the dispatch `name` when the dispatch was named, else the
    agent `type`. `name` is absent on an ordinary unnamed dispatch -- the common case -- so a
    renderer keyed on `name` alone leads every row with the model ID, which identifies nothing.

    Capped at `_IDENTITY_CAP`: the `label` rung serves an unbounded live activity string, and
    an uncapped identity overflows the row rather than yielding width to `description`.
    """
    for key in ("name", "label", "type"):
        value = task.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        # `type` carries the task KIND (`local_agent`) as often as it carries the agent type --
        # a kind is identical on every row, so it identifies nothing and is worse than an
        # absent segment, which at least spends no width.
        if value.lower() in _GENERIC_KINDS:
            continue
        value = " ".join(value.split())
        if len(value) > _IDENTITY_CAP:
            value = value[: _IDENTITY_CAP - 1] + _ELLIPSIS
        return value
    return None


def _activity(task: dict) -> str | None:
    """What the worker is DOING -- the default row's most load-bearing field. `description` is
    the dispatch's own one-line summary. `label` is left to `_identity` -- the row's who is the
    stronger claim on it, and a description-less row simply has no activity segment."""
    value = task.get("description")
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return None


def _elapsed_segment(start_time: object, now: float | None = None) -> str | None:
    """How long this worker has been running -- `1h04m`, `7m20s`, `45s`.

    `startTime` arrives as an epoch number (seconds or milliseconds -- disambiguated by
    magnitude, since a seconds-valued epoch cannot reach the millisecond threshold for another
    three millennia). A non-numeric `startTime` (e.g. a string) drops the segment, the same
    degrade as an unparseable or future-dated value -- this field is undocumented in
    `statusline.md`, so a shape other than the observed numeric epoch is treated as absent
    rather than parsed.
    """
    epoch = None
    if isinstance(start_time, (int, float)) and not isinstance(start_time, bool):
        epoch = start_time / 1000.0 if start_time > 1e11 else float(start_time)
    if epoch is None:
        return None

    seconds = int((time.time() if now is None else now) - epoch)
    if seconds < 0:
        return None
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h{mins:02d}m"


def _tokens_segment(token_count: object) -> str | None:
    """Absolute context spend -- `148.7k`, `1.2M` -- beside the percentage, which alone hides
    how much a worker is actually burning when models with different windows share the panel."""
    if not isinstance(token_count, (int, float)) or isinstance(token_count, bool):
        return None
    if token_count < 0:
        return None
    if token_count < 1000:
        return str(int(token_count))
    if token_count < 1_000_000:
        return f"{token_count / 1000:.1f}k"
    return f"{token_count / 1_000_000:.1f}M"


def _model_segment(model: object) -> str | None:
    """`claude-opus-5[1m]` renders as `opus-5[1m]`: the vendor prefix is constant across every
    row, so it spends width distinguishing nothing."""
    if not isinstance(model, str) or not model.strip():
        return None
    return model.strip().removeprefix("claude-") or None


def _percentage(token_count: object, context_window_size: object) -> str:
    """The row's used-percentage segment. Always renders SOMETHING -- never omitted -- so the
    segment is either a real percentage or the dash placeholder, never absent outright.

    Mirrors `statusline.py::_percentage`'s asymmetric-clamp reasoning: a reading over 100%
    clamps down (overstating nothing), but there is no clamp-up for a bad low reading --
    an absent or zero `contextWindowSize`, or an absent `tokenCount`, returns the dash
    placeholder instead of `0%`, never a confident wrong number. Division by zero is guarded
    structurally, not caught.
    """
    if not isinstance(context_window_size, (int, float)) or isinstance(context_window_size, bool):
        return _UNKNOWN_PCT
    if context_window_size <= 0:
        return _UNKNOWN_PCT
    if not isinstance(token_count, (int, float)) or isinstance(token_count, bool):
        return _UNKNOWN_PCT
    pct = round((token_count / context_window_size) * 100)
    return f"{min(100, max(0, pct))}%"


def _effort_segment(effort: object) -> str | None:
    """`effort` renders as-is: a level string (`low`/`medium`/.../`max`) or a numeric token
    budget (`statusline.md` documents both shapes). Absent whenever the subagent inherits the
    session's effort level -- that is a normal state, not a fault, so it drops the segment
    silently rather than rendering a placeholder."""
    if isinstance(effort, str) and effort.strip():
        return effort.strip()
    if isinstance(effort, (int, float)) and not isinstance(effort, bool):
        return str(effort)
    return None


def _render_row(task: dict, columns: int | None) -> str | None:
    """The row body for one task, or None if there is nothing renderable.

    Segment order: `identity · activity · model · effort · <pct>% · status`. Any absent field drops its own
    segment and separator rather than leaving a stray `· ·`. Truncates to `columns` when given,
    never wrapping -- and a truncation that empties the string is reported as "nothing to
    render" so the caller can skip emitting the row rather than hiding it with `""`.
    """
    fixed = []
    identity = _identity(task)
    if identity:
        fixed.append(identity)
    model = _model_segment(task.get("model"))
    if model:
        fixed.append(model)
    effort = _effort_segment(task.get("effort"))
    if effort:
        fixed.append(effort)
    elapsed = _elapsed_segment(task.get("startTime"))
    if elapsed:
        fixed.append(elapsed)
    tokens = _tokens_segment(task.get("tokenCount"))
    pct = _percentage(task.get("tokenCount"), task.get("contextWindowSize"))
    # Spend and pressure read together: the percentage alone hides how much a worker is
    # actually burning once models with different window sizes share one panel.
    fixed.append(f"{tokens} ({pct})" if tokens else pct)
    status = task.get("status")
    if isinstance(status, str) and status.strip():
        fixed.append(status.strip())

    if not fixed:
        return None

    # The activity text is the one variable-length segment, so it absorbs the width squeeze
    # alone: the gauges after it are fixed-width and carry the state a squeezed row still has
    # to show, and truncating the whole joined string would eat them first. Two policies:
    # insert it whole when it fits, else ellipsize it to whatever `columns` leaves (floor one
    # character of text plus the ellipsis); the hard slice below is the backstop either way.
    activity = _activity(task)
    if activity:
        position = 1 if identity else 0
        budget = None
        if isinstance(columns, (int, float)) and not isinstance(columns, bool) and columns >= 0:
            spent = len(_SEP.join(fixed)) + len(_SEP)
            budget = int(columns) - spent
        if budget is None or budget >= len(activity):
            fixed.insert(position, activity)
        else:
            clipped = max(budget, 2)
            fixed.insert(position, activity[: clipped - 1] + _ELLIPSIS)

    content = _SEP.join(fixed)
    # A negative `columns` means no truncation constraint, not a clamp to 0.
    if isinstance(columns, (int, float)) and not isinstance(columns, bool) and columns >= 0:
        content = content[: int(columns)]
    return content or None


def main(argv: list[str] | None = None) -> int:
    """`argv` is accepted (never parsed — this CLI reads stdin, not argv) so the warm door can
    call `main(argv)` uniformly across every `coordinator/bin/` entrypoint
    (`coordinator_core.warm.serve_classifier :: _main_arity_ok`); the door still replays
    `sys.argv[1:]` from the `__main__` guard below (ARGV_SHAPE_TAIL)."""
    del argv  # unused — see docstring
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # ValueError also catches UnicodeDecodeError from a genuinely undecodable stdin
        # byte stream (e.g. a non-UTF-8 Windows console) -- same exit-0, emit-nothing path.
        return 0
    if not isinstance(payload, dict):
        return 0

    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return 0

    columns = payload.get("columns")

    lines = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            # No id: the harness keeps its own default render for this row. Emitting a
            # line with no id would not target any row, so this is a silent skip, not a
            # degrade path.
            continue
        content = _render_row(task, columns)
        if content is None:
            # Nothing renderable (or truncated to nothing) -- skip rather than emit an
            # empty `content`, which would HIDE an otherwise-live row from the panel.
            continue
        lines.append(json.dumps({"id": task_id, "content": content}))

    if lines:
        sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
