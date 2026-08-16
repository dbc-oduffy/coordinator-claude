"""coordinator_whoami.project_rag — project-rag-specific whoami subpackage.

Provides the project-rag implementation of the cross-plugin whoami contract.
Consumers invoke the CLI via ``python -m coordinator_whoami.project_rag``.

Public API surfaces (authored in Tasks 2 and 4):
- ``compose() -> dict`` — host introspection; returns CLI-output-shaped dict
- ``compose_envelope() -> dict`` — projects compose() output into contract envelope
- ``persist(envelope: dict) -> None`` — writes envelope to
  ``<settings-home>/project-rag/install-profile.json`` (DR-072)

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 1
"""

from coordinator_whoami.project_rag.cli import compose, WHOAMI_SCHEMA_VERSION
from coordinator_whoami.project_rag.envelope import compose_envelope, persist

__all__ = ["compose", "compose_envelope", "persist", "WHOAMI_SCHEMA_VERSION"]
