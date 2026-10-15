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
# rewrote the baseline would allow. Growth past the band is still red, still
# wants a `raised:` block, and still needs someone named.
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
    parsed skill-weight-budget JSON read from the proposed tree, so a
    deliberate same-commit limit raise is honoured (the suite's ratchet-floor
    leg polices it). A skill absent from `base` counts as 0 there. Each line
    reads `<leg> <name>: <measured> B > <limit> B (+<delta>)`, where delta is
    growth versus base."""
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
