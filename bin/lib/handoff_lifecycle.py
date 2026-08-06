"""handoff_lifecycle.py — single shared accessor for DR-084 handoff lifecycle
frontmatter fields (Python side).

DR-084 renames handoff lifecycle vocabulary: `consumed_by:` -> `claimed_by:`,
`consumed_at:` -> `claimed_at:`, and the status axis `active | consumed` ->
`open | claimed`. The write path has not cut over yet (phase P3, sibling repo
Claude-klabauter) — the on-disk corpus is MIXED. Every Python reader of these
fields must dual-read: prefer the new vocabulary, fall back to the old.

THIS MODULE IS THE SINGLE EDIT SITE for that dual-read on the Python side —
mirroring coordinator/bin/lib/consumed-marker.js on the JS side (TERMINAL_STATUS
here is deliberately identical to that module's set; see the constant below).
When the P1..P4 migration window closes, the fallbacks collapse HERE and
NOWHERE ELSE — no caller should ever inline a raw `consumed_by`/`claimed_by`
(or `consumed_at`/`claimed_at`, or a hand-rolled status-membership check)
again. A second raw read site is exactly the failure this module closes: a
code review of the JS-side dual-read wave found a raw `consumed_by` read 180
lines from an already-fixed site, same file — the durable lesson (independently
demonstrated twice in this tree, JS-side) is that one shared accessor per
lifecycle field means a rename has one edit site, not N silent ones.

Input-shape decision: `claim_holder`/`claim_timestamp` accept EITHER a
frontmatter dict OR a file path (str). Existing callers are split on this —
reap-orphaned-in-flight-handoffs.py's `_fm_field` reads a single key straight
off disk (path-based, no full-frontmatter parse), while other callers already
hold a parsed dict. Forcing dict-only would make the reaper build a throwaway
dict just to satisfy this module's signature; forcing path-only would make a
dict-holding caller round-trip through a tempfile. A `Union[str, dict]` input
with an internal dispatch is the smaller adapter — it costs one `isinstance`
check here instead of an awkward call-site shim in every caller. Path input
reuses the same minimal frontmatter-value scanner reap-orphaned-in-flight-
handoffs.py already had (single-key linear scan bounded by the first `---`
fence pair) rather than a full YAML parse — this module has no YAML dependency
and doesn't want one for a single scalar lookup.

Negative-spec: does NOT parse the full frontmatter block into a dict when
given a path — it scans for one key at a time (same bounded linear-scan idiom
the retired bash oracle and the reaper's `_fm_field` used). A caller that
already has a parsed dict should pass the dict, not a path, to avoid the
re-scan.

Spec backlink: docs/decisions/DR-084-handoff-lifecycle-vocabulary-overhaul-open-claimed-continued-closed.md
"""
from __future__ import annotations

from typing import Union

# Fields whose status values are terminal (no flip allowed). DR-084 additive
# widen: 'consumed' is being renamed to 'claimed'; both vocabularies are
# accepted while the corpus is mixed. MUST mirror
# coordinator/bin/lib/consumed-marker.js's TERMINAL_STATUS exactly — if the
# two ever diverge, that is a cross-language drift bug, not an intentional
# per-language choice.
TERMINAL_STATUS = {"consumed", "claimed", "superseded"}

# Status values meaning "claimed" under either vocabulary (a strict subset of
# TERMINAL_STATUS — 'superseded' is terminal but not a claim-status value).
_CLAIMED_STATUSES = {"consumed", "claimed"}

FrontmatterOrPath = Union[str, dict]


def _fm_field(path: str, key: str) -> str:
    """Single-key bounded linear scan of a handoff's YAML frontmatter block.

    Mirrors reap-orphaned-in-flight-handoffs.py's retired local `_fm_field` —
    same idiom (scan between the first `---`/`---` fence pair, first match
    wins, single-quote-pair stripping for a YAML-serialized all-digit
    scalar). Returns "" on any read failure or missing key — never raises.
    """
    prefix = key + ":"
    val = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            in_fm = False
            for line in fh:
                stripped_line = line.rstrip("\n").rstrip("\r")
                if not in_fm:
                    if stripped_line.strip() == "---":
                        in_fm = True
                    continue
                if stripped_line.strip() == "---":
                    break
                if stripped_line.startswith(prefix):
                    val = stripped_line[len(prefix):].strip()
                    break
    except OSError:
        return ""

    # serializeYamlScalar (coordinator/bin/lib/schema.js) single-quotes
    # all-digit values (e.g. a synthetic all-digit session id); strip one
    # matched pair of surrounding quotes so an unstripped quoted value
    # doesn't fail a downstream equality/liveness comparison.
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1]
    return val


def _read_field(source: FrontmatterOrPath, new_key: str, old_key: str) -> str:
    """Dual-read dispatch shared by claim_holder/claim_timestamp.

    Accepts a parsed frontmatter dict OR a file path; prefers new_key, falls
    back to old_key. Missing/falsy values on either input shape resolve to
    "".
    """
    if isinstance(source, dict):
        return source.get(new_key) or source.get(old_key) or ""
    return _fm_field(source, new_key) or _fm_field(source, old_key)


def claim_holder(frontmatter_or_path: FrontmatterOrPath) -> str:
    """DR-084 dual-read: prefer `claimed_by`, fall back to `consumed_by`.

    Accepts either a parsed frontmatter dict or a handoff file path (see
    module docstring's input-shape decision). Returns "" when neither field
    is present/non-empty.
    """
    return _read_field(frontmatter_or_path, "claimed_by", "consumed_by")


def claim_timestamp(frontmatter_or_path: FrontmatterOrPath) -> str:
    """DR-084 dual-read: prefer `claimed_at`, fall back to `consumed_at`.

    Accepts either a parsed frontmatter dict or a handoff file path (see
    module docstring's input-shape decision). Returns "" when neither field
    is present/non-empty.
    """
    return _read_field(frontmatter_or_path, "claimed_at", "consumed_at")


def is_claimed_status(status: str) -> bool:
    """True iff `status` is a claimed-handoff value under either vocabulary
    (`consumed` or `claimed`). Distinct from TERMINAL_STATUS membership —
    `superseded` is terminal but not a claim-status value, so
    `is_claimed_status("superseded")` is False; test membership in
    TERMINAL_STATUS directly for the broader terminal-state check.
    """
    return status in _CLAIMED_STATUSES
