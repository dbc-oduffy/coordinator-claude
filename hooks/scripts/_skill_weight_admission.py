"""Pure admission predicate for the skill-weight pre-commit guard, and the one
definition of the three skill-weight ceiling constants.

`admission_violations(proposed, base, baseline)` answers: which skill, or the
fleet total, does this proposed tree put over its limit while growing it
versus the base? Growth is the trigger, so a tree already over budget still
admits a commit that shrinks it. The test suite
(`test_skill_weight_budget.py`) imports `CEILING`, `NEW_SKILL_CAP` and
`CEILING_NOISE_BAND` from here, so the test and the gate cannot disagree.

Negative-spec: no subprocess, no filesystem read of the repo state. Callers
(`guard-skill-weight-budget-precommit.py`) own the git I/O and pass plain
`{skill name: resident bytes}` mappings plus the parsed baseline JSON.

A limit is never raised to admit growth. `limit_raises(proposed_baseline,
base_baseline)` refuses any baseline edit that moves a limit, floor or the
ceiling upward, or adds an exception above CEILING; the way to fit an addition
is to cut text.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[2] / "tests"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
import _hook_ratchet_shared as shared  # noqa: E402

# Chosen as ~3x the measured corpus median resident load (8,357 B -- see the
# baseline's own `fleet.coverage_note` for the live-measured figure this was
# justified against), not reverse-engineered from a target. See the baseline
# `coverage_note` for exactly which skills this flags today.
CEILING = 25_600  # 25 KiB

# A brand-new skill with no manifest entry is held to the bare CEILING --
# same reasoning as the hook gate's own NEW_HOOK_CAP: this domain already
# has a hard per-item ceiling every skill, new or old, is held to, so there
# is no principled basis for granting a new skill more headroom than an
# existing one gets.
NEW_SKILL_CAP = CEILING

# Ceiling-leg noise band. A skill's measured resident moves by tens to low
# hundreds of bytes on an ordinary reworded sentence, and without a band this
# ratchet converts that jitter into an authored-justification ceremony plus a
# PERMANENT floor raise. The band buys the jitter and nothing else.
#
# It does NOT re-baseline, and that is the whole design. A within-band overage
# passes while the recorded `limit` stays where it is, so the comparison on the
# next run is still against the ORIGINAL limit -- drift cannot accumulate 255 B
# at a time into an unbounded rise, which is exactly what a band that silently
# rewrote the baseline would allow. Growth past the band is still red, and the
# limit is never raised to admit it: `limit_raises` refuses that edit.
#
# Flat, not proportional: jitter is a property of prose editing, not of entry
# size, so a percentage would hand the largest entries the largest free pass
# for no reason connected to how they actually change.
CEILING_NOISE_BAND = 256


def admission_violations(
    proposed: "dict[str, int]", base: "dict[str, int]", baseline: dict
) -> "list[str]":
    """Refusal lines for growth over budget; empty means admit.

    `proposed` and `base` map skill name -> resident bytes. `baseline` is the
    parsed skill-weight-budget JSON read from the proposed tree; a raised
    limit in it is judged separately by `limit_raises`. A skill absent from
    `base` counts as 0 there. Each line reads
    `<leg> <name>: <measured> B > <limit> B (+<delta>)`, where delta is growth
    versus base."""
    lines: "list[str]" = []

    total, base_total = sum(proposed.values()), sum(base.values())
    fleet_limit = baseline["fleet"]["resident_limit"]
    if shared.fleet_over(total, fleet_limit) and total > base_total:
        lines.append(f"fleet resident: {total} B > {fleet_limit} B (+{total - base_total})")

    manifest = baseline.get("exceptions", {})
    banded = {
        name: {"limit": entry["limit"] + CEILING_NOISE_BAND} for name, entry in manifest.items()
    }
    over = dict(shared.over_limit(proposed, banded))
    over.update(
        {
            name: (size, NEW_SKILL_CAP)
            for name, size in shared.unbaselined_over(proposed, manifest, NEW_SKILL_CAP).items()
        }
    )
    for name in sorted(over):
        size, limit = over[name]
        grown = size - base.get(name, 0)
        if grown > 0:
            lines.append(f"skill {name}: {size} B > {limit} B (+{grown})")
    return lines


def limit_raises(proposed_baseline: dict, base_baseline: "dict | None") -> "list[str]":
    """Refusal lines for a baseline edit that raises any limit; empty means admit.

    Compares `fleet.resident_limit`, `fleet.resident_ratchet_floor`, the
    top-level `ceiling`, and each exception's `limit` and `ratchet_floor`
    against the base. A new exception whose `limit` exceeds CEILING counts as a
    raise from CEILING. `base_baseline is None` (no prior revision) admits.
    Lowering a value or deleting an exception is never a finding. Each line
    reads `limit-raise <path>: <old> B -> <new> B (+<delta>)`."""
    if base_baseline is None:
        return []
    lines: "list[str]" = []

    def _check(path: str, old, new) -> None:
        if isinstance(old, int) and isinstance(new, int) and new > old:
            lines.append(f"limit-raise {path}: {old} B -> {new} B (+{new - old})")

    proposed_fleet, base_fleet = proposed_baseline.get("fleet", {}), base_baseline.get("fleet", {})
    for key in ("resident_limit", "resident_ratchet_floor"):
        _check(f"fleet.{key}", base_fleet.get(key), proposed_fleet.get(key))
    _check("ceiling", base_baseline.get("ceiling"), proposed_baseline.get("ceiling"))

    base_exceptions = base_baseline.get("exceptions", {})
    for name, entry in sorted(proposed_baseline.get("exceptions", {}).items()):
        if name not in base_exceptions:
            _check(f"exceptions.{name}.limit", CEILING, entry.get("limit"))
            continue
        for key in ("limit", "ratchet_floor"):
            _check(f"exceptions.{name}.{key}", base_exceptions[name].get(key), entry.get(key))
    return lines
