"""SessionStart hook — self-heals `repos.claude_klabauter` in the machine-local
registry so a box that never ran the installer still resolves a published
engine.

**The gap this closes, measured.** A cloud session container clones every fleet
repo and installs no coordinator, so `<settings-home>` carries no machine-local
registry at all. `_engine_root.py`'s ladder then falls past its published-engine
rung (nothing registered) to rung 3's sibling walk and answers the LIVE
`claude-klabauter` working tree — which on such a box was never built and carries
no `coordinator_core/_engine_stamp`. The engine's dispatch stamp gate refuses
every op against it with "not a published engine", naming a remedy binary that
the same missing install means is not on the box either. The operator meets an
engine-root error whose stated fix does not exist, and nothing anywhere names
the actual gap: the registry was never written.

The published mirror is sitting right there as a sibling, stamped and healthy.
This hook registers it.

Contract:
  stdin   — SessionStart JSON payload (unused; this hook resolves its OWN root
            from `__file__`, per CLAUDE.md "Scripts self-resolve their own root
            from BASH_SOURCE, never cwd")
  stdout  — NOTHING, on every path. Carried by `sessionstart-async-dispatch.py`
            (`async: true`): this hook's whole value is the registry side
            effect, and a hook that chatters on every healthy session is worse
            than the gap it closes.
  exit 0  — ALWAYS. Fail open at every step; every failure mode degrades to a
            silent no-op. Mirrors `session-start-register-doe-claude-root.py`,
            its sibling in the same fan-in — read that file first if editing
            this one.

**Silent when healthy, and cheap about establishing that.** The first thing
this hook does is `resolve_claude_klabauter_root_with_provenance()` — zero-spawn, a
handful of stat/read calls. A box already answering `RESOLUTION_RESOLVED_ENGINE`
returns immediately, having written nothing and spawned nothing. So does a box
resolving a live working tree that IS stamped: that is a co-development machine
resolving the tree it means to, and the stamp is the evidence the tree is
usable. Only an UNSTAMPED resolution — the state whose downstream consequence is
a refusal at every op dispatch — goes looking for a mirror to register.

**Never overwrites a value a real install wrote.** A present, non-empty
`repos.claude_klabauter` ends this hook, whatever it points at and whatever the
ladder did with it. If a registered mirror is not producing a resolved engine,
that is a different defect with a different owner, and clobbering the operator's
(or the engine installer's) value is not this hook's call to make.

**Discovery is name-anchored, not a scan.** The candidate is a directory named
`claude-klabauter` in one of the two positions rung 3's own sibling walk
probes — beside the plugin root (flat mirror layout) or beside its parent
(nested layout) — anchored via `_engine_root._find_plugin_root`, never a fixed
`parents[]` count. A scan of every sibling looking for something engine-shaped
would eventually register a tree nobody meant, and a false positive here is
worse than the gap: it points every session on the box at the wrong engine.

**And it must be STAMPED.** The candidate is accepted only if
`coordinator_core/_engine_stamp` is readable and non-empty — the same validity
bar `_engine_root._resolve_published_engine` applies to the value it reads back,
so this hook can never register a root that rung would then refuse. Registering
an unstamped clone would move the failure without fixing it.

**What this hook deliberately does NOT write: `engine.target`.** With
`repos.claude_klabauter` registered, rung 2 still needs one of its two
disjuncts. The legacy disjunct fires for any repo the registry can confirm is
not an engine working repo, which covers every consumer repo on the box — and
that is the measured case this closes. The other disjunct wants `engine.target`,
and `engine.target` is a DECLARATION of which channel the box runs, not an
observation: the engine plane's own health probe carries an explicit negative
spec against inferring it from what the mirror has checked out, precisely so the
probe can detect a disagreement instead of agreeing with itself. A self-heal
that invented a value would destroy that instrument and would then be found
present — and skipped — by the real install that should have written it. So a
DoE-claude-rooted session on an uninstalled box still resolves the unstamped
live tree; `coordinator/bin/emit-dispatch-workflow.py` names that state and its
remedy at the point of refusal rather than this hook guessing.

Tripwire:
`coordinator/docs/wiki/coordinator-tripwires/a-box-that-never-ran-the-installer-resolves-an-unstamped-engine.md`
"""

from __future__ import annotations

import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

try:
    from _engine_root import (  # noqa: E402
        RESOLUTION_RESOLVED_ENGINE,
        _find_plugin_root,
        _registry_value as _engine_registry_value,
        _settings_home_registry_dir,
        resolve_claude_klabauter_root_with_provenance,
    )
except Exception:  # pragma: no cover - partial-deploy defence
    RESOLUTION_RESOLVED_ENGINE = "resolved-engine"  # type: ignore[assignment]

    def _find_plugin_root(start):  # type: ignore[no-redef]
        return None

    def _engine_registry_value(reg_dir, key):  # type: ignore[no-redef]
        return None

    def _settings_home_registry_dir():  # type: ignore[no-redef]
        return None

    def resolve_claude_klabauter_root_with_provenance():  # type: ignore[no-redef]
        return None, "unresolved", "none"

try:
    from _registry_write import machine_local_set as _machine_local_set  # noqa: E402
except Exception:  # pragma: no cover - partial-deploy defence
    def _machine_local_set(key, value):  # type: ignore[no-redef]
        return None


_REGISTRY_KEY = "repos.claude_klabauter"
_MIRROR_DIR_NAME = "claude-klabauter"


def is_stamped_engine_root(candidate: Path) -> bool:
    """True when `candidate` is a directory carrying a readable, NON-EMPTY
    `coordinator_core/_engine_stamp`.

    Same validity bar as `_engine_root._resolve_published_engine`'s own stamp
    check — readable and non-empty, not merely present, because a partial write
    leaves a zero-byte file behind. Reimplemented here rather than shared with
    that function on purpose: its source is byte-pinned by
    `test_engine_root_conformance.py::test_ladder_source_shape_pin`, and
    refactoring a hot-path resolution rung to serve a self-heal hook would spend
    a cross-plane heads-up on a hook that needs no ladder change at all.

    Never raises; any read failure is `False`, the fail-closed direction for a
    predicate gating a registration.
    """
    try:
        root = Path(candidate)
        if not (root / "coordinator_core").is_dir():
            return False
        return bool((root / "coordinator_core" / "_engine_stamp").read_bytes())
    except Exception:
        return False


def discover_published_mirror() -> Path | None:
    """A stamped `claude-klabauter` in one of rung 3's two sibling positions.

    See the module docstring's "Discovery is name-anchored, not a scan" and
    "And it must be STAMPED" sections. Never raises.
    """
    try:
        plugin_root = _find_plugin_root(Path(__file__).resolve().parent)
        if plugin_root is None:
            return None
        for candidate in (
            plugin_root.parent / _MIRROR_DIR_NAME,
            plugin_root.parent.parent / _MIRROR_DIR_NAME,
        ):
            if candidate.is_dir() and is_stamped_engine_root(candidate):
                return candidate
    except Exception:
        return None
    return None


def main() -> int:
    try:
        root, resolution_class, _provenance = resolve_claude_klabauter_root_with_provenance()
    except Exception:
        return 0

    if resolution_class == RESOLUTION_RESOLVED_ENGINE:
        return 0  # already healthy — no read of the registry, no write, no spawn

    try:
        if root and is_stamped_engine_root(Path(root)):
            return 0  # a live tree that IS a usable build — the co-dev box
    except Exception:
        return 0

    mirror = discover_published_mirror()
    if mirror is None:
        return 0  # nothing on this box to register; the refusal surfaces name it

    try:
        reg_dir = _settings_home_registry_dir()
        if reg_dir is None:
            return 0
        if _engine_registry_value(reg_dir, _REGISTRY_KEY):
            return 0  # a real install (or an operator) already wrote it
    except Exception:
        return 0

    try:
        _machine_local_set(_REGISTRY_KEY, str(mirror))
    except Exception:
        # `machine_local_set` already fails open internally; this call site
        # swallows too, because a SessionStart hook raising is worse than one
        # that silently no-ops.
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
