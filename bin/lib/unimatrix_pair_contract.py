"""Unimatrix pair contract: which directed links a mesh expects, and who owns a pair's mirror.

Pure functions over alias strings; no I/O.
"""
from __future__ import annotations

from typing import Iterable


def _distinct(members: Iterable[str]) -> list[str]:
    """Aliases deduplicated by casefold (first spelling kept), sorted casefolded."""
    seen: dict[str, str] = {}
    for m in members:
        seen.setdefault(m.casefold(), m)
    return [seen[k] for k in sorted(seen)]


def expected_directions(members: Iterable[str]) -> set[tuple[str, str]]:
    """Every directed (from, to) pair between distinct members; a symmetric mesh expects both directions."""
    ordered = _distinct(members)
    return {(a, b) for a in ordered for b in ordered if a != b}


def mirror_owner(a: str, b: str) -> str:
    """The alias holding the pair's single mirror: the lower by casefolded sort, order-independent.

    A casefold tie between different spellings resolves to the plain-sorted lower, so the answer is still symmetric.
    """
    return min((a, b), key=lambda s: (s.casefold(), s))
