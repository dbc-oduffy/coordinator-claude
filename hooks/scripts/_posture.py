"""Shared, fail-open `engagement_posture` resolver.

Spec backlink: docs/plans/2026-08-10-posture-scaled-autonomous-disposition.md (chunk C1).

Gives `engagement_posture` its first code consumer. Sibling hook scripts
import this module the same way `_message_envelope.py` is already consumed
(see nudge-autonomous-askuserquestion.py:57-58 for the established
sys.path-insert idiom).

Resolution order:
  1. `coordinator.local.md` frontmatter key `engagement_posture`, at the
     repo root, when it resolves and the key is present (per-repo override).
  2. `~/.claude/coordinator-identity.yaml` key `engagement_posture` (the
     durable machine-local record).
  3. Fail open to "precision".

FAIL-OPEN DIRECTION IS LOAD-BEARING: "precision" is the anchor whose
behaviour stays unchanged. Every failure path -- missing file, unreadable
file, unparseable content, absent key, value outside the enum -- returns
"precision". An unreadable identity file degrades to "change nothing",
never to "start blocking".

Both consulted files are flat `key: value` text (a YAML-flavored
frontmatter block and a flat YAML mapping respectively); a line-scan parser
is correct here and avoids adding a YAML dependency on a hot path.
"""

from __future__ import annotations

import os

_VALID_POSTURES = frozenset({"precision", "default", "substrate-free"})
_FAIL_OPEN_POSTURE = "precision"

_cached_posture: str | None = None
# Cache lifetime is the hook process; do not import this module into a
# long-lived process without adding a TTL or invalidation path.


def _extract_key_from_lines(lines, key: str) -> str | None:
    """Scan flat `key: value` lines and return the first value for `key`,
    or None if absent. Tolerates a leading `---` frontmatter fence and
    trailing inline comments; does not attempt general YAML parsing."""
    prefix = key + ":"
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if "#" in value:
                value = value.split("#", 1)[0].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if value:
                return value
    return None


def _read_key_from_file(path: str, key: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    except UnicodeDecodeError:
        return None
    return _extract_key_from_lines(lines, key)


def _find_repo_root() -> str | None:
    """Walk upward from this file looking for a directory containing
    `coordinator.local.md` -- this repo's own root. Purely local
    filesystem walk; never assumes cwd."""
    current = os.path.dirname(os.path.abspath(__file__))
    while True:
        candidate = os.path.join(current, "coordinator.local.md")
        if os.path.isfile(candidate):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def resolve_posture() -> str:
    """Return the resolved engagement posture, one of "precision",
    "default", "substrate-free". Fails open to "precision" on any
    unreadable/unparseable/absent/out-of-enum condition, and on any other
    exception raised anywhere in the resolution body (path walk, expanduser,
    etc.) -- callers importing this module get the fail-open contract
    unconditionally, not just for the two guarded I/O paths. Cached per
    process in a module-level global."""
    global _cached_posture
    if _cached_posture is not None:
        return _cached_posture

    try:
        repo_root = _find_repo_root()
        if repo_root is not None:
            local_md = os.path.join(repo_root, "coordinator.local.md")
            value = _read_key_from_file(local_md, "engagement_posture")
            if value is not None:
                value = value.lower()
            if value in _VALID_POSTURES:
                _cached_posture = value
                return _cached_posture

        identity_path = os.path.join(os.path.expanduser("~"), ".claude", "coordinator-identity.yaml")
        value = _read_key_from_file(identity_path, "engagement_posture")
        if value is not None:
            value = value.lower()
        if value in _VALID_POSTURES:
            _cached_posture = value
            return _cached_posture
    except Exception:
        pass

    _cached_posture = _FAIL_OPEN_POSTURE
    return _cached_posture
