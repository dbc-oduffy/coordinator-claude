"""Envelope validator — wraps jsonschema.Draft202012Validator against
the package-vendored whoami-envelope.v1.json schema.

jsonschema is declared runtime hardening (pyproject.toml), not a hard import
requirement: coordinator_whoami/__init__.py imports this module unconditionally,
so a bare/unprovisioned interpreter (no .venv — the exact fresh-machine
scenario tests/project_rag/test_cli_runs_on_fresh_machine.py simulates) must
still be able to import the package and run the CLI. validate_envelope()
degrades to a structural required-keys check when jsonschema is absent,
matching the fallback already established in
tests/project_rag/test_envelope_conformance.py.
"""
import importlib.resources
import json

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

def load_contract_schema() -> dict:
    """Load the cross-plugin envelope schema from package data."""
    return json.loads(
        importlib.resources.files("coordinator_whoami.schemas")
        .joinpath("whoami-envelope.v1.json")
        .read_text(encoding="utf-8")
    )

def validate_envelope(envelope: dict) -> None:
    """Raise on non-conforming envelope — jsonschema.ValidationError when
    jsonschema is installed, ValueError from a structural required-keys
    check when it isn't."""
    schema = load_contract_schema()
    if Draft202012Validator is None:
        missing = [key for key in schema.get("required", []) if key not in envelope]
        if missing:
            raise ValueError(f"envelope missing required keys: {missing}")
        return
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(envelope)
