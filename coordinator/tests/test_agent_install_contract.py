"""
plugins/coordinator/tests/test_agent_install_contract.py

Validates plugins/coordinator/docs/install/agent-install-manifest.json
against the v2 agent-install contract schema and asserts required fields for the
coordinator-claude install surface.

Adapted from plugins/deep-research/tests/test_agent_install_contract.py
(DR Phase B C5 shape) with these coordinator-claude-specific adaptations:
  - COORDINATOR_ROOT resolves from tests/<file> (two parent levels) rather than
    tests/install/<file>
  - Manifest path: plugins/coordinator/docs/install/agent-install-manifest.json
    (nested working-repo layout — two extra hops up then back down)
  - Named tests that correspond exactly to the AC1 decomposition in the plan §6:
      test_manifest_valid, test_repo_id_and_empty_deps,
      test_override_flags_schema
  - coord declares NO direct deps: direct_deps == [] (coord is DAG root)
  - Contract version expected: 3 (v2→v3 cutover 2026-06-23 — system_prerequisites array)

Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §6 AC1 + AC6
Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution
#
# In the nested working-repo layout, this file lives at:
#   plugins/coordinator/tests/test_agent_install_contract.py
# COORDINATOR_ROOT is the coordinator plugin root (two parents up from this file):
#   tests/<file> → tests/ → coordinator plugin root
# The manifest lives at:
#   plugins/coordinator/docs/install/agent-install-manifest.json
# We compute COORDINATOR_ROOT as two parents up from this file so the test is
# layout-agnostic: in the flat publish-repo (X:\coordinator-claude\), the file
# lives at tests/test_agent_install_contract.py so COORDINATOR_ROOT = Path(__file__)
# .resolve().parent.parent would point at the flat repo root, where docs/install/
# also lives.
# ---------------------------------------------------------------------------

# Two parent levels: tests/<file> → tests/ → coordinator plugin root (or flat repo root)
COORDINATOR_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = COORDINATOR_ROOT / "docs" / "install" / "agent-install-manifest.json"
SCHEMA_PATH = COORDINATOR_ROOT / "docs" / "install" / "agent-install-manifest.schema.json"
AGENT_MD_PATH = COORDINATOR_ROOT / "docs" / "install" / "AGENT.md"

# Contract constants — duplicated here so tests are self-contained.
_EXPECTED_CONTRACT_VERSION = 3
_EXPECTED_REPO_ID = "coordinator-claude"
_EXPECTED_DIRECT_DEPS: list = []  # coord is DAG root — no upstream dependencies


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# AC1 (named sub-test 1 of 3): test_manifest_valid
#
# Loads the manifest, validates it against the schema (jsonschema when
# available; stdlib structural check otherwise), and asserts no missing
# required top-level fields.
# Spec: plan §6 AC1 "schema-validate"
# ---------------------------------------------------------------------------


def test_manifest_valid():
    """Loads manifest, validates against schema, asserts all required top-level fields present.

    Uses jsonschema when available (acceptable test-only dep per contract § Runtime vs test-time
    validation). Falls back to a stdlib-only structural field check so the test suite is
    runnable in environments without jsonschema installed.

    Tests are intentionally RED until C1 lands the manifest. That is the contract —
    see plan §7 C5: 'Tests will be RED on dispatch return; that's the contract.'

    Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §6 AC1
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "C1 must land before this test can be green. Tests are intentionally RED until Wave 2."
    )
    manifest = _load_manifest()
    assert isinstance(manifest, dict), (
        f"Manifest top-level must be an object; got {type(manifest).__name__}"
    )

    # Required top-level fields per contract § Schema reference
    required_top_level = [
        "agent_install_contract_version",
        "repo_id",
        "setup_skill",
        "standalone_setup_script",
        "direct_deps",
        "required_env_vars",
        "override_flags",
    ]
    missing = [f for f in required_top_level if f not in manifest]
    assert not missing, (
        f"agent-install-manifest.json is missing required top-level fields: {missing}. "
        "See plugins/coordinator/docs/wiki/agent-install-contract.md § Schema reference."
    )

    # Review: code-reviewer F9 — use pytest.importorskip for cleaner conditional-dep pattern.
    # jsonschema is a required test-only dep; absent = skip (stdlib structural check above still ran).
    jsonschema = pytest.importorskip(
        "jsonschema",
        reason="jsonschema not installed — install with: pip install jsonschema",
    )

    assert SCHEMA_PATH.exists(), (
        f"agent-install-manifest.schema.json not found at {SCHEMA_PATH}. "
        "Schema file must be present alongside the manifest (C1 in-scope expansion per PM disposition)."
    )
    schema = _load_schema()
    # Raises jsonschema.ValidationError on constraint violation.
    jsonschema.validate(instance=manifest, schema=schema)


# ---------------------------------------------------------------------------
# AC1 (named sub-test 2 of 3): test_repo_id_and_empty_deps
#
# Loads manifest, asserts repo_id == "coordinator-claude" AND direct_deps == [].
# Coord is the DAG root (chain step 5 of 5 — no upstream dependencies).
# Spec: plan §6 AC1 "field-by-field — repo_id + direct_deps"
# ---------------------------------------------------------------------------


def test_repo_id_and_empty_deps():
    """repo_id == 'coordinator-claude' and direct_deps == [] (DAG root, no upstream deps).

    Coordinator-claude is DAG root (chain step 5 of 5). It declares no direct
    dependencies. This assertion is decoupled from JSON serialisation order.

    Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §6 AC1
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § DirectDep fields
    Predecessor §7.4: coord direct_deps: [] is structural (DAG root).
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "C1 must land before this test can be green. Tests are intentionally RED until Wave 2."
    )
    manifest = _load_manifest()

    assert manifest.get("repo_id") == _EXPECTED_REPO_ID, (
        f"repo_id expected {_EXPECTED_REPO_ID!r}; got {manifest.get('repo_id')!r}. "
        "repo_id must match the GitHub repository name (coordinator-claude)."
    )

    deps = manifest.get("direct_deps", "MISSING")
    assert deps != "MISSING", (
        "direct_deps key is absent from manifest. Required field per contract § Schema reference."
    )
    assert isinstance(deps, list), (
        f"direct_deps must be an array; got {type(deps).__name__}. "
        "Contract v2 schema: direct_deps is an array (empty array valid for DAG root)."
    )
    assert deps == _EXPECTED_DIRECT_DEPS, (
        f"direct_deps expected {_EXPECTED_DIRECT_DEPS!r} (empty — coord is DAG root, chain step 5 of 5); "
        f"got {deps!r}. "
        "Predecessor §7.4 structural decision: coordinator-claude declares direct_deps: []."
    )


# ---------------------------------------------------------------------------
# AC1 (named sub-test 3 of 3): test_override_flags_schema
#
# Asserts override_flags has both schema-canonical keys:
#   skip_dep_check, accept_hallucination_risk
# And that their values are the contract-locked CLI flag strings.
# Spec: plan §6 AC1 "field-by-field — override_flags"
# ---------------------------------------------------------------------------


def test_override_flags_schema():
    """override_flags has both schema-canonical keys with correct CLI flag values.

    Contract note: the KEY is schema-canonical (skip_dep_check, accept_hallucination_risk);
    the VALUE is the CLI flag string the setup scripts accept (--skip-dep-check,
    --accept-missing-deps-risk). This is the same convention used in DR Phase B.

    Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §6 AC1
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § Schema reference
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    flags = manifest.get("override_flags", {})

    assert "skip_dep_check" in flags, (
        "override_flags.skip_dep_check is required (contract § Schema reference). "
        "Note: the KEY is schema-canonical; the VALUE is the CLI flag string."
    )
    assert flags["skip_dep_check"] == "--skip-dep-check", (
        f"override_flags.skip_dep_check value expected '--skip-dep-check'; "
        f"got {flags['skip_dep_check']!r}. "
        "Per predecessor §7.2: --skip-dep-check is the contract-locked CLI flag."
    )

    assert "accept_hallucination_risk" in flags, (
        "override_flags.accept_hallucination_risk is required (contract § Schema reference). "
        "Per the Staff Engineer Finding 1: key is accept_hallucination_risk (schema-canonical); "
        "value is --accept-missing-deps-risk (predecessor §7.2 vestigial-path naming)."
    )
    assert flags["accept_hallucination_risk"] == "--accept-missing-deps-risk", (
        f"override_flags.accept_hallucination_risk value expected '--accept-missing-deps-risk'; "
        f"got {flags['accept_hallucination_risk']!r}. "
        "Per predecessor §7.2 PM-ratified naming (accept_hallucination_risk key, --accept-missing-deps-risk value)."
    )


# ---------------------------------------------------------------------------
# Supporting structural tests (AC6: schema + contract version)
# ---------------------------------------------------------------------------


def test_manifest_contract_version():
    """agent_install_contract_version is 3 (current contract version for coord).

    Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §5.2
    Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md C6/C7
    PM disposition 2026-06-23: coord flips to v3 in the fleet-wide simultaneous-merge cutover
    (system_prerequisites array added; all consumer readers widened to {1,2,3} in the same
    merge wave, so no reader-widen-first round-trip is needed — the synchronized merge closes
    the deployment-skew window structurally).
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    version = manifest.get("agent_install_contract_version")
    assert version == _EXPECTED_CONTRACT_VERSION, (
        f"agent_install_contract_version expected {_EXPECTED_CONTRACT_VERSION}; got {version!r}. "
        "Per 2026-06-23 cutover: coord ships at v3 (system_prerequisites)."
    )


def test_schema_mirror_exists():
    """Schema mirror exists at coordinator/docs/install/agent-install-manifest.schema.json.

    AC6: schema mirror at coord canonical is present. Byte-identity against the contract-
    canonical source is verified separately by test_publish_propagation.sh.

    Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §6 AC6
    PM disposition 2026-06-15: MIRROR schema under coord tree (symmetric with DR Phase B C1).
    """
    assert SCHEMA_PATH.exists(), (
        f"agent-install-manifest.schema.json not found at {SCHEMA_PATH}. "
        "C1 (in-scope expansion per PM disposition) must land this file. "
        "Tests are intentionally RED until Wave 2."
    )
    schema = _load_schema()
    assert isinstance(schema, dict), (
        f"Schema top-level must be an object; got {type(schema).__name__}"
    )
    # Minimal structural check: JSON Schema v7 draft has $schema property
    # (or similar); the agent-install-manifest schema must have a title or
    # $schema entry at minimum.
    assert "$schema" in schema or "title" in schema, (
        f"Schema appears malformed — neither '$schema' nor 'title' key present. Schema keys: {list(schema.keys())}"
    )


def test_setup_skill_field():
    """setup_skill declares '/coordinator:setup' (the chain-walker skill).

    Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C1 verbatim manifest
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    assert manifest.get("setup_skill") == "/coordinator:setup", (
        f"setup_skill expected '/coordinator:setup'; got {manifest.get('setup_skill')!r}. "
        "Per plan §7 C1 verbatim manifest content."
    )


def test_doctor_skill_optional_and_not_native_collision():
    """doctor_skill is OPTIONAL — coordinator declares none (its health surface is /coordinator:code-health).

    Reverses the earlier C1/C4b shape (doctor_skill required → stub skill at skills/doctor/SKILL.md).
    The field is informational and unread by the chain-walker, so requiring it forced a do-nothing
    stub whose bare name collided with Claude Code's native /doctor. The contract now omits it for
    repos with no health-check flow. If a repo DOES declare one, it must not be the bare name `doctor`.

    Spec backlink: docs/wiki/agent-install-contract.md § Schema reference (doctor_skill OPTIONAL).
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    doctor = manifest.get("doctor_skill")
    assert doctor is None, (
        f"coordinator declares no doctor_skill (optional field; health surface is /coordinator:code-health); "
        f"got {doctor!r}."
    )
    # Forward guard: if a future health command is added, it must not re-introduce the native /doctor
    # collision. Conditional so it bites a real value rather than being vacuously true under `is None`.
    if doctor is not None:
        assert doctor != "/coordinator:doctor", (
            "doctor_skill must not be '/coordinator:doctor' — bare /doctor collides with Claude Code's native command."
        )


def test_system_prerequisites_present_and_well_formed():
    """system_prerequisites is present, non-empty, and each entry has required v3 fields.

    v3 defining payload: top-level system_prerequisites array. Each entry must have:
      - id (string)
      - tier (string)
      - probe (dict containing at least 'cmd')
      - install (dict containing at least 'mode')

    Structural check only — full jsonschema validation is handled by
    tests/install/test_system_prereq_schema.sh.

    Spec backlink: docs/plans/2026-06-23-coordinator-root-system-prerequisites.md C6/C7
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § SystemPrereq fields
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()

    assert "system_prerequisites" in manifest, (
        "system_prerequisites key is absent from the v3 manifest. "
        "v3 defining payload requires this top-level array (may be empty array but must be present). "
        "See docs/wiki/agent-install-contract.md § SystemPrereq fields."
    )
    prereqs = manifest["system_prerequisites"]
    assert isinstance(prereqs, list), (
        f"system_prerequisites must be an array; got {type(prereqs).__name__}."
    )
    assert len(prereqs) > 0, (
        "system_prerequisites must be non-empty for coordinator-claude (declares python, gh, node, git, clone_auth). "
        "See docs/plans/2026-06-23-coordinator-root-system-prerequisites.md."
    )
    for i, entry in enumerate(prereqs):
        assert isinstance(entry, dict), (
            f"system_prerequisites[{i}] must be an object; got {type(entry).__name__}."
        )
        assert "id" in entry, (
            f"system_prerequisites[{i}] missing required field 'id'. "
            "See docs/wiki/agent-install-contract.md § SystemPrereq fields."
        )
        assert "tier" in entry, (
            f"system_prerequisites[{i}] (id={entry.get('id')!r}) missing required field 'tier'."
        )
        assert "probe" in entry, (
            f"system_prerequisites[{i}] (id={entry.get('id')!r}) missing required field 'probe'."
        )
        assert isinstance(entry["probe"], dict), (
            f"system_prerequisites[{i}].probe must be an object; got {type(entry['probe']).__name__}."
        )
        assert "cmd" in entry["probe"], (
            f"system_prerequisites[{i}] (id={entry.get('id')!r}) probe missing required 'cmd' field. "
            "probe.cmd is the universal portable shell command (e.g. 'command -v git')."
        )
        assert "install" in entry, (
            f"system_prerequisites[{i}] (id={entry.get('id')!r}) missing required field 'install'."
        )
        assert isinstance(entry["install"], dict), (
            f"system_prerequisites[{i}].install must be an object; got {type(entry['install']).__name__}."
        )
        assert "mode" in entry["install"], (
            f"system_prerequisites[{i}] (id={entry.get('id')!r}) install missing required 'mode' field."
        )


def test_provider_capabilities_declared():
    """provider_capabilities is declared with the correct role and hoistable_at_step_zero values.

    coordinator-claude is the DAG root (upstream-provider). All four sub-fields are
    required when provider_capabilities is present (per contract § provider_capabilities
    and schema `required` enforcement). Asserts:
      - provider_capabilities key is present
      - role == "upstream-provider"
      - hoistable_at_step_zero is True

    Spec backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § AC12
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § provider_capabilities
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()

    assert "provider_capabilities" in manifest, (
        "provider_capabilities key is absent from the coordinator-claude manifest. "
        "coordinator-claude is the DAG root and must declare provider_capabilities. "
        "See docs/wiki/agent-install-contract.md § provider_capabilities."
    )
    pc = manifest["provider_capabilities"]
    assert isinstance(pc, dict), (
        f"provider_capabilities must be an object; got {type(pc).__name__}."
    )
    assert pc.get("role") == "upstream-provider", (
        f"provider_capabilities.role expected 'upstream-provider'; got {pc.get('role')!r}. "
        "coordinator-claude is the DAG root — its role enum value is 'upstream-provider'."
    )
    assert pc.get("hoistable_at_step_zero") is True, (
        f"provider_capabilities.hoistable_at_step_zero expected True; got {pc.get('hoistable_at_step_zero')!r}. "
        "coordinator-claude's setup may be hoisted to Step Zero by the chain-walker."
    )


def test_doctor_skill_when_present_is_pattern_constrained():
    """The retained (optional) doctor_skill property still constrains values when a repo declares one.

    The field is optional, but the schema KEEPS the property definition so a repo with a genuine health
    command (e.g. holodeck) can declare one informationally. This pins that the pattern still validates a
    well-formed slash-command and rejects a malformed one.

    Note the bare-`/doctor` collision rule is a coordinator TEST convention, not a schema constraint:
    `/doctor` is itself a well-formed slash-command per the pattern, so the schema cannot reject it. The
    collision guard lives in test_doctor_skill_optional_and_not_native_collision above.

    Spec backlink: docs/wiki/agent-install-contract.md § Schema reference (doctor_skill OPTIONAL).
    Addresses the Staff Engineer 2026-06-17 finding 0 (positive-validation path for the retained optional property).
    """
    jsonschema = pytest.importorskip(
        "jsonschema", reason="jsonschema not installed — install with: pip install jsonschema"
    )
    assert SCHEMA_PATH.exists(), f"schema not found at {SCHEMA_PATH}"
    schema = _load_schema()
    base = _load_manifest()

    # A well-formed, non-colliding health command validates against the optional property.
    jsonschema.validate(instance=dict(base, doctor_skill="/coordinator:code-health"), schema=schema)

    # Malformed values are rejected by the pattern (missing leading slash; uppercase).
    for bad in ("doctor", "coordinator:health", "/Doctor", "/coordinator:Health"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=dict(base, doctor_skill=bad), schema=schema)
