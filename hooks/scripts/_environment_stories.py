"""Composed non-strictest environment stories for the environment-switch mechanism.

Spec backlink: docs/plans/2026-09-07-compose-the-environment-story-and-select.md
(chunk C2, roadmap cloud-em-2026-09-06). This module composes INTO
`_environment_story.py` (`cloudem-04`'s landed core) -- it reimplements none
of `Story`, `register_story`, `validate_story`, `CoreOmissionError` or
`CORE_RULE_IDS`; it supplies one more admitted `Story` and registers it.

WHAT THIS MODULE COMPOSES
--------------------------
`ephemeral-cloud-vm`: the story for a single-tenant ephemeral Linux VM (one
job, one EM session, a fresh checkout, no peer sessions, no sibling
repositories on the disk, destroyed at job end). Its prose is FIXED by the
plan's "The composed cloud story -- authored here, not delegated" section
and landed VERBATIM below. The only edit made in transit is mechanical: the
plan renders the prose as a Markdown blockquote (each line prefixed
`"> "`), and that prefix -- along with the blockquote's line WRAPPING,
which is a render-width artifact, not a sentence break -- is removed;
paragraph breaks (blank `>` lines in the source) are preserved as the
`"\\n\\n"` joins below. Do not rewrite, tighten, re-punctuate or "clean up"
this prose in a future edit: it is this baton's composition judgement, made
once, on purpose, in one place. One exception, equally deliberate: a
closing paragraph stating what the register behind `rule_ids` does and does
not claim -- this story is composed FROM that register, so its printed prose
is where a reader needs that caveat.

HOW `rule_ids` IS DERIVED -- the accounting surface, never parsed from prose
-----------------------------------------------------------------------------
Source: `state/audits/2026-09-06-doctrine-rule-class-register.yaml` (1,830
rows; see its own `counts` block at end of file).

RULE-BEARING, for this module's purpose, is exactly the register's own
`rule_rows` disposition set -- the six values its `counts` block sums to
`rule_rows` (1,209): `binds` (395), `premise-false-but-binds` (420),
`genuinely-inapplicable` (309), `cannot-name-a-party` (1),
`owned-by-cloudem-06` (70), `engine-plane` (14). NOT rule-bearing, for this
purpose: `no-environment-scoped-premise` (606) and `not-rule-bearing` (14)
-- both are FILE-LEVEL rows (`rule: null`, per the register's own row
schema comment: "`null` for a file-level disposition row"); they record
"this file has no environment-scoped rule to point at" (or no rule at
all), not a rule, so neither carries an id that belongs in a
rule-accounting set. Arithmetic check, against the register's own numbers,
not recomputed independently: 606 + 14 + 1 excluded = 621 non-rule-bearing;
1,209 + 621 = 1,830 = `rows_total`.

`EPHEMERAL_CLOUD_VM_STORY.rule_ids` = ALL rule-bearing ids UNION
`CORE_RULE_IDS`. Every rule stays in the story; nothing is omitted today.

That is 1,209 register ids IN the story, plus the 2 `CORE_RULE_IDS` members
(`naked-python-mandate`, `cross-repo-write-gating` -- NOT register ids;
every register id is `rcr-<8 hex>`, so there is no collision to resolve)
= 1,211 total members of `EPHEMERAL_CLOUD_VM_STORY.rule_ids`.

WHY NOTHING IS OMITTED, given the register marks 309 rows
`genuinely-inapplicable`. That disposition makes a rule a CANDIDATE for
omission; it does not ratify one.
`DR-an-omission-is-ratified-by-the-plane-that-enforces-the-rule` is
`accepted`, and its safe arm binds: an omission is ratified by the plane
that ENFORCES the rule recording that its guard does not fire here. No
enforcement-verdict artifact bridges an `rcr-<hash>` id to an engine-plane
guard verdict, so no omission is ratifiable today and every unestablished
case resolves toward PRESENCE.

A prior version of this constant carried 902 ids, excluding the 309. That
left those 309 in neither the story nor the omission register -- the one
state the accounting exists to make impossible -- and the emitter's own
consistency check passed anyway, because it asserted an arithmetic
identity rather than the criterion. Both are fixed; the story now carries
the class entire and the omission register is legitimately empty.

`cannot-name-a-party` (1 row) and the two DEFERRAL dispositions
(`owned-by-cloudem-06`, `engine-plane`; 84 rows together) are all kept IN
the story under this rule: none of the three is `genuinely-inapplicable`,
and the register states plainly that every disposition but that one
"keeps the rule in every story". This is also the conservative reading
where a case is not fully settled by the register's own header: presence
is the safe direction, so a row this module does not itself re-classify
stays present rather than silently dropped.

WHY A BUILT CONSTANT, NOT A RUNTIME READ
------------------------------------------
The resolver this story feeds runs at session start (see
`_environment_story.py`'s module docstring), and the register is a single
~22,000-line YAML file -- reading it there would breach the 500ms
brightline (`docs/decisions/DR-344-the-brightline-process-budget-for-
Claude-klabauter.md`) on every session start, for every session, forever. So the id
set below is a CHECKED-IN CONSTANT, derived once at build time by the
generator in this module's own `if __name__ == "__main__":` block below.
That generator is a stdlib-only LINE SCAN over the register's
`"- id: rcr-<hex>"` / `"  disposition: <value>"` row pairs -- not a YAML
parse -- because the register's own header pins the two lines as 1:1 per
row (verified: 1,830 of each, in file order, no row missing either), and
this generator is dev-time tooling, never the shipped surface, so avoiding
a third-party YAML dependency costs nothing here it would cost the
resolver.

Regenerate with (from the repo root):

    python coordinator/hooks/scripts/_environment_stories.py

which reads `state/audits/2026-09-06-doctrine-rule-class-register.yaml`,
recomputes the set above, and prints a ready-to-paste Python literal
(sorted, one row's id per emitted token) for
`_EPHEMERAL_CLOUD_VM_REGISTER_RULE_IDS` below -- diff the output against
the committed constant rather than trusting either copy on its own.

CONSTRAINTS (mirrors `_environment_story.py`'s own, stated there so both
files can be read side by side)
-----------------------------------------------------------------------
Import-light, stdlib-only, no module-level file I/O, no `subprocess`, no
third-party import. The one place this module opens a file is the
`--main--`-only regenerator below, which never runs on import.

IDEMPOTENT REGISTRATION
------------------------
`register_story` admits into `_environment_story._registry`, a plain
`dict[str, Story]` keyed by `story.name` (see that module). This module's
only module-level side effect is one `register_story(EPHEMERAL_CLOUD_VM_
STORY)` call against a frozen, constant `Story`. Python's module cache
means normal re-`import`s never re-run that line at all; the one way it
runs twice in one process is this file being loaded under two different
`sys.modules` keys (e.g. once via a bare `import _environment_stories` and
once via a differently-rooted path) -- and even then, re-registering the
identical constant `Story` under the same name is a same-key, same-value
dict overwrite, never an append or a second entry. So repeated
registration is safe by the same mechanism that already makes
`_environment_story.py` itself safe to import more than once, not by an
added guard that could itself drift from that mechanism.
"""

from __future__ import annotations

import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _environment_story import (  # noqa: E402
    CORE_RULE_IDS,
    Story,
    register_story,
)

# The composed prose -- FIXED by the plan, landed verbatim. See the module
# docstring's "WHAT THIS MODULE COMPOSES" for what was and was not changed
# in transit (the blockquote marker and its line-wrap only).
EPHEMERAL_CLOUD_VM_PROSE = "\n\n".join(
    (
        '**Where you are.** A single-tenant ephemeral Linux VM. One job, one EM session, a fresh checkout, no peer sessions and no sibling repositories on the disk. The box is yours for the length of this job and is destroyed when it ends.',
        '**What that changes, and what it does not.** Nothing on this box is shared with another session, so there is no peer to contend with and no shared worktree to keep out of. You still contend with yourself: a fan-out competes with its own subagents over four cores, and the speed bar is harder here than on a workstation, not softer.',
        '**The only durable thing here is a commit.** The filesystem, every uncommitted edit, every staged file and every note to yourself is destroyed at job end. Anything a person must see later is written, committed and pushed, or it did not happen. A question you meant to ask is not merely unanswered here — it is destroyed with the session that asked it, leaving no trace it existed. If you need an answer, land the question somewhere that outlives you.',
        "**Your work leaves this box and joins everyone else's.** Code authored here is committed, reviewed and merged into the tree every workstation checks out, so it is written for every host this fleet runs on and not for the one that produced the diff. A reviewer with full context reads what you send, and every cross-repo write is gated exactly as if they will — because they will. Nothing here is relaxed on the theory that someone is absent; where presence cannot be told, the rule stays.",
        "**What the rule count above does and does not claim.** The rule set this story carries is built from the doctrine rule-class register, which records only rules whose applicability turns on the host. A rule missing from that register carries no environment-scoped premise captured there for it — never proof that no such rule exists.",
    )
)

# Derived from `state/audits/2026-09-06-doctrine-rule-class-register.yaml`
# at build time -- see "WHY A BUILT CONSTANT, NOT A RUNTIME READ" above.
# Regenerate with: python coordinator/hooks/scripts/_environment_stories.py
# 1,209 ids: EVERY rule-bearing row id, `genuinely-inapplicable` included --
# see the module docstring on why nothing is omitted while no
# enforcement-verdict artifact exists. `CORE_RULE_IDS` is unioned in separately, below, not
# baked in here, so this constant stays a pure function of the register.
_EPHEMERAL_CLOUD_VM_REGISTER_RULE_IDS: frozenset[str] = frozenset(
    {
        'rcr-0052d77b', 'rcr-00aea9f2', 'rcr-00d3a2c2', 'rcr-00e18823', 'rcr-0114b737', 'rcr-01480747',
        'rcr-01be0e14', 'rcr-01d963a1', 'rcr-01fca1be', 'rcr-020165b5', 'rcr-020b34b3', 'rcr-02629c93',
        'rcr-0270016e', 'rcr-02d9b6b0', 'rcr-02ffecc5', 'rcr-030f0393', 'rcr-031fb9b6', 'rcr-0346caf1',
        'rcr-035e219a', 'rcr-038866b5', 'rcr-040ef3bc', 'rcr-041f48cc', 'rcr-0437292e', 'rcr-04e95999',
        'rcr-04fd0c6f', 'rcr-050db803', 'rcr-0519552e', 'rcr-05279dc1', 'rcr-056f1f83', 'rcr-057105f0',
        'rcr-05782ddf', 'rcr-05c670e8', 'rcr-05ffeb10', 'rcr-0604a17c', 'rcr-06328a30', 'rcr-06619a8b',
        'rcr-066c8ef9', 'rcr-06898af1', 'rcr-0698a7ef', 'rcr-06c47f73', 'rcr-06f8b04c', 'rcr-0790e8fb',
        'rcr-07d79754', 'rcr-083b854a', 'rcr-08659881', 'rcr-08af544c', 'rcr-08c01689', 'rcr-08c55bdb',
        'rcr-091246d7', 'rcr-091a7bf4', 'rcr-09659f63', 'rcr-0a08044b', 'rcr-0a1e5e06', 'rcr-0a23869b',
        'rcr-0b7315fa', 'rcr-0bc067d1', 'rcr-0bc0c624', 'rcr-0c00a7c8', 'rcr-0c2975f8', 'rcr-0c5e39c7',
        'rcr-0cb8771d', 'rcr-0cd8a004', 'rcr-0d20c466', 'rcr-0d85b744', 'rcr-0dc76241', 'rcr-0deb7c6b',
        'rcr-0df6ae7a', 'rcr-0e168d5d', 'rcr-0e51a395', 'rcr-0e684ca4', 'rcr-0f0a4891', 'rcr-0f2893ca',
        'rcr-0f327991', 'rcr-0f6c499f', 'rcr-0f6e59dd', 'rcr-0f9673b2', 'rcr-0ff8c35c', 'rcr-104ffeed',
        'rcr-108b4337', 'rcr-10d4c22e', 'rcr-10ed7ef0', 'rcr-10eda4b4', 'rcr-118758ab', 'rcr-1198c59f',
        'rcr-11c3712a', 'rcr-11d35bef', 'rcr-11d804c0', 'rcr-11f08338', 'rcr-11ffa083', 'rcr-1201f062',
        'rcr-122d8795', 'rcr-127aa869', 'rcr-12a3d51b', 'rcr-12bdd743', 'rcr-12f32bdd', 'rcr-1358c6c6',
        'rcr-13d7ea50', 'rcr-13f4fe5e', 'rcr-14772e38', 'rcr-1480fe1f', 'rcr-14c25a3e', 'rcr-14cf52b7',
        'rcr-14da2720', 'rcr-1502f44f', 'rcr-15380bbb', 'rcr-154591a4', 'rcr-155de316', 'rcr-15886b16',
        'rcr-15b7ae27', 'rcr-15ece1fb', 'rcr-161b67fd', 'rcr-163ed6e1', 'rcr-167dd159', 'rcr-1684a374',
        'rcr-16959663', 'rcr-16c52f30', 'rcr-171c17ba', 'rcr-17b11318', 'rcr-17eccb39', 'rcr-17f8353d',
        'rcr-17f9e008', 'rcr-17fbae2b', 'rcr-18333c47', 'rcr-184359a5', 'rcr-1870ef96', 'rcr-189a8444',
        'rcr-18ade142', 'rcr-18b0301b', 'rcr-18c0650f', 'rcr-191de44d', 'rcr-193b8a84', 'rcr-19597417',
        'rcr-1969c85d', 'rcr-19cfee16', 'rcr-19f4f4bf', 'rcr-1a196159', 'rcr-1a2413e2', 'rcr-1a3cd4c8',
        'rcr-1a911884', 'rcr-1ab0dc65', 'rcr-1abeac30', 'rcr-1ac1f6e6', 'rcr-1afeb652', 'rcr-1bb5ffe1',
        'rcr-1bc2e805', 'rcr-1be64608', 'rcr-1c950103', 'rcr-1c98e008', 'rcr-1cc6f6c3', 'rcr-1cedf65b',
        'rcr-1d3c21c0', 'rcr-1d79dbf1', 'rcr-1e0ef61c', 'rcr-1e5ef914', 'rcr-1e66ffc9', 'rcr-1e6bc4ee',
        'rcr-1e934b80', 'rcr-1ec2f9d2', 'rcr-1ef74c35', 'rcr-1f389481', 'rcr-1f75f8ef', 'rcr-1f7e5ac1',
        'rcr-1f9de6ad', 'rcr-1fd43e50', 'rcr-1fe8501b', 'rcr-20114693', 'rcr-20367057', 'rcr-2038d883',
        'rcr-20477aa6', 'rcr-20a60652', 'rcr-20e4fdb3', 'rcr-2111bfa3', 'rcr-215fbb07', 'rcr-21e975f4',
        'rcr-22c696ec', 'rcr-22f78641', 'rcr-22f7ebf3', 'rcr-23234f1b', 'rcr-232dc988', 'rcr-238c0bfd',
        'rcr-238c641c', 'rcr-239b194f', 'rcr-23ac7ae7', 'rcr-23f6c217', 'rcr-242ac2ac', 'rcr-246b3698',
        'rcr-24b08549', 'rcr-24bf0bbc', 'rcr-24d9c54d', 'rcr-24ebe19a', 'rcr-24f731ad', 'rcr-251c8fa4',
        'rcr-253dc464', 'rcr-255c085e', 'rcr-25c0ee1c', 'rcr-26ce7e50', 'rcr-2720469d', 'rcr-274bcca3',
        'rcr-2752e8ed', 'rcr-275c4ced', 'rcr-27870a59', 'rcr-279e9bf7', 'rcr-281ad138', 'rcr-285b9e77',
        'rcr-28992045', 'rcr-28d84936', 'rcr-28ec54d7', 'rcr-28f769d1', 'rcr-290a58db', 'rcr-2917b06d',
        'rcr-291959a1', 'rcr-2963c8e7', 'rcr-297a7b9a', 'rcr-29d277ce', 'rcr-2a36d355', 'rcr-2a3d6ca7',
        'rcr-2a403630', 'rcr-2adf0f0a', 'rcr-2aff38a8', 'rcr-2b6623e0', 'rcr-2b78b910', 'rcr-2bd34e5c',
        'rcr-2be2221f', 'rcr-2bfa90b4', 'rcr-2c0147ed', 'rcr-2c91df5d', 'rcr-2ca05e23', 'rcr-2cd047ac',
        'rcr-2cd7f4b6', 'rcr-2cdc1149', 'rcr-2ceefae8', 'rcr-2cf234d6', 'rcr-2cff427d', 'rcr-2d1b8a7b',
        'rcr-2d4c7526', 'rcr-2d62ff78', 'rcr-2d8e3b49', 'rcr-2d993f04', 'rcr-2dae9c16', 'rcr-2e53d30e',
        'rcr-2e89c368', 'rcr-2e8d15ad', 'rcr-2eed419a', 'rcr-2f2bccae', 'rcr-2f361820', 'rcr-2f740ec8',
        'rcr-2ff8c412', 'rcr-3042e0ab', 'rcr-3075dc8d', 'rcr-30a428d7', 'rcr-30b89d24', 'rcr-31208707',
        'rcr-31c2fe18', 'rcr-31e03b7a', 'rcr-31fc9cb3', 'rcr-32dfc135', 'rcr-32f378d1', 'rcr-330500d1',
        'rcr-336e37fb', 'rcr-3372cc0d', 'rcr-33ac8a31', 'rcr-33e6c7c9', 'rcr-34a86ce9', 'rcr-34ad14a4',
        'rcr-34c02263', 'rcr-34f0ee67', 'rcr-3521d4e2', 'rcr-35272de4', 'rcr-353173d3', 'rcr-357b7d05',
        'rcr-359a03e8', 'rcr-35d238d2', 'rcr-35e9d1db', 'rcr-3640c40c', 'rcr-36921420', 'rcr-36f9f9c4',
        'rcr-375cbce9', 'rcr-37c1b36f', 'rcr-37e2a5df', 'rcr-3813ab0d', 'rcr-381c01fe', 'rcr-382f9cf5',
        'rcr-38418730', 'rcr-388e6ff6', 'rcr-38bf7d11', 'rcr-38c0dc7d', 'rcr-38d5ad49', 'rcr-38fa4513',
        'rcr-3950ff40', 'rcr-3996899c', 'rcr-39b7d31a', 'rcr-39c397b8', 'rcr-39d5108c', 'rcr-3a20ebab',
        'rcr-3a417e37', 'rcr-3a736dfa', 'rcr-3a97ffe1', 'rcr-3ae81080', 'rcr-3af79185', 'rcr-3b1a0194',
        'rcr-3b57b7a9', 'rcr-3b57e242', 'rcr-3b63bc6c', 'rcr-3b6ff9e9', 'rcr-3b8d9e73', 'rcr-3c1dbe19',
        'rcr-3c33fd42', 'rcr-3c34b2c3', 'rcr-3cac55a4', 'rcr-3cb70fba', 'rcr-3d1ef1ec', 'rcr-3d501b5f',
        'rcr-3d53a789', 'rcr-3d65572c', 'rcr-3e20df78', 'rcr-3e21f06f', 'rcr-3e42744a', 'rcr-3e995c20',
        'rcr-3ec79966', 'rcr-3ef5ed3a', 'rcr-3efb9b4d', 'rcr-3f107f66', 'rcr-3f55a897', 'rcr-3f6e42d7',
        'rcr-3f7bf5aa', 'rcr-3f8aa633', 'rcr-3fdcab31', 'rcr-40965628', 'rcr-40f6dac6', 'rcr-41061c87',
        'rcr-4130ca75', 'rcr-413650df', 'rcr-4168eaa5', 'rcr-418e4082', 'rcr-41c32845', 'rcr-42221c03',
        'rcr-425b5963', 'rcr-428a52f8', 'rcr-42bbfb27', 'rcr-42bfe333', 'rcr-433c017e', 'rcr-435ec828',
        'rcr-43621f93', 'rcr-43d16fb1', 'rcr-43d45b71', 'rcr-43decbc4', 'rcr-4424ecff', 'rcr-44c036ed',
        'rcr-44ecc79a', 'rcr-450012ce', 'rcr-451d862c', 'rcr-456d30a9', 'rcr-459939e7', 'rcr-45b85098',
        'rcr-45ddf87c', 'rcr-466624d4', 'rcr-46f1c76b', 'rcr-46ff96bd', 'rcr-471032a6', 'rcr-4730e693',
        'rcr-476949c0', 'rcr-47c2c26c', 'rcr-47c79850', 'rcr-48337876', 'rcr-48559baa', 'rcr-48889164',
        'rcr-48a7a07c', 'rcr-48aef468', 'rcr-48d5d96c', 'rcr-48d82bf7', 'rcr-48d8f6fc', 'rcr-48eef8bb',
        'rcr-48f4d8b4', 'rcr-492132c2', 'rcr-4942bbc2', 'rcr-49525f1b', 'rcr-499aeaa7', 'rcr-49ba5556',
        'rcr-49bfa3fd', 'rcr-4a31c433', 'rcr-4a4fb4fe', 'rcr-4a982fa7', 'rcr-4aa109f5', 'rcr-4adbda3d',
        'rcr-4ade8c75', 'rcr-4b190a8d', 'rcr-4bda61c7', 'rcr-4be34e6b', 'rcr-4c302656', 'rcr-4c4a9f54',
        'rcr-4c9e543c', 'rcr-4cbdb7b9', 'rcr-4cf7ddbd', 'rcr-4d010c3f', 'rcr-4d3b97ce', 'rcr-4dd38fab',
        'rcr-4dfbc408', 'rcr-4e5cc6e3', 'rcr-4ec600e6', 'rcr-4ec67262', 'rcr-4eebbdfd', 'rcr-4ef07d9b',
        'rcr-4f7aa60e', 'rcr-4f9e19f0', 'rcr-4fa2a2e0', 'rcr-50584cd8', 'rcr-5079e128', 'rcr-50b53c4c',
        'rcr-50eb79b1', 'rcr-516a9278', 'rcr-519dae8b', 'rcr-51cb2f3c', 'rcr-51dd4499', 'rcr-51e5073f',
        'rcr-524bded1', 'rcr-525ac5e8', 'rcr-525d7b63', 'rcr-52c49254', 'rcr-52e71afc', 'rcr-53688529',
        'rcr-53b42fae', 'rcr-53ff14fd', 'rcr-540e9479', 'rcr-547b21c5', 'rcr-54b7195c', 'rcr-54e74cc3',
        'rcr-5509771a', 'rcr-5532b517', 'rcr-5535493b', 'rcr-555a207f', 'rcr-55e18518', 'rcr-56144803',
        'rcr-56325656', 'rcr-56431a27', 'rcr-56537103', 'rcr-566178b5', 'rcr-5696ff2c', 'rcr-5697c0ed',
        'rcr-56a3297e', 'rcr-56c15404', 'rcr-56cb76a2', 'rcr-570191d3', 'rcr-57497cac', 'rcr-5755e282',
        'rcr-57802d09', 'rcr-57906331', 'rcr-57ef436a', 'rcr-58096dcc', 'rcr-581616bb', 'rcr-58b49549',
        'rcr-58c796ec', 'rcr-58dc59ef', 'rcr-590bf1ec', 'rcr-593f85d9', 'rcr-594bf207', 'rcr-5996883a',
        'rcr-599b31fa', 'rcr-5a2212ad', 'rcr-5ab67f8e', 'rcr-5aebfab0', 'rcr-5aec647c', 'rcr-5b9f31cd',
        'rcr-5beabda7', 'rcr-5c02e5f1', 'rcr-5c30d744', 'rcr-5c476f6a', 'rcr-5ce33b10', 'rcr-5d61ed6f',
        'rcr-5d8c67e0', 'rcr-5dedb46d', 'rcr-5dfb3575', 'rcr-5e4c4a7e', 'rcr-5e56321d', 'rcr-5e631389',
        'rcr-5ec804c9', 'rcr-5f3da779', 'rcr-5f82624b', 'rcr-5fe11f85', 'rcr-5fe5df75', 'rcr-5ffc789c',
        'rcr-60993de8', 'rcr-60a83456', 'rcr-60b0d8c4', 'rcr-60e392ee', 'rcr-611c45a9', 'rcr-61ebc4eb',
        'rcr-62327d00', 'rcr-626ba45e', 'rcr-62962ba8', 'rcr-63079d78', 'rcr-6320fdc1', 'rcr-635d4745',
        'rcr-638999a6', 'rcr-63e4f647', 'rcr-645e7da6', 'rcr-64a3f315', 'rcr-64bc6d52', 'rcr-64c01031',
        'rcr-651ada68', 'rcr-651e4b82', 'rcr-6577a06f', 'rcr-65917665', 'rcr-659b2470', 'rcr-659d4996',
        'rcr-65e3417c', 'rcr-65ebfc4c', 'rcr-66576c43', 'rcr-66b4e126', 'rcr-66bbaa5a', 'rcr-673347cd',
        'rcr-675b427d', 'rcr-6781465d', 'rcr-678febd7', 'rcr-679b7ce2', 'rcr-67a1a491', 'rcr-67ad4f31',
        'rcr-67ed993e', 'rcr-68842698', 'rcr-68f876d1', 'rcr-69055b26', 'rcr-6914a665', 'rcr-6940d86c',
        'rcr-69a54fa1', 'rcr-69cae219', 'rcr-69ecd7de', 'rcr-69f0c60f', 'rcr-69f52757', 'rcr-6a56861d',
        'rcr-6a6eb8e3', 'rcr-6ab2de40', 'rcr-6acfeefa', 'rcr-6b17c86a', 'rcr-6b3de3b1', 'rcr-6b521198',
        'rcr-6b6eb828', 'rcr-6b824c39', 'rcr-6bd0c55b', 'rcr-6c161068', 'rcr-6c1b97b6', 'rcr-6c23360e',
        'rcr-6c574122', 'rcr-6cdb3841', 'rcr-6cfa038c', 'rcr-6d5bdb23', 'rcr-6d7fe6a3', 'rcr-6d8391a6',
        'rcr-6d9867da', 'rcr-6da16b7b', 'rcr-6dabe9eb', 'rcr-6e1280ec', 'rcr-6e1c4edd', 'rcr-6ede9116',
        'rcr-6f3f4596', 'rcr-6f4ffab1', 'rcr-6f673d09', 'rcr-6f8a3c3e', 'rcr-703b2067', 'rcr-706bffbd',
        'rcr-70c3c51f', 'rcr-70c9c0db', 'rcr-70d6e9f0', 'rcr-710afa28', 'rcr-71812b68', 'rcr-718f96f8',
        'rcr-71db9763', 'rcr-71f7f36a', 'rcr-71ffbb5f', 'rcr-7205d596', 'rcr-720cd20a', 'rcr-72263192',
        'rcr-723bb8e3', 'rcr-72487611', 'rcr-72b1622b', 'rcr-72bca05c', 'rcr-7307ef22', 'rcr-73098c02',
        'rcr-73666865', 'rcr-738640d7', 'rcr-73b30af0', 'rcr-73b7180d', 'rcr-73ede31d', 'rcr-740acf54',
        'rcr-7412bf7a', 'rcr-7429bc4f', 'rcr-742f1c1e', 'rcr-7435bb00', 'rcr-748ce535', 'rcr-748dcf23',
        'rcr-7495b815', 'rcr-74973ca0', 'rcr-74ddb14c', 'rcr-7537b9ac', 'rcr-75472054', 'rcr-756596c3',
        'rcr-759c401d', 'rcr-75d64096', 'rcr-76145a0b', 'rcr-7615c1f5', 'rcr-761a0fb7', 'rcr-7627adb2',
        'rcr-763f71e3', 'rcr-76478fc1', 'rcr-7653adb3', 'rcr-765ff057', 'rcr-76a1613e', 'rcr-76a76171',
        'rcr-76b1790e', 'rcr-76dff6de', 'rcr-76e6bd93', 'rcr-77338f99', 'rcr-773bcedc', 'rcr-7743090d',
        'rcr-7746b4ec', 'rcr-77a2db50', 'rcr-78205341', 'rcr-78205950', 'rcr-78466e0c', 'rcr-785d7c46',
        'rcr-786df75e', 'rcr-78bedf3b', 'rcr-78d13ae2', 'rcr-79484aef', 'rcr-797a6be6', 'rcr-79c882f5',
        'rcr-79caf099', 'rcr-79eccd2a', 'rcr-7a0da061', 'rcr-7a5c28e5', 'rcr-7aa5429d', 'rcr-7ac67408',
        'rcr-7b4a1dd8', 'rcr-7b62490e', 'rcr-7b679b1d', 'rcr-7b96eb2a', 'rcr-7bab2c54', 'rcr-7bb3776d',
        'rcr-7bce5d7b', 'rcr-7bdd584c', 'rcr-7c1dbebf', 'rcr-7c387606', 'rcr-7c5c5f33', 'rcr-7dcf3459',
        'rcr-7e582eee', 'rcr-7e66c42e', 'rcr-7eaa1c53', 'rcr-7f1173bb', 'rcr-7f53c8f6', 'rcr-7f7418bb',
        'rcr-7fce900a', 'rcr-7feaaf57', 'rcr-801ce00f', 'rcr-80dca259', 'rcr-80dfaa57', 'rcr-8114ee82',
        'rcr-813c1179', 'rcr-81af042b', 'rcr-81b8a23b', 'rcr-820d46fb', 'rcr-8224fa4f', 'rcr-82ef562f',
        'rcr-8324cd55', 'rcr-83531486', 'rcr-83cdf6a3', 'rcr-83cf50b0', 'rcr-83e0a982', 'rcr-83fb1ea6',
        'rcr-842096ee', 'rcr-84219753', 'rcr-845859f1', 'rcr-8475dbff', 'rcr-84a08171', 'rcr-84ad1917',
        'rcr-84e18c92', 'rcr-855bb643', 'rcr-85b3e223', 'rcr-85bc2d74', 'rcr-85bc39cd', 'rcr-85e5a6aa',
        'rcr-87899f5f', 'rcr-87b4b861', 'rcr-87cbc4ba', 'rcr-88022a50', 'rcr-882bf835', 'rcr-8868ecd6',
        'rcr-8889206a', 'rcr-88a084a7', 'rcr-88b75fcc', 'rcr-8906640d', 'rcr-89a02409', 'rcr-89b8d8b9',
        'rcr-89d9c1e6', 'rcr-89f5aec5', 'rcr-8a483016', 'rcr-8a89f9b5', 'rcr-8a9faae0', 'rcr-8ac2473a',
        'rcr-8ad7de49', 'rcr-8aeb2346', 'rcr-8b01a8d1', 'rcr-8b05706e', 'rcr-8b0a3c54', 'rcr-8b7d5207',
        'rcr-8bf9664e', 'rcr-8c20f68d', 'rcr-8c43280e', 'rcr-8cf5d715', 'rcr-8d1a234d', 'rcr-8d2587ad',
        'rcr-8d316066', 'rcr-8d362abd', 'rcr-8d39e600', 'rcr-8d3c7ac5', 'rcr-8d41924f', 'rcr-8d710da8',
        'rcr-8d8ec9bb', 'rcr-8e319ccd', 'rcr-8e33a7c3', 'rcr-8e456947', 'rcr-8e62f56d', 'rcr-8f32c576',
        'rcr-8f58c16b', 'rcr-8f700a8f', 'rcr-8fa133eb', 'rcr-8ff89791', 'rcr-9015cdda', 'rcr-9042d4bc',
        'rcr-9048dc14', 'rcr-9098cf69', 'rcr-909cbac8', 'rcr-90c5a906', 'rcr-90e4da66', 'rcr-90f3f931',
        'rcr-90fcffcc', 'rcr-911b27b9', 'rcr-919e6cfe', 'rcr-91a5a519', 'rcr-91ae151e', 'rcr-91b479d2',
        'rcr-91bbb023', 'rcr-91edf5f2', 'rcr-922826c6', 'rcr-927091f6', 'rcr-9273c95c', 'rcr-92d7db84',
        'rcr-92e7fe7b', 'rcr-92ff63b8', 'rcr-9302e5f9', 'rcr-933443a6', 'rcr-937e8d17', 'rcr-93d39222',
        'rcr-93fbd13d', 'rcr-9414169e', 'rcr-9432f867', 'rcr-94bf7488', 'rcr-94c24bd6', 'rcr-9513ed26',
        'rcr-9540bbce', 'rcr-95cf4f0a', 'rcr-95eb936a', 'rcr-9627634e', 'rcr-96981c2e', 'rcr-97319b73',
        'rcr-973cfb44', 'rcr-9761fde0', 'rcr-97a5a251', 'rcr-97d39ba2', 'rcr-98251450', 'rcr-98ac3594',
        'rcr-98dbbbeb', 'rcr-98f1b35e', 'rcr-98fb3bc6', 'rcr-9991130b', 'rcr-99bc0985', 'rcr-99be447d',
        'rcr-9a025fc9', 'rcr-9a1c5819', 'rcr-9a45df20', 'rcr-9a5c039a', 'rcr-9a636262', 'rcr-9aa6792b',
        'rcr-9ac62cb2', 'rcr-9ac6a91b', 'rcr-9ad2389c', 'rcr-9af2bd39', 'rcr-9b5a9a8a', 'rcr-9bf33c10',
        'rcr-9c2c4df0', 'rcr-9c3b0d0c', 'rcr-9c48d395', 'rcr-9cb14710', 'rcr-9cc44339', 'rcr-9d2c4758',
        'rcr-9d3b6704', 'rcr-9d3fc0a5', 'rcr-9de5cbf9', 'rcr-9e5338db', 'rcr-9e621b17', 'rcr-9e667dea',
        'rcr-9e6ee9ed', 'rcr-9e8a80d3', 'rcr-9e9c7476', 'rcr-9f04dcd1', 'rcr-9f068fec', 'rcr-9f4ae77c',
        'rcr-9f597203', 'rcr-9f7d1908', 'rcr-9fac7e82', 'rcr-a052828d', 'rcr-a07c961c', 'rcr-a0f94429',
        'rcr-a12d1a4a', 'rcr-a189dd5b', 'rcr-a20b6c50', 'rcr-a2f42a03', 'rcr-a2f7fd2d', 'rcr-a38c2d81',
        'rcr-a391a321', 'rcr-a39288f8', 'rcr-a3c23fe4', 'rcr-a3d306ca', 'rcr-a4647a8f', 'rcr-a5154449',
        'rcr-a524b38e', 'rcr-a5303b02', 'rcr-a542796e', 'rcr-a568149b', 'rcr-a5801d3e', 'rcr-a61f8cc2',
        'rcr-a6c9d2c0', 'rcr-a6e6efb9', 'rcr-a70ae7dc', 'rcr-a724349c', 'rcr-a77d01e4', 'rcr-a7bb4989',
        'rcr-a7de8e95', 'rcr-a7fcaa1c', 'rcr-a845c6e7', 'rcr-a848af64', 'rcr-a871aced', 'rcr-a8963fc5',
        'rcr-a8f0c184', 'rcr-a8f2fbad', 'rcr-a92a32cd', 'rcr-a940ea6e', 'rcr-a952452a', 'rcr-a97fdc02',
        'rcr-a9814e89', 'rcr-aa4be36c', 'rcr-aa61e07c', 'rcr-aa984e44', 'rcr-aaebefda', 'rcr-ab04e19a',
        'rcr-ab62ab59', 'rcr-ab88de4f', 'rcr-aba37119', 'rcr-ac4735a6', 'rcr-acabf760', 'rcr-acb9362d',
        'rcr-ad063bf2', 'rcr-ad7f00eb', 'rcr-adc898e4', 'rcr-ae5383ac', 'rcr-ae8adeef', 'rcr-af3a7d14',
        'rcr-af9d5a3b', 'rcr-afb0ecf3', 'rcr-afb7de25', 'rcr-afda570e', 'rcr-affa5f09', 'rcr-b00ee8b1',
        'rcr-b0413bc7', 'rcr-b042a659', 'rcr-b063b1b5', 'rcr-b0748264', 'rcr-b07b4a37', 'rcr-b08e5bcd',
        'rcr-b0b534de', 'rcr-b18b90b6', 'rcr-b1e3d6c0', 'rcr-b224d167', 'rcr-b22ab158', 'rcr-b2f1b999',
        'rcr-b37a5e8b', 'rcr-b3f242c1', 'rcr-b4166b1b', 'rcr-b41ed755', 'rcr-b434f433', 'rcr-b445d0f7',
        'rcr-b496e41d', 'rcr-b5e0385c', 'rcr-b5f78d9b', 'rcr-b60dd3e0', 'rcr-b6556431', 'rcr-b687efdd',
        'rcr-b69dfedf', 'rcr-b6c40fd3', 'rcr-b743752e', 'rcr-b74c7f49', 'rcr-b74dd31d', 'rcr-b798d952',
        'rcr-b8242795', 'rcr-b83042ad', 'rcr-b8ad109c', 'rcr-b8ee3d26', 'rcr-b90b0057', 'rcr-b99a9be5',
        'rcr-b9d70efd', 'rcr-ba0a750b', 'rcr-ba49bd9f', 'rcr-ba4ab75a', 'rcr-ba584f20', 'rcr-bab7c90f',
        'rcr-bad8cec8', 'rcr-bafaa023', 'rcr-bbd55b2e', 'rcr-bc0789de', 'rcr-bc8d8773', 'rcr-bcf5201b',
        'rcr-bd2cc27e', 'rcr-bd35dc47', 'rcr-bd4f893a', 'rcr-bd522698', 'rcr-bd5a86f4', 'rcr-bd64985a',
        'rcr-bd7168fa', 'rcr-bdd62f7d', 'rcr-bdee5298', 'rcr-bed51b2c', 'rcr-bf48674d', 'rcr-bf593181',
        'rcr-bf8d77c9', 'rcr-c139d8f6', 'rcr-c1450c79', 'rcr-c1d06c0f', 'rcr-c1ddf8f6', 'rcr-c245e0fe',
        'rcr-c2b0e808', 'rcr-c2dd241d', 'rcr-c39d72a5', 'rcr-c3ab58fc', 'rcr-c3b6fb20', 'rcr-c3b77ae8',
        'rcr-c45c326a', 'rcr-c46722c4', 'rcr-c46de77a', 'rcr-c47e2b78', 'rcr-c487871c', 'rcr-c4be886e',
        'rcr-c4e834f8', 'rcr-c5793120', 'rcr-c5a874c9', 'rcr-c638806c', 'rcr-c6b87a15', 'rcr-c6c45b7b',
        'rcr-c6d36b22', 'rcr-c70a840a', 'rcr-c77a80fe', 'rcr-c80163f0', 'rcr-c869ffaa', 'rcr-c8a1c32c',
        'rcr-c8ab4dc5', 'rcr-c8d8039c', 'rcr-c96b8dc7', 'rcr-c97f943a', 'rcr-c984265f', 'rcr-c98fac22',
        'rcr-c994977a', 'rcr-c9fc2ae5', 'rcr-ca676131', 'rcr-caaf2fca', 'rcr-cb0953fd', 'rcr-cb0b2840',
        'rcr-cb4093af', 'rcr-cb4db54c', 'rcr-cb7d4056', 'rcr-cba217b1', 'rcr-cbabe3db', 'rcr-cbe25110',
        'rcr-cbec4da3', 'rcr-cbf7cd28', 'rcr-cc385977', 'rcr-cc602d63', 'rcr-ccc99ea4', 'rcr-cccaabbb',
        'rcr-cd40df77', 'rcr-cd53dd60', 'rcr-cdaf1105', 'rcr-ced9f362', 'rcr-cede0d7b', 'rcr-cf13d8b2',
        'rcr-cf7c4faa', 'rcr-cf9ba1b3', 'rcr-d07ad850', 'rcr-d0ccb3e7', 'rcr-d1047aa8', 'rcr-d112eaf6',
        'rcr-d1ab71aa', 'rcr-d243c450', 'rcr-d2a0f087', 'rcr-d2a78f33', 'rcr-d2b2165e', 'rcr-d345a377',
        'rcr-d3a944b6', 'rcr-d3cd9f30', 'rcr-d3eaedb7', 'rcr-d411f437', 'rcr-d45107b0', 'rcr-d4567556',
        'rcr-d457a507', 'rcr-d4ac991c', 'rcr-d52d9617', 'rcr-d5fc52d9', 'rcr-d6256d3a', 'rcr-d6401183',
        'rcr-d69b18db', 'rcr-d6a4aef6', 'rcr-d6b29933', 'rcr-d7311789', 'rcr-d73c847a', 'rcr-d84a264d',
        'rcr-d854fa30', 'rcr-d87a988e', 'rcr-d8a56ebe', 'rcr-d93e0ca7', 'rcr-d9b4f0ee', 'rcr-d9e8b695',
        'rcr-d9ede284', 'rcr-da0d38dd', 'rcr-da180a0c', 'rcr-da53c0b6', 'rcr-da8a0f7e', 'rcr-daa4999c',
        'rcr-dab241ac', 'rcr-dad24a96', 'rcr-dae0b9d4', 'rcr-db15f0d3', 'rcr-db2714ab', 'rcr-db661201',
        'rcr-dbe7a4b8', 'rcr-dc172a26', 'rcr-dc1c423f', 'rcr-dc57ef8b', 'rcr-dc65370b', 'rcr-dc6ecb2a',
        'rcr-dcf5f317', 'rcr-dd1b3000', 'rcr-dd3c1397', 'rcr-dd635bd9', 'rcr-dd8d4d51', 'rcr-de2b676d',
        'rcr-dea5d482', 'rcr-df329752', 'rcr-dfd28cde', 'rcr-dfd33e2b', 'rcr-dfd8deac', 'rcr-dfe02859',
        'rcr-dfe05371', 'rcr-dffc93da', 'rcr-e00db91f', 'rcr-e0313700', 'rcr-e0a5dd64', 'rcr-e0b37f17',
        'rcr-e0e28391', 'rcr-e1c5fa51', 'rcr-e1fb33ec', 'rcr-e248c52c', 'rcr-e251e8ac', 'rcr-e28db7c3',
        'rcr-e28e457b', 'rcr-e29076de', 'rcr-e291cbdc', 'rcr-e2ce8426', 'rcr-e2f3d080', 'rcr-e36a54e4',
        'rcr-e38d8c0d', 'rcr-e3bc63c0', 'rcr-e3c00593', 'rcr-e402b03c', 'rcr-e42d1c56', 'rcr-e459ae26',
        'rcr-e4b10c36', 'rcr-e4eaac64', 'rcr-e5491ac6', 'rcr-e5c32cfc', 'rcr-e5e860c2', 'rcr-e60267ca',
        'rcr-e6341699', 'rcr-e6dc9baa', 'rcr-e7694f16', 'rcr-e76f6725', 'rcr-e78230f7', 'rcr-e7f88c2f',
        'rcr-e8946235', 'rcr-e8b4c7d9', 'rcr-e8b9149d', 'rcr-e8f6fa44', 'rcr-e93610be', 'rcr-e9779849',
        'rcr-e97876d2', 'rcr-e987600e', 'rcr-e9c4df7a', 'rcr-e9fe0595', 'rcr-ea679893', 'rcr-ea9937df',
        'rcr-ead308c9', 'rcr-ead44b61', 'rcr-eada8ee4', 'rcr-eb815483', 'rcr-eb876c93', 'rcr-eba2dbee',
        'rcr-ebf219bb', 'rcr-ec30b9ea', 'rcr-ec321ce3', 'rcr-ec896693', 'rcr-ec9f7a7d', 'rcr-eccbce18',
        'rcr-ed16ea4c', 'rcr-ed733b36', 'rcr-ed99b378', 'rcr-ee05406b', 'rcr-ee774a28', 'rcr-ee9fe52a',
        'rcr-ef180d86', 'rcr-ef3303bb', 'rcr-ef33602e', 'rcr-ef9af4df', 'rcr-efae4b8f', 'rcr-efc3a7f1',
        'rcr-f0796db0', 'rcr-f09eab1c', 'rcr-f0f76aee', 'rcr-f1294a52', 'rcr-f1563c6a', 'rcr-f1605399',
        'rcr-f1794fdf', 'rcr-f190e453', 'rcr-f1cb5897', 'rcr-f1fabf88', 'rcr-f1fca7d0', 'rcr-f2271d4a',
        'rcr-f22c201f', 'rcr-f2905646', 'rcr-f2d24427', 'rcr-f337d330', 'rcr-f36d471a', 'rcr-f3b4f275',
        'rcr-f440e546', 'rcr-f47f805b', 'rcr-f487a3a7', 'rcr-f4bdf57d', 'rcr-f5538e08', 'rcr-f58424c5',
        'rcr-f58b5d24', 'rcr-f61e5eb3', 'rcr-f62330b4', 'rcr-f634b138', 'rcr-f6798de0', 'rcr-f67f9db2',
        'rcr-f70dd605', 'rcr-f7196b9b', 'rcr-f739b3d8', 'rcr-f7863a0c', 'rcr-f7b94a76', 'rcr-f7cdfbd5',
        'rcr-f82ffd46', 'rcr-f8719582', 'rcr-f87adc16', 'rcr-f8843235', 'rcr-f88802d4', 'rcr-f8c1cb04',
        'rcr-f8f05e00', 'rcr-f8fc7bdd', 'rcr-f9185f8a', 'rcr-fa15c566', 'rcr-fa253419', 'rcr-fa38f1b6',
        'rcr-fa3dc601', 'rcr-fa47f8b7', 'rcr-fa9bd59f', 'rcr-fad707e3', 'rcr-fb160811', 'rcr-fb6cdefa',
        'rcr-fba42fe3', 'rcr-fbaa3f2f', 'rcr-fbcfa583', 'rcr-fbd2aeb3', 'rcr-fc3e0621', 'rcr-fc503ced',
        'rcr-fc8c4c55', 'rcr-fca1257a', 'rcr-fca2b760', 'rcr-fcb8155a', 'rcr-fcc494cb', 'rcr-fce62f98',
        'rcr-fce7996d', 'rcr-fd08650b', 'rcr-fd31e853', 'rcr-fdc9e51e', 'rcr-fe468fb4', 'rcr-fe4e8c9c',
        'rcr-fe9f5fae', 'rcr-ff10b6f9', 'rcr-ff336c4b', 'rcr-ff3f41f2', 'rcr-ff4a1f48', 'rcr-ff4aad5e',
        'rcr-ff4cefbf', 'rcr-ffd447dc', 'rcr-ffe28284',
    }
)

EPHEMERAL_CLOUD_VM_STORY = Story(
    name="ephemeral-cloud-vm",
    prose=EPHEMERAL_CLOUD_VM_PROSE,
    rule_ids=_EPHEMERAL_CLOUD_VM_REGISTER_RULE_IDS | CORE_RULE_IDS,
)

# `register_story` calls `validate_story` on the way in -- a story missing
# either `CORE_RULE_IDS` member raises `CoreOmissionError` here, at import
# time, rather than admitting a core-omitting story silently. See
# "IDEMPOTENT REGISTRATION" above for why re-running this line is safe.
register_story(EPHEMERAL_CLOUD_VM_STORY)

# MEMBERSHIP VERDICTS. Bar: a candidate is a member only if at least one
# register row takes a different disposition in it than in every other
# member; candidates with identical omission sets collapse into one story.
#
# INPUT READ: the doctrine rule-class register's 309 `genuinely-inapplicable`
# DISPOSITIONS -- what would omit once an enforcement verdict exists -- not the
# omission register's emitted rows, which are empty for every story
# (`carrying_an_omission_row_count: 0`) and would make distinctness vacuous.
# That register classifies against ONE target, the single-tenant ephemeral VM,
# measured against a reference environment that is a workstation (header
# "THE TARGET ENVIRONMENT"; "The reference environment on axes 1 and 2"). Its
# `per_story` block carries only `strictest` and `ephemeral-cloud-vm`, so the
# bar is APPLIED only to `ephemeral-cloud-vm`; `workstation` and `unmanaged`
# have no register input and are decided by construction and by fail-safe, not
# by argued dispositions. The JOB axis collapses structurally: the resolver
# returns a HOST-only scalar, so no JOB variant is selectable.
#
# `candidate` is `Story.name` for a composed story, so the table joins to the
# registry by name. A COLLAPSED row's `basis` names the member it collapses
# into. Do not add an assertion that no two stories share an omission set:
# over empty sets it is vacuously green and the omission ledger owns it.
MEMBER = "MEMBER"
COLLAPSED = "COLLAPSED"

STORY_MEMBERSHIP_VERDICTS: tuple[tuple[str, str, str], ...] = (
    (
        "strictest",
        MEMBER,
        "The fail-safe story every resolver failure returns; it omits nothing "
        "and is the reference the other candidates are measured against.",
    ),
    (
        "ephemeral-cloud-vm",
        MEMBER,
        "309 `genuinely-inapplicable` register dispositions are omission "
        "candidates here and none is in `strictest`'s omission set; the only "
        "input on which the bar discriminates.",
    ),
    (
        "workstation",
        COLLAPSED,
        "Collapses into `strictest`: it IS the register's reference "
        "environment, so no rule is inapplicable there and its omission set "
        "is empty.",
    ),
    (
        "unmanaged",
        COLLAPSED,
        "Collapses into `strictest` by the fail-safe: no register basis "
        "exists, so there is no evidence of a distinct omission set.",
    ),
    (
        "job-axis",
        COLLAPSED,
        "Collapses into `strictest` for every attended/unattended variant of "
        "an unselected HOST, and into the HOST-selected member otherwise: "
        "cloudem-04 D1 pins `resolve_environment_story()` to a HOST-only "
        "scalar, so no JOB variant can be selected as a distinct story.",
    ),
)


def _derive_register_rule_ids(
    register_path: str, omitted_ids: "frozenset[str] | None" = None
) -> "frozenset[str]":
    """Stdlib-only line scan over the register's `"- id: rcr-<hex>"` /
    `"  disposition: <value>"` row pairs (see the module docstring for why
    this is a line scan and not a YAML parse). Returns EVERY rule-bearing id,
    `genuinely-inapplicable` included -- this story's register-derived
    contribution to `rule_ids`, before the `CORE_RULE_IDS` union.

    `omitted_ids` is subtracted from the result: the ids the emitted omission
    ledger records as RATIFIED omissions for this story, under
    `DR-an-omission-is-ratified-by-the-plane-that-enforces-the-rule`. Passing
    an empty set -- the state whenever no guard-enforcement join has been
    delivered -- returns every rule-bearing id, which is the safe arm and was
    this function's only behaviour before the join existed.

    THE LEDGER IS THE SUBTRAHEND, AND NOTHING ELSE MAY BE. A rule must be in
    exactly one of two places: present in the story, or carrying an omission
    row that says why it is not. Deriving the exclusion from anything other
    than the ledger -- a disposition read here, a second copy of the join --
    lets the two drift, and a rule that is in NEITHER is the one state this
    whole mechanism exists to make impossible. An earlier constant here
    excluded the 309 genuinely-inapplicable rows directly and produced
    exactly that: unaccounted for, in neither place. `emit-omission-register.
    py`'s story-consistency check is what catches the drift, and it can only
    catch it if these two are computed from one source.

    Order matters and is one-way: emit the ledger first (it reads the
    register and the join, and knows nothing about the story), then
    regenerate this constant from register minus ledger. There is no cycle.

    Regenerate with the `__main__` block below rather than hand-editing; the
    two disagreed once already.

    Dev-time tooling only: called from `__main__` below, never from
    this module's import path."""
    # Function-local: the enum split has one definition, in the omission ledger,
    # and this keeps that module off the session-start import path, which only
    # __main__ needs it on.
    from _environment_story_omission_ledger import RULE_BEARING_DISPOSITIONS

    rule_bearing_not_omitted: set[str] = set()
    current_id = None
    with open(register_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("- id: rcr-"):
                current_id = line[len("- id: "):].strip()
                continue
            if line.startswith("  disposition: ") and current_id is not None:
                disposition = line[len("  disposition: "):].strip()
                if disposition in RULE_BEARING_DISPOSITIONS:
                    rule_bearing_not_omitted.add(current_id)
                current_id = None
    return frozenset(rule_bearing_not_omitted - (omitted_ids or frozenset()))


def _read_ratified_omissions(ledger_path: str, story_name: str) -> "frozenset[str]":
    """`rule_id`s the emitted omission ledger records for `story_name` AND
    actually ratifies.

    RATIFICATION IS CHECKED HERE, NOT ASSUMED FROM THE FILE'S NAME. Under
    `DR-an-omission-is-ratified-by-the-plane-that-enforces-the-rule`'s safe
    arm a row buys an omission only when it carries `enforcing_guard: none`
    AND `enforcement_verdict: n/a` -- i.e. a committed artifact established
    that no guard enforces the rule. An earlier cut of this function read
    `rule_id` and `story` alone while calling its result "ratified": a row
    carrying a real guard name, or a `pending-ratification` verdict, would
    have removed its rule from the story anyway. This is the one path by
    which a rule leaves the story, so the bar belongs on it and not only in
    the ledger emitter that happens to feed it today.

    ROWS ARE ACCUMULATED, NOT KEY-ORDER-MATCHED. The predecessor keyed on
    `- rule_id: ` leading each row, which held only because the emitter
    builds its dict with `rule_id` first and dumps with `sort_keys=False`.
    Flipping either would have made this return the empty set forever while
    the regenerator printed "minus 0 ratified omission(s)" against a ledger
    holding rows -- silent, and it inverts the mechanism. A row here is
    whatever lies between one `- ` and the next, and its keys may come in any
    order.

    Stdlib line scan for the same reason `_derive_register_rule_ids` is one:
    this file may not acquire a third-party YAML import even in tooling that
    only runs under `__main__`. An absent ledger yields the empty set -- the
    safe arm, and the state before any join is delivered."""
    omitted: set[str] = set()
    row: dict = {}

    def _flush() -> None:
        if (
            row.get("story") == story_name
            and row.get("enforcing_guard") == "none"
            and row.get("enforcement_verdict") == "n/a"
            and row.get("rule_id")
        ):
            omitted.add(row["rule_id"])

    try:
        handle = open(ledger_path, "r", encoding="utf-8")
    except OSError:
        return frozenset()
    with handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("- "):
                _flush()
                row = {}
                stripped = stripped[2:]
            if ": " in stripped:
                key, _, value = stripped.partition(": ")
                row[key.strip()] = value.strip().strip("'\"")
    _flush()
    return frozenset(omitted)


if __name__ == "__main__":
    # Regenerator, not a runtime path -- see "WHY A BUILT CONSTANT, NOT A
    # RUNTIME READ" above. Walks up from this file's own directory to the
    # repo root (coordinator/hooks/scripts -> coordinator/hooks ->
    # coordinator -> repo root) with `os.path`, never a literal `/`, so
    # this also runs unmodified on Windows.
    _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPTS_DIR)))
    _register_path = os.path.join(
        _repo_root,
        "state",
        "audits",
        "2026-09-06-doctrine-rule-class-register.yaml",
    )
    _ledger_path = os.path.join(
        _repo_root,
        "state",
        "audits",
        "2026-09-07-environment-story-omission-register.yaml",
    )
    _omitted = _read_ratified_omissions(_ledger_path, "ephemeral-cloud-vm")
    _derived = sorted(_derive_register_rule_ids(_register_path, _omitted))
    print(f"# {len(_derived)} ids derived from {_register_path}")
    print(f"# minus {len(_omitted)} ratified omission(s) from {_ledger_path}")
    print("# Diff against _EPHEMERAL_CLOUD_VM_REGISTER_RULE_IDS above; paste over it if it differs.")
    print("_EPHEMERAL_CLOUD_VM_REGISTER_RULE_IDS: frozenset[str] = frozenset(")
    print("    {")
    _per_line = 6
    for _i in range(0, len(_derived), _per_line):
        _chunk = _derived[_i : _i + _per_line]
        print("        " + ", ".join(repr(_x) for _x in _chunk) + ",")
    print("    }")
    print(")")
