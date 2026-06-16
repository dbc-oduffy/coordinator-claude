"""
plugins/deep-research/tests/test_agent_install_contract.py

Validates plugins/deep-research/docs/install/agent-install-manifest.json
against the v2 agent-install contract schema and asserts required per-dep fields for the
deep-research-claude install surface.

Adapted from X:\\project-rag\\tests\\install\\test_agent_install_contract.py with these
deep-research-specific adaptations:
  - REPO_ROOT resolves from tests/<file> (two parent levels) rather than tests/install/<file>
  - Manifest path: plugins/deep-research/docs/install/agent-install-manifest.json
    (nested working-repo layout — two extra hops up then back down)
  - Named tests that correspond exactly to the AC1 decomposition in the plan §6:
      test_manifest_valid, test_direct_dep_id_and_severity,
      test_functional_probe_shape, test_consumer_install_args_empty
  - DR declares one soft dep: coordinator-claude (no hard deps)
  - Contract version expected: 2

Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §6 AC1 + AC6
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
#   plugins/deep-research/tests/test_agent_install_contract.py
# REPO_ROOT is ~/.claude (two parent levels: tests/ → deep-research/ → coordinator-claude/
# → plugins/ → ~/.claude/).
# The manifest lives at:
#   plugins/deep-research/docs/install/agent-install-manifest.json
# We compute DR_ROOT as the deep-research plugin root (two parents up from this file),
# then resolve docs/install/ from there. This keeps the test layout-agnostic: in the
# flat publish-repo, the file lives at tests/test_agent_install_contract.py so
# DR_ROOT = Path(__file__).resolve().parent.parent would point at the flat repo root,
# where docs/install/ also lives.
# ---------------------------------------------------------------------------

# Two parent levels: tests/<file> → tests/ → DR plugin root (or flat repo root)
DR_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = DR_ROOT / "docs" / "install" / "agent-install-manifest.json"
SCHEMA_PATH = DR_ROOT / "docs" / "install" / "agent-install-manifest.schema.json"
AGENT_MD_PATH = DR_ROOT / "docs" / "install" / "AGENT.md"

# Closed enums from the contract — duplicated here so tests are self-contained.
_VALID_SEVERITIES = frozenset({"hard", "soft", "optional"})
_VALID_PROBE_KINDS = frozenset({"sibling_dir_exists", "file_exists", "python_import", "command_succeeds"})

# The single direct dep declared by deep-research-claude (DR manifest §direct_deps[0])
_EXPECTED_DEP_ID = "coordinator-claude"
_EXPECTED_DEP_SEVERITY = "soft"
_EXPECTED_DEP_SIBLING_DIR_NAME = "coordinator-claude"
_EXPECTED_DEP_UPSTREAM_URL = "https://github.com/dbc-oduffy/coordinator-claude"
_EXPECTED_PROBE_KIND = "file_exists"
_EXPECTED_PROBE_PATH = "plugins/coordinator/CLAUDE.md"
_EXPECTED_CONSUMER_INSTALL_ARGS: list[str] = []
_EXPECTED_CONTRACT_VERSION = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _get_direct_deps() -> list[dict]:
    manifest = _load_manifest()
    return manifest.get("direct_deps", [])


# ---------------------------------------------------------------------------
# AC1 (named sub-test 1 of 4): test_manifest_valid
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

    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §6 AC1
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "C1 must land before this test can be green. Tests are intentionally RED until Wave 2."
    )
    manifest = _load_manifest()
    assert isinstance(manifest, dict), f"Manifest top-level must be an object; got {type(manifest).__name__}"

    # Required top-level fields per contract § Schema reference
    required_top_level = [
        "agent_install_contract_version",
        "repo_id",
        "setup_skill",
        "doctor_skill",
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

    # jsonschema validation when available
    try:
        import jsonschema  # type: ignore[import]
    except ImportError:
        pytest.skip("jsonschema not installed — install with: pip install jsonschema")
        return  # unreachable; satisfies type-checkers

    assert SCHEMA_PATH.exists(), (
        f"agent-install-manifest.schema.json not found at {SCHEMA_PATH}. "
        "Schema file must be present alongside the manifest."
    )
    schema = _load_schema()
    # Raises jsonschema.ValidationError on constraint violation.
    jsonschema.validate(instance=manifest, schema=schema)


# ---------------------------------------------------------------------------
# AC1 (named sub-test 2 of 4): test_direct_dep_id_and_severity
#
# Loads manifest, asserts direct_deps[0]["id"] == "coordinator-claude"
# AND direct_deps[0]["severity"] == "soft".
# Spec: plan §6 AC1 "field-by-field — id + severity"
# ---------------------------------------------------------------------------


def test_direct_dep_id_and_severity():
    """direct_deps[0] has id == 'coordinator-claude' and severity == 'soft'.

    DR declares exactly one direct dep: coordinator-claude at soft severity.
    This assertion is decoupled from JSON serialisation order — it inspects
    direct_deps[0] by index as declared in the manifest rather than by
    full-dict equality.

    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §6 AC1
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § DirectDep fields
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "C1 must land before this test can be green. Tests are intentionally RED until Wave 2."
    )
    manifest = _load_manifest()
    deps = manifest.get("direct_deps", [])
    assert len(deps) >= 1, (
        f"direct_deps is empty; expected at least one dep (coordinator-claude). "
        f"Manifest direct_deps: {deps!r}"
    )
    dep = deps[0]
    assert dep.get("id") == _EXPECTED_DEP_ID, (
        f"direct_deps[0]['id'] expected {_EXPECTED_DEP_ID!r}; got {dep.get('id')!r}. "
        "Per plan §7 C1 verbatim manifest content."
    )
    assert dep.get("severity") == _EXPECTED_DEP_SEVERITY, (
        f"direct_deps[0]['severity'] expected {_EXPECTED_DEP_SEVERITY!r}; "
        f"got {dep.get('severity')!r}. "
        "coordinator-claude is a soft dep of deep-research-claude (predecessor §7.3)."
    )


# ---------------------------------------------------------------------------
# AC1 (named sub-test 3 of 4): test_functional_probe_shape
#
# Asserts functional_probe.kind == "file_exists" AND the path key is
# present and points at plugins/coordinator/CLAUDE.md.
# Spec: plan §6 AC1 "field-by-field — functional_probe"
# ---------------------------------------------------------------------------


def test_functional_probe_shape():
    """direct_deps[0].functional_probe has kind='file_exists' and the correct path.

    The functional probe for coordinator-claude verifies that the coordinator's
    CLAUDE.md exists at the expected path within the sibling clone. This is
    the minimal viable functional proof that the coord plugin is wired up.

    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §6 AC1
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § FunctionalProbe fields
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "C1 must land before this test can be green. Tests are intentionally RED until Wave 2."
    )
    manifest = _load_manifest()
    deps = manifest.get("direct_deps", [])
    assert len(deps) >= 1, (
        f"direct_deps is empty; expected at least one dep. Manifest: {manifest!r}"
    )
    dep = deps[0]
    probe = dep.get("functional_probe")
    assert isinstance(probe, dict), (
        f"direct_deps[0]['functional_probe'] must be a dict; got {type(probe).__name__}"
    )
    assert probe.get("kind") == _EXPECTED_PROBE_KIND, (
        f"functional_probe.kind expected {_EXPECTED_PROBE_KIND!r}; got {probe.get('kind')!r}. "
        "Per contract § FunctionalProbe fields: file_exists requires 'path'."
    )
    assert "path" in probe, (
        f"functional_probe is missing 'path' key (required when kind='file_exists'). "
        f"Probe: {probe!r}"
    )
    assert probe.get("path") == _EXPECTED_PROBE_PATH, (
        f"functional_probe.path expected {_EXPECTED_PROBE_PATH!r}; "
        f"got {probe.get('path')!r}. "
        "Path is relative to the sibling repo root (coordinator-claude/)."
    )


# ---------------------------------------------------------------------------
# AC1 (named sub-test 4 of 4): test_consumer_install_args_empty
#
# Asserts direct_deps[0]["consumer_install_args"] == [] (v2 field).
# Spec: plan §6 AC1 "field-by-field — consumer_install_args"
# ---------------------------------------------------------------------------


def test_consumer_install_args_empty():
    """direct_deps[0]['consumer_install_args'] == [] (v2 additive field, empty for DR).

    DR has no consumer-authored install args for coordinator-claude. The field is
    declared (not omitted) to make the v2 shape explicit and to confirm the manifest
    is schema-valid under v2 (where consumer_install_args is optional but must be
    an array when present).

    Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §6 AC1
    Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md § DirectDep fields
    """
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "C1 must land before this test can be green. Tests are intentionally RED until Wave 2."
    )
    manifest = _load_manifest()
    deps = manifest.get("direct_deps", [])
    assert len(deps) >= 1, (
        f"direct_deps is empty; expected at least one dep. Manifest: {manifest!r}"
    )
    dep = deps[0]
    assert "consumer_install_args" in dep, (
        f"direct_deps[0] is missing 'consumer_install_args' key. "
        "DR manifest must declare this v2 field explicitly (even as an empty array). "
        "Per plan NG1: authoring at v2 current."
    )
    val = dep["consumer_install_args"]
    assert val == _EXPECTED_CONSUMER_INSTALL_ARGS, (
        f"direct_deps[0]['consumer_install_args'] expected {_EXPECTED_CONSUMER_INSTALL_ARGS!r}; "
        f"got {val!r}. "
        "DR has no consumer-authored install args for coordinator-claude."
    )


# ---------------------------------------------------------------------------
# Supporting structural tests (AC6: schema + contract version)
# ---------------------------------------------------------------------------


def test_manifest_contract_version():
    """agent_install_contract_version is 2 (current contract version for DR)."""
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    version = manifest.get("agent_install_contract_version")
    assert version == _EXPECTED_CONTRACT_VERSION, (
        f"agent_install_contract_version expected {_EXPECTED_CONTRACT_VERSION}; got {version!r}. "
        "Per plan NG1 + PM disposition 2026-06-15: DR ships at v2 (current)."
    )


def test_manifest_repo_id():
    """repo_id is 'deep-research-claude' (matches the GitHub repo name)."""
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    assert manifest.get("repo_id") == "deep-research-claude", (
        f"repo_id expected 'deep-research-claude'; got {manifest.get('repo_id')!r}. "
        "repo_id must match the GitHub repository name."
    )


def test_override_flags_schema_keys():
    """override_flags has both schema-canonical keys: skip_dep_check, accept_hallucination_risk."""
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
    assert "accept_hallucination_risk" in flags, (
        "override_flags.accept_hallucination_risk is required (contract § Schema reference). "
        "Per the Staff Engineer Finding 1: key is accept_hallucination_risk (schema-canonical); "
        "value is --accept-missing-deps-risk (predecessor §7.2 vestigial-path naming)."
    )


def test_dep_sibling_dir_name():
    """direct_deps[0].sibling_dir_name == 'coordinator-claude'."""
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    deps = manifest.get("direct_deps", [])
    assert len(deps) >= 1, "direct_deps is empty"
    dep = deps[0]
    assert dep.get("sibling_dir_name") == _EXPECTED_DEP_SIBLING_DIR_NAME, (
        f"direct_deps[0].sibling_dir_name expected {_EXPECTED_DEP_SIBLING_DIR_NAME!r}; "
        f"got {dep.get('sibling_dir_name')!r}"
    )


def test_dep_upstream_url():
    """direct_deps[0].upstream_url is the correct GitHub HTTPS URL for coordinator-claude."""
    assert MANIFEST_PATH.exists(), (
        f"agent-install-manifest.json not found at {MANIFEST_PATH}. "
        "Tests are intentionally RED until Wave 2 lands the manifest."
    )
    manifest = _load_manifest()
    deps = manifest.get("direct_deps", [])
    assert len(deps) >= 1, "direct_deps is empty"
    dep = deps[0]
    assert dep.get("upstream_url") == _EXPECTED_DEP_UPSTREAM_URL, (
        f"direct_deps[0].upstream_url expected {_EXPECTED_DEP_UPSTREAM_URL!r}; "
        f"got {dep.get('upstream_url')!r}"
    )
