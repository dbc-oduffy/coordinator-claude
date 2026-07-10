"""coordinator_whoami — cross-plugin MCP whoami package.

Generic surfaces (``validate_envelope``, ``build_envelope``) live at the
package root and are plugin-agnostic.  Per-plugin implementations live in
subpackages (e.g., ``coordinator_whoami.project_rag``).  When a second plugin
adopts this contract, author a sibling subpackage (e.g.,
``coordinator_whoami.example_game_repo_control``) reusing the generic surfaces — no
refactor needed.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 1
Contract spec: docs/wiki/cross-plugin-whoami-contract.md
"""

from coordinator_whoami.contract import validate_envelope
from coordinator_whoami.envelope_base import build_envelope

__all__ = ["validate_envelope", "build_envelope"]
