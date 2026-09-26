
from __future__ import annotations

import sys
from fnmatch import fnmatchcase
from typing import Tuple

USAGE_MESSAGE = (
    "coordinator_artifact_subject: usage: "
    "coordinator_artifact_subject <artifact-path>"
)


def _matches_any(path: str, patterns: list) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def _is_cross_cutting(path: str) -> bool:
    return _matches_any(
        path,
        [
            "*DR-207*",
            "*dr-207*",
            "*fleet-spine*emitter*",
            "*emitter-binding*",
        ],
    )


def _is_engine(path: str) -> bool:
    return _matches_any(
        path,
        [
            "*coordinator_core*",
            "*pcore*",
            "*claude-klabauter*install*",
            "*claude-klabauter-install*",
            "*resident-service*",
            "*docs/research*mcp-server*",
            "*docs/research*mcp_server*",
            "*docs/plans*mcp-server*",
            "*docs/plans*mcp_server*",
            "*to-claude-klabauter*",
            "*to-claude-klabauter*",
        ],
    )


def coordinator_artifact_subject(path: str) -> Tuple[str, str, int]:
    if not path:
        return "", USAGE_MESSAGE + "\n", 1

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

    if _matches_any(path, ["*commands/install*", "*skills/repo-setup*"]):
        return "doctrine", "", 0

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

    if _is_engine(path):
        return "engine", "", 0

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
