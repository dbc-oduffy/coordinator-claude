"""
tests/project_rag/test_envelope_conformance.py

Validates that compose() output conforms to the CLI output schema, and that
compose_envelope() output conforms to the cross-plugin contract envelope schema.

Tests that depend on Tasks 4/5 modules (envelope.py, contract.py, envelope_base.py)
are import-guarded with pytest.importorskip. They will SKIP on the current tree
(where Task 4 is not yet landed) and ACTIVATE automatically once Task 4 ships.

Choice rationale: pytest.importorskip is cleaner than module-level pytest.skip
because it signals "this module isn't here yet" rather than "this test is
permanently skipped". The skip reason documents the expected dependency.

Review: Reviewer B B-F5 — fresh_env fixture removed; canonical copy is in conftest.py.
Review: Reviewer B B-F10 — _load_cli_schema() removed; canonical copy is in conftest.py.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O26, O27)
"""
from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

import pytest

from tests.project_rag.conftest import _load_cli_schema


def _load_envelope_schema() -> dict:
    """Load the cross-plugin contract envelope schema from package data."""
    return json.loads(
        importlib.resources.files("coordinator_whoami.schemas")
        .joinpath("whoami-envelope.v1.json")
        .read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Tests that CAN run now (compose() exists)
# ---------------------------------------------------------------------------

def test_cli_output_validates_against_cli_schema(fresh_env: Path) -> None:
    """O24 / O26: compose() output must validate against cli_output.v1.json."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    schema = _load_cli_schema()

    try:
        import jsonschema
        from jsonschema import Draft202012Validator
        Draft202012Validator(schema).validate(profile)
    except ImportError:
        # Structural fallback — verify required keys present.
        for key in schema.get("required", []):
            assert key in profile, f"Required key {key!r} missing from compose() output"


def test_cli_schema_itself_is_draft_2020_12_conformant() -> None:
    """The cli_output.v1.json schema must be a valid Draft 2020-12 schema."""
    schema = _load_cli_schema()
    assert "$schema" in schema
    assert "2020-12" in schema["$schema"], (
        f"Expected Draft 2020-12 schema, got {schema['$schema']!r}"
    )
    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
    except ImportError:
        pytest.skip("jsonschema not available — structural check only")


def test_envelope_schema_itself_is_draft_2020_12_conformant() -> None:
    """The whoami-envelope.v1.json schema must be a valid Draft 2020-12 schema."""
    schema = _load_envelope_schema()
    assert "$schema" in schema
    assert "2020-12" in schema["$schema"], (
        f"Expected Draft 2020-12 schema, got {schema['$schema']!r}"
    )
    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator.check_schema(schema)
    except ImportError:
        pytest.skip("jsonschema not available — structural check only")


# ---------------------------------------------------------------------------
# Tests that depend on Task 4 (envelope.py, contract.py) — import-guarded
# ---------------------------------------------------------------------------

def test_envelope_validates_against_v1_schema(fresh_env: Path) -> None:
    """O26/O27: compose_envelope() output must validate against whoami-envelope.v1.json.

    SKIP until Task 4 lands envelope.py — pytest.importorskip will activate this
    test automatically once coordinator_whoami.project_rag.envelope is importable.
    """
    envelope_mod = pytest.importorskip(
        "coordinator_whoami.project_rag.envelope",
        reason="Task 4 (envelope.py) not yet landed — will activate post-Task-4",
    )
    compose_envelope = envelope_mod.compose_envelope

    envelope = compose_envelope()
    schema = _load_envelope_schema()

    try:
        from jsonschema import Draft202012Validator
        Draft202012Validator(schema).validate(envelope)
    except ImportError:
        # Structural fallback.
        for key in schema.get("required", []):
            assert key in envelope, f"Required envelope key {key!r} missing"


def test_contract_version_is_1() -> None:
    """contract_version field in compose_envelope() output must be 1.

    SKIP until Task 4 lands envelope.py.
    """
    envelope_mod = pytest.importorskip(
        "coordinator_whoami.project_rag.envelope",
        reason="Task 4 (envelope.py) not yet landed — will activate post-Task-4",
    )
    compose_envelope = envelope_mod.compose_envelope

    envelope = compose_envelope()
    assert envelope.get("contract_version") == 1, (
        f"contract_version must be 1, got {envelope.get('contract_version')!r}"
    )


def test_plugin_name_is_project_rag() -> None:
    """plugin_name field in compose_envelope() output must be 'project-rag'.

    SKIP until Task 4 lands envelope.py.
    """
    envelope_mod = pytest.importorskip(
        "coordinator_whoami.project_rag.envelope",
        reason="Task 4 (envelope.py) not yet landed — will activate post-Task-4",
    )
    compose_envelope = envelope_mod.compose_envelope

    envelope = compose_envelope()
    assert envelope.get("plugin_name") == "project-rag", (
        f"plugin_name must be 'project-rag', got {envelope.get('plugin_name')!r}"
    )


def test_envelope_extras_key_regex() -> None:
    """Decision § 6: extras keys with leading underscores must be accepted by the schema.

    The outer contract regex is ^[a-z_][a-z0-9_]*$ (allows leading underscore).
    This test verifies the broader regex is honoured by the schema's propertyNames
    constraint (not just the inner CLI addon regex ^[a-z][a-z0-9_]+$).

    This test validates the CONTRACT schema directly (no Task 4 import needed).
    """
    schema = _load_envelope_schema()
    extras_prop = schema.get("properties", {}).get("extras", {})
    property_names = extras_prop.get("propertyNames", {})
    pattern = property_names.get("pattern", "")

    assert pattern, (
        "extras.propertyNames must have a 'pattern' constraint in whoami-envelope.v1.json"
    )

    import re
    compiled = re.compile(pattern)

    # Leading underscore must be accepted (the broader contract regex).
    assert compiled.match("_internal"), (
        f"extras propertyNames pattern {pattern!r} must accept leading-underscore keys"
    )
    # Standard snake_case keys must be accepted.
    assert compiled.match("project_rag"), (
        f"extras propertyNames pattern {pattern!r} must accept 'project_rag'"
    )
    assert compiled.match("holodeck_control"), (
        f"extras propertyNames pattern {pattern!r} must accept 'holodeck_control'"
    )


# ---------------------------------------------------------------------------
# Binding-kind correctness (Finding 1 — 2026-05-21 session-end code review)
# ---------------------------------------------------------------------------

def test_binding_unbound_when_no_registered_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """binding.kind must be 'unbound' when _resolve_bound_project_root() returns None.

    Verifies the fix for code-review Finding 1 (bf96a420): binding.kind was
    structurally always 'bound' because compose_envelope() used project.get("root")
    (cwd-detection) instead of _resolve_bound_project_root() (registry-detection).
    The "unbound" branch in /project-onboarding and /session-start could never fire.

    SKIP until Task 4 lands envelope.py.

    Patch-target note: we patch `envelope._resolve_bound_project_root` (the name
    as bound in this module via `from ... import`), NOT `cli._resolve_bound_project_root`.
    If envelope.py is ever refactored to call `cli._resolve_bound_project_root()` via
    qualified module reference, the patch target must change to `cli....` or the test
    will silently un-patch and pass against the real registry. A future dependency-injection
    refactor (compose_envelope taking a `_root_resolver` param) would simplify this.
    """
    envelope_mod = pytest.importorskip(
        "coordinator_whoami.project_rag.envelope",
        reason="Task 4 (envelope.py) not yet landed — will activate post-Task-4",
    )
    compose_envelope = envelope_mod.compose_envelope

    monkeypatch.setattr(
        "coordinator_whoami.project_rag.envelope._resolve_bound_project_root",
        lambda: None,
    )

    envelope = compose_envelope()
    assert envelope["binding"]["kind"] == "unbound", (
        f"binding.kind must be 'unbound' when no registered source covers cwd, "
        f"got {envelope['binding']['kind']!r}"
    )
    assert envelope["binding"]["target"] is None, (
        f"binding.target must be None when unbound, got {envelope['binding']['target']!r}"
    )


def test_binding_bound_when_registered_source_matches_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """binding.kind must be 'bound' and binding.target the root path when registered.

    Verifies the fix for code-review Finding 1 (bf96a420): when
    _resolve_bound_project_root() returns a Path, compose_envelope() must produce
    binding.kind='bound' and binding.target as the string representation of that path.

    SKIP until Task 4 lands envelope.py.

    Patch-target note: see sibling test test_binding_unbound_when_no_registered_source
    for the rationale on why `envelope._resolve_bound_project_root` (not `cli....`) is
    the correct monkeypatch target.
    """
    envelope_mod = pytest.importorskip(
        "coordinator_whoami.project_rag.envelope",
        reason="Task 4 (envelope.py) not yet landed — will activate post-Task-4",
    )
    compose_envelope = envelope_mod.compose_envelope

    registered_root = Path("/some/registered/root")
    monkeypatch.setattr(
        "coordinator_whoami.project_rag.envelope._resolve_bound_project_root",
        lambda: registered_root,
    )

    envelope = compose_envelope()
    assert envelope["binding"]["kind"] == "bound", (
        f"binding.kind must be 'bound' when a registered source covers cwd, "
        f"got {envelope['binding']['kind']!r}"
    )
    # str(Path(...)) is OS-native — compare against str(registered_root) to stay
    # cross-platform (Windows produces backslashes; Unix produces forward slashes).
    assert envelope["binding"]["target"] == str(registered_root), (
        f"binding.target must be the string path of the registered root, "
        f"got {envelope['binding']['target']!r}"
    )
