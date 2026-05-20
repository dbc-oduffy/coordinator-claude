"""Envelope validator — wraps jsonschema.Draft202012Validator against
the package-vendored whoami-envelope.v1.json schema.
"""
import importlib.resources
import json
from jsonschema import Draft202012Validator

def load_contract_schema() -> dict:
    """Load the cross-plugin envelope schema from package data."""
    return json.loads(
        importlib.resources.files("coordinator_whoami.schemas")
        .joinpath("whoami-envelope.v1.json")
        .read_text(encoding="utf-8")
    )

def validate_envelope(envelope: dict) -> None:
    """Raise jsonschema.ValidationError on non-conforming envelope."""
    schema = load_contract_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(envelope)
