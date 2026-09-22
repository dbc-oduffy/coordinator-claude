#!/usr/bin/env python3
"""PostToolUseFailure naked-Python inline-remediation hook for register entry #17.

Fires for exactly ONE bounded case: a `Bash` tool call running a `cross-repo-memo`
invocation that exits 127 ("command not found"). Register entry #17's discharge
target, per the reachability spike
(`state/reference/anthropic-docs/_hook-frontmatter-reachability.md` Part 1 +
"PostToolUseFailure fires for a bounded class"): `PostToolUseFailure` fires only for
a HARD tool failure carrying a top-level `error` key -- confirmed for `Bash`
non-zero exit and `Read` on a missing path -- and does NOT fire for an error
returned as `<tool_use_error>` content inside an otherwise-successful result (that
shape surfaces only inside `PostToolBatch`). A `cross-repo-memo` exit-127 is
squarely in the firing class.

ONE CASE ONLY -- negative spec, binding (plan body, C6): the register calls DEFER
on a general Bash-failure-remediation table and RECOMMEND only for this one named
case. This hook does not grow into a lookup table "while here"; a second failure
pattern is a new register entry, not an addition to this file.

Offer-shape (never blocks): this hook ALWAYS exits 0. On the matching failure it
emits {"hookSpecificOutput":{"hookEventName":"PostToolUseFailure",
"additionalContext":"<remediation>"}} on stdout; NOTHING otherwise (silent pass).
It never sets "decision":"block" and never returns a non-zero exit code.

RESOLVE THE FORWARDER, DO NOT RESTATE IT. The baton this plan carries points at a
now-removed meta-repo local-doctrine file for the settings-home forwarder path.
This hook calls the live in-tree resolver, `_forwarder_resolve.resolve_forwarder`,
against `<settings-home>/bin` -- a path resolved at runtime on THIS box, never a
path copied out of a dead document. `resolve_forwarder` also probes the native
`.exe` forwarder generation, not just the extensionless script (see that module's
own docstring on why suffix-only probing silently degrades on Windows).

Contract:
  stdin   -- PostToolUseFailure JSON (cwd, duration_ms, effort, error,
             hook_event_name, is_interrupt, permission_mode, prompt_id,
             session_id, tool_input, tool_name, tool_use_id, transcript_path)
  stdout  -- one hookSpecificOutput JSON envelope (additionalContext) on a
             matching cross-repo-memo exit-127; NOTHING otherwise (silent pass)
  exit 0  -- always (advisory only; never blocks/denies)

Graceful degradation -- REQUIRED: any failure to parse stdin, or to resolve the
forwarder, falls through to a silent pass (exit 0, no stdout, or an unresolved-
forwarder note in the message body -- never a crash). A filesystem hiccup must
never brick a tool-failure report.

House pattern: `${CLAUDE_PLUGIN_ROOT}` resolution is the registration's concern,
not this script's; this script resolves its own sibling directory via
`Path(__file__).resolve().parent`, mirroring every other naked-Python hook in this
directory. Fail-open on every internal error (broad `except Exception`), per the
`_hook_boot.py` house bootstrap this registration will run under.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _forwarder_resolve import resolve_forwarder
except Exception:
    # Defensive fallback -- a deploy missing its sibling _forwarder_resolve.py
    # must still emit the remediation prose (minus a resolved path) rather than
    # crash this fail-open hook on import.
    def resolve_forwarder(bin_dir, name):  # type: ignore[misc]
        return None


import os

# Matches the exit-127 case only: the observed payload shape is a leading
# "Exit code 127" line (reachability spike, verbatim: `error: "Exit code 127\n…
# command not found"`). A different non-zero exit is a different failure and is
# out of this hook's one-case scope.
_EXIT_127_RE = re.compile(r"(?m)^Exit code 127\b")

_MEMO_SUBSTRING = "cross-repo-memo"


def _settings_home() -> Path:
    """`COORDINATOR_SETTINGS_HOME` env var, else `CLAUDE_HOME` env var, else
    `Path.home()` -- the same fallback ladder `sweep-boot.py::_settings_home`
    and `project-orientation.py::_settings_home` use, resolved at runtime on
    THIS box. Never a hardcoded path -- multi-os-first-class (project
    CLAUDE.md § Runtime conventions)."""
    v = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if v:
        return Path(v)
    claude_home = os.environ.get("CLAUDE_HOME")
    if claude_home:
        return Path(claude_home) / ".coordinator-claude-settings"
    return Path.home() / ".coordinator-claude-settings"


def _compose_remediation() -> str:
    """One remediation message for the one case this hook handles. Resolves the
    forwarder at call time; degrades to a name-only pointer (never a restated
    dead-document path) if resolution fails."""
    forwarder = None
    try:
        forwarder = resolve_forwarder(_settings_home() / "bin", "cross-repo-memo")
    except Exception:
        forwarder = None

    if forwarder:
        return (
            "[cross-repo-memo remediation] exit 127 means the shell could not find "
            "`cross-repo-memo` on PATH. The resolved forwarder for this install is "
            f"`{forwarder}` -- invoke it directly, or add its directory to PATH."
        )
    return (
        "[cross-repo-memo remediation] exit 127 means the shell could not find "
        "`cross-repo-memo` on PATH. No settings-home forwarder resolved for this "
        "install -- confirm the coordinator install's `bin/cross-repo-memo` "
        "forwarder is present under `<settings-home>/bin/`."
    )


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

    if payload.get("tool_name") != "Bash":
        return 0

    error = payload.get("error")
    if not isinstance(error, str) or not error:
        return 0
    if not _EXIT_127_RE.search(error):
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or _MEMO_SUBSTRING not in command:
        return 0

    try:
        message = _compose_remediation()
    except Exception:
        return 0

    envelope = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUseFailure",
            "additionalContext": message,
        }
    }
    try:
        sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail-open, unconditionally -- a PostToolUseFailure hook that itself
        # raises must never brick tool-failure reporting.
        sys.exit(0)
