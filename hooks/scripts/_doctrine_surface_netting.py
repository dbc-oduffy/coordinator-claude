"""Pure, importable netting primitives for Layer 1 leg 1b -- the enforcing
git pre-commit gate (`guard-doctrine-surface-ratio-precommit.py`).

Spec: docs/plans/2026-08-13-doctrinal-surface-weight-ratchet.md, chunk C9b
(§ D2's credit-scope column, D3 carve-out 1, D7).

Why this module exists, separate from the guard/shim
-------------------------------------------------------
Leg 1b is a native git pre-commit hook, never exercised by `pytest`
collection (D7's "Consequence for the test plane") -- these two functions
are its ONLY test surface. Both are PURE: they take already-parsed
`(old_bytes, new_bytes, path)` rows plus a `tier_of` resolver and never
shell out to `git` or `git cat-file` themselves. The shim
(`guard-doctrine-surface-ratio-precommit.py`) is the thin, untested wrapper
that runs `git diff --cached --raw -z -M` + `git cat-file -s`, parses rows,
builds `tier_of` (closing over each row's pre-edit `old_bytes`, per
C3b's `tier_boundaries_for`), and calls these functions.

UNIT IS BYTES, never a line-oriented diff -- `git diff --cached --numstat`
prices LINES, not bytes, and leg 1a already prices bytes
(`_sentinel_write_guard.reconstruct_after`'s byte-length delta). Billing
leg 1b off numstat would price one currency and bill another (see the
shim's own module docstring for the full argument).

`tier_of` contract
-------------------
`tier_of: Callable[[str], str]` maps a repo-relative path to its
CREDIT-SCOPE POOL for this commit -- `"surface"` at the 2:1 tier,
`"file"` at the 5:1/10:1 tiers (PM ruling, 2026-08-13; `tier_boundaries_
for`'s own `credit_scope` field, D2's credit-scope column). The caller
(the shim) builds this resolver by composing `doctrine_surface_tiers.
tier_boundaries_for(surface_of(path))` with the path's PRE-EDIT size
(`old_bytes`, already available in the parsed row) -- neither netting
function re-derives a path's tier itself; each only asks `tier_of(path)`
which pool a row belongs to, and gates the row in or out of its own pool
family (`net_bytes_by_surface` only ever sums `"surface"`-scoped rows,
`net_bytes_by_file` only ever sums `"file"`-scoped rows). This gate is
the load-bearing piece `test_credit_scope_is_tier_dependent`'s
`_goes_red` companion exercises -- a naive `net_bytes_by_surface`-only
implementation with no `tier_of` gate would let a cut on one file net
against a DIFFERENT file's steep-tier bill, which this split structurally
forbids.

Negative-spec: neither function knows about the 512 B floor, the
sub-floor accumulator, the reasoned-growth marker, or the new-file
admission cap -- those are the shim's carve-outs 2-4, layered on top of
these functions' raw net output. Per D3 carve-out 2's test (a): "the pure
function's raw output is used directly for the in-commit price, no
separate floor re-derivation."
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _doctrine_changelog_prose import surface_of  # noqa: E402

#: The two `credit_scope` values `tier_boundaries_for` ever returns --
#: mirrored here as the exact strings a `tier_of` resolver must produce,
#: so a caller building one has a single literal source to match against.
CREDIT_SCOPE_SURFACE = "surface"
CREDIT_SCOPE_FILE = "file"

#: The pure-function row shape shared by `net_bytes_by_surface`/
#: `net_bytes_by_file` and the shim's own `_parse_raw_diff` output --
#: `(old_bytes, new_bytes, path)`. Used as the annotation on both
#: functions' `blob_size_rows` parameter below.
BlobSizeRow = "tuple[int, int, str]"


def net_bytes_by_surface(
    blob_size_rows: "list[BlobSizeRow]",
    tier_of: Callable[[str], str],
) -> "dict[str, int]":
    """The 2:1-tier surface-wide netting pool: `{surface: net_bytes}`,
    summing `new_bytes - old_bytes` across every row whose `tier_of(path)
    == CREDIT_SCOPE_SURFACE`, grouped by `surface_of(path)`. Rows scoped
    `"file"` (5:1/10:1) and rows whose path is not a recognised doctrine
    surface are excluded -- they belong to `net_bytes_by_file` or nowhere.
    """
    totals: "dict[str, int]" = {}
    for old_bytes, new_bytes, path in blob_size_rows:
        if tier_of(path) != CREDIT_SCOPE_SURFACE:
            continue
        surface = surface_of(Path(path))
        if surface is None:
            continue
        totals[surface] = totals.get(surface, 0) + (new_bytes - old_bytes)
    return totals


def net_bytes_by_file(
    blob_size_rows: "list[BlobSizeRow]",
    tier_of: Callable[[str], str],
) -> "dict[str, int]":
    """The 5:1/10:1-tier same-file netting pool: `{path: net_bytes}`,
    summing `new_bytes - old_bytes` across every row whose `tier_of(path)
    == CREDIT_SCOPE_FILE`, keyed by the row's own (new, post-rename) path
    -- never grouped across files, which is exactly what keeps a cut on a
    DIFFERENT file from paying a steep-tier file's bill (D3 carve-out 1's
    "the pool it nets against narrows to the file being grown")."""
    totals: "dict[str, int]" = {}
    for old_bytes, new_bytes, path in blob_size_rows:
        if tier_of(path) != CREDIT_SCOPE_FILE:
            continue
        totals[path] = totals.get(path, 0) + (new_bytes - old_bytes)
    return totals


# ---------------------------------------------------------------------------
# `_goes_red` reference implementations -- NOT used by the shim, kept here
# only so the test module can import a shared naive baseline rather than
# re-deriving one inline per D3's own precedent
# (`test_agent_body_envelope.py`'s module docstring: a `_goes_red`
# companion that re-derives its own inline comparison, rather than calling
# into shared naive code, can pass even after a real regression).
# ---------------------------------------------------------------------------


def _naive_net_bytes_by_surface_always(
    blob_size_rows: "list[tuple[int, int, str]]",
) -> "dict[str, int]":
    """The regression `test_credit_scope_is_tier_dependent`'s `_goes_red`
    companion asserts against: sums EVERY row into its surface pool
    regardless of `tier_of`, exactly what a flat "surface-wide credit at
    every tier" implementation (the PM-rejected design) would do."""
    totals: "dict[str, int]" = {}
    for old_bytes, new_bytes, path in blob_size_rows:
        surface = surface_of(Path(path))
        if surface is None:
            continue
        totals[surface] = totals.get(surface, 0) + (new_bytes - old_bytes)
    return totals


# ---------------------------------------------------------------------------
# Closed-enum reasoned-growth marker (carve-out 3) -- mirrors
# `_hook_ratchet_shared.py`'s `missing_reason` shape, but against a CLOSED
# set rather than "any non-empty string" -- silence without the marker is
# not an exception, and a value outside this set fails exactly the same
# way an empty/missing reason already does.
# ---------------------------------------------------------------------------

#: The closed set of sanctioned reasons a marker comment or commit trailer
#: may name for growth beyond a surface/file's ratio. Not free text --
#: an unrecognised value is treated identically to no marker at all.
REASONED_GROWTH_MARKERS = frozenset(
    {
        "new-surface-onboarding",
        "regulatory-or-contractual-requirement",
        "generated-content-not-hand-authored",
        "temporary-migration-scaffolding",
    }
)


def is_sanctioned_reason(value: "str | None") -> bool:
    """`True` only for a value drawn from `REASONED_GROWTH_MARKERS`. `None`,
    the empty string, whitespace-only, and any out-of-enum value are all
    unsanctioned -- "silence is not an exception" (carve-out 3), and an
    unreasoned marker fails the same way `missing_reason` already does on
    the shipped ratchets."""
    if value is None:
        return False
    return value.strip() in REASONED_GROWTH_MARKERS
