# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py's own hooks.json PreToolUse(Write|Edit|MultiEdit)
# registration calls in-process. This basename is deliberately never
# referenced literally in hooks.json text -- that IS the mechanism, matching
# every other enrolled write-path guard (see `_guard_runner_contract.
# ENROLLED_GUARD_MODULES`); a standalone hooks.json registration for this
# guard would fire it TWICE alongside the dispatcher and trip
# `test_hook_registrations_fail_open.py::
# test_write_path_guard_names_have_no_standalone_registration`.
"""PreToolUse hook (matcher: Write|Edit|MultiEdit, via the runner): WARNS,
never blocks, when a write introduces the retired POSIX-only coordinator-CLI
invocation shape into a doctrine surface.

Why this exists
----------------
`coordinator/snippets/resolve-coordinator-bin.md` rung 0 ranks a PowerShell
host's Shape W (the `.cmd` sibling via the call operator) above Shape A/B's
`${VAR:-default}` POSIX shell expansion for EVERY invocation, not only a
POSIX-labelled example -- rungs 1-3 are POSIX-shell fences unrunnable on a
PowerShell-only host without spawning a bash first (see that snippet's own
"Why not bareword" and rung-0 sections, and
docs/plans/2026-08-18-retire-posix-invocation-doctrine.md's Problem
statement). This guard is the write-time half of keeping that shape from
recurring across `coordinator/skills/`, `coordinator/commands/`, and
`coordinator/docs/wiki/`; the BIG-RED hard-fail half is
`test_no_command_fences_in_doctrine.py` (chunk C5 of the same plan).

PM ruling, verbatim (2026-08-18): "not blocking on write, it can be warn on
write, because otherwise we waste tokens. this should be triggered as a BIG
RED in tests though." A blocking hook bills a retry cycle on every hit --
the exact token waste the guard exists to prevent -- so this hook ALWAYS
exits 0 and NEVER emits a `CHANNEL_DENY` verdict; it composes a
`CHANNEL_ADDITIONAL_CONTEXT` advisory only, exactly the class-2 (advisory,
not deny) shape `guard-doctrine-changelog-prose.py` already establishes for
an ambiguous-but-not-config-hard-deny doctrine class.

The advisory NAMES THE REMEDY (rung 0 / Shape W in
`coordinator/snippets/resolve-coordinator-bin.md`) rather than only saying
"don't" -- a warning that stops at "don't do this" is what let this shape
recur in the first place; naming the working alternative is the whole point
of a warn-not-block guard (see this repo's own "Design tooling as offers,
not nags" convention).

Detection
---------
Delegates entirely to `_posix_invocation_detect.find_posix_forwarder_
invocations` -- the ONE shared predicate this guard and
`test_no_command_fences_in_doctrine.py`'s hard-fail assertion both import,
so a hook and a test can never disagree about what counts as a violation
(see that module's own docstring).

Scoping
-------
Fires only on `new_hits(before, after)` -- hits present in `after` that were
not already present in `before` (a multiset/Counter difference over matched
text, mirroring `guard-doctrine-changelog-prose.py`'s own `new_violations`
delta contract) -- never on pre-existing debt sitting untouched in a file
being edited for an unrelated reason. Scope is the same three trees AC5
names: `coordinator/skills/`, `coordinator/commands/`,
`coordinator/docs/wiki/`.

Reconstructing before/after
-----------------------------
Same contract as `guard-doctrine-changelog-prose.py`: `before` is the
current on-disk content (empty string for a not-yet-existing file); `after`
is reconstructed from `tool_input` via `_sentinel_write_guard.
reconstruct_after`.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable
stdin payload; `tool_name` not in the guarded set; no target path in
`tool_input`; target not under one of the three guarded trees; on-disk read
failure for an existing file; unreconstructable before/after; zero new
hits.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _posix_invocation_detect import find_posix_forwarder_invocations  # noqa: E402
from _message_envelope import (  # noqa: E402
    CHANNEL_ADDITIONAL_CONTEXT,
    Message,
    compose,
    emit,
)

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: The three trees AC5 names -- forward-slash-only; `is_in_scope` normalizes
#: the target path before checking.
GUARDED_TREES = (
    "coordinator/skills/",
    "coordinator/commands/",
    "coordinator/docs/wiki/",
)

#: Where the remedy actually lives -- named directly in the advisory text
#: too (not only via this anchor), per this guard's own "lead with the
#: alternative" requirement.
_RULE_ANCHOR = "coordinator/snippets/resolve-coordinator-bin.md (rung 0 / Shape W)"


def is_in_scope(target_path: str) -> bool:
    """True if `target_path` (a raw, possibly backslash-separated payload
    string) falls under one of `GUARDED_TREES`. Forward-slash-normalized
    before the substring check, mirroring `GuardScopeDescriptor.matches`'s
    own Windows-payload handling in `_guard_runner_contract.py`."""
    if not target_path:
        return False
    normalized = target_path.replace("\\", "/")
    return any(tree in normalized for tree in GUARDED_TREES)


def new_hits(before: str, after: str) -> list:
    """`find_posix_forwarder_invocations(after)` hits whose matched text was
    not already present the same number of times in `before` -- a
    Counter-multiset difference over `hit.text`, so a write that only
    rearranges or removes existing hits reports zero new hits, and a write
    that introduces a genuinely new one (even if the file already had a
    different POSIX-invocation hit elsewhere) is still caught."""
    from collections import Counter  # noqa: PLC0415

    before_counts = Counter(h.text for h in find_posix_forwarder_invocations(before))
    after_hits = find_posix_forwarder_invocations(after)
    result = []
    seen = Counter()
    for hit in after_hits:
        seen[hit.text] += 1
        if seen[hit.text] > before_counts[hit.text]:
            result.append(hit)
    return result


def _advisory_reason(target: str, hits: list) -> str:
    clis = sorted({h.cli for h in hits})
    shown = clis[:2]
    clis_text = ", ".join(shown)
    if len(clis) > len(shown):
        clis_text += f", +{len(clis) - len(shown)} more"
    return (
        f"{target} adds a POSIX-only `${{VAR:-default}}` invocation "
        f"reaching {clis_text} -- unrunnable on a PowerShell-only host. "
        "Use rung 0 / Shape W instead."
    )


def _advisory_message(target: str, hits: list) -> Message:
    return compose(_advisory_reason(target, hits), anchor=_RULE_ANCHOR)


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw:
        return 0

    import json  # noqa: PLC0415

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    if payload.get("tool_name", "") not in _GUARDED_TOOLS:
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    target_raw = extract_target_path(tool_input)
    if not target_raw:
        return 0

    if not is_in_scope(target_raw):
        return 0

    try:
        target = Path(target_raw).resolve()
    except Exception:
        return 0

    try:
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    except Exception:
        return 0

    after = reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    hits = new_hits(before, after)
    if not hits:
        return 0

    emit(_advisory_message(target_raw, hits), CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
