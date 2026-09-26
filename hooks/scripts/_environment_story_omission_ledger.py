"""The omission ledger's enforcement mechanism: ONE predicate module owning
every refusal a composed environment story's omission accounting must pass,
imported by its invariant test rather than re-derived there.

Spec backlink: `state/handoffs/2026-09-06_210002_roadmap-cloudem-03.md`
(roadmap cloud-em-2026-09-06, cluster C13) -- "It is the check on the
composition baton, and a check written by the composer in the composer's
session is not a check." Mirrors `_claude_md_ledger.py`'s shape: a closed
set of refusal predicates plus a fail-loud validator, read by a test
independent of whatever code produced the artifact being checked. This
module is that predicate's ONLY definition; a caller that re-derives one of
these checks inline (as `coordinator/tests/test_environment_story_
composition.py`'s claim-5 test currently does for refusal 1 -- see that
file, flagged rather than silently duplicated here) is exactly the drift
this module exists to close off.

INPUTS this module reasons over -- both are DATA it reads, never a module
it imports for behaviour:
  - the doctrine rule-class register's `rows:`
    (`state/audits/2026-09-06-doctrine-rule-class-register.yaml`), each a
    dict with at least `id` and `disposition`;
  - the emitted per-story omission register's `rows:`
    (`state/audits/2026-09-07-environment-story-omission-register.yaml`),
    each a dict with `rule_id`, `story`, `reason`, `stated_party`,
    `harmed_party`, `enforcing_guard`, `enforcement_verdict` -- the schema
    `coordinator/bin/emit-omission-register.py` already emits.

THE THREE REFUSALS, exhaustive over this baton's brief
--------------------------------------------------------
1. **Unaccounted rule** (`find_unaccounted_rule_ids`). A rule-bearing
   register id that is neither in the story's `rule_ids` nor carries an
   omission-register row with a non-empty `reason`. Rule-bearing is every
   disposition except the two file-level ones (`no-environment-scoped-
   premise`, `not-rule-bearing`) -- `RULE_BEARING_DISPOSITIONS` names the
   six that are, and a committed test checks that set against the
   register's own `counts:` block rather than trusting it silently.

   This is the refusal a prior check already went green without: the
   emitter's own consistency check once asserted an arithmetic identity
   ("the story keeps exactly N ids") instead of the actual criterion (every
   id is present-or-omitted), and passed while 309 rules sat in neither
   place. `find_unaccounted_rule_ids` is a real set difference against the
   full rule-bearing class, not a count compared to a remembered N, so it
   cannot repeat that failure by construction -- see this module's test for
   a fixture that reconstructs the exact incident.

2. **A row that cannot name both parties** (`find_unnamed_party_rows`,
   Constraint 3). An omission row whose `stated_party` or `harmed_party` is
   empty or a bare placeholder (`n/a`, `none`, `same`, and near-spellings)
   is refused outright -- such a rule is not omittable, it is a finding.
   Placeholders are detected BY VALUE (`is_placeholder_party`), never by an
   id list.

   Constraint 5 is the deliberately different case and this module keeps it
   separate rather than folding it into refusal 2: a party that CAN be
   named but whose presence in a given environment cannot be TOLD resolves
   toward presence -- the rule simply stays in the story and never becomes
   an omission row in the first place, so there is nothing for this
   predicate to refuse. This module's test asserts that default directly
   against the real register (every `genuinely-inapplicable` id with an
   unresolved or placeholder harmed-party reading is still present in
   `EPHEMERAL_CLOUD_VM_STORY.rule_ids` today), rather than only proving the
   refusal side.

3. **Guard-enforced with no agreeing verdict** (`find_unresolved_
   enforcement_rows`, `docs/decisions/DR-an-omission-is-ratified-by-the-
   plane-that-enforces-the-rule.md`). An omission row is valid only when it
   carries the SAFE-ARM answer exactly: `enforcing_guard == "none"` and
   `enforcement_verdict == "n/a"`. Any other combination -- a named guard,
   a `pending-ratification` verdict, or either field missing/unresolved --
   is refused, because while the DR stands `proposed` only its safe arm is
   in force and silence never buys an omission.

WHAT THIS LEDGER DOES NOT CATCH
--------------------------------
This mechanism verifies one thing only: that every rule in the enumerated
class is present in a composed story or omitted with a reasoned, party-
complete, enforcement-cleared row. It says nothing about whether a NUMBER
or FACT asserted elsewhere in a roadmap's own prose is true of what it
claims to be true of. Measured against this repo's three most recent
predicate-mismatch incidents (a file count asserted as a guard-body count;
working-tree presence asserted as remote reachability; a superseded
decision asserted as still-standing) -- none is a rule silently dropped
from a story, so none would have been caught by this ledger even had it
existed beforehand. This ledger is necessary but not sufficient for that
wider class; the wider discipline over measured claims generally is a
separate, unbuilt mechanism, not a gap in this one's scope.

CONSTRAINTS
-----------
Import-light, stdlib-only, no module-level file I/O, no `subprocess`, no
third-party import -- mirrors every sibling module in this directory. This
module never reads a file itself; every function takes already-loaded data
so it stays reusable from a future PreToolUse-style hook exactly as it is
from the CI-path test, per `_claude_md_ledger.py`'s own precedent.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Optional, Sequence

RULE_BEARING_DISPOSITIONS: frozenset[str] = frozenset(
    {
        "binds",
        "premise-false-but-binds",
        "genuinely-inapplicable",
        "cannot-name-a-party",
        "owned-by-cloudem-06",
        "engine-plane",
    }
)

_SAFE_ARM_GUARD = "none"
_SAFE_ARM_VERDICT = "n/a"

_PLACEHOLDER_LEAD_RE = re.compile(r"^(n/a|none|same)\b", re.IGNORECASE)

_PARTY_NOUN_TOKENS = frozenset(
    {
        "party", "parties",
        "session", "sessions",
        "operator", "operators",
        "tenant", "tenants",
        "team", "teams",
        "reviewer", "reviewers",
        "maintainer", "maintainers",
        "peer", "peers",
        "developer", "developers",
        "user", "users",
        "agent", "agents",
        "committer", "committers",
        "claimant", "claimants",
        "em", "ems",
        "victim", "victims",
        "colleague", "colleagues",
        "stakeholder", "stakeholders",
        "owner", "owners",
        "author", "authors",
        "subagent", "subagents",
        "pm", "pms",
    }
)

_WORD_RE = re.compile(r"[A-Za-z']+")


class OmissionLedgerError(Exception):
    pass


def is_placeholder_party(value: Optional[str]) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    if not stripped:
        return True
    if not _PLACEHOLDER_LEAD_RE.match(stripped):
        return False
    words = {w.lower() for w in _WORD_RE.findall(stripped)}
    return words.isdisjoint(_PARTY_NOUN_TOKENS)


def rule_bearing_ids(register_rows: Iterable[Mapping]) -> frozenset[str]:
    """Every register row id whose disposition is rule-bearing
    (`RULE_BEARING_DISPOSITIONS`) -- the universe refusal 1 accounts over."""
    return frozenset(
        row["id"] for row in register_rows if row.get("disposition") in RULE_BEARING_DISPOSITIONS
    )


def find_unaccounted_rule_ids(
    rule_bearing: Iterable[str],
    story_rule_ids: Iterable[str],
    omission_rows_for_story: Sequence[Mapping],
) -> frozenset[str]:
    carrying_a_reasoned_row = {
        row["rule_id"]
        for row in omission_rows_for_story
        if (row.get("reason") or "").strip()
    }
    return frozenset(set(rule_bearing) - set(story_rule_ids) - carrying_a_reasoned_row)


def find_unnamed_party_rows(omission_rows: Sequence[Mapping]) -> list[Mapping]:
    return [
        row
        for row in omission_rows
        if is_placeholder_party(row.get("stated_party"))
        or is_placeholder_party(row.get("harmed_party"))
    ]


def find_unresolved_enforcement_rows(omission_rows: Sequence[Mapping]) -> list[Mapping]:
    return [
        row
        for row in omission_rows
        if row.get("enforcing_guard") != _SAFE_ARM_GUARD
        or row.get("enforcement_verdict") != _SAFE_ARM_VERDICT
    ]


def validate_omission_rows(omission_rows: Sequence[Mapping]) -> None:
    unnamed = find_unnamed_party_rows(omission_rows)
    unresolved = find_unresolved_enforcement_rows(omission_rows)
    if not unnamed and not unresolved:
        return
    problems = []
    if unnamed:
        problems.append(
            "row(s) cannot name both parties (Constraint 3, not omittable): "
            + ", ".join(sorted(r.get("rule_id", "<no id>") for r in unnamed))
        )
    if unresolved:
        problems.append(
            "row(s) claim omission with no agreeing enforcement verdict (DR "
            "safe arm): "
            + ", ".join(sorted(r.get("rule_id", "<no id>") for r in unresolved))
        )
    raise OmissionLedgerError("; ".join(problems))


def validate_story_accounting(
    rule_bearing: Iterable[str],
    story_rule_ids: Iterable[str],
    omission_rows_for_story: Sequence[Mapping],
) -> None:
    unaccounted = find_unaccounted_rule_ids(rule_bearing, story_rule_ids, omission_rows_for_story)
    if unaccounted:
        raise OmissionLedgerError(
            f"{len(unaccounted)} rule-bearing id(s) are neither present in the "
            f"story's rule_ids nor carry a reasoned omission row: "
            f"{sorted(unaccounted)[:10]!r}"
            + (" (truncated)" if len(unaccounted) > 10 else "")
        )


def validate_ledger(
    register_rows: Iterable[Mapping],
    story_rule_ids: Iterable[str],
    omission_rows_for_story: Sequence[Mapping],
) -> None:
    validate_omission_rows(omission_rows_for_story)
    validate_story_accounting(
        rule_bearing_ids(register_rows), story_rule_ids, omission_rows_for_story
    )
