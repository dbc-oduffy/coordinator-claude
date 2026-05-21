"""project-rag-specific envelope projection + persistence.

R2 (PM 2026-05-19): CLI emits envelope; persist() stores envelope under whoami_profile.
R3 (PM 2026-05-19): addon contributions lift to first-class extras keys (extras.<ns>),
NOT nested under extras.project_rag.addons.<ns>.

Status field placeholder semantics (the Director of Engineering F-Minor 2 2026-05-19):
status.state defaults to "healthy" and status.since defaults to None. Neither
reflects a real liveness probe. A future plan adding a state-tracker may set
both fields meaningfully; until then, status.since=None is the correct shape
(captured_at would falsely reset the since-timestamp on every probe call).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coordinator_whoami.envelope_base import build_envelope
from coordinator_whoami.project_rag.cli import compose, WHOAMI_SCHEMA_VERSION, _resolve_bound_project_root
from coordinator_whoami.project_rag._paths import resolve_user_marker_dir


def compose_envelope() -> dict[str, Any]:
    raw = compose()
    project = raw.get("project") or {}
    state = raw.get("project_rag_state") or {}

    # binding.kind reflects project-rag source-registration for cwd, not cwd-existence
    # (see contract wiki §binding semantics).
    # Uses _resolve_bound_project_root() — the registry-aware primitive in cli.py — rather
    # than project.get("root") (which is cwd-detection, not registration-detection).
    # Without this, binding.kind is structurally always "bound" because cwd is always
    # non-empty; the "unbound" branch in downstream consumers (project-onboarding,
    # session-start) never fires. See 2026-05-21-whoami-first-class-substrate session-end
    # code review Finding 1.
    bound_root = _resolve_bound_project_root()
    binding_kind = "bound" if bound_root else "unbound"
    binding_target = str(bound_root) if bound_root else None

    # project-rag's own host-introspection payload (everything from compose() EXCEPT
    # the addon contributions — those lift to first-class extras keys per R3).
    project_rag_extras = {
        "envelope_version": WHOAMI_SCHEMA_VERSION,
        "captured_at": raw.get("captured_at"),
        "os": raw.get("os"),
        "arch": raw.get("arch"),
        "gpu": raw.get("gpu"),
        "python": raw.get("python"),
        "uv": raw.get("uv"),
        "claude": raw.get("claude"),
        "coordinator": raw.get("coordinator"),
        "project": raw.get("project"),
        "project_rag_state": raw.get("project_rag_state"),
        # NEW native probes (R2 system improvement; landed in Task 2):
        "source": raw.get("source"),
        "engine_version": raw.get("engine_version"),
        "project_kind": raw.get("project_kind"),
        # MCP-tool layer augments with: registered_sources, addon_sources_available
    }

    # R3 — addon contributions lift to first-class extras keys
    addon_extras = raw.get("addons") or {}

    return build_envelope(
        plugin_name="project-rag",
        extras_key="project_rag",
        plugin_version=state.get("version") if isinstance(state, dict) else None,
        binding={"kind": binding_kind, "target": binding_target},
        status={
            "state": "healthy",  # placeholder — no liveness probe yet; see module docstring
            "since": None,       # placeholder per the Director of Engineering F-Minor 2 — null is correct when no state-tracker
            "reason": None,
        },
        plugin_extras=project_rag_extras,
        addon_extras=addon_extras,
    )


def persist(envelope: dict[str, Any]) -> Path:
    """Persist the envelope to ~/.claude/project-rag/install-profile.json under whoami_profile.

    R2 (PM 2026-05-19): the whoami_profile sub-key now carries the ENVELOPE shape,
    not the legacy 12-key flat shape. Downstream consumers (/project-rag:doctor,
    install scripts, addon standalone CLI) update access paths. See Task 8 host
    relay memo for cleanup obligations.
    """
    user_dir = resolve_user_marker_dir()
    profile_path = user_dir / "install-profile.json"

    existing: dict[str, Any] = {}
    if profile_path.exists():
        try:
            existing = json.loads(profile_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing["whoami_profile"] = envelope
    # Mirror compose()'s top-level captured_at expectations: use the envelope's
    # extras.project_rag.captured_at if present, else now.
    existing["captured_at"] = (
        envelope.get("extras", {}).get("project_rag", {}).get("captured_at")
        or datetime.now(tz=timezone.utc).isoformat()
    )
    user_dir.mkdir(parents=True, exist_ok=True)
    # Review: Reviewer A A-F1 — atomic write via tmp+os.replace; prevents partial reads on crash
    import os as _os
    tmp = profile_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    _os.replace(tmp, profile_path)
    return profile_path
