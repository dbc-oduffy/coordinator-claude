"""coordinator-artifact-subject.py — artifact subject-matter classifier.

Purpose: given the path of a coordinator working-data artifact, classifies
its SUBJECT MATTER and prints exactly one of: engine, doctrine, or
cross-cutting to stdout. The discriminator is what the artifact is ABOUT,
not where it physically lives on disk. Subject-matter is the routing key
used by coordinator_state_root to place doctrine artifacts in the DoE plane
and engine artifacts in the engine-repo plane.

Spec backlinks:
  docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.2
  docs/wiki/state-placement-law.md § Plan Homes

Classification contract (from state-placement-law.md § Plan Homes and
§ Residency Is Not Ownership):

  engine       — artifact is ABOUT engine internals: coordinator_core/**,
                 pcore roadmap, claude-klabauter's own install-chain node (NOT the
                 coordinator install skill), MCP/resident-service research,
                 memos addressed TO claude-klabauter. Exit 0.

  doctrine     — artifact is ABOUT coordinator doctrine: skills, hooks,
                 agents, ceremonies, coordinator plugin source
                 (plugins/coordinator/**), meta-repo
                 doctrine surfaces (CLAUDE.md, CLAUDE.local.md,
                 docs/decisions/, docs/wiki/), coordinator install skill /
                 commands/install.md. Default class for everything else
                 coordinator. Exit 0.

  cross-cutting — artifact genuinely spans BOTH planes; requires an explicit
                 human routing decision. detect-then-fail-loud contract:
                 prints 'cross-cutting' to stdout AND emits a remediation
                 message to stderr. Exit 2 (distinct from usage error = 1).
                 Never silently auto-routes a cross-cutting artifact.

Install-chain disambiguation (required by spec):
  claude-klabauter's own install script                        → engine
  coordinator install skill / commands/install.md   → doctrine
  Discriminator: whose install it is (subject), not the shared word "install".

Consumer contract (W2.3 coordinator_state_root):
  - stdout: a single token parseable by the caller.
  - exit code: 0 = confident (engine | doctrine); 2 = cross-cutting.
  - stderr: diagnostics only — never parsed by the consumer.

Port of: coordinator-artifact-subject.sh (DoE 6fb5fb37, 2026-07-22). This
port preserves the exact CLI contract (args, exit codes, stdout/stderr
shape) so callers repoint without behavior change.
"""

from __future__ import annotations

import sys
from fnmatch import fnmatchcase
from typing import Tuple

USAGE_MESSAGE = (
    "coordinator_artifact_subject: usage: "
    "coordinator_artifact_subject <artifact-path>"
)


def _matches_any(path: str, patterns: list) -> bool:
    """Case-shell-glob match against any of `patterns` (bash `case` semantics)."""
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def _is_cross_cutting(path: str) -> bool:
    """Returns True if the path matches a known cross-cutting pattern.

    Named cross-cutting examples from the plan (W2.2 spec):
      DR-207-shaped artifact  — a DR spanning both doctrine and engine planes.
      fleet-spine emitter-binding plan — defines coordinator spine AND engine
                                         emit operations; neither plane solely owns it.

    Negative-spec: this function does NOT attempt to detect all possible
    cross-cutting artifacts — that is undecidable from path alone. It catches
    the explicitly-named patterns from the plan. Truly undecidable paths that
    match none of the patterns fall through to the engine/doctrine heuristics
    (acceptable; the named patterns are the fail-loud surface for known cases).
    """
    return _matches_any(
        path,
        [
            "*DR-207*",
            "*dr-207*",
            "*fleet-spine*emitter*",
            # Review: code-reviewer F8 — standalone *emitter-binding* covers any
            # artifact whose name signals a spine/emit straddle that doesn't
            # carry the fleet-spine prefix (e.g. a future
            # cockpit-emitter-binding plan). The fleet-spine pattern above
            # catches the primary known instance; this is the catch-all.
            "*emitter-binding*",
        ],
    )


def _is_engine(path: str) -> bool:
    """Returns True if the path signals engine-subject matter.

    NOTE: The install-chain disambiguation (commands/install.md → doctrine)
    runs BEFORE this check in coordinator_artifact_subject, so the
    `*install*` pattern here safely catches only claude-klabauter's own install
    artefacts.
    """
    return _matches_any(
        path,
        [
            # coordinator_core/** — most explicit engine-internal signal
            "*coordinator_core*",
            # pcore roadmap (claude-klabauter runtime core, pre-engine)
            "*pcore*",
            # Claude-Klabauter's own install-chain node (NOT coordinator install skill —
            # that case is pre-empted in coordinator_artifact_subject before
            # this call)
            "*claude-klabauter*install*",
            "*claude-klabauter-install*",
            # MCP server / resident-service research (engine-plane infra).
            # Review: code-reviewer F1 — *mcp-server* was too broad:
            # coordinator doctrine paths (e.g.
            # docs/wiki/mcp-server-configuration.md) would misclassify as
            # engine. Pattern narrowed to research/ and plans/ dirs only;
            # coordinator-plugin and wiki paths are pre-empted to doctrine
            # in Phase 2 before this function fires. Discriminator: is the
            # artifact ABOUT the engine's MCP infra?
            "*resident-service*",
            "*docs/research*mcp-server*",
            "*docs/research*mcp_server*",
            "*docs/plans*mcp-server*",
            "*docs/plans*mcp_server*",
            # Memo addressed TO claude-klabauter (claude-klabauter-addressed memo → engine)
            "*to-claude-klabauter*",
            "*to-claude-klabauter*",
        ],
    )


def coordinator_artifact_subject(path: str) -> Tuple[str, str, int]:
    """Classifies the subject matter of a coordinator working-data artifact.

    Returns a (stdout, stderr, returncode) tuple:
      returncode 0 — confident classification (engine or doctrine)
      returncode 1 — usage error (empty artifact path)
      returncode 2 — cross-cutting ambiguity detected; human routing
                     decision required. stdout: cross-cutting.
                     stderr: remediation message naming the artifact and
                     required action.
    """
    if not path:
        return "", USAGE_MESSAGE + "\n", 1

    # Phase 1: Cross-cutting check.
    # Must run BEFORE engine/doctrine so genuinely ambiguous artifacts surface
    # for human routing rather than silently auto-routing to one plane.
    # This is the detect-then-fail-loud-on-ambiguity contract.
    if _is_cross_cutting(path):
        stderr_lines = [
            f"coordinator_artifact_subject: cross-cutting artifact detected — '{path}'",
            "  This artifact spans both doctrine and engine planes. It cannot be",
            "  auto-routed and requires an explicit human routing decision.",
            "  Action: identify which plane OWNS the changed contract or doctrine",
            "  surface and route the artifact manually to that plane.",
            "  Reference: docs/wiki/state-placement-law.md § Plan Homes",
            "             (cross-cutting plans paragraph)",
            "  Spec: docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.2",
        ]
        return "cross-cutting", "\n".join(stderr_lines) + "\n", 2

    # Phase 2: Install-chain disambiguation + coordinator-doctrine pre-emption.
    # Fires BEFORE the engine _is_engine check so coordinator-plugin paths
    # that happen to contain "install", "mcp-server", etc. do not accidentally
    # match engine patterns.
    #
    # Review: code-reviewer F1 — coordinator-plugin and wiki mcp-server paths
    # are pre-empted here so the narrowed engine MCP pattern in _is_engine
    # (scoped to docs/research and docs/plans) never fires for coordinator
    # doctrine surfaces.
    if _matches_any(path, ["*commands/install*", "*skills/repo-setup*"]):
        return "doctrine", "", 0

    # Coordinator-plugin paths containing "mcp-server" → doctrine (coordinator
    # MCP config/wiki artifacts, NOT engine MCP infrastructure research).
    if _matches_any(
        path,
        [
            "*plugins/coordinator-claude*mcp-server*",
            "*plugins/coordinator-claude*mcp_server*",
            "*docs/wiki*mcp-server*",
            "*docs/wiki*mcp_server*",
            "*commands*mcp-server*",
            "*commands*mcp_server*",
        ],
    ):
        return "doctrine", "", 0

    # Phase 3: Engine subject-matter check.
    if _is_engine(path):
        return "engine", "", 0

    # Phase 4: Doctrine (default).
    # Everything not matched above is doctrine — coordinator doctrine is the
    # default class for all coordinator-plane artifacts (skills, hooks,
    # agents, ceremonies, plugin source, meta-repo doctrine surfaces,
    # CLAUDE.md, wikis, decisions, plans about coordinator internals, etc.).
    return "doctrine", "", 0


def main(argv: list) -> int:
    if len(argv) < 1 or not argv[0]:
        sys.stderr.write(USAGE_MESSAGE + "\n")
        return 1

    stdout, stderr, rc = coordinator_artifact_subject(argv[0])
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
