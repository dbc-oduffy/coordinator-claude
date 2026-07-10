#!/usr/bin/env python3
"""provenance.py — single executable realization of ccos-3 design B's absence⟹unknown default.

This module is the ONE place raw-record consumers (ccos-4/5/6) resolve a work-item
record's provenance completeness.  Design B: if `system.provenance_completeness` is
absent (the record predates provenance capture), return 'unknown' — an honest marker,
never a fabricated value.

Spec backlink: state/handoffs/2026-06-27_095003_roadmap-ccos-3.md § Specification
  (ccos-3 — shared read-side resolver)

Negative-spec:
  - Do NOT read schema files or import schema_loader — resolves from a record dict only.
  - Do NOT invent a default value other than 'unknown' for absent/null provenance.
  - Do NOT import third-party libraries — pure stdlib only.
"""

from __future__ import annotations


def get_provenance_completeness(record: dict) -> str:
    """Resolve a work-item record's provenance completeness.

    Returns 'complete' or 'unknown'.

    Design-B default: a record with no `system` block, or a `system` block
    lacking `provenance_completeness`, resolves to 'unknown' (provenance was
    never captured — honest marker, not fabricated).  Returns the stored value
    when `system.provenance_completeness` is present.

    Args:
        record: A work-item record dict (e.g. loaded from a frontmatter YAML file).

    Returns:
        The stored provenance_completeness string, or 'unknown' when absent/null.
    """
    system = record.get("system")
    if not isinstance(system, dict):
        return "unknown"
    value = system.get("provenance_completeness")
    if not value:  # None, empty string, or other falsy (0, False, []) — all treated as absent/unknown
        return "unknown"
    return str(value)
