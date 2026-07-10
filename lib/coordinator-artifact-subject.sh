#!/usr/bin/env bash
# coordinator-artifact-subject.sh — artifact subject-matter classifier.
#
# Purpose: given the path of a coordinator working-data artifact, classifies
# its SUBJECT MATTER and prints exactly one of: engine, doctrine, or
# cross-cutting to stdout. The discriminator is what the artifact is ABOUT,
# not where it physically lives on disk. Subject-matter is the routing key
# used by coordinator_state_root to place doctrine artifacts in the DoE plane
# and engine artifacts in the example-orchestration-hub plane.
#
# Spec backlinks:
#   docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.2
#   docs/wiki/state-placement-law.md § Plan Homes
#
# Classification contract (from state-placement-law.md § Plan Homes and
# § Residency Is Not Ownership):
#
#   engine       — artifact is ABOUT engine internals: coordinator_core/**,
#                  pcore roadmap, example-orchestration-hub's own install-chain node (NOT the
#                  coordinator install skill), MCP/resident-service research,
#                  memos addressed TO example-orchestration-hub-repo. Exit 0.
#
#   doctrine     — artifact is ABOUT coordinator doctrine: skills, hooks,
#                  agents, ceremonies, coordinator plugin source
#                  (plugins/coordinator/**), meta-repo
#                  doctrine surfaces (CLAUDE.md, CLAUDE.local.md,
#                  docs/decisions/, docs/wiki/), coordinator install skill /
#                  commands/install.md. Default class for everything else
#                  coordinator. Exit 0.
#
#   cross-cutting — artifact genuinely spans BOTH planes; requires an explicit
#                  human routing decision. detect-then-fail-loud contract:
#                  prints 'cross-cutting' to stdout AND emits a remediation
#                  message to stderr. Exit 2 (distinct from usage error = 1).
#                  Never silently auto-routes a cross-cutting artifact.
#
# Install-chain disambiguation (required by spec):
#   example-orchestration-hub's own install script                        → engine
#   coordinator install skill / commands/install.md   → doctrine
#   Discriminator: whose install it is (subject), not the shared word "install".
#
# Consumer contract (W2.3 coordinator_state_root):
#   - stdout: a single token parseable via subject=$(...).
#   - exit code: 0 = confident (engine | doctrine); 2 = cross-cutting.
#   - stderr: diagnostics only — never parsed by the consumer.
#
# Cross-platform: bash ≥3.2, no GNU-isms (no sed -i, grep -P, realpath).
# Safe to source multiple times — all names prefixed coordinator_artifact_ or
# _cas_ (private) to avoid collision with caller state.
#
# NOTE: deliberately no set -e — this file is SOURCED. A file-scope errexit in
# a sourced lib propagates to the caller's shell. Functions capture exit codes
# explicitly. Mirrors coordinator-example-orchestration-hub-root.sh convention.
# NOTE: set -u and set -o pipefail (below) also propagate to any script that
# sources this lib — callers must be nounset-clean and handle pipeline exits.
set -uo pipefail

# ---------------------------------------------------------------------------
# Private: _cas_is_cross_cutting <path>
# ---------------------------------------------------------------------------
# Returns 0 if the path matches a known cross-cutting pattern; 1 otherwise.
#
# Named cross-cutting examples from the plan (W2.2 spec):
#   DR-207-shaped artifact  — a DR spanning both doctrine and engine planes.
#   fleet-spine emitter-binding plan — defines coordinator spine AND engine
#                                      emit operations; neither plane solely owns it.
#
# Negative-spec: this function does NOT attempt to detect all possible
# cross-cutting artifacts — that is undecidable from path alone. It catches
# the explicitly-named patterns from the plan. Truly undecidable paths that
# match none of the patterns fall through to the engine/doctrine heuristics
# (acceptable; the named patterns are the fail-loud surface for known cases).
_cas_is_cross_cutting() {
  local _p="$1"
  case "$_p" in
    *DR-207* | *dr-207* )          return 0 ;;  # DR-207-shaped: spans both planes
    *fleet-spine*emitter* )        return 0 ;;  # fleet-spine emitter-binding (also matches the compact fleet-spine-emitter slug)
    # Review: code-reviewer F8 — standalone *emitter-binding* covers any artifact
    # whose name signals a spine/emit straddle that doesn't carry the fleet-spine
    # prefix (e.g. a future cockpit-emitter-binding plan). The fleet-spine pattern
    # above catches the primary known instance; this is the catch-all for the class.
    *emitter-binding* )            return 0 ;;  # emitter-binding: spine+emit straddle
  esac
  return 1
}

# ---------------------------------------------------------------------------
# Private: _cas_is_engine <path>
# ---------------------------------------------------------------------------
# Returns 0 if the path signals engine-subject matter; 1 otherwise.
#
# NOTE: The install-chain disambiguation (commands/install.md → doctrine) runs
# BEFORE this function in coordinator_artifact_subject, so the `*install*`
# pattern here safely catches only example-orchestration-hub's own install artefacts.
_cas_is_engine() {
  local _p="$1"
  case "$_p" in
    # coordinator_core/** — most explicit engine-internal signal
    *coordinator_core* )                        return 0 ;;
    # pcore roadmap (example-orchestration-hub runtime core, pre-engine)
    *pcore* )                                   return 0 ;;
    # ExampleOrchestrationHub's own install-chain node (NOT coordinator install skill —
    # that case is pre-empted in coordinator_artifact_subject before this call)
    *example-orchestration-hub-repo*install* | *example-orchestration-hub-install* )
                                                return 0 ;;
    # MCP server / resident-service research (engine-plane infra).
    # Review: code-reviewer F1 — *mcp-server* was too broad: coordinator doctrine
    # paths (e.g. docs/wiki/mcp-server-configuration.md) would misclassify as
    # engine. Pattern narrowed to research/ and plans/ dirs only; coordinator-
    # plugin and wiki paths are pre-empted to doctrine in Phase 2 before this
    # function fires. Discriminator: is the artifact ABOUT the engine's MCP infra?
    *resident-service* )                        return 0 ;;
    *docs/research*mcp-server* | *docs/research*mcp_server* \
    | *docs/plans*mcp-server* | *docs/plans*mcp_server* )
                                                return 0 ;;
    # Memo addressed TO example-orchestration-hub-repo (example-orchestration-hub-addressed memo → engine)
    *to-example-orchestration-hub-repo* | *to-example-orchestration-hub* )         return 0 ;;
  esac
  return 1
}

# ---------------------------------------------------------------------------
# Public: coordinator_artifact_subject <artifact-path>
# ---------------------------------------------------------------------------
# Classifies the subject matter of a coordinator working-data artifact.
# Prints exactly one token to stdout: engine | doctrine | cross-cutting.
#
# Returns:
#   0 — confident classification (engine or doctrine)
#   1 — usage error (no argument or empty argument)
#   2 — cross-cutting ambiguity detected; human routing decision required
#         stdout: cross-cutting
#         stderr: remediation message naming the artifact and required action
coordinator_artifact_subject() {
  if [[ $# -lt 1 || -z "${1:-}" ]]; then
    echo "coordinator_artifact_subject: usage: coordinator_artifact_subject <artifact-path>" >&2
    return 1
  fi

  local _path="$1"

  # Phase 1: Cross-cutting check.
  # Must run BEFORE engine/doctrine so genuinely ambiguous artifacts surface
  # for human routing rather than silently auto-routing to one plane.
  # This is the detect-then-fail-loud-on-ambiguity contract.
  if _cas_is_cross_cutting "$_path"; then
    printf '%s' 'cross-cutting'
    {
      echo "coordinator_artifact_subject: cross-cutting artifact detected — '$_path'"
      echo "  This artifact spans both doctrine and engine planes. It cannot be"
      echo "  auto-routed and requires an explicit human routing decision."
      echo "  Action: identify which plane OWNS the changed contract or doctrine"
      echo "  surface and route the artifact manually to that plane."
      echo "  Reference: docs/wiki/state-placement-law.md § Plan Homes"
      echo "             (cross-cutting plans paragraph)"
      echo "  Spec: docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.2"
    } >&2
    return 2
  fi

  # Phase 2: Install-chain disambiguation + coordinator-doctrine pre-emption.
  # Fires BEFORE the engine _cas_is_engine check so coordinator-plugin paths
  # that happen to contain "install", "mcp-server", etc. do not accidentally
  # match engine patterns.
  #
  # Review: code-reviewer F1 — coordinator-plugin and wiki mcp-server paths are
  # pre-empted here so the narrowed engine MCP pattern in _cas_is_engine (scoped
  # to docs/research and docs/plans) never fires for coordinator doctrine surfaces.
  case "$_path" in
    *commands/install* | *skills/repo-setup* )
      printf '%s' 'doctrine'
      return 0
      ;;
    # Coordinator-plugin paths containing "mcp-server" → doctrine (coordinator
    # MCP config/wiki artifacts, NOT engine MCP infrastructure research).
    *plugins/coordinator-claude*mcp-server* | *plugins/coordinator-claude*mcp_server* \
    | *docs/wiki*mcp-server* | *docs/wiki*mcp_server* \
    | *commands*mcp-server* | *commands*mcp_server* )
      printf '%s' 'doctrine'
      return 0
      ;;
  esac

  # Phase 3: Engine subject-matter check.
  if _cas_is_engine "$_path"; then
    printf '%s' 'engine'
    return 0
  fi

  # Phase 4: Doctrine (default).
  # Everything not matched above is doctrine — coordinator doctrine is the
  # default class for all coordinator-plane artifacts (skills, hooks, agents,
  # ceremonies, plugin source, meta-repo doctrine surfaces, CLAUDE.md, wikis,
  # decisions, plans about coordinator internals, etc.).
  printf '%s' 'doctrine'
  return 0
}
