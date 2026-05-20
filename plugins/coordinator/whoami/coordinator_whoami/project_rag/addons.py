"""Addon contributor discovery + dispatch for project-rag's whoami.

Extracted from cli.py's _collect_addon_blocks() per Task 5 of the migration plan.

Cross-package import guard (Task 5 hard constraint, per prior-art-checker Conflict #1 2026-05-19):
project-rag-side pluggy infrastructure is imported under try/except ImportError. When
project-rag is not installed (coordinator_whoami standalone install), discover_contributors()
returns [] and collect_addon_blocks() returns {} — no crash.

Addon-vs-addon collision discipline (Zolí F-Minor 3 2026-05-19):
discover_contributors() returns at most one payload per namespace. Multiple registered
contributors claiming the same namespace is a configuration error — first-wins-with-warning
+ `_collision_skipped: [<contributor source ids>]` marker on the winning payload.

R3 note (F-Minor 4 2026-05-19):
compose() retains the legacy `addons.<ns>` top-level key per O14 (input to cli_output.v1.json
validation). The R3 lift to first-class `extras.<ns>` keys happens in envelope.py (Task 4),
reading compose()['addons'] and re-keying. Task 5 does NOT change compose()'s output shape.

TODO: when project-rag ships ADDON_PROTOCOL_VERSION 9, the hookspec rename
(project_rag_register_whoami_contributor → project_rag_register_whoami_extras) lands upstream.
This adapter currently targets v14 (current). On v9 publish, update the hookspec lookup;
this comment is the load-bearing reminder.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 5
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("coordinator_whoami.project_rag.addons")

# Cross-package import guard — degrade gracefully when project-rag absent
# Review: Reviewer A A-F4 — widen guard to cover ALL three project-rag modules so
# _project_rag_available reliably reflects import-readiness of the full surface.
try:
    from core.addon_protocol import AddonWhoamiContributorSpec  # type: ignore[import-not-found]
    from core.addon_discovery import aggregate_whoami_contributors as _  # type: ignore[import-not-found] # noqa: F401
    # Use graph.schema.SCHEMA_VERSION (graph.db schema, currently 12) — not
    # core.structural_schema.SCHEMA_VERSION (authority_version sidecar, value 4).
    # Mismatch causes AddonProtocolMismatchError on addons requiring schema >= 12.
    from project_rag_mcp.graph.schema import SCHEMA_VERSION as _sv  # type: ignore[import-not-found] # noqa: F401
    del _, _sv  # imported only to validate availability; used lazily inside discover_contributors
    _project_rag_available = True
except ImportError:
    AddonWhoamiContributorSpec = None  # type: ignore[assignment,misc]
    _project_rag_available = False
    log.info("project-rag not on sys.path; addon contributor discovery returns empty list")


def discover_contributors() -> list[Any]:
    """Discover registered whoami contributors via project-rag's pluggy hookspec.

    Returns a list of contributor specs (one per registered addon, deduplicated by namespace).
    Multiple contributors claiming the same namespace: first-wins-with-warning; the dropped
    contributors are recorded under the winner's `_collision_skipped` marker (set on the
    payload at collect time, not at discovery time).

    Standalone (no project-rag): returns [].
    """
    if not _project_rag_available:
        return []

    try:
        # Lazy imports to keep module load cheap when project-rag is present but unused.
        # Use the canonical aggregation helper from core.addon_discovery — it owns
        # PluginManager construction (discover_addons) and namespace-uniqueness
        # validation (aggregate_whoami_contributors). This matches the pre-migration
        # core/whoami.py call shape and avoids reimplementing pluggy plumbing.
        # (Fixed 2026-05-19 — the original adapter imported a non-existent symbol
        # `get_addon_plugin_manager` from core.addon_protocol; project-rag's actual
        # entry point lives in core.addon_discovery.)
        from pathlib import Path
        from core.addon_discovery import aggregate_whoami_contributors, discover_addons  # type: ignore[import-not-found]
        # Use graph.schema.SCHEMA_VERSION (graph.db schema, 12) — see availability
        # guard above for why this is the correct authority for addon discovery.
        from project_rag_mcp.graph.schema import SCHEMA_VERSION  # type: ignore[import-not-found]

        pm = discover_addons(project_root=Path.cwd(), schema_version=SCHEMA_VERSION)
        contributors = aggregate_whoami_contributors(pm)

        # aggregate_whoami_contributors already enforces namespace uniqueness and
        # validates spec shape; collision handling below is belt-and-suspenders
        # against any future relaxation of that contract.
        seen_ns: dict[str, Any] = {}
        collisions: dict[str, list[str]] = {}
        for spec in contributors:
            ns = getattr(spec, "namespace", None)
            if ns is None:
                log.warning("Whoami contributor without .namespace attribute; skipping: %r", spec)
                continue
            if ns in seen_ns:
                other_id = repr(spec)
                collisions.setdefault(ns, []).append(other_id)
                log.warning(
                    "Addon namespace %r already registered by %r; ignoring later contributor %r "
                    "(first-wins-with-warning per Zolí F-Minor 3 2026-05-19)",
                    ns, seen_ns[ns], spec,
                )
                continue
            seen_ns[ns] = spec
        for ns, skipped_ids in collisions.items():
            try:
                setattr(seen_ns[ns], "_collision_skipped", skipped_ids)
            except (AttributeError, TypeError):
                log.info("Could not attach _collision_skipped marker to spec for %r: %s", ns, skipped_ids)
        return list(seen_ns.values())
    except Exception as exc:  # noqa: BLE001 — defensive boundary
        log.warning("Whoami contributor discovery failed: %s: %s", type(exc).__name__, exc)
        return []


def collect_addon_blocks() -> dict[str, Any]:
    """Run all discovered contributors' probe() and return {namespace: payload} dict.

    Per O15: contributor probe exceptions are recorded as
    {"probe_error": "<exception class>: <message>", "schema_version": None}
    and discovery continues with remaining contributors. Defensive boundary preserved.

    If a contributor was annotated with _collision_skipped during discovery, that marker is
    folded into the returned payload at this layer (so the marker survives even on probe
    failure).
    """
    contributors = discover_contributors()
    addons: dict[str, Any] = {}
    for spec in contributors:
        ns = getattr(spec, "namespace", None)
        if ns is None:
            continue
        try:
            result = spec.probe()
            if not isinstance(result, dict):
                addons[ns] = {
                    "probe_error": f"probe() returned {type(result).__name__}, expected dict",
                    "schema_version": None,
                }
            else:
                addons[ns] = result
        except Exception as exc:  # noqa: BLE001
            addons[ns] = {
                "probe_error": f"{type(exc).__name__}: {exc}",
                "schema_version": None,
            }
        # Attach collision marker if discovery noted any
        skipped = getattr(spec, "_collision_skipped", None)
        if skipped:
            addons[ns]["_collision_skipped"] = skipped
    return addons
