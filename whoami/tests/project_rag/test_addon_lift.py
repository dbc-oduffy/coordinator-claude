"""
tests/project_rag/test_addon_lift.py

O35 coverage — addon namespace lift to first-class extras keys (R3, Decision § 6).

Tests were scaffolded in Task 6 and gated behind pytest.skip until Tasks 4 and 5
landed. Both are now shipped (commits 22c79636 and c5c3b8b2). This file activates
all four stubs.

Coverage targets:
  - R3 lift: each addon's namespace becomes extras.<ns>, NOT extras.project_rag.addons.<ns>.
  - R3 collision rule: addon namespace matching the plugin canonical key (e.g., "project_rag")
    is log+skipped, never a silent overwrite.
  - Addon-vs-addon namespace collision: first-wins-with-warning at the adapter layer
    (discover_contributors / collect_addon_blocks in addons.py).

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O35),
  Decision § 6 R3, the Director of Engineering F-Minor 3 2026-05-19
"""
from __future__ import annotations

import logging
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

from coordinator_whoami.envelope_base import build_envelope
from coordinator_whoami.project_rag.envelope import compose_envelope  # noqa: F401 — imported for integration assertions


# ---------------------------------------------------------------------------
# Internal helper — simple in-memory log capture without MemoryHandler flush quirks
# ---------------------------------------------------------------------------

class _ListHandler(logging.Handler):
    """Logging handler that accumulates records in a plain list."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _capture_logs:
    """Context manager: capture all log records from *logger_name* during the body.

    Usage::

        with _capture_logs("coordinator_whoami.envelope_base") as records:
            do_something()
        assert any("collision" in r.getMessage() for r in records)
    """

    def __init__(self, logger_name: str) -> None:
        self._logger_name = logger_name
        self._handler: _ListHandler | None = None

    def __enter__(self) -> list[logging.LogRecord]:
        self._handler = _ListHandler()
        logger = logging.getLogger(self._logger_name)
        logger.addHandler(self._handler)
        # Ensure the logger propagates nothing so records don't double-count.
        self._prev_propagate = logger.propagate
        logger.propagate = False
        # Lower effective level so WARNING records always reach the handler.
        self._prev_level = logger.level
        logger.setLevel(logging.DEBUG)
        self._logger = logger
        return self._handler.records

    def __exit__(self, *_: object) -> None:
        if self._handler is not None:
            self._logger.removeHandler(self._handler)
            self._logger.propagate = self._prev_propagate
            self._logger.setLevel(self._prev_level)


# ---------------------------------------------------------------------------
# R3 addon lift tests
# ---------------------------------------------------------------------------

def test_addon_namespace_lifts_to_first_class_extras() -> None:
    """O35: each addon's namespace must appear as extras.<ns>, NOT extras.project_rag.addons.<ns>.

    Calls build_envelope() with a single addon namespace "ue" and asserts:
      - envelope["extras"]["ue"] is present as a sibling of "project_rag"
      - "addons" is NOT a key under extras["project_rag"]
    """
    ue_payload = {"schema_version": 1, "engine_version": "5.3"}
    envelope = build_envelope(
        plugin_name="project-rag",
        extras_key="project_rag",
        plugin_version="1.0.0",
        binding={"kind": "unbound", "target": None},
        status={"state": "healthy", "since": None, "reason": None},
        plugin_extras={"envelope_version": 1},
        addon_extras={"ue": ue_payload},
    )

    extras = envelope["extras"]
    # R3 lift: "ue" is a first-class sibling of "project_rag"
    assert "ue" in extras, "addon namespace 'ue' must be lifted to extras top-level"
    assert extras["ue"] == ue_payload

    # "ue" must NOT be nested under project_rag.addons
    project_rag_block = extras.get("project_rag", {})
    assert "addons" not in project_rag_block, (
        "extras.project_rag must not contain 'addons' sub-key; R3 lifts addons to top-level"
    )


def test_addon_collision_with_plugin_canonical_key_is_skipped() -> None:
    """O35: addon namespace 'project_rag' must be skipped (collision with plugin canonical key).

    Calls build_envelope() with extras_key="project_rag" AND addon_extras={"project_rag": {...}}.
    Asserts:
      - The plugin's original payload is untouched at extras["project_rag"]
      - The rogue addon key ("rogue") does NOT appear in extras["project_rag"]
      - A warning is emitted via the coordinator_whoami.envelope_base logger (caplog optional per spec)
    """
    plugin_payload = {"envelope_version": 1, "os": "linux"}
    rogue_payload = {"rogue": "value", "foo": "bar"}

    with _capture_logs("coordinator_whoami.envelope_base") as records:
        envelope = build_envelope(
            plugin_name="project-rag",
            extras_key="project_rag",
            plugin_version="1.0.0",
            binding={"kind": "unbound", "target": None},
            status={"state": "healthy", "since": None, "reason": None},
            plugin_extras=plugin_payload,
            addon_extras={"project_rag": rogue_payload},
        )

    extras = envelope["extras"]

    # Plugin payload must be intact — the addon must not overwrite it
    assert extras["project_rag"] == plugin_payload, (
        "Plugin's own extras['project_rag'] must not be overwritten by the addon"
    )
    # Rogue key must not have leaked into the plugin block
    assert "rogue" not in extras["project_rag"], (
        "Addon's 'rogue' key must not appear in extras['project_rag']"
    )

    # At least one WARNING must have been logged about the collision
    warnings = [r for r in records if r.levelno >= logging.WARNING]
    assert warnings, "build_envelope() must log a warning when an addon collides with the plugin key"
    assert any("project_rag" in r.getMessage() for r in warnings), (
        "Warning message must name the colliding namespace 'project_rag'"
    )


def test_addon_vs_addon_namespace_collision_first_wins() -> None:
    """O35: when two addons claim the same namespace, first-registered wins with a warning.

    Uses unittest.mock to patch core.addon_discovery so that aggregate_whoami_contributors()
    returns two contributor specs both claiming namespace="ue". Asserts:
      - discover_contributors() returns exactly one spec for "ue"
      - The first contributor's spec is the winner
      - The winning spec carries a _collision_skipped marker

    The test patches _project_rag_available and core.addon_discovery directly, so it does
    NOT need the real core.addon_protocol module — the importorskip was unnecessary.

    Review: Reviewer B B-F7 — removed importorskip on core.addon_protocol; the test
    patches core.addon_discovery.aggregate_whoami_contributors and _project_rag_available,
    so it runs unconditionally without real project-rag infrastructure.

    Implementation note: the dispatch spec referenced get_addon_plugin_manager from
    core.addon_protocol; the actual addons.py (post-fix) routes through
    core.addon_discovery.aggregate_whoami_contributors. Patching that path instead.
    """
    # patch("core.addon_discovery...") below requires the project-rag `core` package to be
    # importable — mock.patch imports the target module. In the isolated whoami venv (no
    # project-rag installed) it is absent, so skip, matching the suite's importorskip
    # convention (test_envelope_conformance.py). B-F7 removed this guard on the false premise
    # that patching alone avoids the import; it does not.
    pytest.importorskip("core.addon_discovery")
    from coordinator_whoami.project_rag.addons import discover_contributors

    # Build two mock contributor specs both claiming namespace="ue"
    first_spec = MagicMock()
    first_spec.namespace = "ue"
    first_spec.__repr__ = lambda self: "<AddonSpec ue-first>"

    second_spec = MagicMock()
    second_spec.namespace = "ue"
    second_spec.__repr__ = lambda self: "<AddonSpec ue-second>"

    mock_pm = MagicMock()

    # Patch discover_addons (returns pm) and aggregate_whoami_contributors (returns flat spec list).
    # The collision-deduplication logic in discover_contributors() runs AFTER
    # aggregate_whoami_contributors returns, so return both specs to exercise the collision path.
    with patch("coordinator_whoami.project_rag.addons._project_rag_available", True), \
         patch("core.addon_discovery.discover_addons", return_value=mock_pm), \
         patch("core.addon_discovery.aggregate_whoami_contributors", return_value=[first_spec, second_spec]):
        contributors = discover_contributors()

    # Exactly one contributor for namespace "ue"
    ue_contributors = [c for c in contributors if getattr(c, "namespace", None) == "ue"]
    assert len(ue_contributors) == 1, (
        f"Expected exactly 1 contributor for namespace 'ue', got {len(ue_contributors)}"
    )

    winner = ue_contributors[0]
    # First-registered wins
    assert winner is first_spec, "first-registered contributor must win namespace collision"

    # _collision_skipped marker must be attached to the winner
    skipped = getattr(winner, "_collision_skipped", None)
    assert skipped is not None, "winner spec must carry a _collision_skipped marker"
    assert len(skipped) >= 1, "_collision_skipped must list at least one dropped contributor id"


def test_extras_structure_after_addon_lift() -> None:
    """O35: full extras structure — plugin key + addon keys as first-class siblings.

    Calls build_envelope() with:
      - plugin_extras={"foo": "bar"}
      - addon_extras={"ue": {"engine_version": "5.3"}, "rag_docs": {"doc_count": 42}}

    Asserts (R3 shape):
      - extras has exactly 3 keys: "project_rag", "ue", "rag_docs"
      - extras["project_rag"] is the plugin payload (not nested addons)
      - extras["ue"] is the ue addon payload (top-level, not under extras.project_rag.addons.ue)
      - extras["rag_docs"] is the rag-docs addon payload (also top-level)
      - "addons" is NOT a key anywhere in extras (R3 fully replaces the nested shape)
    """
    plugin_payload = {"foo": "bar"}
    ue_payload = {"engine_version": "5.3"}
    rag_docs_payload = {"doc_count": 42}

    envelope = build_envelope(
        plugin_name="project-rag",
        extras_key="project_rag",
        plugin_version="1.0.0",
        binding={"kind": "unbound", "target": None},
        status={"state": "healthy", "since": None, "reason": None},
        plugin_extras=plugin_payload,
        addon_extras={"ue": ue_payload, "rag_docs": rag_docs_payload},
    )

    extras = envelope["extras"]

    # Exactly 3 keys
    assert set(extras.keys()) == {"project_rag", "ue", "rag_docs"}, (
        f"extras must have exactly keys {{'project_rag', 'ue', 'rag_docs'}}, got {set(extras.keys())}"
    )

    # Plugin payload is intact
    assert extras["project_rag"] == plugin_payload, (
        "extras['project_rag'] must be the plugin payload"
    )

    # Addon payloads are top-level siblings, not nested under project_rag.addons
    assert extras["ue"] == ue_payload, "extras['ue'] must be the ue addon payload (top-level)"
    assert extras["rag_docs"] == rag_docs_payload, (
        "extras['rag_docs'] must be the rag-docs addon payload (top-level)"
    )

    # R3 fully replaces nested shape — "addons" must not appear anywhere in extras
    assert "addons" not in extras, (
        "extras must not contain an 'addons' sub-key after R3 lift"
    )
    assert "addons" not in extras.get("project_rag", {}), (
        "extras['project_rag'] must not contain an 'addons' sub-key after R3 lift"
    )
