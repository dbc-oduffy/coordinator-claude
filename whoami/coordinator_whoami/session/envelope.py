"""coordinator_whoami/session/envelope.py — coordinator-session envelope composition.

Builds a v1-conformant whoami envelope for the coordinator-session adopter.
This adopter answers "am I oriented?" from git + filesystem state alone —
zero MCP dependency, zero daemon dependency, zero torch import.

Live-not-receipt invariant (cross-plugin-whoami-contract.md:144-152):
  This adopter ALWAYS sets source_kind="live". It computes orientation health
  at call time and NEVER persists its envelope to disk (no install-profile.json
  write). Every call is a fresh probe of live state. An offline fallback that
  reconstructs from on-disk artifacts is a separate adopter; this one is
  source_kind:live by design.

Binding semantics (binary, not ternary):
  binding.kind is either "bound" (cwd is inside a coordinator-onboarded repo —
  tasks/ dir AND a project tracker present) or "unbound" (not onboarded).
  "degraded" is never emitted by this adopter — the cache-staleness / reconcile
  gradient is expressed on status.state instead (healthy / degraded / error).

Status mapping:
  healthy  — orientation_cache stored HEAD == live HEAD AND not behind origin/main
  degraded — cache stale (HEAD drift) OR behind origin/main; status.reason names which
  error    — unreadable git / fs state prevents probe (partial-None results)
  since    — always null (no state-tracker; consistent with project-rag precedent)

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C2
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from coordinator_whoami.envelope_base import build_envelope
import coordinator_whoami.session.probes as _probes

_PLUGIN_NAME = "coordinator-session"
_EXTRAS_KEY = "coordinator_session"


# ---------------------------------------------------------------------------
# Binding resolution
# ---------------------------------------------------------------------------

def _resolve_binding() -> dict[str, Any]:
    """Determine whether cwd is inside a coordinator-onboarded repo.

    A repo is considered coordinator-onboarded when it has BOTH:
      - a tasks/ directory (coordinator task-management surface)
      - a coordinator anchor (CLAUDE.md)

    This is intentionally a narrow heuristic: broad git-repo detection
    (root == Path("/")) is explicitly excluded so we don't bind to
    system git repos. The session adopter is coordinator-specific.

    No project-tracker leg: rendered tracker artifacts are retired
    fleet-wide and are not reintroduced as a binding signal for any
    onboarded repo.

    Returns {"kind": "bound", "target": <repo root str>} or
            {"kind": "unbound", "target": null}.
    """
    root = _probes.git_root()  # review: F4 — renamed to public git_root (reviewer: code-reviewer, P2)
    if root is None:
        return {"kind": "unbound", "target": None}

    tasks_dir = root / "tasks"
    # Avoid binding to root filesystem or bare git roots without coordinator structure
    has_tasks = tasks_dir.is_dir()
    has_anchor = (root / "CLAUDE.md").exists()

    if has_tasks and has_anchor:
        return {"kind": "bound", "target": str(root)}
    return {"kind": "unbound", "target": None}


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------

def _compute_status(
    git_state: dict[str, Any],
    orientation: dict[str, Any],
) -> dict[str, Any]:
    """Map probe results to status.state + reason.

    error:    git_state branch is None (git unreadable) OR orientation
              present=True but stored_head/live_head both None (fs unreadable).
    degraded: cache stale (HEAD drift) OR behind > 0 commits on origin/main.
              status.reason names the first condition that fired.
    healthy:  cache present and fresh, AND not behind origin/main.
    """
    # Error: git entirely unavailable
    if git_state.get("branch") is None:
        return {"state": "error", "since": None, "reason": "git state unavailable"}

    # Error: cache present but both SHAs are unreadable (fs/git failure mid-probe)
    if (
        orientation.get("present")
        and orientation.get("stored_head") is None
        and orientation.get("live_head") is None
    ):
        return {"state": "error", "since": None, "reason": "orientation cache unreadable"}

    reasons = []

    # review: F2 — absent cache must be degraded, not healthy; docstring says
    # healthy requires cache present+fresh (reviewer: code-reviewer, P1)
    if not orientation.get("present"):
        reasons.append("orientation cache absent")

    # Degraded: cache is stale (HEAD drift)
    if orientation.get("present") and orientation.get("stale") is True:
        reasons.append("orientation cache stale (HEAD drift)")

    # Degraded: behind origin/main
    behind = git_state.get("behind")
    if isinstance(behind, int) and behind > 0:
        reasons.append(f"behind origin/main by {behind} commit(s)")

    if reasons:
        return {"state": "degraded", "since": None, "reason": "; ".join(reasons)}

    return {"state": "healthy", "since": None, "reason": None}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def compose_envelope() -> dict[str, Any]:
    """Build and return the coordinator-session whoami envelope.

    Probes git + filesystem state live at call time. Never persists to disk.
    source_kind="live" is always set explicitly (the Director of Engineering F4 — self-documenting
    at a structural boundary for the adopter whose purpose is daemon-independent
    liveness; cross-plugin-whoami-contract.md:144-152).
    """
    git_state = _probes.probe_git_state()
    orientation = _probes.probe_orientation_cache()
    handoffs = _probes.probe_handoff_counts()

    binding = _resolve_binding()
    status = _compute_status(git_state, orientation)

    plugin_extras: dict[str, Any] = {
        "git_state": git_state,
        "orientation_cache": orientation,
        "handoff_counts": handoffs,
    }

    return build_envelope(
        plugin_name=_PLUGIN_NAME,
        extras_key=_EXTRAS_KEY,
        plugin_version=None,
        binding=binding,
        status=status,
        plugin_extras=plugin_extras,
        addon_extras=None,
        source_kind="live",
    )
