"""Read the engine plane's guard-enforcement join and answer, for one DoE
doctrine rule id, whether a guard enforces it.

WHAT THIS IS FOR
    `DR-an-omission-is-ratified-by-the-plane-that-enforces-the-rule` makes
    omission authority follow enforcement, and names three exhaustive cases.
    Case 1 -- no guard enforces the rule -- is DoE's to decide alone and is
    "the large majority". Deciding it needs one fact this repo cannot produce:
    which of `claude-klabauter`'s registered guards enforce which of this
    repo's `rcr-<hash>` rule ids. That fact is the join, and until it exists
    every case-1 rule is indistinguishable from a case-3 rule and stays
    present. This module reads the join once it has been delivered.

WHICH WAY "CAUTIOUS" POINTS HERE, BECAUSE IT IS THE OPPOSITE OF THE OBVIOUS
    The join is read GUARD-FIRST, so a rule named by nobody is the rule that
    becomes omittable. That inverts the intuition an author brings to it:
    leaving a doubtful rule id OFF a guard's list does not keep the rule
    present, it makes the rule easier to omit. Claiming is the cautious act
    here and dropping is the risky one.

    `uncertain_rule_ids` exists so an author is never forced to choose
    between two wrong answers. A rule id there resolves to UNRESOLVED --
    never to "no guard enforces it" -- so a guess costs presence rather than
    an omission, and the distinction between "I proved this guard fires on
    this rule" and "this looks likely" survives in the file instead of
    being flattened into whichever list felt safer.

THE ASYMMETRY IS DELIBERATE: A NEGATIVE NEEDS COMPLETENESS, A POSITIVE DOES NOT
    "Guard G enforces rule X" is established by one row. "NO guard enforces
    rule X" is established only by having asked every guard. So this module
    answers `("none", "n/a")` -- the only answer that buys an omission --
    ONLY when the join declares itself complete over the live registered
    guard population AND names no guard for the rule. An incomplete join
    answers `None` for every rule, which keeps every rule present. A join
    that is merely EMPTY is the sharpest case of this: read without the
    completeness gate it would say no guard enforces anything and omit the
    whole candidate set at once.

WHY THIS REPO HOLDS A COPY RATHER THAN READING THE SIBLING
    `coordinator/bin/emit-omission-register.py` must run against a checkout
    of this repo alone -- it reads `claude-klabauter` for nothing, and a
    resolver that imported the sibling's tree would make this repo's ledger
    unbuildable wherever that tree is absent, which includes every cloud
    session and every OSS mirror. The join is therefore DELIVERED: the engine
    plane authors it, and a copy lands here carrying the source repo and the
    sha it was cut at, so a reader can tell what it is a copy OF.

WHAT THIS MODULE REFUSES TO DO
    It does not decide case 2 (guard-enforced, guard inert in this
    environment). The DR permits that omission on a ratified verdict, and
    this module reports the verdict faithfully, but
    `compute_story_omissions` keeps any rule with a named guard present.
    Under-omitting is the direction the DR says to be wrong in; the widening
    is named in this repo's queue rather than assumed here.

Stdlib plus PyYAML, matching `coordinator/bin/emit-omission-register.py`,
which is this module's only caller and is dev-time tooling.
"""

from __future__ import annotations

import os
from typing import Optional

import yaml

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPTS_DIR)))

#: Where a delivered join lands. One path, named here rather than passed in,
#: so that "the join is absent" is a checkable fact about this repo and not a
#: property of how some caller was invoked.
DEFAULT_JOIN_PATH = os.path.join(
    _REPO_ROOT, "state", "audits", "2026-09-07-guard-enforcement-join-from-claude-klabauter.yaml"
)

#: NO VERDICT IS TREATED AS MEANING "THIS GUARD DOES NOT FIRE HERE", and that
#: is a finding rather than an omission.
#:
#: `cloud_verdict` answers "is the harm this guard protects against reachable
#: in the target environment?" -- the harmed-party axis the ratification DR
#: turns on. It does NOT answer "does this guard fire here", and the two come
#: apart exactly where it matters. `nudge_windows_subprocess_popup` is the
#: worked case: its premise is false on a headless VM (nobody sits at a
#: Windows console to have their focus stolen) and yet the module carries no
#: host gate whatsoever -- it is extension- and content-gated over authored
#: code, so a Linux session writing a Windows-targeted launcher trips it.
#: Premise false, guard live.
#:
#: So `resolve` below reports the first guard naming the rule and does not
#: rank them. An earlier cut carried an `INERT_VERDICTS` set and picked the
#: "strictest" guard from it; measured against the live artifact it matched
#: zero of 105 rows, could not change a single emitted byte, and existed only
#: to defend its own narrowness. Whether a guard fires here is derivable from
#: its band, advisory value and tool surface -- if that computed field lands,
#: it belongs here as a real discriminator, not as this constant restored.


class JoinError(ValueError):
    """The join file exists but cannot be trusted to answer anything.

    Raised rather than returned, and never caught by this module: a
    malformed join is a delivery defect on the engine plane, and silently
    degrading it to "unresolved" would hide a broken artifact behind the
    same empty ledger a missing one produces."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise JoinError(message)


class GuardEnforcementJoin:
    """One delivered join, parsed and queryable.

    `complete_over_guards` is the single fact that licenses a negative
    answer: the engine plane asserting that the rows below cover every
    registered guard in the population named by `guard_population`."""

    def __init__(self, document: dict) -> None:
        _require(isinstance(document, dict), "join is not a mapping")
        self.source_repo: str = document.get("source_repo") or ""
        self.source_sha: str = document.get("source_sha") or ""
        self.guard_population: str = document.get("guard_population") or ""
        completeness = document.get("complete_over_guards")
        _require(
            isinstance(completeness, bool),
            "complete_over_guards must be a real boolean, not "
            f"{type(completeness).__name__} {completeness!r} -- this is the ONE field "
            "that licenses an omission, and truthiness coercion makes the string "
            "'false', 'partial' and 'pending' all mean complete",
        )
        self.complete_over_guards: bool = completeness
        _require(bool(self.source_repo), "join names no source_repo")
        _require(bool(self.source_sha), "join names no source_sha")

        rows = document.get("guards")
        _require(isinstance(rows, list), "join `guards` is not a list")
        _require(
            bool(rows),
            "join carries zero guard rows. A join asking to be read as complete over "
            "an empty guard population answers 'no guard enforces this' for EVERY "
            "rule -- the whole candidate set omitted from one truncated or "
            "mis-serialised artifact. An empty population can license nothing, so it "
            "is refused rather than believed",
        )

        declared = (document.get("counts") or {}).get("guards")
        _require(
            declared is None or declared == len(rows),
            f"join says counts.guards is {declared} but carries {len(rows)} rows -- a "
            "truncated delivery is exactly the shape that silently shrinks the "
            "population a negative rests on",
        )

        self._rule_to_guards: dict[str, list[tuple[str, str]]] = {}
        self._uncertain_rule_ids: set[str] = set()
        self.guard_count = 0
        for row in rows:
            _require(isinstance(row, dict), "join guard row is not a mapping")
            guard_id = row.get("guard_id")
            verdict = row.get("cloud_verdict")
            _require(bool(guard_id), "join guard row names no guard_id")
            _require(bool(verdict), f"{guard_id}: guard row names no cloud_verdict")
            _require(
                guard_id != "none",
                "'none' is this module's reserved answer for an unenforced rule and "
                "may not name a guard",
            )
            self.guard_count += 1
            enforced = row.get("enforces_rule_ids")
            _require(
                isinstance(enforced, list),
                f"{guard_id}: enforces_rule_ids must be a list, empty where the guard "
                "enforces no register rule -- an absent key cannot be told apart from "
                "an unexamined guard",
            )
            for rule_id in enforced:
                self._rule_to_guards.setdefault(str(rule_id), []).append((guard_id, verdict))

            uncertain = row.get("uncertain_rule_ids")
            _require(
                isinstance(uncertain, list),
                f"{guard_id}: uncertain_rule_ids must be a list, empty where the author "
                "had no doubt -- an absent key cannot be told apart from a guard nobody "
                "thought about, and doubt is the one thing this file must not lose",
            )
            self._uncertain_rule_ids.update(str(rule_id) for rule_id in uncertain)

    @property
    def enforced_rule_count(self) -> int:
        return len(self._rule_to_guards)

    @property
    def uncertain_rule_count(self) -> int:
        return len(self._uncertain_rule_ids)

    def resolve(self, rule_id: str) -> "Optional[tuple[str, str]]":
        """`(guard, verdict)` for `rule_id`, or `None` when this join cannot
        say.

        A rule named by no guard resolves to `("none", "n/a")` -- but only
        under `complete_over_guards`, and never if any guard listed it as
        UNCERTAIN, per this module's docstring. A rule named by several
        resolves to the first; they are not ranked, because no verdict in the
        live vocabulary means the guard is silent here (see the note above
        `JoinError`). Any named guard keeps the rule present, so which one is
        reported changes the record, never the outcome.

        THE UNCERTAIN CHECK SITS UNDER `if not enforcing` DELIBERATELY, so an
        id appearing in BOTH lists resolves as enforced and its doubt does
        not reach this answer. That is the module's own asymmetry applied,
        not doubt discarded: a positive is established by one row, so a guard
        claiming the rule settles it whatever a second guard doubted, and the
        rule is kept present down either path -- the only difference is
        whether the record names the guard or says nothing could be told."""
        enforcing = self._rule_to_guards.get(rule_id)
        if not enforcing:
            if not self.complete_over_guards:
                return None
            if rule_id in self._uncertain_rule_ids:
                return None
            return ("none", "n/a")
        return enforcing[0]


def load_join(path: Optional[str] = None) -> "Optional[GuardEnforcementJoin]":
    """The delivered join, or `None` when none has been delivered.

    Absence is the expected state until the engine plane walks this path and
    is not an error -- see `DR-an-omission-is-ratified-by-the-plane-that-
    enforces-the-rule` § "The blocker is no longer a decision, it is a
    missing artifact"."""
    target = path or DEFAULT_JOIN_PATH
    if not os.path.isfile(target):
        return None
    with open(target, "r", encoding="utf-8") as handle:
        return GuardEnforcementJoin(yaml.safe_load(handle))
