"""coordinator_whoami.session — daemon-independent orientation-health surface.

Provides a first-class whoami adopter computed from git + filesystem state,
with zero MCP dependency. The coordinator's orientation spine routes through
this adopter rather than the project-rag plugin adopter.

Public surface:
    compose_envelope() — returns a v1-conformant whoami envelope (live probe).

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C2
"""
from coordinator_whoami.session.envelope import compose_envelope

__all__ = ["compose_envelope"]
