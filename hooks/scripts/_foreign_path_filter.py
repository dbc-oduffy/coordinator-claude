"""The plane-repo predicate: is THIS session's own repo one of the two planes?

Spec: 2026-08-30 foreign-repo-identity-suppression plan, chunk C2. One module,
one question — `session_repo_is_plane(cwd) -> bool`. S1 and S3
(`project-orientation.py`) share exactly this one fact: whether the session's
own repo root is this doctrine repo, or one of the engine plane's own working
trees (`repos.*` — the authoring checkout and the published-and-shipped one;
see this repo's `CLAUDE.md` § Place in the fleet). Nothing else is built
here.

Negative-spec — no call-site subject/incidental classification API. An earlier
draft of this plan carried a three-question protocol (subject-vs-incidental,
trigger-scope, remedy-scope) for call sites to declare against. That protocol
had zero runtime consumers once C6 (the fail-open exemption chunk) was cut:
S4/S5/S9 are message rewrites that never call a filter, S8 is a declared
exemption on the same footing as a site that never calls one, and S1/S3 need
only this one predicate. Keep only what has a live caller.

Reads the machine-local registry directly, same rungs `_engine_root.py`
already uses (`_settings_home_registry_dir`, `_registry_value`), rather than
re-deriving the settings-home precedence a second time. Comparison goes
through `_engine_root._same_repo_path` — samefile with a normcase+realpath
fallback — so a POSIX-rooted and a drive-lettered registration of the same
plane both match (multi-os-first-class: this must never degenerate into a
literal path list).
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The `repos.*` registry keys naming the two planes: this doctrine repo, and
#: the engine plane's two own working trees (authoring vs. published-and-
#: shipped) — see this module's docstring.
_PLANE_REGISTRY_KEYS = (
    "repos.doe_claude",
    "repos.claude_klabauter",
    "repos.claude_klabauter",
)


def session_repo_is_plane(cwd: str | Path) -> bool:
    """Is `cwd` (the session's own repo root) one of the two planes?

    Fail-open to False: an unreadable registry or an unregistered key means
    "not determinably a plane repo", never a raise. Callers on the hot
    SessionStart path need a plain bool, not a tri-state — the cost of a
    false negative here is one more foreign-path line suppressed-as-shown
    (status quo), never a crash.
    """
    try:
        _hooks_dir = str(Path(__file__).resolve().parent)
        if _hooks_dir not in sys.path:
            sys.path.insert(0, _hooks_dir)
        from _engine_root import _registry_value, _same_repo_path, _settings_home_registry_dir
    except Exception:
        return False

    try:
        reg_dir = _settings_home_registry_dir()
    except Exception:
        return False

    cwd_str = str(cwd)
    for key in _PLANE_REGISTRY_KEYS:
        try:
            root = _registry_value(reg_dir, key)
        except Exception:
            continue
        if not root:
            continue
        if _same_repo_path(cwd_str, root):
            return True

    return False
