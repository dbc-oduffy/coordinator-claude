"""
memo_compose.py — shared composer for cross-repo memo frontmatter and documents.

Purpose: Provide the memo frontmatter and document composition functions used
by both bin/cross-repo-memo (for delivery memos) and bin/coordinator-doc-new
(for local memo skeletons). Extracted from bin/cross-repo-memo so neither
caller inlines the same logic independently.

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-0-canonical-baton-shape.md § C4

Usage:
    import os, sys
    _LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    if _LIB not in sys.path: sys.path.insert(0, _LIB)
    from memo_compose import compose_frontmatter, compose_memo, _SUMMARY_MAX_CHARS

Negative-spec: This module does NOT contain receiver-routing logic, realpath
containment, single-surface delivery, self-receipt delivery, claim-lock, or
any other cross-repo-memo delivery surface. Those remain wholly in
bin/cross-repo-memo. This module is COMPOSER-ONLY — pure string construction
given pre-resolved parameters.

Negative-spec: compose_frontmatter and compose_memo take from_id as an
EXPLICIT parameter. This module never calls machine-local or resolves sender
identity itself — that is routing concern, not composer concern.

Call-site guide (Review: code-reviewer F19):
  External callers: use compose_memo() to obtain a COMPLETE document (frontmatter + body).
  compose_frontmatter() is the lower-level building block — calling it directly gives you
  ONLY the YAML frontmatter block, without the body. A caller that accidentally uses
  compose_frontmatter() where compose_memo() is needed writes a file with no body.
"""
from __future__ import annotations

import datetime

# Maximum summary length — mirrors the ≤120-char rule in bin/lib/schema.js
# CROSS_FIELD_RULES.cross_repo_memo summary validation. If schema.js bumps the
# cap, update this constant too. Both sides must stay in sync.
_SUMMARY_MAX_CHARS = 120


def _yaml_quote(value: str) -> str:
    """Double-quote a string for YAML, escaping backslashes, double-quotes,
    and newlines/tabs. Always double-quotes — appropriate for memo frontmatter
    where all values are authored strings and unambiguous quoting is required.

    Negative-spec: unlike coordinator-queue-append's _yaml_quote_string, this
    function ALWAYS wraps in double-quotes and never emits bare YAML strings.
    The two serve different field grammars; do not conflate them.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _today() -> str:
    """Return today's date as YYYY-MM-DD (ISO-8601 date)."""
    return datetime.date.today().isoformat()


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format (seconds precision)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _derive_summary(body: str) -> str:
    """Derive a summary from the first non-empty line of the memo body.

    Truncates to _SUMMARY_MAX_CHARS with a '…' suffix so the composed memo
    never violates the schema.js ≤120-char cross-field rule.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            if len(stripped) <= _SUMMARY_MAX_CHARS:
                return stripped
            # Truncate preserving full words where possible.
            return stripped[: _SUMMARY_MAX_CHARS - 1] + "…"
    return ""


def _render_scoped_to(scoped_to: dict[str, str]) -> str:
    """Render the nested `scoped_to:` frontmatter mapping.

    Matches the shape claude-klabauter's memo.send op composes into
    engine-delivered memos (`coordinator_core/ops/fleet/memo_send.py`
    `_render_extra_field`/`_render_yaml_block`, bcc7cdbe): a `scoped_to:`
    key followed by 2-space-indented `sub_key: "value"` lines, each scalar
    double-quoted via `_yaml_quote`. Keys are rendered in `scoped_to`'s own
    iteration order — callers (via `_build_scoped_to`) insert artifact,
    version-or-sha, then seam, matching claude-klabauter's field order.
    """
    lines = ["scoped_to:"]
    for key, value in scoped_to.items():
        lines.append(f"  {key}: {_yaml_quote(value)}")
    return "\n".join(lines)


def compose_frontmatter(
    *,
    from_id: str,
    title: str,
    to: str,
    topic: str,
    body: str,
    self_receipt: bool = False,
    decision: str | None = None,
    supersedes: str | None = None,
    summary: str | None = None,
    kind: str | None = None,
    scoped_to: dict[str, str] | None = None,
    sent_by: str | None = None,
    draft: bool = False,
) -> str:
    """Compose the YAML frontmatter block for a memo.

    Parameters:
        from_id: Sender EM identity (e.g. "claude-central-em"). Callers MUST
                 resolve this from their context before calling.
                 cross-repo-memo passes _sender_em_id(); coordinator-doc-new
                 passes its own cwd-resolved identity. Never hardcoded here.
        title:   Memo title (will be double-quoted in output).
        to:      Receiver EM identity (e.g. "project-rag-em").
        topic:   Slug used in the filename — NOT emitted in frontmatter.
        body:    Memo body text; used to derive summary when summary=None.
        self_receipt: True when dispatcher is also the receiver.
        decision: Required when self_receipt=True (accepted|declined|partial|superseded).
        supersedes: Optional; set on a re-issued memo to chain the supersession.
        summary: Explicit one-line tl;dr (≤120 chars); derived from first
                 non-empty body line when None. Truncated at _SUMMARY_MAX_CHARS.
        kind:    Optional sender-declared shape: ask | consult | fyi | proposal.
                 When None, NO kind: line is emitted (absence is meaningful —
                 readers apply an 'ask' default for unlabelled memos).
        scoped_to: Optional nested {artifact, version|sha, seam} mapping —
                 same shape `_build_scoped_to` (cross-repo-memo) assembles
                 and claude-klabauter's memo.send op composes into engine-delivered
                 memos. Rendered AFTER kind:/supersedes:, mirroring
                 memo_send.py's field order. Omitted entirely when None or
                 empty (no `scoped_to:` line at all) — never emitted as a
                 present-but-empty mapping.
        sent_by: Optional sender session UUID (docs/plans/2026-08-13-session-
                 identity-earns-its-keep.md § C7), mirroring picked_up_by on
                 the receive path. Resolved at SEND time by the caller — this
                 composer never resolves session identity itself (same
                 negative-spec as from_id above). Rendered AFTER scoped_to
                 and BEFORE the self_receipt block — this composer's field
                 order is NOT the same as memo_send.py._compose_memo's
                 (which renders sent_by BEFORE scoped_to); YAML mapping
                 order is not semantically load-bearing for a parsed
                 frontmatter dict, so the two orders are deliberately not
                 kept in lockstep. Omitted entirely when None or empty.

    Schema backlink:
        docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 3

    Negative-spec: this function never calls machine-local, _sender_em_id(),
    or any routing helper. from_id is always explicit.
    """
    # Guard: decision is required when self_receipt=True.
    # _compose_frontmatter would emit 'decision: "None"' (the string "None") if called
    # without a decision. Fail loudly rather than silently writing a malformed field.
    if self_receipt and decision is None:
        raise ValueError(
            "compose_frontmatter: decision is required when self_receipt=True. "
            "Pass a decision value (accepted|declined|partial|superseded)."
        )

    # Resolve and enforce summary length.
    resolved_summary = summary if summary is not None else _derive_summary(body)
    if len(resolved_summary) > _SUMMARY_MAX_CHARS:
        resolved_summary = resolved_summary[: _SUMMARY_MAX_CHARS - 1] + "…"

    today = _today()
    # Canonical terminal status is 'actioned' (open → actioned). 'action_taken'
    # is a grandfathered pre-2026-05-21 value — do not stamp it on new memos.
    # `draft` is the OUTBOX status (2026-08-30): a staged draft under
    # state/memo-outbox/ that memo.send has not delivered yet. It is a
    # different lifecycle point from `open` (delivered, awaiting the
    # receiver) and `actioned` (terminal), and _outbox_frontmatter_rules
    # REQUIRES it -- a scaffolder emitting `open` produces a file that
    # validator rejects. `self_receipt` still wins: a self-receipt is
    # terminal by construction and is never a draft.
    if self_receipt:
        status = "actioned"
    elif draft:
        status = "draft"
    else:
        status = "open"
    # All string values are quoted so '#', leading '[', and trailing-space-before-':'
    # in titles don't truncate via the YAML parser. 'topic' lives in the filename,
    # not the schema — intentionally absent from frontmatter.
    lines = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"from: {_yaml_quote(from_id)}",
        f"to: {_yaml_quote(to)}",
        f"created: {today}",
        f"status: {status}",
        f"delivery_mode: receiver-repo",
        f"summary: {_yaml_quote(resolved_summary)}",
    ]
    if kind is not None:
        lines.append(f"kind: {_yaml_quote(kind)}")
    if supersedes:
        lines.append(f"supersedes: {_yaml_quote(supersedes)}")
    if scoped_to:
        lines.append(_render_scoped_to(scoped_to))
    if sent_by:
        lines.append(f"sent_by: {_yaml_quote(sent_by)}")
    if self_receipt:
        lines.append(f"action_taken_at: {_now_iso()}")
        lines.append(f"decision: {_yaml_quote(decision)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def compose_memo(
    *,
    from_id: str,
    title: str,
    to: str,
    topic: str,
    body: str,
    self_receipt: bool = False,
    decision: str | None = None,
    supersedes: str | None = None,
    summary: str | None = None,
    kind: str | None = None,
    scoped_to: dict[str, str] | None = None,
    sent_by: str | None = None,
    draft: bool = False,
) -> str:
    """Compose the full memo document (frontmatter + body).

    Returns the complete document string ready for writing to disk.
    Delegates frontmatter composition to compose_frontmatter().

    sent_by: see compose_frontmatter's docstring — resolved by the caller at
    SEND time, this function only forwards it.
    """
    frontmatter = compose_frontmatter(
        draft=draft,
        from_id=from_id,
        title=title,
        to=to,
        topic=topic,
        body=body,
        self_receipt=self_receipt,
        decision=decision,
        supersedes=supersedes,
        summary=summary,
        kind=kind,
        scoped_to=scoped_to,
        sent_by=sent_by,
    )
    return frontmatter + "\n" + body.rstrip("\n") + "\n"
