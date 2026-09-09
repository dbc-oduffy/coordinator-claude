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
once, on purpose, in one place.

HOW `rule_ids` IS DERIVED -- the accounting surface, never parsed from prose
-----------------------------------------------------------------------------
Source: `state/audits/2026-09-06-doctrine-rule-class-register.yaml` (1,833
rows; see its own `counts` block at end of file).

RULE-BEARING, for this module's purpose, is exactly the register's own
`rule_rows` disposition set -- the six values its `counts` block sums to
`rule_rows` (1,211): `binds` (395), `premise-false-but-binds` (422),
`genuinely-inapplicable` (309), `cannot-name-a-party` (1),
`owned-by-cloudem-06` (70), `engine-plane` (14). NOT rule-bearing, for this
purpose: `no-environment-scoped-premise` (608) and `not-rule-bearing` (14)
-- both are FILE-LEVEL rows (`rule: null`, per the register's own row
schema comment: "`null` for a file-level disposition row"); they record
"this file has no environment-scoped rule to point at" (or no rule at
all), not a rule, so neither carries an id that belongs in a
rule-accounting set. Arithmetic check, against the register's own numbers,
not recomputed independently: 608 + 14 = 622 non-rule-bearing;
1,211 + 622 = 1,833 = `rows_total`.

`EPHEMERAL_CLOUD_VM_STORY.rule_ids` = ALL rule-bearing ids UNION
`CORE_RULE_IDS`. Every rule stays in the story; nothing is omitted today.

That is 1,211 register ids IN the story, plus the 2 `CORE_RULE_IDS` members
(`naked-python-mandate`, `cross-repo-write-gating` -- NOT register ids;
every register id is `rcr-<8 hex>`, so there is no collision to resolve)
= 1,213 total members of `EPHEMERAL_CLOUD_VM_STORY.rule_ids`.

WHY NOTHING IS OMITTED, given the register marks 309 rows
`genuinely-inapplicable`. That disposition makes a rule a CANDIDATE for
omission; it does not ratify one.
`DR-an-omission-is-ratified-by-the-plane-that-enforces-the-rule` stands
`proposed`, so only its safe arm is in force: an omission is ratified by
the plane that ENFORCES the rule recording that its guard does not fire
here. No artifact in this repo bridges an `rcr-<hash>` id to an
engine-plane guard verdict, so no omission is ratifiable today and every
unestablished case resolves toward PRESENCE.

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
row (verified: 1,833 of each, in file order, no row missing either), and
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
    )
)

# Derived from `state/audits/2026-09-06-doctrine-rule-class-register.yaml`
# at build time -- see "WHY A BUILT CONSTANT, NOT A RUNTIME READ" above.
# Regenerate with: python coordinator/hooks/scripts/_environment_stories.py
# 1,211 ids: EVERY rule-bearing row id, `genuinely-inapplicable` included --
# see the module docstring on why nothing is omitted while the ratification
# DR stands proposed. `CORE_RULE_IDS` is unioned in separately, below, not
# baked in here, so this constant stays a pure function of the register.
_EPHEMERAL_CLOUD_VM_REGISTER_RULE_IDS: frozenset[str] = frozenset(
    {
        'rcr-00ff2b33', 'rcr-01480747', 'rcr-01a18c5d', 'rcr-01d0991c', 'rcr-01d963a1', 'rcr-020b34b3',
        'rcr-021d1721', 'rcr-022deaaa', 'rcr-0250e9f5', 'rcr-026a0ebc', 'rcr-0270016e', 'rcr-0280d523',
        'rcr-02eaf1ed', 'rcr-030f0393', 'rcr-0346caf1', 'rcr-03d08001', 'rcr-03fa4d60', 'rcr-040ef3bc',
        'rcr-046f0457', 'rcr-047a5142', 'rcr-04af2eb1', 'rcr-04b7f96d', 'rcr-04f6516b', 'rcr-0519552e',
        'rcr-05279dc1', 'rcr-057105f0', 'rcr-05782ddf', 'rcr-057efa86', 'rcr-058cea9a', 'rcr-0604a17c',
        'rcr-06065e0a', 'rcr-064b06a2', 'rcr-06898af1', 'rcr-068b1937', 'rcr-0772d046', 'rcr-07815e5f',
        'rcr-07bf3407', 'rcr-07cc8fd5', 'rcr-0800fbcf', 'rcr-083b854a', 'rcr-0858cdd0', 'rcr-08978251',
        'rcr-08af544c', 'rcr-08c01689', 'rcr-09058e3c', 'rcr-09ea37f4', 'rcr-09f49f1e', 'rcr-0a074d4a',
        'rcr-0a23869b', 'rcr-0a408666', 'rcr-0a745fc0', 'rcr-0aa1545c', 'rcr-0b71dc94', 'rcr-0bc1120e',
        'rcr-0bf08f0b', 'rcr-0c00a7c8', 'rcr-0c2975f8', 'rcr-0c5e39c7', 'rcr-0c942f04', 'rcr-0ccf12b9',
        'rcr-0d4c36c4', 'rcr-0d72ee49', 'rcr-0d8c581a', 'rcr-0dc76241', 'rcr-0deb7c6b', 'rcr-0df6ae7a',
        'rcr-0e50a312', 'rcr-0e9b2dc4', 'rcr-0ee00701', 'rcr-0f2893ca', 'rcr-0f2fb6f6', 'rcr-0f6e477c',
        'rcr-0f6e59dd', 'rcr-0ff8c35c', 'rcr-1033e320', 'rcr-104ffeed', 'rcr-107b10be', 'rcr-10c17b79',
        'rcr-10d4c22e', 'rcr-10eda4b4', 'rcr-10f44f69', 'rcr-10fddedc', 'rcr-1141041f', 'rcr-11ba2292',
        'rcr-11d804c0', 'rcr-11f08338', 'rcr-11fa42bc', 'rcr-11ffa083', 'rcr-1201f062', 'rcr-1213f66c',
        'rcr-122d8795', 'rcr-12363c58', 'rcr-1263cab8', 'rcr-12988146', 'rcr-12a3d51b', 'rcr-12e409d5',
        'rcr-12f7c139', 'rcr-13de71fb', 'rcr-13f52104', 'rcr-1411997f', 'rcr-14772e38', 'rcr-14b1aab3',
        'rcr-14c25a3e', 'rcr-14cf52b7', 'rcr-152118d6', 'rcr-15380bbb', 'rcr-154591a4', 'rcr-156620b0',
        'rcr-15886b16', 'rcr-159038c2', 'rcr-15b7ae27', 'rcr-15ece1fb', 'rcr-1617a7cd', 'rcr-161b67fd',
        'rcr-163688c9', 'rcr-166cd30f', 'rcr-16959663', 'rcr-16c52f30', 'rcr-16feb04f', 'rcr-171c17ba',
        'rcr-179692b5', 'rcr-17f8353d', 'rcr-181181ec', 'rcr-18184cb6', 'rcr-18333c47', 'rcr-1870ef96',
        'rcr-18b0301b', 'rcr-18c0650f', 'rcr-19597417', 'rcr-1969c85d', 'rcr-19845e55', 'rcr-19bf3450',
        'rcr-19cfee16', 'rcr-19e68210', 'rcr-1a0a36f0', 'rcr-1a3220da', 'rcr-1a4e413e', 'rcr-1a83cd1f',
        'rcr-1a911884', 'rcr-1ab0dc65', 'rcr-1afeb652', 'rcr-1b08cb41', 'rcr-1b0ddb2f', 'rcr-1b7465b1',
        'rcr-1b957986', 'rcr-1b960b6e', 'rcr-1bb16892', 'rcr-1bc2e805', 'rcr-1bf4b1f2', 'rcr-1c228476',
        'rcr-1c5dc859', 'rcr-1ca30594', 'rcr-1cc6f6c3', 'rcr-1cf72295', 'rcr-1d3c21c0', 'rcr-1dd0d4f2',
        'rcr-1e0ef61c', 'rcr-1e66ffc9', 'rcr-1e6bc4ee', 'rcr-1ec2f9d2', 'rcr-1ef74c35', 'rcr-1f2a6461',
        'rcr-1f389481', 'rcr-1f47fb8c', 'rcr-1f9de6ad', 'rcr-2008eed5', 'rcr-200da51c', 'rcr-201d4269',
        'rcr-20367057', 'rcr-2038d883', 'rcr-21009289', 'rcr-2200cd74', 'rcr-229b8ce0', 'rcr-22c696ec',
        'rcr-23234f1b', 'rcr-232dc988', 'rcr-238c0bfd', 'rcr-23b6820f', 'rcr-23d3802e', 'rcr-24237752',
        'rcr-249ee847', 'rcr-24b08549', 'rcr-24bf0bbc', 'rcr-24f731ad', 'rcr-253dc464', 'rcr-2550234a',
        'rcr-25516459', 'rcr-255c722f', 'rcr-25a2f92a', 'rcr-261e294a', 'rcr-26ce7e50', 'rcr-2705797b',
        'rcr-2728c572', 'rcr-27361335', 'rcr-274bcca3', 'rcr-27870a59', 'rcr-279cb653', 'rcr-281ad138',
        'rcr-285b9e77', 'rcr-2871d508', 'rcr-28992045', 'rcr-28998593', 'rcr-28e32df3', 'rcr-28ec54d7',
        'rcr-28f769d1', 'rcr-290a58db', 'rcr-2917b06d', 'rcr-293bed5f', 'rcr-293c9f5b', 'rcr-294f54dc',
        'rcr-2992f014', 'rcr-29a35ba8', 'rcr-2a3d6ca7', 'rcr-2a7f37d7', 'rcr-2ab60797', 'rcr-2aff38a8',
        'rcr-2b89380e', 'rcr-2be2221f', 'rcr-2c5f4e05', 'rcr-2ca05e23', 'rcr-2ca63e4e', 'rcr-2cdc1149',
        'rcr-2ce1eb59', 'rcr-2ce9de5a', 'rcr-2cec5ec6', 'rcr-2cff427d', 'rcr-2d1b8a7b', 'rcr-2d4c7526',
        'rcr-2e49eb2c', 'rcr-2e8d15ad', 'rcr-2ec6349e', 'rcr-2ed628ec', 'rcr-2eed419a', 'rcr-2ef4dcb9',
        'rcr-2f1f2b6a', 'rcr-2f2c6798', 'rcr-2f361820', 'rcr-2f621fa6', 'rcr-2f6905e0', 'rcr-2f86c57a',
        'rcr-2fed3e27', 'rcr-2ff8c412', 'rcr-303c6633', 'rcr-3045a5ba', 'rcr-30588e13', 'rcr-3075dc8d',
        'rcr-30df7612', 'rcr-31208707', 'rcr-3120da32', 'rcr-312f9787', 'rcr-316fe5da', 'rcr-31e03b7a',
        'rcr-3299384d', 'rcr-32dc2eb6', 'rcr-32f378d1', 'rcr-32fe35f3', 'rcr-3304648d', 'rcr-330500d1',
        'rcr-332e6ac5', 'rcr-33502a3b', 'rcr-3378c09e', 'rcr-33ac8a31', 'rcr-33e7f7e4', 'rcr-34299392',
        'rcr-342b6249', 'rcr-34353dcc', 'rcr-344bac2b', 'rcr-34ad14a4', 'rcr-34c02263', 'rcr-355ad63f',
        'rcr-356b6e6d', 'rcr-359a03e8', 'rcr-35d238d2', 'rcr-35fc9114', 'rcr-3623ea12', 'rcr-364f071e',
        'rcr-36613354', 'rcr-36921420', 'rcr-36aeab4c', 'rcr-36c19210', 'rcr-36cd797c', 'rcr-36f9f9c4',
        'rcr-37192dcd', 'rcr-371a953a', 'rcr-3759a47c', 'rcr-37b6d6d2', 'rcr-37c2fbe8', 'rcr-37f667c8',
        'rcr-38313553', 'rcr-388e6ff6', 'rcr-38a2bf17', 'rcr-38bf7d11', 'rcr-393ff34f', 'rcr-397a5e56',
        'rcr-398218af', 'rcr-3996899c', 'rcr-39d5108c', 'rcr-39db11be', 'rcr-39dcaa57', 'rcr-39e41dfa',
        'rcr-3a12318e', 'rcr-3a20ebab', 'rcr-3a736dfa', 'rcr-3b57b7a9', 'rcr-3b6e2b09', 'rcr-3c0a1ebb',
        'rcr-3c71f6ee', 'rcr-3cac55a4', 'rcr-3d028f87', 'rcr-3d1dd963', 'rcr-3d1ef1ec', 'rcr-3d465705',
        'rcr-3d53a789', 'rcr-3d542f61', 'rcr-3d8b82c9', 'rcr-3df9619d', 'rcr-3e7bfaae', 'rcr-3e995c20',
        'rcr-3ec32100', 'rcr-3ec79966', 'rcr-3ececa79', 'rcr-3ef5ed3a', 'rcr-3f107f66', 'rcr-3f339b9f',
        'rcr-3f56453e', 'rcr-3f8aa633', 'rcr-3f8eefa8', 'rcr-407ca169', 'rcr-40ac1853', 'rcr-40ec97ed',
        'rcr-40f6dac6', 'rcr-410cebea', 'rcr-413650df', 'rcr-419b4c64', 'rcr-420069d1', 'rcr-4219c24f',
        'rcr-42221c03', 'rcr-425b5963', 'rcr-428a52f8', 'rcr-42ccc86d', 'rcr-43143551', 'rcr-43160835',
        'rcr-4367ca29', 'rcr-43d16fb1', 'rcr-43fec4e8', 'rcr-4453e320', 'rcr-4468822d', 'rcr-451d862c',
        'rcr-456d30a9', 'rcr-45796a59', 'rcr-4593ecf9', 'rcr-45bdbbe1', 'rcr-45f9062a', 'rcr-466473f9',
        'rcr-466b1cb5', 'rcr-46e82b63', 'rcr-46f1c76b', 'rcr-46ff96bd', 'rcr-47009bab', 'rcr-471032a6',
        'rcr-4714f885', 'rcr-4730e693', 'rcr-4751c8fb', 'rcr-476949c0', 'rcr-47c2c26c', 'rcr-48229fa5',
        'rcr-48559baa', 'rcr-48889164', 'rcr-48d82bf7', 'rcr-48dad05d', 'rcr-48f4d8b4', 'rcr-490fc34e',
        'rcr-49360185', 'rcr-49360676', 'rcr-4942bbc2', 'rcr-49525f1b', 'rcr-498a9731', 'rcr-499aeaa7',
        'rcr-49bfa3fd', 'rcr-49f24e79', 'rcr-4a018236', 'rcr-4a4fb4fe', 'rcr-4aa109f5', 'rcr-4ab547ba',
        'rcr-4acd6b35', 'rcr-4ae80e00', 'rcr-4b190a8d', 'rcr-4b4ae30b', 'rcr-4bda61c7', 'rcr-4c0992af',
        'rcr-4c0c24b0', 'rcr-4c13a396', 'rcr-4c506861', 'rcr-4c9e543c', 'rcr-4cbca6ed', 'rcr-4cf7ddbd',
        'rcr-4d010c3f', 'rcr-4d3b97ce', 'rcr-4d9494ed', 'rcr-4da7f41b', 'rcr-4e06a2a5', 'rcr-4e5d7916',
        'rcr-4f0cdbc8', 'rcr-4f9e19f0', 'rcr-4fa00610', 'rcr-4fa2a2e0', 'rcr-5014529b', 'rcr-505c2538',
        'rcr-50effbfb', 'rcr-5100af46', 'rcr-516a9278', 'rcr-519dae8b', 'rcr-51cb2f3c', 'rcr-51dd4499',
        'rcr-51f1e432', 'rcr-5205354f', 'rcr-521e3f5b', 'rcr-5236c3cc', 'rcr-525ac5e8', 'rcr-52e71afc',
        'rcr-53688529', 'rcr-5373b2e6', 'rcr-53c321d0', 'rcr-53dbfe1b', 'rcr-53ff14fd', 'rcr-547b21c5',
        'rcr-54cb9137', 'rcr-54e74cc3', 'rcr-5580660d', 'rcr-55f43929', 'rcr-560a175f', 'rcr-569276a9',
        'rcr-56a3297e', 'rcr-56c15404', 'rcr-56cb76a2', 'rcr-570191d3', 'rcr-57413d6b', 'rcr-57ef436a',
        'rcr-58096dcc', 'rcr-58133122', 'rcr-581616bb', 'rcr-582c4121', 'rcr-587c850f', 'rcr-58b49549',
        'rcr-590911ec', 'rcr-59279455', 'rcr-5996883a', 'rcr-599b31fa', 'rcr-59ae7ce1', 'rcr-5a4bbda5',
        'rcr-5a91ee40', 'rcr-5b6098ae', 'rcr-5b73f71c', 'rcr-5b980cb4', 'rcr-5b9f31cd', 'rcr-5bbeeefb',
        'rcr-5bedc432', 'rcr-5bfeb350', 'rcr-5c476f6a', 'rcr-5c8785ec', 'rcr-5d61ed6f', 'rcr-5d8c67e0',
        'rcr-5dd46991', 'rcr-5e389403', 'rcr-5e631389', 'rcr-5ec804c9', 'rcr-5f11b76e', 'rcr-5f1e5f12',
        'rcr-5f3da779', 'rcr-5f82624b', 'rcr-5fe11f85', 'rcr-5ffc789c', 'rcr-600bc518', 'rcr-602f421e',
        'rcr-60c413f0', 'rcr-611c45a9', 'rcr-61ebc4eb', 'rcr-6275a0ca', 'rcr-62db05de', 'rcr-6331b4f1',
        'rcr-635d4745', 'rcr-638999a6', 'rcr-63bd6d71', 'rcr-63d50bc1', 'rcr-63e4f647', 'rcr-645e7da6',
        'rcr-647bc93f', 'rcr-64827f4c', 'rcr-64c01031', 'rcr-64ef928f', 'rcr-6532c716', 'rcr-6577a06f',
        'rcr-6583dc85', 'rcr-659d4996', 'rcr-65bb6364', 'rcr-6647b180', 'rcr-669cfcbf', 'rcr-66bbaa5a',
        'rcr-66f2f624', 'rcr-671b02d0', 'rcr-673347cd', 'rcr-678febd7', 'rcr-679b7ce2', 'rcr-67a1a491',
        'rcr-67ad4f31', 'rcr-67ed993e', 'rcr-6816e019', 'rcr-68f8126e', 'rcr-68f876d1', 'rcr-6914a665',
        'rcr-6940d86c', 'rcr-698f25c1', 'rcr-69be2531', 'rcr-69f52757', 'rcr-6a56861d', 'rcr-6a6eb8e3',
        'rcr-6b10f57d', 'rcr-6b17c86a', 'rcr-6b2e396d', 'rcr-6b3de3b1', 'rcr-6b6eb828', 'rcr-6b822f00',
        'rcr-6c1d0bc4', 'rcr-6c23360e', 'rcr-6c252dd2', 'rcr-6cde624d', 'rcr-6d7fe6a3', 'rcr-6d8391a6',
        'rcr-6d9867da', 'rcr-6da16b7b', 'rcr-6db20ddc', 'rcr-6dc99bb1', 'rcr-6e65efcb', 'rcr-6f02e6e5',
        'rcr-6f3f4596', 'rcr-6f673d09', 'rcr-6f8a3c3e', 'rcr-6fc9eef0', 'rcr-6fea49f0', 'rcr-703b2067',
        'rcr-706bffbd', 'rcr-70a14b7c', 'rcr-70c3c51f', 'rcr-710afa28', 'rcr-712c7b8e', 'rcr-718f96f8',
        'rcr-71f7f36a', 'rcr-7205d596', 'rcr-720cd20a', 'rcr-723bb8e3', 'rcr-7244bcff', 'rcr-72587431',
        'rcr-7271bae9', 'rcr-72b1622b', 'rcr-72bbaf6a', 'rcr-72bca05c', 'rcr-72f25887', 'rcr-7307ef22',
        'rcr-7369f1fb', 'rcr-73ede31d', 'rcr-7412bf7a', 'rcr-7458fb3b', 'rcr-748ce535', 'rcr-74d5a91c',
        'rcr-74ddb14c', 'rcr-7510a643', 'rcr-759925df', 'rcr-7615c1f5', 'rcr-7689b22a', 'rcr-76a1613e',
        'rcr-76ad6d57', 'rcr-76ade443', 'rcr-76bc0ce1', 'rcr-7708d223', 'rcr-773bcedc', 'rcr-7746b4ec',
        'rcr-77a2db50', 'rcr-77aa95a8', 'rcr-77d1cede', 'rcr-780cc817', 'rcr-78205341', 'rcr-78356241',
        'rcr-78466e0c', 'rcr-78b8971b', 'rcr-78bd4351', 'rcr-79006aae', 'rcr-7916ae9a', 'rcr-791952d8',
        'rcr-797a6be6', 'rcr-79c882f5', 'rcr-79e06194', 'rcr-79eccd2a', 'rcr-7a0da061', 'rcr-7a5c28e5',
        'rcr-7a8b0781', 'rcr-7b3b9b92', 'rcr-7b90cd41', 'rcr-7b96eb2a', 'rcr-7bb3776d', 'rcr-7bb7a71d',
        'rcr-7bc81b74', 'rcr-7bdd71c5', 'rcr-7c0ee8e2', 'rcr-7c2900cc', 'rcr-7c387606', 'rcr-7cb90dc2',
        'rcr-7d0acf27', 'rcr-7d16b15b', 'rcr-7d1ac3e8', 'rcr-7d499ca1', 'rcr-7d83bc88', 'rcr-7db5530b',
        'rcr-7dc89c3d', 'rcr-7e1cc6ce', 'rcr-7e857463', 'rcr-7eaa1c53', 'rcr-7eb48f09', 'rcr-7f53c8f6',
        'rcr-7fb45eb2', 'rcr-7fce900a', 'rcr-7ffb9eb2', 'rcr-802b36bf', 'rcr-80411ad9', 'rcr-804c06d6',
        'rcr-807e2ab9', 'rcr-809ab7c0', 'rcr-80a71c3d', 'rcr-80b1672a', 'rcr-80dca259', 'rcr-80e7b0f9',
        'rcr-80f11054', 'rcr-8114ee82', 'rcr-813c1179', 'rcr-8185936d', 'rcr-81af042b', 'rcr-81b8a23b',
        'rcr-8224fa4f', 'rcr-82ef562f', 'rcr-83fb1ea6', 'rcr-842096ee', 'rcr-843725e2', 'rcr-84886a72',
        'rcr-848ff85c', 'rcr-84a08171', 'rcr-85163477', 'rcr-85787815', 'rcr-85a2a47d', 'rcr-85ad44da',
        'rcr-85b3e223', 'rcr-85bc39cd', 'rcr-85e5a6aa', 'rcr-85f3c745', 'rcr-870e84bd', 'rcr-8783f28e',
        'rcr-87a0d48f', 'rcr-87cf2936', 'rcr-88022a50', 'rcr-8871cfeb', 'rcr-88b75fcc', 'rcr-89147b7d',
        'rcr-89b8d8b9', 'rcr-8a08dcf3', 'rcr-8a2ef083', 'rcr-8a583440', 'rcr-8a66e8e6', 'rcr-8a73f320',
        'rcr-8ad7de49', 'rcr-8aeb2346', 'rcr-8b01a8d1', 'rcr-8b5a9aa9', 'rcr-8b7d5207', 'rcr-8c20f68d',
        'rcr-8c43280e', 'rcr-8cf5d715', 'rcr-8d1a234d', 'rcr-8d2258d2', 'rcr-8d2587ad', 'rcr-8d362abd',
        'rcr-8d41924f', 'rcr-8d62e9c6', 'rcr-8d65ce08', 'rcr-8debbe20', 'rcr-8e2dc08c', 'rcr-8e33a7c3',
        'rcr-8e456947', 'rcr-8f32c576', 'rcr-8f700a8f', 'rcr-8f875359', 'rcr-8fa7c247', 'rcr-8fcdc2b1',
        'rcr-8fdc4352', 'rcr-8ff89791', 'rcr-9004ccbd', 'rcr-9042d4bc', 'rcr-9098cf69', 'rcr-909cbac8',
        'rcr-90d3df79', 'rcr-90e9f9a0', 'rcr-90f3f931', 'rcr-911e20f8', 'rcr-91679b2d', 'rcr-9199c776',
        'rcr-919e6cfe', 'rcr-91a5a519', 'rcr-91b479d2', 'rcr-91ea0293', 'rcr-91edf5f2', 'rcr-927091f6',
        'rcr-9280b3de', 'rcr-928a20b3', 'rcr-929a835c', 'rcr-92b718ba', 'rcr-92c207a3', 'rcr-92d7db84',
        'rcr-92ff63b8', 'rcr-935f5b77', 'rcr-9362ad80', 'rcr-93a331f6', 'rcr-93b0b54d', 'rcr-9432f867',
        'rcr-945bff16', 'rcr-94680640', 'rcr-94bf7488', 'rcr-94c24bd6', 'rcr-9513ed26', 'rcr-955d8eca',
        'rcr-95740842', 'rcr-95abb371', 'rcr-95c656f5', 'rcr-95cca476', 'rcr-968a4bf7', 'rcr-96981c2e',
        'rcr-969a5592', 'rcr-96b60171', 'rcr-975d05b9', 'rcr-979af30d', 'rcr-97a14f1a', 'rcr-97d39ba2',
        'rcr-9838eb32', 'rcr-98ac3594', 'rcr-98f1b35e', 'rcr-9991130b', 'rcr-99be447d', 'rcr-99d683ac',
        'rcr-99f72073', 'rcr-9a1c5819', 'rcr-9a20872a', 'rcr-9a4071fb', 'rcr-9a537b34', 'rcr-9a5fba22',
        'rcr-9ac61018', 'rcr-9ac62cb2', 'rcr-9ac9e437', 'rcr-9af2bd39', 'rcr-9b5a9a8a', 'rcr-9bf33c10',
        'rcr-9c2b50cf', 'rcr-9c2c4df0', 'rcr-9c48d395', 'rcr-9cb14710', 'rcr-9d2c4758', 'rcr-9d3b6704',
        'rcr-9d3fc0a5', 'rcr-9d4de4c7', 'rcr-9db8f728', 'rcr-9e0773cc', 'rcr-9e0fed6a', 'rcr-9e5338db',
        'rcr-9e5472e3', 'rcr-9e8a80d3', 'rcr-9f787e1f', 'rcr-9f7d1908', 'rcr-9fd73e0d', 'rcr-9ffd5ac5',
        'rcr-a0999a9c', 'rcr-a09d1f77', 'rcr-a0b407a7', 'rcr-a0d8679f', 'rcr-a0eeb84d', 'rcr-a0f94429',
        'rcr-a1ddc065', 'rcr-a2b88390', 'rcr-a2cc0ca4', 'rcr-a321d6ef', 'rcr-a360215c', 'rcr-a39288f8',
        'rcr-a3c23fe4', 'rcr-a3ec5d24', 'rcr-a45a7366', 'rcr-a45d7209', 'rcr-a4647a8f', 'rcr-a4f519a8',
        'rcr-a524b38e', 'rcr-a52ea26f', 'rcr-a5f6328a', 'rcr-a61f8cc2', 'rcr-a6c9d2c0', 'rcr-a6cf850a',
        'rcr-a71d9897', 'rcr-a7de8e95', 'rcr-a7fcaa1c', 'rcr-a8963fc5', 'rcr-a8b9fbaf', 'rcr-a8f0c184',
        'rcr-a8f2fbad', 'rcr-a952452a', 'rcr-a96098e1', 'rcr-a96f916b', 'rcr-a97fdc02', 'rcr-a98d4767',
        'rcr-a9c67243', 'rcr-a9de6c78', 'rcr-a9eb1b87', 'rcr-a9f678a1', 'rcr-aa4be36c', 'rcr-aa5dc411',
        'rcr-aa631347', 'rcr-aa7d522c', 'rcr-aaf50297', 'rcr-ab1bf735', 'rcr-ab53ed81', 'rcr-ab62ab59',
        'rcr-abc6f081', 'rcr-abf4775f', 'rcr-ac800a88', 'rcr-acabf760', 'rcr-acbffe98', 'rcr-acc8f62c',
        'rcr-ad063bf2', 'rcr-ad1a4e28', 'rcr-adcd5999', 'rcr-adec2b9b', 'rcr-ae5383ac', 'rcr-ae8adeef',
        'rcr-aeb44166', 'rcr-aed4ab0e', 'rcr-aee8bd16', 'rcr-af73b35c', 'rcr-af9d5a3b', 'rcr-afb7de25',
        'rcr-afda570e', 'rcr-aff7b33b', 'rcr-affa5f09', 'rcr-b063b1b5', 'rcr-b07b4a37', 'rcr-b0850c95',
        'rcr-b08e5bcd', 'rcr-b09dd6ac', 'rcr-b0a33a98', 'rcr-b0b04db0', 'rcr-b0c5e565', 'rcr-b1706e20',
        'rcr-b1cec0f4', 'rcr-b1e3d6c0', 'rcr-b22ab158', 'rcr-b2f1b999', 'rcr-b3902d23', 'rcr-b3b6f047',
        'rcr-b3d4194a', 'rcr-b3fb9c2c', 'rcr-b41ed755', 'rcr-b445d0f7', 'rcr-b5cb43b6', 'rcr-b65e6d71',
        'rcr-b69dfedf', 'rcr-b6c40fd3', 'rcr-b6e7be1c', 'rcr-b6ed36d9', 'rcr-b705ba8a', 'rcr-b70df423',
        'rcr-b744502a', 'rcr-b74c7f49', 'rcr-b7747dcd', 'rcr-b8242795', 'rcr-b83042ad', 'rcr-b83325aa',
        'rcr-b857d2a0', 'rcr-b8639e2c', 'rcr-b8ee3d26', 'rcr-b90b0057', 'rcr-b93a4666', 'rcr-b98b721a',
        'rcr-b98fab64', 'rcr-b99efa8f', 'rcr-b9d70efd', 'rcr-ba0a750b', 'rcr-ba129dc1', 'rcr-ba49bd9f',
        'rcr-ba4ab75a', 'rcr-ba52bad4', 'rcr-ba8f57b6', 'rcr-bab7c90f', 'rcr-bafaa023', 'rcr-bb51d5f7',
        'rcr-bb73bdb8', 'rcr-bb9f9cf3', 'rcr-bbc2796b', 'rcr-bbc931d4', 'rcr-bc03fc71', 'rcr-bd2cc27e',
        'rcr-bd35dc47', 'rcr-bd45c2a8', 'rcr-bd522698', 'rcr-bd64985a', 'rcr-bd7168fa', 'rcr-bdee5298',
        'rcr-bf0550da', 'rcr-bf593181', 'rcr-bf8d77c9', 'rcr-bfae5eda', 'rcr-c020ca82', 'rcr-c1c9efc8',
        'rcr-c1ddf8f6', 'rcr-c245e0fe', 'rcr-c26d67a8', 'rcr-c2b0e808', 'rcr-c2c86f73', 'rcr-c3106931',
        'rcr-c31f31d9', 'rcr-c349d9e5', 'rcr-c38a8312', 'rcr-c3ab58fc', 'rcr-c3aee97b', 'rcr-c3b77ae8',
        'rcr-c416773e', 'rcr-c45c326a', 'rcr-c46722c4', 'rcr-c46de77a', 'rcr-c47e2b78', 'rcr-c487871c',
        'rcr-c4f1f2c0', 'rcr-c5793120', 'rcr-c5c3fe8c', 'rcr-c6dce287', 'rcr-c841eea8', 'rcr-c8a1c32c',
        'rcr-c8ab4dc5', 'rcr-c8d8039c', 'rcr-c8f27da4', 'rcr-c8f7ee2d', 'rcr-c956670f', 'rcr-c96b8dc7',
        'rcr-c97f943a', 'rcr-c984265f', 'rcr-c98fac22', 'rcr-c9911b60', 'rcr-c994977a', 'rcr-c9d39ec0',
        'rcr-c9fc2ae5', 'rcr-ca4d214a', 'rcr-ca676131', 'rcr-cae17f6a', 'rcr-cb334fa1', 'rcr-cb37bd7b',
        'rcr-cb4db54c', 'rcr-cba217b1', 'rcr-cbc93b52', 'rcr-cc385977', 'rcr-cc38fd85', 'rcr-cc44f203',
        'rcr-cca6d1e3', 'rcr-ccc99ea4', 'rcr-cd18e7ce', 'rcr-cd40df77', 'rcr-cdaf1105', 'rcr-cde33e78',
        'rcr-ce03c09f', 'rcr-ce8ddb8f', 'rcr-ced9f362', 'rcr-cee4a8a4', 'rcr-cf74355e', 'rcr-cfd2a78a',
        'rcr-cffd5ead', 'rcr-d10427cb', 'rcr-d1c202f2', 'rcr-d265897c', 'rcr-d292b52f', 'rcr-d2a0f087',
        'rcr-d2b2165e', 'rcr-d2d532c0', 'rcr-d3548a58', 'rcr-d38eebaf', 'rcr-d3956f42', 'rcr-d39b0fae',
        'rcr-d3a944b6', 'rcr-d3cd9f30', 'rcr-d4072142', 'rcr-d40c3357', 'rcr-d411f437', 'rcr-d45107b0',
        'rcr-d4567556', 'rcr-d48f8cfa', 'rcr-d4e0e8e0', 'rcr-d50a2902', 'rcr-d536c2e9', 'rcr-d586fe9f',
        'rcr-d5d8c4a2', 'rcr-d6401183', 'rcr-d69b18db', 'rcr-d6c6c867', 'rcr-d74f1b72', 'rcr-d75488dd',
        'rcr-d7f89313', 'rcr-d84a264d', 'rcr-d84b79c3', 'rcr-d854fa30', 'rcr-d8ae5638', 'rcr-d9481c9a',
        'rcr-d9b4f0ee', 'rcr-d9e8b695', 'rcr-d9ede284', 'rcr-d9f0ebc6', 'rcr-da2c28be', 'rcr-da7f5cec',
        'rcr-da8a0f7e', 'rcr-daa4999c', 'rcr-dac517e6', 'rcr-dac70d40', 'rcr-dad124a5', 'rcr-db0c6926',
        'rcr-db15f0d3', 'rcr-db2714ab', 'rcr-db661201', 'rcr-db8bec48', 'rcr-db8dab65', 'rcr-dc00d9fa',
        'rcr-dc09af4e', 'rcr-dc38e379', 'rcr-dc65370b', 'rcr-dc7d47cd', 'rcr-dc7e78b5', 'rcr-dc9a31fb',
        'rcr-dcf2e6e4', 'rcr-dd635bd9', 'rcr-dd6d4ea6', 'rcr-dd8d4d51', 'rcr-ddd7ad16', 'rcr-ddfc271d',
        'rcr-de2b676d', 'rcr-de49f5fe', 'rcr-de5909ad', 'rcr-dea5d482', 'rcr-deb22f5b', 'rcr-dede9219',
        'rcr-dee50eab', 'rcr-df75470f', 'rcr-dfe05371', 'rcr-dffc93da', 'rcr-e00ce93d', 'rcr-e01d17d6',
        'rcr-e0313700', 'rcr-e04a4d0d', 'rcr-e07360e4', 'rcr-e0a5dd64', 'rcr-e0b37f17', 'rcr-e0be5285',
        'rcr-e0e33a5f', 'rcr-e11caadb', 'rcr-e135c2c5', 'rcr-e162d97d', 'rcr-e1c5fa51', 'rcr-e1df72d6',
        'rcr-e1fb33ec', 'rcr-e2115fa6', 'rcr-e251e8ac', 'rcr-e28e457b', 'rcr-e291cbdc', 'rcr-e2ce8426',
        'rcr-e2f3d080', 'rcr-e357c5c1', 'rcr-e375e747', 'rcr-e3c00593', 'rcr-e3e01b9d', 'rcr-e43f0db5',
        'rcr-e459ae26', 'rcr-e4b10c36', 'rcr-e4bcb648', 'rcr-e4c29568', 'rcr-e4eaac64', 'rcr-e5491ac6',
        'rcr-e69a81d0', 'rcr-e6aeee0c', 'rcr-e6dc9baa', 'rcr-e6e05dac', 'rcr-e6e21396', 'rcr-e73a8ce8',
        'rcr-e7694f16', 'rcr-e76bec95', 'rcr-e76f9180', 'rcr-e7919fef', 'rcr-e79e097c', 'rcr-e7ba0235',
        'rcr-e7d28a36', 'rcr-e7e2fd0a', 'rcr-e7f88c2f', 'rcr-e8264032', 'rcr-e88e79d5', 'rcr-e89ecc92',
        'rcr-e8eac6a8', 'rcr-e8f6fa44', 'rcr-e9073b14', 'rcr-e9779849', 'rcr-e9c4df7a', 'rcr-ea5028f6',
        'rcr-ea679893', 'rcr-ea7d9a02', 'rcr-ead308c9', 'rcr-eb4c0bc2', 'rcr-eb79817e', 'rcr-ebe8d6d3',
        'rcr-ebff559d', 'rcr-ec52a39e', 'rcr-ec623b59', 'rcr-ec828508', 'rcr-ec9f7a7d', 'rcr-ed5a939e',
        'rcr-ed733b36', 'rcr-ed99b378', 'rcr-ed9c3bd5', 'rcr-ee3c053b', 'rcr-ee9fe52a', 'rcr-eed8056b',
        'rcr-ef5de713', 'rcr-efa1a6b1', 'rcr-efb3d9a1', 'rcr-efd5387c', 'rcr-efd5ac65', 'rcr-f061c887',
        'rcr-f0796db0', 'rcr-f09eab1c', 'rcr-f1794fdf', 'rcr-f1fabf88', 'rcr-f21922f0', 'rcr-f2271d4a',
        'rcr-f27997f8', 'rcr-f2905646', 'rcr-f2b03743', 'rcr-f2d0b6e6', 'rcr-f2d24427', 'rcr-f2f415ce',
        'rcr-f337d330', 'rcr-f35a152a', 'rcr-f38697cf', 'rcr-f3b886a4', 'rcr-f45c1efe', 'rcr-f4812605',
        'rcr-f4bdf57d', 'rcr-f4c1ea27', 'rcr-f4d3dacf', 'rcr-f51de172', 'rcr-f5538e08', 'rcr-f563d7c7',
        'rcr-f58424c5', 'rcr-f591a577', 'rcr-f5a5a4de', 'rcr-f5f854c3', 'rcr-f60610e9', 'rcr-f614cd47',
        'rcr-f634b138', 'rcr-f652ce71', 'rcr-f67f9db2', 'rcr-f6f84ca8', 'rcr-f7196b9b', 'rcr-f7768c18',
        'rcr-f7863a0c', 'rcr-f7b44628', 'rcr-f7b94a76', 'rcr-f7cdfbd5', 'rcr-f80e07ca', 'rcr-f824beff',
        'rcr-f87adc16', 'rcr-f8c1cb04', 'rcr-f8f05e00', 'rcr-f8fc7bdd', 'rcr-f9185f8a', 'rcr-f95e533b',
        'rcr-fa15c566', 'rcr-fa47f8b7', 'rcr-faa22b5e', 'rcr-faad95c0', 'rcr-fae2a731', 'rcr-fae2bdcb',
        'rcr-faf498f5', 'rcr-fb059b0f', 'rcr-fb07a638', 'rcr-fb594a1e', 'rcr-fb6cdefa', 'rcr-fb8033a6',
        'rcr-fbb96b89', 'rcr-fbcf61a6', 'rcr-fbcfa583', 'rcr-fbe052af', 'rcr-fc4edd1b', 'rcr-fc547658',
        'rcr-fc889454', 'rcr-fc8c4c55', 'rcr-fc953843', 'rcr-fca1257a', 'rcr-fcc494cb', 'rcr-fd2efab5',
        'rcr-fd31e853', 'rcr-fd9ab5f7', 'rcr-fdc9e51e', 'rcr-fe468fb4', 'rcr-fe4e8c9c', 'rcr-fe9f5fae',
        'rcr-fee133df', 'rcr-ff336c4b', 'rcr-ff4a1f48', 'rcr-ff657619', 'rcr-ffd447dc',
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
    # Function-local for the same reason `_read_ratified_omissions` refuses a
    # YAML parser: the enum split has ONE definition, in the omission ledger,
    # and this module reaches it without putting a second module on the
    # session-start import path that only `__main__` ever needs.
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
