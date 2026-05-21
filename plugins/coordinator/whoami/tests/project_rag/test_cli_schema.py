"""
tests/project_rag/test_cli_schema.py

JSON-schema validation of `coordinator_whoami.project_rag.cli.compose()` output
against the migrated `coordinator_whoami/project_rag/schemas/cli_output.v1.json`.

Migrated from X:/project-rag/tests/install/test_whoami_schema.py (290 lines).
Import paths updated from `core.whoami` to `coordinator_whoami.project_rag.cli`.
Schema path updated to load via importlib.resources from the package.
Three new assertion blocks added for O32/O33/O34 (source, engine_version,
project_kind keys).

Uses `jsonschema` when available; falls back to a structural hand-rolled
validator so the test is runnable in a lean install without jsonschema.

Review: Reviewer B B-F5 — fresh_env fixture removed; canonical copy is in conftest.py.
Review: Reviewer B B-F10 — _load_cli_schema() removed; canonical copy is in conftest.py.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6
Origin: docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at X:/project-rag
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.project_rag.conftest import _load_cli_schema


@pytest.fixture(scope="session")
def whoami_schema() -> dict:
    """Load and return the parsed whoami CLI output JSON schema."""
    return _load_cli_schema()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_with_jsonschema(instance: dict, schema: dict) -> None:
    """Validate `instance` against `schema` using the jsonschema library."""
    import jsonschema  # type: ignore[import]
    jsonschema.validate(instance=instance, schema=schema)


def _validate_structural(instance: dict, schema: dict) -> None:
    """Minimal structural validator for envs where jsonschema is unavailable.

    Checks:
    - Required top-level keys are present.
    - `schema_version` is an integer equal to 1.
    - `captured_at` is a string starting with the ISO 8601 date prefix.
    - `addons` is a dict.
    - All required sub-object keys are present.

    This validator is intentionally lightweight — it exists only as a fallback
    so the test does not become a hard jsonschema dependency.
    """
    required = schema.get("required", [])
    for key in required:
        assert key in instance, (
            f"Schema-required top-level key {key!r} missing from compose() output"
        )

    # schema_version: integer, const=1
    assert isinstance(instance.get("schema_version"), int), (
        "schema_version must be int"
    )
    assert instance["schema_version"] == 1, (
        f"schema_version must be 1, got {instance['schema_version']!r}"
    )

    # captured_at: string, must look ISO 8601-ish
    captured_at = instance.get("captured_at", "")
    assert isinstance(captured_at, str), "captured_at must be str"
    assert len(captured_at) >= 19 and "T" in captured_at, (
        f"captured_at does not look like ISO 8601: {captured_at!r}"
    )

    # addons: object
    assert isinstance(instance.get("addons"), dict), "addons must be a dict"

    # Sub-object required-key checks
    sub_required = {
        "os": ["name", "version", "shell"],
        "arch": ["machine", "apple_silicon"],
        "gpu": ["present"],
        "python": ["invoking_version", "invoking_path", "ms_store_shim", "venv_present"],
        "uv": ["present"],
        "claude": ["json_present", "project_rag_entry"],
        "coordinator": ["installed"],
        "project": ["root", "kinds_detected", "uproject_present"],
        "project_rag_state": ["data_dir_present"],
    }
    for block_name, keys in sub_required.items():
        block = instance.get(block_name)
        assert isinstance(block, dict), f"{block_name!r} must be a dict"
        for k in keys:
            assert k in block, (
                f"{block_name!r} block missing required key {k!r}"
            )


def validate(instance: dict, schema: dict) -> None:
    """Validate with jsonschema if available; fall back to structural check."""
    try:
        _validate_with_jsonschema(instance, schema)
    except ImportError:
        _validate_structural(instance, schema)


# ---------------------------------------------------------------------------
# Tests — original schema coverage (migrated from project-rag)
# ---------------------------------------------------------------------------

def test_schema_file_exists_and_is_valid_json() -> None:
    """cli_output.v1.json must exist as a package resource and be valid JSON with a $schema key."""
    schema = _load_cli_schema()
    assert isinstance(schema, dict), "cli_output.v1.json must be a JSON object"
    assert "$schema" in schema, "cli_output.v1.json must have a '$schema' key"
    assert "required" in schema, "cli_output.v1.json must declare 'required' keys"


def test_compose_output_validates_against_schema(
    fresh_env: Path, whoami_schema: dict
) -> None:
    """compose() output on a fresh machine must validate against cli_output.v1.json."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    validate(profile, whoami_schema)


def test_schema_requires_original_12_top_level_keys(whoami_schema: dict) -> None:
    """The schema must declare the original 12 expected top-level keys as required."""
    original_12 = {
        "schema_version",
        "captured_at",
        "os",
        "arch",
        "gpu",
        "python",
        "uv",
        "claude",
        "coordinator",
        "project",
        "project_rag_state",
        "addons",
    }
    declared_required = set(whoami_schema.get("required", []))
    missing = original_12 - declared_required
    assert not missing, (
        f"cli_output.v1.json 'required' array is missing original keys: {sorted(missing)}"
    )


def test_schema_addons_key_allows_empty_object(
    fresh_env: Path, whoami_schema: dict
) -> None:
    """An empty addons dict must validate (fresh machine has no addons)."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert isinstance(profile["addons"], dict)
    validate(profile, whoami_schema)


def test_probe_error_shape_validates(whoami_schema: dict) -> None:
    """A synthetic probe_error sub-block under addons must be a valid dict per schema."""
    sample = {
        "schema_version": 1,
        "captured_at": "2026-05-19T12:00:00+00:00",
        "os": {"name": "Linux", "version": "5.15", "shell": "/bin/bash"},
        "arch": {"machine": "x86_64", "apple_silicon": False},
        "gpu": {"present": False, "vendor": None, "vram_free_mib": None, "cuda_driver": None},
        "python": {
            "invoking_version": "3.12.0",
            "invoking_path": "/usr/bin/python3",
            "ms_store_shim": False,
            "venv_present": False,
            "venv_python": None,
        },
        "uv": {"present": False, "version": None},
        "claude": {"json_present": False, "project_rag_entry": "no_file"},
        "coordinator": {"installed": False, "version": None},
        "project": {"root": "/tmp", "kinds_detected": [], "uproject_present": False},
        "project_rag_state": {
            "data_dir_present": False,
            "schema_version": None,
            "chroma_collection_present": None,
        },
        "addons": {
            "ue": {"probe_error": "RuntimeError: something failed", "schema_version": None}
        },
        "source": None,
        "engine_version": None,
        "project_kind": None,
    }
    validate(sample, whoami_schema)


def test_apple_silicon_true_validates(whoami_schema: dict) -> None:
    """A whoami output with apple_silicon=true must validate (macOS arm64 machine)."""
    sample = {
        "schema_version": 1,
        "captured_at": "2026-05-19T12:00:00+00:00",
        "os": {"name": "macOS", "version": "23.0.0", "shell": "/bin/zsh"},
        "arch": {"machine": "arm64", "apple_silicon": True},
        "gpu": {"present": False, "vendor": None, "vram_free_mib": None, "cuda_driver": None},
        "python": {
            "invoking_version": "3.12.0",
            "invoking_path": "/usr/bin/python3",
            "ms_store_shim": False,
            "venv_present": False,
            "venv_python": None,
        },
        "uv": {"present": False, "version": None},
        "claude": {"json_present": False, "project_rag_entry": "no_file"},
        "coordinator": {"installed": False, "version": None},
        "project": {"root": "/Users/alice/myproject", "kinds_detected": [], "uproject_present": False},
        "project_rag_state": {
            "data_dir_present": False,
            "schema_version": None,
            "chroma_collection_present": None,
        },
        "addons": {},
        "source": None,
        "engine_version": None,
        "project_kind": None,
    }
    validate(sample, whoami_schema)


def test_nvidia_gpu_present_validates(whoami_schema: dict) -> None:
    """A whoami output with a detected NVIDIA GPU must validate."""
    sample = {
        "schema_version": 1,
        "captured_at": "2026-05-19T12:00:00+00:00",
        "os": {"name": "Windows", "version": "10.0.22631", "shell": "powershell"},
        "arch": {"machine": "AMD64", "apple_silicon": False},
        "gpu": {
            "present": True,
            "vendor": "nvidia",
            "vram_free_mib": 22000,
            "cuda_driver": "13.0",
        },
        "python": {
            "invoking_version": "3.12.0",
            "invoking_path": "C:\\Python312\\python.exe",
            "ms_store_shim": False,
            "venv_present": True,
            "venv_python": "X:\\project-rag\\.venv\\Scripts\\python.exe",
        },
        "uv": {"present": True, "version": "0.4.18"},
        "claude": {"json_present": True, "project_rag_entry": "healthy"},
        "coordinator": {"installed": True, "version": None},
        "project": {"root": "X:\\project-rag", "kinds_detected": ["python"], "uproject_present": False},
        "project_rag_state": {
            "data_dir_present": True,
            "schema_version": 12,
            "chroma_collection_present": True,
        },
        "addons": {},
        "source": "project-rag",
        "engine_version": None,
        "project_kind": "python",
    }
    validate(sample, whoami_schema)


# ---------------------------------------------------------------------------
# O32/O33/O34 — new probe assertion blocks (Task 6 addition)
# ---------------------------------------------------------------------------

def test_schema_requires_source_engine_version_project_kind(whoami_schema: dict) -> None:
    """O32/O33/O34: schema must declare source, engine_version, project_kind as required."""
    declared_required = set(whoami_schema.get("required", []))
    new_keys = {"source", "engine_version", "project_kind"}
    missing = new_keys - declared_required
    assert not missing, (
        f"cli_output.v1.json 'required' array is missing new probe keys: {sorted(missing)}"
    )


def test_compose_includes_source_key(fresh_env: Path) -> None:
    """O32: compose() must include 'source' key; value is string or null on fresh machine."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert "source" in profile, "compose() output must include 'source' key"
    assert profile["source"] is None or isinstance(profile["source"], str), (
        f"source must be string or null, got {type(profile['source'])}"
    )


def test_compose_includes_engine_version_key(fresh_env: Path) -> None:
    """O33: compose() must include 'engine_version' key; null on fresh machine (no registry)."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert "engine_version" in profile, "compose() output must include 'engine_version' key"
    # On a fresh machine with no registry, must be null.
    assert profile["engine_version"] is None, (
        f"engine_version must be null on fresh machine, got {profile['engine_version']!r}"
    )


def test_compose_includes_project_kind_key(fresh_env: Path) -> None:
    """O34: compose() must include 'project_kind' key; null on fresh machine (no registry)."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert "project_kind" in profile, "compose() output must include 'project_kind' key"
    # On a fresh machine with no registry, must be null.
    assert profile["project_kind"] is None, (
        f"project_kind must be null on fresh machine, got {profile['project_kind']!r}"
    )


def test_project_kind_enum_values_validated(whoami_schema: dict) -> None:
    """O34: schema must define project_kind as enum of known values (ue, python, typescript, null)."""
    props = whoami_schema.get("properties", {})
    pk_prop = props.get("project_kind", {})
    enum_vals = pk_prop.get("enum")
    assert enum_vals is not None, "project_kind property must have an 'enum' constraint"
    expected = {"ue", "python", "typescript", None}
    actual = set(enum_vals)
    assert actual == expected, (
        f"project_kind enum mismatch. Expected {expected}, got {actual}"
    )


def test_source_is_string_or_null_in_schema(whoami_schema: dict) -> None:
    """O32: schema must define source as ["string", "null"] (Draft 2020-12 convention).

    Review: Reviewer B B-F14 — tightened from over-permissive else-branch to exact
    list assertion; Draft 2020-12 encodes nullable types as ["string", "null"] arrays,
    not as the legacy oneOf/anyOf pattern or bare string scalars.
    """
    props = whoami_schema.get("properties", {})
    source_prop = props.get("source", {})
    type_def = source_prop.get("type")
    assert type_def is not None, "source property must have a 'type' constraint"
    assert type_def == ["string", "null"], (
        f"source type must be [\"string\", \"null\"] (Draft 2020-12), got {type_def!r}"
    )


def test_engine_version_is_string_or_null_in_schema(whoami_schema: dict) -> None:
    """O33: schema must define engine_version as string|null type."""
    props = whoami_schema.get("properties", {})
    ev_prop = props.get("engine_version", {})
    type_def = ev_prop.get("type")
    assert type_def is not None, "engine_version property must have a 'type' constraint"
    if isinstance(type_def, list):
        assert "string" in type_def and "null" in type_def, (
            f"engine_version type must allow string and null, got {type_def}"
        )
    else:
        assert type_def in ("string", "null"), (
            f"engine_version type must be string or null, got {type_def!r}"
        )


def test_compose_output_with_new_probes_validates_against_schema(
    fresh_env: Path, whoami_schema: dict
) -> None:
    """O32/O33/O34: compose() with new probes must still fully validate against the schema."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    # Ensure new keys are present before validation.
    assert "source" in profile
    assert "engine_version" in profile
    assert "project_kind" in profile
    validate(profile, whoami_schema)
