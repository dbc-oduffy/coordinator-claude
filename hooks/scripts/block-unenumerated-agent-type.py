"""PreToolUse(Agent) doctrine-plane-side registration shim for the engine plane's
unenumerated-`subagent_type` hard-deny guard.

DR-047 boundary: this file is the thin transport shim ONLY -- it resolves
the engine plane, imports and calls `coordinator_core.hooks.
block_unenumerated_agent_type.check`, and relays whatever it returns to
stdout. It owns ZERO roster grammar and ZERO deny-reason wording -- that
logic is entirely the engine plane's
(coordinator_core/hooks/block_unenumerated_agent_type.py), including the
override marker, which `check()` honours.

AN UNREACHABLE ENGINE PASSES, LOUDLY. When the engine root is unresolvable,
the engine module is unimportable, or `check()` raises, this guard did not
run, and the dispatch proceeds carrying a `systemMessage` for the operator
and `additionalContext` for the model saying so. It never denies on that
basis: this guard is ergonomics and fleet hygiene, not a security boundary,
and a guard that cannot reach its engine denying every dispatch on the box
is a worse failure than one unenumerated type slipping through a visible
gap. Only a verdict the engine actually returned can deny. Rule:
`coordinator/docs/wiki/coordinator-tripwires/an-unreachable-engine-passes-loudly-never-denies.md`.

HARNESS-SHAPE CARVE-OUT (`_HARNESS_SHAPES_NOT_IN_ENGINE_ROSTER`).
Harness-owned Agent dispatch shapes that the engine plane's roster does not
yet enumerate. `fork` is a documented value of the Agent tool's own
`subagent_type` schema and was MEASURED LIVE on this host reaching
PreToolUse(Agent) as the literal string `"fork"` (observed in
`.git/coordinator-sessions/<sid>/dispatched-agents.txt` column 3). Each
entry in this set is PROVISIONAL: it is removed the moment the engine
plane's own `_HARNESS_BUILTIN_TYPES` constant carries it -- the outbound memo
requesting that addition is cross-repo/inbox/-side commit 787871452. This
set is NOT a second roster and must NEVER grow to hold coordinator-authored
or plugin agent types -- those belong in `subagent-sandbox-policy.yaml` or
`coordinator/agents/`, never here.

HONEST LIMITATION -- the shared `runpy` bootstrap in `hooks.json` (the
`python3 -c ...; runpy.run_path(p, ...) if os.path.isfile(p) else
sys.stderr.write('COORDINATOR HOOK SEAM: ... unreachable -- failing OPEN
...')` wrapper every entry in this file's matcher list shares) fails OPEN
when THIS script itself is missing or has drifted off its registered path
-- it writes one `COORDINATOR HOOK SEAM:` line to stderr and runs nothing,
silently disarming this entire guard. That is install drift, outside this
file's control, and must NOT be "fixed" by editing the shared bootstrap
(every other registered hook shares that same wrapper and that same
fail-open contract for a missing script).

Spec backlink: cross-repo/inbox/2026-08-10-claude-klabauter-em-agent-type-deny-guard-needs-registration.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


#: See module docstring "HARNESS-SHAPE CARVE-OUT" -- harness-owned dispatch shapes the
#: engine roster does not yet enumerate. Provisional; removed once the
#: engine plane's `_HARNESS_BUILTIN_TYPES` carries the entry. NEVER grows to hold
#: coordinator-authored or plugin agent types.
_HARNESS_SHAPES_NOT_IN_ENGINE_ROSTER = frozenset({"fork"})


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py must still resolve to a callable that
    # returns None (driving the loud-pass leg below), never crash on
    # import.
    def _resolve_claude_klabauter_root() -> Optional[str]:
        return None


def _guard_did_not_run(what_failed: str) -> None:
    """Emit the loud pass: no permission decision, so the dispatch proceeds,
    but the operator and the model both see that this guard did not run."""
    sys.stdout.write(json.dumps(
        {
            "systemMessage": f"coordinator: unenumerated-agent-type guard did not run ({what_failed})",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": (
                    "The coordinator guard that checks subagent_type against the "
                    f"enumerated roster could not be evaluated ({what_failed}). "
                    "It did not pass -- it did not run. This dispatch was allowed "
                    "through unchecked."
                ),
            },
        },
        ensure_ascii=False, separators=(",", ":"),
    ))
    sys.stdout.write("\n")


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    if not raw:
        return 0
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    if (payload.get("tool_name") or "") != "Agent":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    subagent_type = tool_input.get("subagent_type")
    if not isinstance(subagent_type, str) or not subagent_type.strip():
        return 0
    subagent_type = subagent_type.strip()

    if subagent_type in _HARNESS_SHAPES_NOT_IN_ENGINE_ROSTER:
        return 0

    try:
        root = _resolve_claude_klabauter_root()
    except Exception as exc:
        _guard_did_not_run(f"engine-root resolution raised {type(exc).__name__}: {exc}")
        return 0
    if not root:
        _guard_did_not_run("the engine root is unresolvable on this host")
        return 0

    from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
    _place_engine_root_on_path(root)

    try:
        from coordinator_core.hooks.block_unenumerated_agent_type import check  # noqa: E402
    except Exception as exc:
        _guard_did_not_run(f"engine guard module unimportable: {type(exc).__name__}: {exc}")
        return 0

    try:
        envelope = check(payload)
    except Exception as exc:
        _guard_did_not_run(f"check() raised {type(exc).__name__}: {exc}")
        return 0

    if envelope:
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
