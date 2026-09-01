# guard-not-a-hook-entrypoint -- invoked via the in-process guard runner's
# REAL_GUARD_REGISTRY (coordinator/hooks/scripts/_guard_runner.py), which
# preuse-write-dispatch.py's own hooks.json PreToolUse(Write|Edit|MultiEdit)
# registration calls in-process. This basename is deliberately never
# referenced literally in hooks.json text -- that IS the mechanism, not an
# omission.
"""PreToolUse hook (matcher: Write|Edit|MultiEdit): warns on a write that
would leave a handoff's `summary:` frontmatter field over its 140-char cap.

Why this exists
----------------
`coordinator/docs/wiki/coordinator-tripwires/normalize-at-creation-does-not-
cover-a-later-hand-edit.md` names the gap directly: `handoff_normalize
._normalize_one_text` caps `summary:` to 140 chars, but only at handoff
*creation* (`coordinator_core.ops.handoff_author_fork`). A skill that then
has the EM hand-edit the scaffolded file (e.g. `skills/spinoff/SKILL.md`
Step 2) runs entirely after that normalizer -- a 207-char `summary:` typed
at that step sails straight through to `pickup-assemble apply`, which
refuses the claim outright, at a surface owned by whoever consumes the
handoff rather than whoever wrote it. This guard is the authoring-time
correction the tripwire names but never built: flag the over-cap value at
the moment it is TYPED, in this repo's own hook surface, as advisory
context alongside the write rather than leaving the author to discover it
only at the downstream engine-plane consumer. The write proceeds either
way -- `pickup-assemble apply`'s own refusal is the backstop that actually
blocks an over-cap claim, and this guard deliberately does not duplicate
that as a second block at authoring time: an over-cap `summary:` is loud
and one-line-recoverable there, while a deny here costs the author a full
body re-send on every miss.

Schema is the source of the cap, not a local guess
----------------------------------------------------
`coordinator/schemas/handoff.schema.json`'s `summary` property description
states the cap in prose ("One-line session summary (<=140 chars)"); the
schema itself carries no `maxLength` (the real enforcement is a cross-field
rule in the engine plane). `_HANDOFF_SUMMARY_CAP` below is that same 140,
transcribed once, at the one place this guard needs it -- not re-derived
from the schema file at hook time, since a plain non-JSON-Schema prose
cap has nothing machine-parseable to derive it FROM.

Only handoffs are in scope. `cross-repo-memo.schema.json` carries a
sibling capped `summary` (120 chars), warned rather than denied by its own
guard because `memo_send.py`'s own SEND-time gate normalizes ahead of
itself -- an over-cap memo summary never reaches a downstream refusal.
Handoffs have no such send-time normalizer; `pickup-assemble apply` is the
only place an over-cap `summary:` is ever caught outright, which is why
this guard warns at authoring time too: give the author the diagnosis
early, without gating the write on it.

Scope, mirroring `guard-python-syntax-on-write.py`
-----------------------------------------------------
A `.md` file under `state/handoffs/` (this repo's live handoff directory --
see `state/handoffs/*.md` for the frontmatter shape `summary:` lives in).
Archived handoffs (`state/handoffs/archive/`) are NOT excluded on purpose:
a hand-edit to an archived file's frontmatter is the same class of defect,
and excluding it would just move the hole rather than close it.

Fail-open guards (all exit 0 silent, in order): unreadable/unparseable
stdin payload; tool_name not in the guarded set; no target path in
tool_input; target not a `.md` file under `state/handoffs/`; on-disk read
failure for an existing file; ambiguous before/after reconstruction
(`reconstruct_after` returned None); no frontmatter fence in the
reconstructed after-text; unparseable YAML frontmatter (PyYAML unavailable
included); no `summary` key, or a non-string `summary` value (schema
compliance is this guard's business only for the field it caps, never a
general frontmatter validator); a `summary` at or under the cap. A guard
that cannot compute its own input has no basis to warn.

Warn message
-------------
Names the actual length and the cap -- the reader is mid-edit on the exact
file the count is wrong in, so no wiki anchor is spent sending them
elsewhere (same reasoning as `guard-python-syntax-on-write.py`'s own
message note).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, Message, compose, emit  # noqa: E402

try:
    import yaml
except Exception:  # pragma: no cover -- exercised only in a PyYAML-less env
    yaml = None  # type: ignore[assignment]

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: Directory substring, not a suffix restriction beyond `.md` -- matches
#: `state/handoffs/` anywhere in the resolved path, including the
#: `archive/` subtree (see module docstring, "Scope").
_SCOPE_DIR = "state/handoffs/"

#: Transcribed from `coordinator/schemas/handoff.schema.json`'s `summary`
#: property description ("One-line session summary (<=140 chars)"). See
#: module docstring, "Schema is the source of the cap".
_HANDOFF_SUMMARY_CAP = 140


def is_in_scope(target: Path) -> bool:
    """A `.md` file somewhere under a `state/handoffs/` directory."""
    if target.suffix != ".md":
        return False
    posix = target.as_posix()
    return _SCOPE_DIR in posix or posix.endswith(_SCOPE_DIR.rstrip("/"))


def _split_frontmatter(text: str) -> "tuple[dict | None, str]":
    """Split a `---\\n<yaml>\\n---\\n<body>` document into
    `(frontmatter_dict, body)`. Returns `(None, text)` on ANY shape
    mismatch (no leading `---` fence, fewer than two fences, unparseable
    YAML, a non-dict parsed value, or PyYAML unavailable) -- fail-open,
    mirroring `handoff-segment-inject.py`'s own `_split_frontmatter`
    (a self-contained copy here rather than a shared import: that module's
    purpose is unrelated, and this guard's only dependency on it would be
    this one small, stable parsing shape)."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    fm_text, body = parts[1], parts[2]
    if body.startswith("\n"):
        body = body[1:]
    if yaml is None:
        return None, text
    try:
        fm = yaml.safe_load(fm_text)
    except Exception:
        return None, text
    if not isinstance(fm, dict):
        return None, text
    return fm, body


def _warn_reason(target: str, length: int) -> str:
    """The prose diagnosis (the only part `_message_envelope.CEILING`
    counts)."""
    return (
        f"summary-cap: {target}'s `summary:` frontmatter is {length} chars, "
        f"over the {_HANDOFF_SUMMARY_CAP}-char cap "
        "(coordinator/schemas/handoff.schema.json). A normalizer caps this "
        "field at handoff creation but not on a later hand-edit -- the "
        "write proceeds; fix the field on the next edit."
    )


def _warn_message(target: str, length: int) -> Message:
    return compose(_warn_reason(target, length))


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

    if not is_in_scope(target):
        return 0

    try:
        before = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    except Exception:
        return 0

    after = reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    fm, _body = _split_frontmatter(after)
    if fm is None:
        return 0

    summary = fm.get("summary")
    if not isinstance(summary, str):
        return 0

    length = len(summary)
    if length <= _HANDOFF_SUMMARY_CAP:
        return 0

    emit(_warn_message(target_raw, length), CHANNEL_ADDITIONAL_CONTEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
