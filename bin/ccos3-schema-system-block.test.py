"""
ccos3-schema-system-block.test.py — tests for AC1/AC2/AC3 of the ccos-3 system: provenance block.

Spec backlink: state/handoffs/2026-06-27_095003_roadmap-ccos-3.md § Specification

Validation goes through the node CLI (bin/schema-cli.js) — the sole parser after
option-(d) retirement of the Python schema_loader module.

Tests:
  AC1 (placement_guard): 'system' is in optional, NOT in required, for all three schemas.
      Required key sets are byte-identical to the hardcoded baselines below.
  AC2 (validate): records with and without a system block both pass --validate.
  AC3 (system_block_golden): the node CLI (schema.js) parses the system block with
      the expected key structure and provenance_completeness enum values.

Runnable via: python3 bin/ccos3-schema-system-block.test.py
Exit 0 = all tests pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Path to schema-cli.js — sibling of this file in bin/.
_SCHEMA_CLI = Path(__file__).resolve().parent / "schema-cli.js"

# All three schemas under test.
_SCHEMA_NAMES = ["improvement-queue", "debt-backlog", "bug-backlog"]

# Hardcoded required-key baselines — sourced from reading the schema YAML files
# on disk as of the ccos-3 authoring pass. These are the authoritative sets;
# the test asserts BYTE-IDENTICAL membership so that future accidental additions
# to required: are caught immediately.
_REQUIRED_KEYS_BASELINE: dict[str, frozenset[str]] = {
    "improvement-queue": frozenset({
        "created", "title", "body", "status", "surface",
        "proposed_action", "from_repo", "change_kind",
    }),
    "debt-backlog": frozenset({
        "created", "title", "body", "status", "source",
        "risk", "proposed_action",
    }),
    "bug-backlog": frozenset({
        "created", "title", "body", "status", "surface", "severity",
    }),
}

# Minimal valid required fields for each schema (used in AC2 validate tests).
_MINIMAL_VALID_RECORDS: dict[str, dict] = {
    "improvement-queue": {
        "created": "2026-06-27",
        "title": "Test improvement",
        "body": "Some body text",
        "status": "open",
        "surface": "bin/some-script.py",
        "proposed_action": "Refactor X",
        "from_repo": "claude-central",
        "change_kind": "script-edit",
    },
    "debt-backlog": {
        "created": "2026-06-27",
        "title": "Test debt",
        "body": "Some body text",
        "status": "open",
        "source": "code-review",
        "risk": "medium",
        "proposed_action": "Refactor Y",
    },
    "bug-backlog": {
        "created": "2026-06-27",
        "title": "Test bug",
        "body": "Some body text",
        "status": "open",
        "surface": "bin/some-script.py",
        "severity": "P2",
    },
}

# Expected system-block structure (same across all three schemas).
_EXPECTED_SYSTEM_BLOCK: dict = {
    "created_by_session": "string",
    "created_by_agent": "string",
    "linked_sessions": "list-of-string",
    "linked_commits": "list-of-string",
    "provenance_completeness": {
        "type": "enum",
        "values": ["complete", "unknown"],
    },
}

# ---------------------------------------------------------------------------
# Node CLI helpers
# ---------------------------------------------------------------------------

def _node_describe(schema_name: str) -> dict:
    """Call schema-cli.js --describe <schema_name> and return parsed JSON.

    Returns { required: [...], optional: [...], enums: {...} }.
    """
    try:
        proc = subprocess.run(
            ["node", str(_SCHEMA_CLI), "--describe", schema_name],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise AssertionError("node not found on PATH — required for schema-cli.js")

    if proc.returncode != 0:
        raise AssertionError(
            f"schema-cli.js --describe {schema_name!r} failed (exit {proc.returncode}).\n"
            f"stderr: {proc.stderr!r}"
        )

    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Could not parse --describe output as JSON: {exc}\n"
            f"stdout: {proc.stdout!r}"
        ) from exc


def _node_validate(schema_name: str, record: dict) -> tuple[bool, list[str]]:
    """Pipe record JSON to schema-cli.js --validate <schema_name> and return (ok, errors).

    Returns (True, []) on success; (False, [<error strings>]) on validation failure.
    """
    record_json = json.dumps(record)

    try:
        proc = subprocess.run(
            ["node", str(_SCHEMA_CLI), "--validate", schema_name],
            input=record_json,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise AssertionError("node not found on PATH — required for schema-cli.js")

    # Exit 2 = malformed JSON input — that's a test-authoring error, not a validation result.
    if proc.returncode == 2:
        raise AssertionError(
            f"schema-cli.js --validate {schema_name!r} got malformed input (exit 2).\n"
            f"stderr: {proc.stderr!r}"
        )

    try:
        result = json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Could not parse --validate output as JSON: {exc}\n"
            f"stdout: {proc.stdout!r}"
        ) from exc

    ok: bool = result.get("ok", False) is True
    errors: list[str] = result.get("errors", [])
    return ok, errors


# ---------------------------------------------------------------------------
# AC1: placement guard — system in optional, NOT in required
# ---------------------------------------------------------------------------

def test_ac1_placement_guard() -> None:
    """AC1: 'system' in optional and NOT in required, for all three schemas.

    Also asserts that the required key set is byte-identical to the hardcoded
    baseline so that accidental required: additions are caught immediately.
    """
    for name in _SCHEMA_NAMES:
        desc = _node_describe(name)

        optional_fields: list[str] = desc.get("optional") or []
        required_fields: list[str] = desc.get("required") or []

        # 'system' must be in optional.
        assert "system" in optional_fields, (
            f"[{name}] 'system' not found in optional section.\n"
            f"optional fields: {optional_fields}"
        )

        # 'system' must NOT be in required.
        assert "system" not in required_fields, (
            f"[{name}] 'system' was found in required section — must be optional only."
        )

        # Required key set must match the baseline exactly.
        actual_required = frozenset(required_fields)
        expected_required = _REQUIRED_KEYS_BASELINE[name]
        assert actual_required == expected_required, (
            f"[{name}] required key set does not match baseline.\n"
            f"  Actual:   {sorted(actual_required)}\n"
            f"  Expected: {sorted(expected_required)}\n"
            "If a required field was legitimately added, update _REQUIRED_KEYS_BASELINE."
        )


# ---------------------------------------------------------------------------
# AC2: validate — records with and without system block both pass
# ---------------------------------------------------------------------------

def test_ac2_validate_with_system_block() -> None:
    """AC2a: a record with a populated system block passes --validate."""
    for name in _SCHEMA_NAMES:
        record_with_system = dict(_MINIMAL_VALID_RECORDS[name])
        record_with_system["system"] = {
            "created_by_session": "ses-abc123",
            "created_by_agent": "executor",
            "linked_sessions": ["ses-abc123"],
            "linked_commits": ["abc1234"],
            "provenance_completeness": "complete",
        }

        ok, errors = _node_validate(name, record_with_system)
        assert ok, (
            f"[{name}] --validate returned false for a record WITH system block.\n"
            f"errors: {errors!r}"
        )
        assert errors == [], (
            f"[{name}] --validate returned errors for a valid record with system block.\n"
            f"errors: {errors!r}"
        )


def test_ac2_validate_without_system_block() -> None:
    """AC2b: a flat historical record (no system block) also passes --validate.

    Confirms backward-compatibility: pre-ccos3 records that have no 'system'
    key at all continue to validate without error.
    """
    for name in _SCHEMA_NAMES:
        flat_record = dict(_MINIMAL_VALID_RECORDS[name])
        # Explicitly confirm system is absent
        assert "system" not in flat_record

        ok, errors = _node_validate(name, flat_record)
        assert ok, (
            f"[{name}] --validate returned false for a flat historical record (no system block).\n"
            f"errors: {errors!r}"
        )
        assert errors == [], (
            f"[{name}] --validate returned errors for a flat historical record.\n"
            f"errors: {errors!r}"
        )


# ---------------------------------------------------------------------------
# AC3: system_block_golden — schema.js parses the system block as expected
# ---------------------------------------------------------------------------

def _node_load_system_blocks() -> dict[str, object]:
    """Invoke node to call schema.js loadSchemas and extract each schema's optional.system block.

    Returns a dict mapping schema_name -> system block dict as parsed by schema.js.
    Raises AssertionError if node is unavailable or the invocation fails.
    """
    schema_js_path = Path(__file__).resolve().parent / "lib" / "schema.js"
    schemas_dir = Path(__file__).resolve().parent.parent / "schemas"

    node_script = (
        "const s = require(" + json.dumps(str(schema_js_path)) + ");\n"
        "const schemas = s.loadSchemas(" + json.dumps(str(schemas_dir)) + ");\n"
        "const names = ['improvement-queue', 'debt-backlog', 'bug-backlog'];\n"
        "const result = {};\n"
        "for (const name of names) {\n"
        "  const schema = schemas[name];\n"
        "  if (schema && schema.optional && schema.optional.system) {\n"
        "    result[name] = schema.optional.system;\n"
        "  } else {\n"
        "    result[name] = null;\n"
        "  }\n"
        "}\n"
        "process.stdout.write(JSON.stringify(result) + '\\n');\n"
    )

    try:
        proc = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        raise AssertionError("node not found on PATH — required to load system block golden")

    if proc.returncode != 0:
        raise AssertionError(
            f"node invocation failed (exit {proc.returncode}).\n"
            f"stderr: {proc.stderr!r}\n"
            f"script:\n{node_script}"
        )

    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Could not parse node output as JSON: {exc}\n"
            f"stdout: {proc.stdout!r}"
        ) from exc


def test_ac3_system_block_golden() -> None:
    """AC3: schema.js parses the system block with the expected structure (single-parser golden).

    The dual-parser parity assertion is now void — there is only one parser (schema.js via
    node CLI). This test asserts that the node parse path produces the correct system block
    structure: expected key nesting and provenance_completeness enum values.

    Negative-spec: does NOT compare against a Python parser (schema_loader is retired).
    """
    node_blocks = _node_load_system_blocks()

    for name in _SCHEMA_NAMES:
        js_system = node_blocks.get(name)
        assert js_system is not None, (
            f"[{name}] node: optional.system is None after loadSchemas.\n"
            f"node output keys for '{name}': {list(node_blocks.keys())}"
        )

        # Assert system block key set matches expected.
        assert set(js_system.keys()) == set(_EXPECTED_SYSTEM_BLOCK.keys()), (
            f"[{name}] node: system block keys mismatch.\n"
            f"  Actual:   {sorted(js_system.keys())}\n"
            f"  Expected: {sorted(_EXPECTED_SYSTEM_BLOCK.keys())}"
        )

        # Assert provenance_completeness is an enum spec with expected values.
        js_pc = js_system.get("provenance_completeness")
        assert isinstance(js_pc, dict), (
            f"[{name}] node: provenance_completeness is not a dict: {js_pc!r}"
        )
        assert js_pc.get("type") == "enum", (
            f"[{name}] node: provenance_completeness.type != 'enum': {js_pc!r}"
        )
        assert js_pc.get("values") == ["complete", "unknown"], (
            f"[{name}] node: provenance_completeness.values mismatch.\n"
            f"  Actual:   {js_pc.get('values')!r}\n"
            f"  Expected: ['complete', 'unknown']"
        )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _run_all() -> None:
    tests = [
        test_ac1_placement_guard,
        test_ac2_validate_with_system_block,
        test_ac2_validate_without_system_block,
        test_ac3_system_block_golden,
    ]
    failed = 0
    for test_fn in tests:
        name = test_fn.__name__
        try:
            test_fn()
            print(f"  PASS  {name}")
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1

    print()
    if failed:
        print(f"FAILED: {failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"OK: {len(tests)}/{len(tests)} tests passed")


if __name__ == "__main__":
    _run_all()
