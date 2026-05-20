"""Plugin-agnostic envelope builder. Every plugin's compose_envelope() composes
this primitive with its own per-plugin extras payload + any addon-contributed
extras keys (lifted to first-class per R3, Decision § 6).
"""
from typing import Any
import logging

log = logging.getLogger("coordinator_whoami.envelope_base")


def build_envelope(
    *,
    plugin_name: str,
    extras_key: str,
    plugin_version: str | None,
    binding: dict,
    status: dict,
    plugin_extras: dict,
    addon_extras: dict | None = None,
) -> dict[str, Any]:
    """Assemble a contract-conformant envelope.

    plugin_name is the contract's plugin_name field (e.g. "project-rag" — hyphens permitted).
    extras_key is the snake_case key under extras{} where plugin_extras lands (e.g. "project_rag"
    for project-rag). The caller owns both; this primitive embeds NO naming policy
    (Zolí F-Minor 1 2026-05-19).

    R3 (PM 2026-05-19): addon contributions in addon_extras lift to first-class extras keys.
    Collision rule: addon namespace colliding with extras_key triggers log+skip, never silent
    overwrite. Addon-vs-addon collision is resolved at the addon adapter layer, not here
    (Zolí F-Minor 3 2026-05-19; see Task 5 hard-constraint).
    """
    extras = {extras_key: plugin_extras}
    if addon_extras:
        for ns, payload in addon_extras.items():
            if ns in extras:
                log.warning(
                    "Addon namespace %r collides with plugin extras key %r; skipping addon contribution",
                    ns, extras_key,
                )
                continue
            extras[ns] = payload
    return {
        "contract_version": 1,
        "plugin_name": plugin_name,
        "plugin_version": plugin_version,
        "binding": binding,
        "status": status,
        "extras": extras,
    }
