# The DR Corpus: Where Decisions Live and How They're Amended

Conventions for authoring and maintaining `DR-*` decision records — read this before writing a
new one or amending an existing one. This is the durable home for these conventions, on a
surface a decision author hits while authoring, not buried inside one record among 200+.

## The two-directory split is intentional

- `docs/decisions/` — **repo-plane.** Decisions about this repo's own working data, doctrine
  working-data, and cross-repo boundary arbitration. Not shipped anywhere.
- `coordinator/docs/decisions/` — **plugin-plane.** Decisions about the coordinator plugin
  itself, and these ship to the OSS `coordinator-claude` mirror alongside the rest of
  `coordinator/`.

The split is not an accident of history to be flattened — it tracks which plane a decision
governs, the same discriminator that governs every other file placement in this repo (see
project `CLAUDE.md` § Place in the fleet).

## Amend in place, or mint a new DR — the rule is reversal, not change

**A decision still describing live behaviour is amended in place** when the amendment does not
reverse the ruling. Append an `## Amendment (<date>) — <summary> (<ratifier>)` section; do not
duplicate or restate the superseded text elsewhere.

**Mint a new, superseding DR only when the ruling itself reverses** — the new decision says the
opposite of what stood before, not merely a refinement, narrowing, or correction of the same
ruling.

This is why `DR-088` (test-breadth ladder) carries seven-plus amendment sections rather than a
chain of superseding records: none of R1–R10 nor the later amendments reversed the tiered-
invocation-authority ruling itself, each refined or extended it.

## The live-vs-archaeology discriminator is `status:`

- `status: accepted` — live. The record (plus its amendments) describes current behaviour and
  binds present decisions.
- `status: superseded` — archaeology. Read for history, not as a governing rule.

Do not use created-date, DR-number ordering, or "the newest passage wins" as the discriminator —
`status:` is the only field that says whether a record is live.

## Reading DR-numbers from a peer repo

`docs/decisions/` in this repo holds 195+ files; the highest local number is DR-189 (DR-190
being the record that ratified this page). A `DR-` citation numbered higher than that, or
matching a record that does not exist locally, is a **claude-klabauter-plane record**, not a typo or a
missing file here — do not go looking for it in this tree.

## Negative spec

- Not a place to restate the substance of a specific ruling — that lives in the ruling's own
  record.
- Not a changelog of who amended what when — the `## Amendment` headers inside each DR carry
  that; this page states the standing convention, present tense.
