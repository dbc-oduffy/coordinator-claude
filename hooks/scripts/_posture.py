"""Shared, fail-open `engagement_posture` resolver.

Spec backlink: docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md (chunk C1).

Gives `engagement_posture` its first code consumer. Sibling hook scripts
import this module the same way `_message_envelope.py` is already consumed
(see nudge-autonomous-askuserquestion.py:57-58 for the established
sys.path-insert idiom).

Resolution order:
  1. `coordinator.local.md` frontmatter key `engagement_posture`, at the
     CONSUMING repo root, when it resolves and the key is present
     (per-repo override). The consuming repo root is `CLAUDE_PROJECT_DIR`
     when set and a real directory, else a zero-spawn pure-Python upward
     walk for a `.git` entry (directory for a normal clone, file for a
     worktree) -- NOT a walk from this file's own `__file__`, which only
     ever finds THIS plugin's own checkout. On a marketplace install
     (plugin under `~/.claude/plugins/`) `__file__`-anchoring never
     resolves the consumer's repo at all, silently dropping this whole
     rung to the operator-level rung below.
  2. `~/.claude/coordinator-identity.yaml` key `engagement_posture` (the
     durable machine-local record).
  3. Fail open to "precision".

FAIL-OPEN DIRECTION IS LOAD-BEARING: "precision" is the anchor whose
behaviour stays unchanged. Every failure path -- missing file, unreadable
file, unparseable content, absent key, value outside the enum -- returns
"precision". An unreadable identity file degrades to "change nothing",
never to "start blocking".

Both consulted files are read through `coordinator/lib/frontmatter_scan.py`
(column-zero keys only; a YAML-flavored frontmatter block and a flat YAML
mapping respectively), avoiding a YAML dependency on a hot path.
"""

from __future__ import annotations

import os
import sys

_VALID_POSTURES = frozenset({"precision", "default", "substrate-free"})
# Named for what it SELECTS, not for the failure mode that reaches it: resolution
# fails open (never blocks), and the value it falls back to is the most cautious
# posture in the enum. A `_FAIL_OPEN_` prefix would read as the opposite.
_MOST_CAUTIOUS_POSTURE = "precision"

# Cache lifetime is the hook process; do not import this module into a
# long-lived process without adding a TTL or invalidation path.
_cached_posture: str | None = None
# Keyed on the exact `repo_root` string passed to `resolve_posture`; a call
# with a different `repo_root` must never be served a value cached under a
# prior one. Same process-lifetime-only contract as `_cached_posture` above.
_cached_posture_by_root: dict[str, str] = {}

# Reuse the existing root-resolution PRIMITIVE (`_engine_root._session_repo_root`
# -- CLAUDE_PROJECT_DIR when set and real, else a zero-spawn upward walk for a
# `.git` entry) rather than writing a fourth copy of that walk. This is NOT the
# families-spanning shared READER/TRANSPORT module DR-047/DR-118 decline for
# this class of tiny, independently-failing-open helper (see
# `_next_move_ledger._find_repo_root`'s docstring for that ruling) -- this
# module still resolves and caches `engagement_posture` entirely on its own;
# it borrows only the root-finding primitive underneath.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
try:
    from _engine_root import _session_repo_root as _resolve_consuming_repo_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed without its sibling
    # _engine_root.py must still fail-open (this rung simply never resolves)
    # rather than crash on import.
    _resolve_consuming_repo_root = None  # type: ignore[assignment]


_LIB_DIR = os.path.normpath(os.path.join(_SCRIPTS_DIR, "..", "..", "lib"))
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)
try:
    from frontmatter_scan import read_text as _read_text  # noqa: E402
    from frontmatter_scan import scan_frontmatter as _scan_frontmatter  # noqa: E402
    from frontmatter_scan import scan_mapping as _scan_mapping  # noqa: E402
except Exception:
    # An install shape that ships hooks/scripts without coordinator/lib must
    # still fail open to the default posture, never crash at import.
    _read_text = _scan_frontmatter = _scan_mapping = None  # type: ignore[assignment]


def _read_key_from_file(path: str, key: str) -> str | None:
    """Return the scalar string value of `key` from a `.md` frontmatter block
    or a flat `.yaml` mapping; None when unreadable, absent, empty, non-scalar,
    or the scanner is unavailable."""
    if _read_text is None:
        return None
    try:
        text = _read_text(path)
        scan = _scan_frontmatter if str(path).endswith(".md") else _scan_mapping
        value = scan(text).get(key)
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def _find_repo_root() -> str | None:
    """Anchor at the CONSUMING repo root: `CLAUDE_PROJECT_DIR` when set and a
    real directory, else a zero-spawn pure-Python upward walk for a `.git`
    entry (directory for a normal clone, file for a worktree).

    Delegates to `_engine_root._session_repo_root` -- the existing
    root-resolution primitive, reused rather than reimplemented (see the
    module-level comment above this function's import). Previously walked
    upward from THIS FILE's own `__file__` looking for a directory
    containing `coordinator.local.md`, which only ever resolves this
    plugin's own checkout -- correct by accident in a dev repo where
    `--plugin-dir` points the plugin at the working tree itself, and silent
    dead weight on a marketplace install where the plugin lives under
    `~/.claude/plugins/` and the consumer's `coordinator.local.md` lives
    somewhere `__file__` can never reach."""
    if _resolve_consuming_repo_root is None:
        return None
    try:
        root = _resolve_consuming_repo_root()
        return str(root) if root else None
    except Exception:
        return None


def _resolve_posture_from(repo_root: str | None) -> str:
    """Resolution body shared by both `resolve_posture()` call shapes:
    `repo_root` is the already-decided consuming root (explicit-argument
    call), or None to fall back to `_find_repo_root()`'s own anchoring."""
    try:
        root = repo_root if repo_root is not None else _find_repo_root()
        if root is not None:
            local_md = os.path.join(root, "coordinator.local.md")
            value = _read_key_from_file(local_md, "engagement_posture")
            if value is not None:
                value = value.lower()
            if value in _VALID_POSTURES:
                return value

        # CLAUDE_HOME first, `Path.home()` as the terminal rung -- a bare
        # `expanduser("~")` yields the literal "~" when every home rung is
        # unset, which silently reads a posture file that is not the operator's.
        from pathlib import Path
        claude_home = os.environ.get("CLAUDE_HOME") or Path.home()
        identity_path = os.path.join(claude_home, ".claude", "coordinator-identity.yaml")
        value = _read_key_from_file(identity_path, "engagement_posture")
        if value is not None:
            value = value.lower()
        if value in _VALID_POSTURES:
            return value
    except Exception:
        pass

    return _MOST_CAUTIOUS_POSTURE


def resolve_posture(repo_root: str | None = None) -> str:
    """Return the resolved engagement posture, one of "precision",
    "default", "substrate-free". Fails open to "precision" on any
    unreadable/unparseable/absent/out-of-enum condition, and on any other
    exception raised anywhere in the resolution body (path walk, expanduser,
    etc.) -- callers importing this module get the fail-open contract
    unconditionally, not just for the two guarded I/O paths.

    `repo_root` (optional): an already-resolved consuming-repo root to
    anchor at directly, bypassing `_find_repo_root()`'s own CLAUDE_PROJECT_DIR/
    `.git`-walk anchoring. Every existing caller passes nothing and gets
    byte-identical behaviour to before this parameter existed.

    INTENDED CONSUMER: this module's own planned move into the engine
    (`coordinator_core/hooks/support/posture.py`, per
    docs/plans/2026-09-18-doe-holds-no-scripts.md W4-C4) and, ahead of that
    move, any hook here already holding a Stop/PostToolUse payload with a
    `cwd` field (e.g. guard-manufactured-blocker.py, which already reads
    `payload["cwd"]` for its own use). A resident engine process serves ~50
    concurrent sessions and cannot anchor off its own process cwd or
    `CLAUDE_PROJECT_DIR` the way a short-lived per-invocation script can; it
    must derive `repo_root` fresh from each call's own payload and pass it
    in explicitly. No call site does this yet -- the parameter is prepared
    ahead of that consumer, not dead.

    Cached per process, in one of two module-level stores depending on call
    shape -- a call with a different `repo_root` is NEVER served a value
    cached under a prior root:
      - no `repo_root` (or falsy): `_cached_posture`, a bare scalar, matching
        this function's pre-existing single-value cache exactly.
      - explicit `repo_root`: `_cached_posture_by_root`, keyed on the exact
        `repo_root` string passed in.
    """
    global _cached_posture

    if repo_root:
        if repo_root in _cached_posture_by_root:
            return _cached_posture_by_root[repo_root]
        result = _resolve_posture_from(repo_root)
        _cached_posture_by_root[repo_root] = result
        return result

    if _cached_posture is not None:
        return _cached_posture
    _cached_posture = _resolve_posture_from(None)
    return _cached_posture
