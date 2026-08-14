# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py's own hooks.json PreToolUse(Write|Edit|MultiEdit)
# registration calls in-process (C4, docs/plans/2026-08-06-hook-spawn-fan-
# in-finish-and-extend.md). This basename is deliberately never referenced
# literally in hooks.json text -- that IS the mechanism, not an omission.
"""PreToolUse hook (matcher: Write|Edit|MultiEdit): advises when a write
introduces NEW changelog-shaped prose into a coordinator doctrine surface.

Why this exists
----------------
A doctrine surface states the rule as it stands now, present tense, addressed
to the reader who has to obey it next -- it does not carry the rule's own
history (ruling dates, `DR-` supersession chains, "was P now Q", "retired on
<date>", origin-incident narration). That standing rule lives in this repo's
`CLAUDE.md` § Conventions. See `_doctrine_changelog_prose.py`'s module
docstring for the full detection-rule writeup, the two explicitly-handled
ambiguous classes, and the false-positive exemptions this deliberately does
NOT flag.

Advisory for doctrine prose, deny for config debt
----------------------------------------------------
Two classes, two verdicts (`_doctrine_changelog_prose.scope_class`). The
doctrine-prose class cannot always tell a real violation from a legitimate
authority citation with certainty -- the two ambiguous classes in the
detector exist precisely because some shapes are genuinely undecidable from
the text alone. A guard in that position should offer the alternative
rather than refuse the write; the real teeth are `coordinator/tests/
test_doctrine_surfaces_are_not_changelogs.py`, a ratchet whose baseline can
only shrink. Routed through `_message_envelope.compose`/`emit` on
`CHANNEL_ADDITIONAL_CONTEXT`, same channel and one-sentence-diagnosis-plus-
remedy shape as its sibling `guard-prompt-surface-citations.py`.

The config class (a repo-root `coordinator.local.md`) is a PM-ruled HARD
DENY instead, via `CHANNEL_DENY`: no proximity condition, no verb
requirement, and no ambiguous tier softens it, so there is no case where
advising instead of refusing is the safer default. A line marked
`<!-- doctrine-retirement-exemption: <reason> -->` is exempt from the date
leg only -- not the rot-prone-path leg, and not the bare-`DR-` leg, which a
retirement clause satisfies by citing its record path-qualified rather than
by claiming an exemption. See the detector module.

Scoping
-------
Fires only on `new_violations(before, after)` -- a multiset difference
between the file's violations before and after THIS write -- never on
pre-existing debt sitting untouched in a file being edited for an unrelated
reason. See `_doctrine_changelog_prose.new_violations`'s docstring.

Reconstructing before/after
-----------------------------
Same contract as `guard-prompt-surface-citations.py`: `before` is the current
on-disk content (empty string for a not-yet-existing file); `after` is
reconstructed from `tool_input` -- Write's `content` directly, Edit's single
`old_string`/`new_string` replacement (or all occurrences under
`replace_all`), MultiEdit's sequential application over `tool_input["edits"]`.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable stdin
payload; tool_name not in the guarded set; no target path in tool_input;
target's `scope_class()` is `None` (wrong tree/extension, a `tests/`/
`fixtures/` subdirectory, or a `coordinator.local.md` not directly at a
`.git`-rooted repo root); on-disk read failure for an existing file;
unreconstructable before/after; zero new violations -- for BOTH classes
(see `_doctrine_changelog_prose.new_violations`'s docstring for why a deny
still scopes to the delta, never whole-file debt).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _doctrine_changelog_prose import new_violations, scope_class  # noqa: E402
from _message_envelope import (  # noqa: E402
    CHANNEL_ADDITIONAL_CONTEXT,
    CHANNEL_DENY,
    Message,
    compose,
    emit,
)

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Where the rule this guard enforces actually lives -- not a wiki page (this
#: guard was not asked to author one), the repo's own standing convention.
_RULE_ANCHOR = "CLAUDE.md § Conventions (\"Doctrine is not changelog\")"


def _advisory_reason(target: str, violations: list) -> str:
    """The prose diagnosis, kept as a plain-string-returning function
    separable from stdin/envelope plumbing -- same shape as the sibling
    guard's `_deny_reason`.

    High-confidence hits are named directly; an ambiguous-only result gets
    softer language ("worth a second look") since a bare-phrase match can't
    establish a real violation on its own -- see the detector module
    docstring's writeup of the two ambiguous classes."""
    high = [v for v in violations if v.confidence == "high"]
    ambiguous = [v for v in violations if v.confidence == "ambiguous"]

    if high:
        kinds = sorted({v.kind for v in high})
        shown = kinds[:2]
        kinds_text = ", ".join(shown)
        if len(kinds) > len(shown):
            kinds_text += f", +{len(kinds) - len(shown)} more"
        extra = f" (+{len(ambiguous)} ambiguous)" if ambiguous else ""
        return (
            f"{target} adds {len(high)} changelog-shaped passage(s){extra} "
            f"({kinds_text}). State the rule in present tense; put history "
            "in the commit message or a decision record."
        )

    kinds = sorted({v.kind for v in ambiguous})
    kinds_text = ", ".join(kinds[:2])
    return (
        f"{target} adds {len(ambiguous)} passage(s) worth a second look "
        f"({kinds_text}) -- may be live-rule provenance, may be reversal "
        "narration."
    )


def _advisory_message(target: str, violations: list) -> Message:
    return compose(_advisory_reason(target, violations), anchor=_RULE_ANCHOR)


def _deny_reason(target: str, violations: list) -> str:
    """The config-class deny diagnosis -- every hit here is high-confidence
    by construction (`_scan_config_line` has no ambiguous tier), so this
    carries no soft-language branch the sibling `_advisory_reason` needs.
    Same one-sentence-diagnosis-plus-remedy shape."""
    kinds = sorted({v.kind for v in violations})
    shown = kinds[:2]
    kinds_text = ", ".join(shown)
    if len(kinds) > len(shown):
        kinds_text += f", +{len(kinds) - len(shown)} more"
    return (
        f"{target} adds {len(violations)} changelog-shaped config token(s) "
        f"({kinds_text}). This config file class is a hard deny: drop the "
        "date, cite a DR by repo-relative path instead of a bare id (the "
        "number alone matches two decision namespaces), or replace the "
        "rot-prone pointer with the live fact it names. A genuine retirement "
        "keeps its date with <!-- doctrine-retirement-exemption: <reason> -->."
    )


def _deny_message(target: str, violations: list) -> Message:
    return compose(_deny_reason(target, violations), anchor=_RULE_ANCHOR)


def main() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw:
        return 0

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

    try:
        target = Path(target_raw).resolve()
    except Exception:
        return 0

    klass = scope_class(target)
    if klass is None:
        return 0

    try:
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    except Exception:
        return 0

    after = reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    is_config = klass == "config"
    is_json = target.suffix == ".json"
    new = new_violations(before, after, is_json=is_json, is_config=is_config)
    if not new:
        return 0

    if is_config:
        emit(_deny_message(target_raw, new), CHANNEL_DENY)
    else:
        emit(_advisory_message(target_raw, new), CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
