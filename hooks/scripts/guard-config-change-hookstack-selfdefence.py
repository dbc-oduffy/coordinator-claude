"""ConfigChange self-defence flag, register entry #21.

BUILD ARM of docs/plans/2026-09-11-register-unit-b-adopt-the-six-hook-events.md
:: C2, gated on C1's probe verdict (`docs/research/spike-verdicts/
2026-09-11-configchange-trigger-scope-and-block-path.md`, `verdict: BUILD`).

SCOPE FOLLOWS VERDICT. C1 probed #21's declared threat model, (a) out-of-band
edit + (d) plugin `hooks/hooks.json` edit + (e) `disableAllHooks: true` flip,
plus the two out-of-threat-model cases (b) project-tier settings and (c)
user-tier settings, quarantined. Results, LEG 1:
  (a) out-of-band `.claude/settings.local.json` edit -- FIRES (source:
      local_settings)
  (b) `.claude/settings.json` (project tier)          -- FIRES, OUT OF SCOPE
  (c) user-tier settings file                          -- FIRES, OUT OF SCOPE
  (d) plugin `hooks/hooks.json` edit                    -- DOES NOT FIRE
  (e) `disableAllHooks: true` flip                       -- FIRES (source:
      local_settings)
This hook therefore classifies ONLY `source == "local_settings"` payloads --
the one source both threat-model cases that actually fire share. It does
NOT build detection for (d): ConfigChange never fires for a plugin
`hooks/hooks.json` edit, so there is no event here to classify for that
case, ever -- ConfigChange is not the seam that would catch it
(`guard-hook-generation-self-probe.py` is the existing seam for that
hazard). It does NOT flag (b) `project_settings` or (c) `user_settings` --
both fire but sit outside #21's threat model per C1's own framing; flagging
them would be scope creep past what the row asked for.

FLAG, NEVER BLOCK. C1 LEG 2 probed `decision: "block"` on this event against
a live harness and found it emitted-and-ignored: the out-of-band write was
not reverted, and the session's own next turn was not interrupted. This hook
therefore never sets `decision: "block"` and never exits non-zero -- the
only available mechanism is a loud `additionalContext` flag, so that is all
this emits. It always exits 0.

CLASSIFIER -- "what changed and was it authorized", not a bare source match.
Once a `local_settings` ConfigChange payload is seen, the hook reads the
current content of `file_path` (the very field the event names as the
changed file) and distinguishes:
  - the changed file now carries `disableAllHooks: true` -- the (e) case,
    the more severe of the two: the session's own hookstack was disabled
    from outside the tool pipeline. Flagged with a distinct, sharper message.
  - anything else -- the (a) case, a generic out-of-band edit to the
    session's local settings file. Flagged with a generic message.
A read failure (file missing, unreadable, not JSON) degrades to the generic
(a)-shaped message rather than silence -- the ConfigChange event firing at
all is itself the signal C1 proved meaningful; losing the disableAllHooks
detail on a read failure must not cost the flag entirely.

House pattern: `_hook_boot.py` bootstrap (this file is the exec target, not
the entry point), `${CLAUDE_PLUGIN_ROOT}`-relative sibling imports, fail-open
on every internal error -- a stdin parse failure, a missing `source`/
`file_path`, or any exception while reading the changed file all degrade to
a silent pass (exit 0, no stdout), never a crash and never a block.

Negative spec: does not sentinel/dedupe across fires. Each `local_settings`
ConfigChange this session gets its own flag -- an out-of-band edit
mid-session is exactly the kind of event that should not go quiet after the
first occurrence, unlike an authoring nudge a session only needs to see
once.

Contract:
  stdin   -- ConfigChange JSON (source, file_path, session_id, ...)
  stdout  -- one hookSpecificOutput JSON envelope
             ({"hookSpecificOutput": {"hookEventName": "ConfigChange",
             "additionalContext": <text>}}) on a qualifying
             `source == "local_settings"` fire; NOTHING otherwise (silent
             pass)
  exit 0  -- always (advisory only; never blocks/denies -- C1 LEG 2 proved
             `decision: "block"` has no observable effect on this event)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
import _message_envelope as _envelope  # noqa: E402

_WIKI_ANCHOR = (
    "coordinator/docs/wiki/claude-md-surfaces/claude-code-extension-surface.md"
)

_TARGET_SOURCE = "local_settings"


def _compose_disable_all_hooks_offer() -> "_envelope.Message":
    prose = (
        "[ConfigChange self-defence] this session's own hookstack was just "
        "disabled (`disableAllHooks: true`) by a write outside the tool "
        "pipeline -- `decision: \"block\"` is not honored on this event "
        "(proven, not assumed), so this is a flag, not a revert. Verify the "
        "write was intentional before trusting any guard silence for the "
        "rest of this session."
    )
    return _envelope.compose(prose, anchor=_WIKI_ANCHOR)


def _compose_out_of_band_edit_offer() -> "_envelope.Message":
    prose = (
        "[ConfigChange self-defence] this session's local settings file "
        "(`.claude/settings.local.json`) was just edited by a process "
        "outside the tool pipeline. `decision: \"block\"` is not honored on "
        "this event (proven, not assumed), so this is a flag, not a revert "
        "-- review the change before trusting the rest of this session's "
        "hook behaviour."
    )
    return _envelope.compose(prose, anchor=_WIKI_ANCHOR)


def _file_carries_disable_all_hooks(file_path: object) -> bool:
    if not isinstance(file_path, str) or not file_path.strip():
        return False
    try:
        raw = Path(file_path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    return data.get("disableAllHooks") is True


def _emit(message: "_envelope.Message") -> None:
    text = _envelope.render(message)
    try:
        envelope = {
            "hookSpecificOutput": {
                "hookEventName": "ConfigChange",
                "additionalContext": text,
            }
        }
        sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
    except Exception:
        pass


def main() -> int:
    raw = sys.stdin.read()
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    if payload.get("source") != _TARGET_SOURCE:
        return 0

    file_path = payload.get("file_path")

    try:
        disabled = _file_carries_disable_all_hooks(file_path)
    except Exception:
        disabled = False

    try:
        message = (
            _compose_disable_all_hooks_offer()
            if disabled
            else _compose_out_of_band_edit_offer()
        )
    except Exception:
        return 0

    _emit(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
