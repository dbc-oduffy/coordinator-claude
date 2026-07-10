#!/usr/bin/env python3
"""test_provenance.py — self-contained regression tests for the provenance resolver.

Tests:
  T1  absent system key → 'unknown'
  T2  system present but no provenance_completeness key → 'unknown'
  T3  system={'provenance_completeness':'complete'} → 'complete'
  T4  system={'provenance_completeness':'unknown'} → 'unknown'
  T5  system not a dict (e.g. None) → 'unknown'

Run: python3 bin/lib/test_provenance.py
Exit non-zero on any failure.

Spec backlink: state/handoffs/2026-06-27_095003_roadmap-ccos-3.md § Specification
  (ccos-3 — shared read-side resolver)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import the module under test from the same directory as this file.
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR))

from provenance import get_provenance_completeness  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal test runner — matches emit-lesson-summaries.test.py shape
# ---------------------------------------------------------------------------

FAIL_COUNT = 0


def fail(msg: str) -> None:
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"FAIL: {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"ok:   {msg}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    global FAIL_COUNT; FAIL_COUNT = 0  # Review: code-reviewer F5 — re-invocation resets the count
    # T1: record has no 'system' key → 'unknown'
    result = get_provenance_completeness({})
    if result == "unknown":
        ok("T1: absent system key → 'unknown'")
    else:
        fail(f"T1: expected 'unknown', got {result!r}")

    # T2: system present but no provenance_completeness key → 'unknown'
    result = get_provenance_completeness({"system": {"other_field": "value"}})
    if result == "unknown":
        ok("T2: system present without provenance_completeness → 'unknown'")
    else:
        fail(f"T2: expected 'unknown', got {result!r}")

    # T2b: system present, provenance_completeness explicitly None → 'unknown'
    result = get_provenance_completeness({"system": {"provenance_completeness": None}})
    if result == "unknown":
        ok("T2b: system present, provenance_completeness=None → 'unknown'")
    else:
        fail(f"T2b: expected 'unknown', got {result!r}")

    # T2c: system present, provenance_completeness empty string → 'unknown'
    result = get_provenance_completeness({"system": {"provenance_completeness": ""}})
    if result == "unknown":
        ok("T2c: system present, provenance_completeness='' → 'unknown'")
    else:
        fail(f"T2c: expected 'unknown', got {result!r}")

    # T3: system={'provenance_completeness':'complete'} → 'complete'
    result = get_provenance_completeness({"system": {"provenance_completeness": "complete"}})
    if result == "complete":
        ok("T3: system={'provenance_completeness':'complete'} → 'complete'")
    else:
        fail(f"T3: expected 'complete', got {result!r}")

    # T4: system={'provenance_completeness':'unknown'} → 'unknown'
    result = get_provenance_completeness({"system": {"provenance_completeness": "unknown"}})
    if result == "unknown":
        ok("T4: system={'provenance_completeness':'unknown'} → 'unknown'")
    else:
        fail(f"T4: expected 'unknown', got {result!r}")

    # T5: system not a dict (e.g. None) → 'unknown'
    result = get_provenance_completeness({"system": None})
    if result == "unknown":
        ok("T5: system=None (not a dict) → 'unknown'")
    else:
        fail(f"T5: expected 'unknown', got {result!r}")

    # T5b: system is a non-dict scalar → 'unknown'
    result = get_provenance_completeness({"system": "not-a-dict"})
    if result == "unknown":
        ok("T5b: system='not-a-dict' (non-dict scalar) → 'unknown'")
    else:
        fail(f"T5b: expected 'unknown', got {result!r}")

    # T6: unrecognized non-empty string passes through unchanged (documented contract)
    # Review: code-reviewer F4 — docstring promises "returns the stored value when present";
    # this test asserts an invalid enum value is not normalised to 'unknown'.
    result = get_provenance_completeness({"system": {"provenance_completeness": "corrupted_value"}})
    if result == "corrupted_value":
        ok("T6: system={'provenance_completeness':'corrupted_value'} → 'corrupted_value' (pass-through)")
    else:
        fail(f"T6: expected 'corrupted_value', got {result!r}")

    print()
    if FAIL_COUNT == 0:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print(f"{FAIL_COUNT} TEST(S) FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
