
from __future__ import annotations


def get_provenance_completeness(record: dict) -> str:
    system = record.get("system")
    if not isinstance(system, dict):
        return "unknown"
    value = system.get("provenance_completeness")
    if not value:
        return "unknown"
    return str(value)
