---
last-updated: 2026-06-15
---

# Backlog Prune Discipline

Backlog-managing skills must close resolved entries and name the closed IDs in the commit subject — the audit trail lives in `git log`, not in graveyard sections appended to the file.

## Queue Shape — Directory-Form

All coordinator queues use the directory-form shape. There is no markdown-line central queue.

### Directory-Form Queues

**Applies to:** `state/debt-backlog/`, `state/bug-backlog/`, `state/improvement-queue/` (all tiers — project-scoped rows AND central universal rows tagged `queue_scope: central`), `state/cross-repo-commitments/` (own closure enum — see § Cross-Repo-Commitments Closure below).

Each entry is one YAML file: `state/<queue>/<id>.yaml`. The directory is the queue; individual files are the entries.

**Closure mechanic:**

1. Stamp closure frontmatter BEFORE moving the file — edit `state/<queue>/<id>.yaml` to set:
   ```yaml
   status: closed
   closed_at: <ISO date>        # e.g. 2026-06-15
   closed_by: <commit-sha>      # SHA of the fix commit
   ```
2. Move the file to archive:
   ```bash
   git mv state/<queue>/<id>.yaml archive/<queue>/<YYYY-MM>/<id>.yaml
   ```
3. Commit the stamped-then-moved file in the same commit as the fix. The commit subject names the closed entry ID.

**Audit trail:** `git log --oneline -- state/<queue>/<id>.yaml` shows the entry's history; `git log --oneline -- archive/<queue>/<YYYY-MM>/<id>.yaml` shows closure history. Git preserves the full per-entry history through the `git mv` because git tracks content, not paths.

**Empty-directory guard:** After batch closures, an empty source directory causes `git mv` to abort. Handle with:
```bash
rmdir state/<queue>/ 2>/dev/null || true
```
Run this after all `git mv` operations in the batch, before committing.

**Never annotate inline.** A `## Closed` section in a directory-form queue's index file (if any) is forbidden — closure is via `git mv` to archive, not inline annotation. There is no index file to annotate; each entry is its own file.

### Cross-Repo-Commitments Closure

<!-- Spec backlink: docs/plans/2026-07-11-cross-repo-commitment-lifecycle.md § C3b (AC9) -->

`state/cross-repo-commitments/` follows the same directory-form `git mv`-to-archive mechanic
above, with ONE divergence: **its `status:` enum is pinned to `{open, fulfilled, withdrawn}`**
(schema: `coordinator/schemas/cross-repo-commitment.yaml`), NOT the base queue-family
`{open, closed, deferred}` enum used by debt/bug/improvement-queue. Both `fulfilled` and
`withdrawn` are archive-eligible closure states — there is no bare `closed` value for this
schema.

**Negative-spec:** do NOT stamp `status: closed` on a cross-repo-commitment entry — that value
is rejected by `schema-cli.js --validate` (see `docs/wiki/cross-repo-commitments-schema.md`
§ Status enum). Pick `fulfilled` (the sibling delivered) or `withdrawn` (the commitment was
dropped/superseded without delivery) instead.

**Closure mechanic:**

1. Stamp closure frontmatter — set `status: fulfilled` or `status: withdrawn`, plus
   `closed_at: <ISO date>` and `closed_by: <commit-sha-or-prose>`.
2. `git mv state/cross-repo-commitments/<date>-<slug>.yaml archive/cross-repo-commitments/<YYYY-MM>/<date>-<slug>.yaml`
3. Commit the stamped-then-moved file in the same commit as the closing evidence. The commit
   subject names the closed entry slug.

**Note on this CLI's dispatch — NOT the general-purpose pruner:** claude-klabauter
`coordinator/bin/prune-resolved-queue-entries.py`
does not handle this queue — it is a markdown line-deletion pruner path-allowlisted to
`improvement-queue.md`/`bug-backlog.md` and hard-exits on any other path, including a
directory-form YAML queue. `state/cross-repo-commitments/` closes exclusively via the manual
`git mv` mechanic documented here (same shape as the other directory-form queues above), not
via that script.

Written to via `coordinator-queue-append --schema cross-repo-commitment` — see
`docs/wiki/cross-repo-commitments-schema.md` for the full field contract.

---

## Why This Matters

The queue file (or directory) is a workspace, not a ledger. Its job is to show what is open — nothing else. When a resolved entry stays visible (annotated, crossed out, or flagged `resolution: done`), readers must mentally filter noise on every read. The git log carries the history at zero extra cost; the workspace carries only open work.

For directory-form queues, `git mv` preserves per-entry history through the move, making closed entries queryable in `archive/` without polluting the live queue.

## The Discipline

- **Stamp frontmatter, then `git mv` to archive, in the same commit as the fix.**
- **Name closed entry IDs in the commit subject.** The subject line is the index into `git log`; without it, the audit trail requires reading every diff. Example: `fix: collapse duplicate scout step [closes queue: b7e3d2f1]`.
- **Never annotate "resolved/done/closed/complete" inline** in a YAML entry.

## Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| Dropping an entry from the queue without a corresponding commit | "Drop from dispatch queue" is not the same as closing — no paper trail exists |
| Stamping `status: closed` frontmatter WITHOUT the subsequent `git mv` | Entry stays in the live queue dir; `coordinator-queue-append` reads all files in the dir as open; frontmatter alone is not closure |
| Running `git mv` before stamping closure frontmatter | The archived file lands without closure metadata; `closed_at` / `closed_by` are unresolvable after the move without editing the archive |
| Annotating `status: closed` inline without `git mv` for central entries tagged `queue_scope: central` | Same as project entries — central rows use directory-form closure; line-deletion is retired |
| Stamping `status: closed` when the divergence was fixed upstream but the entry's stated closure action (un-skip a test, re-enable a guard) was never performed | The tracking entry claims resolution while the guard stays disabled — silent coverage loss, caught only by grepping the criterion at pickup |

## Closing an Entry Means Satisfying Its Stated Closure Criterion

**A backlog entry's closure criterion is a contract — closing the entry means the criterion is *met*, not that the underlying divergence was resolved somewhere upstream.** An entry whose criterion was "`test-provenance-parity.js` is quarantined (skipped) until this divergence is resolved" was marked `status: closed` and archived when the divergence *was* fixed upstream — but the JS-side test was left skip-quarantined. The parallel vitest guard got un-skipped; the `node:test` guard was forgotten. Net effect: the D4 cross-package drift guard was silently disabled on the JS side while its tracking entry claimed resolution. Caught only at handoff pickup, by grepping `skip` markers against the closed entry's closure criterion.

**How to apply:** before stamping `status: closed`, re-read the entry's own closure criterion and verify it verbatim. If it names a test to un-skip, a guard to re-enable, a flag to flip — grep that the action actually happened. "Resolved upstream" is a necessary condition, not the closure itself; a criterion mentioning `skip:` / `quarantine` / `disabled` demands a grep of that exact marker before the `git mv`.

## Audit Recipe

To see when an entry was added and when it was closed:

```bash
# Full history for an open entry:
git log --oneline -- state/<queue>/<id>.yaml

# Full history for a closed entry (both sides of the mv):
git log --oneline -- state/<queue>/<id>.yaml
git log --oneline -- archive/<queue>/<YYYY-MM>/<id>.yaml

# See the closure diff:
git log -p -- archive/<queue>/<YYYY-MM>/<id>.yaml | head -40
```

Git preserves the rename-chain across the `git mv`, so the combined history spans both paths.

## Age-Ping — Parked-Tier Aging Discipline

<!-- Spec backlink: docs/plans/2026-07-23-queue-triage-terminates-in-batons.md § C5, DEC-1 -->

Applies to the parked tier of the Queue Terminus Doctrine (`docs/wiki/queue-terminus-doctrine.md`)
— `state/debt-backlog/` and `state/bug-backlog/` once each queue family's triage ceremony (currently
`/debt-triage`; `/bug-blitz` per its own chunk) adopts the four-outcome terminus. A parked entry
(`status: deferred` with a mandatory `why_blocked`, per `docs/wiki/debt-backlog-schema.md §
Status enum`) is a deliberate hold, not a closed loop, and this section is the queue-family-generic
home for keeping it from growing monotonically stale — chosen over duplicating the contract in
each per-schema wiki (AC10), since aging/draw-on-demand is cadence discipline shared by every
directory-form queue, the same reason closure mechanics live here rather than per-schema.

**Age-ping contract.** Every triage run over a queue that draws on the parked tier surfaces parked
entries back to the EM/PM by age, alongside the fresh queue rows being triaged that session — not
merely on request. An entry's age is `today - created` (the base queue schema carries no separate
park-date field, so `created` is the age anchor). There is no fixed numeric re-surfacing threshold
mandated here — see below for why; the obligation is that the ceremony *looks*, every run, rather
than never.

**Live state at authoring time:** `state/debt-backlog/` holds 11 entries, all
`created` within an ~18-day span, all under the legacy `status: open`
value (§ Status enum, `debt-backlog-schema.md`). There is no aged tail to ping at launch — the
first triage run under this contract will find nothing overdue. That is expected, not evidence the
contract is unneeded: the tier accumulates an aged tail only as the terminus starts parking
entries under the new `deferred`/`why_blocked` regime, and the age-ping obligation is what keeps
that future tail visible rather than invisible. (Retro-triaging the 11 existing legacy entries is
explicitly out of scope for the terminus plan — this age-ping mechanically re-surfaces them on the
next triage run instead of a one-shot backfill sweep.)

**Why no numeric threshold is pinned here.** Retro-triage of the existing corpus is out of scope
and this repo has no lived experience yet of how fast a deliberately-parked tier ages under the
new regime — pinning a number (30/60/90 days) now would be a guess dressed as a contract. Surface
age at every triage run; let the PM tune a numeric staleness threshold once real aging data exists
— the same posture `check-weekly-staleness.py`'s ≥5-day/≥15-commit thresholds took, tuned from
lived cadence rather than invented up front.

**Draw-on-demand.** See `docs/wiki/queue-terminus-doctrine.md § "Baton inbox is low" — defined
over pickable batons, not raw count` for the definition this hinges on — pickable batons are
handoffs with `deployment_state: ready_to_fire`, never raw `state/handoffs/` directory count. When
a triage run finds the pickable baton inbox low by that definition, it draws from the parked tier
— re-surfacing `deferred` entries as triage candidates for solo-baton / themed-baton / immediate-
dispatch / re-park disposition — rather than only triaging the raw incoming queue rows for that
session. A parked entry drawn back into circulation this way re-enters the four-outcome terminus
like any other item; parking is not a one-way door, and a re-parked entry gets its `why_blocked`
re-stated or updated, not silently carried over unexamined.

## Cross-Links

- Canonical rule: `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Improvement Queue" — closure mechanics, two-tier model.
- Structured-form rollout: `docs/wiki/improvement-queue-schema.md` — directory-form shape + `coordinator-queue-append` CLI.
- Central-queue migration: `docs/plans/2026-06-22-cockpit-contract-ext.md` § C2c — prose→YAML migration of `state/coordinator-improvement-queue.md`.
- Schema docs (per-queue field contracts): `docs/wiki/debt-backlog-schema.md`, `docs/wiki/bug-backlog-schema.md`, `docs/wiki/improvement-queue-schema.md`, `docs/wiki/cross-repo-commitments-schema.md`.
- Parked-tier terminus doctrine: `docs/wiki/queue-terminus-doctrine.md` — the four-outcome triage
  terminus whose outcome class 4 (explicit park) feeds § Age-Ping — Parked-Tier Aging Discipline
  above.
- Applies to:
  - `state/debt-backlog/` (directory-form)
  - `state/bug-backlog/` (directory-form)
  - `state/improvement-queue/` (directory-form — project-scoped rows AND central universal rows tagged `queue_scope: central`)
  - `state/cross-repo-commitments/` (directory-form — own closure enum, see § Cross-Repo-Commitments Closure)
