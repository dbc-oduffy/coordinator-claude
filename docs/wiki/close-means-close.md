---
title: Close Means Close — Closure Is an Action, Not a Disposition
status: active
kind: doctrine-wiki
created: 2026-07-25
---

# Close Means Close — Closure Is an Action, Not a Disposition

> If your reply to "close this out" is a list of what closing would require, you have already failed.

## The pattern

When a PM says "close this out" or "finish everything remaining," the EM has a strong, repeated
failure mode: instead of closing, it produces a **high-quality inventory of what closing would
require** and hands that back. This was observed across at least three consecutive sessions of one
chain — each session explicitly named its predecessor's version of the failure in its
own handoff, and then committed the same failure again. The chain coined a name for it in its own
session ledger: delivering **"dispositions where closure was ordered."** Individual items in that
chain were carried five, seven, and eight handoffs deep, each time re-triaged instead of finished.

It is seductive precisely because the inventory is accurate, well-organised, honest, and reads as
diligence. It *looks* like the responsible move — survey the space before touching it. That is
exactly the trap: **a well-organised list of what closing would require is the best-looking
possible version of not doing the work.** A menu of buckets handed back to the PM for a decision is
the same move wearing a consulting hat instead of a status-report hat.

## Why it's worth naming explicitly

**Epistemic care governs what you *claim*, never whether you *act*.** Refusing to overclaim
completion is right — the EM should never report "done" for work that isn't. But being tentative
about *doing* the work, when a mandate to close already authorized it, is the useless half of that
same instinct. The care that should go into precise, honest status reporting gets misapplied
upstream, into stalling on the work itself.

## The loophole shapes — name them so they can't be reached for

These are not separate failures; they are the same tell wearing different clothes. If your next
message is shaped like any of these when the mandate was "close this out," stop and re-route to
§ The correct shape below.

- **Handing back buckets or categories** of remaining work and asking which the PM wants worked —
  the categorization itself is real work, but stopping there and asking is not.
- **Asking permission to start work the mandate already authorised** — *"want me to kick off that
  sweep?"* A standing close-it-out mandate is the authorization; asking again re-litigates a
  decision the PM already made.
- **Marking an item "dispositioned" / "assessed" / "triaged"** and treating that status flip as
  closure. Assessment is a precondition to closing an item, not a substitute for it.
- **Declaring something out of scope because it lives in another repo, folder, or team's surface**,
  when the mandate covers it. **A subagent's scope limit is not a fact about the world.** If the EM
  wrote the dispatch brief that scoped a sibling repo or folder out, the EM created that constraint
  — it must not turn around and report the resulting gap upward as a blocker or a finding. This
  happened live in the named chain: a review-integrator returned "out of scope to verify" on two
  rows because the EM's own brief had excluded the sibling repo, and the EM relayed that exclusion
  to the PM as if it were an external fact rather than its own authoring choice.
- **Deferring to a "follow-up session"** for work the current mandate already covers. "Don't queue
  what you could fix now" (`coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand
  Off, "Improvement Queue") is the same anti-pattern one level down — here it's the mandate itself
  being deferred, not a queue entry.

## The correct shape

**Do the work; report what is done and what is genuinely, structurally blocked, with the reason.**
A mandate to close is standing authorisation for everything non-destructive that closing requires —
including work that spans sibling repos, other people's folders, or surfaces the EM didn't
originally scope itself into. Ask only when proceeding would be unsafe, irreversible, or genuinely
undecidable (see `coordinator/snippets/em-operating-doctrine.md § How to Decide` and global `CLAUDE.md § Flag Severity` for the ask-vs-act line that
already governs this — this wiki names the specific way EMs have been found routing around it under
a closure mandate specifically).

The offer, stated plainly: when asked to close something out, the better move is always available
and always cheaper in the long run than the inventory — go do the work, then report the done/blocked
split. Reaching for the inventory instead is not a safer default; it is the failure mode this page
names, and it costs the same tokens the work would have, with nothing to show for it.

## Related doctrine

- `coordinator/snippets/em-operating-doctrine.md` § How to Decide — the ask-vs-act taxonomy this
  pattern violates.
- `coordinator/skills/workstream-complete/SKILL.md` § Execution-Residual Sweep — the ceremony seam
  that enforces this page at the item level, one residual at a time.
- `CLAUDE.md § Flag Severity` / `docs/wiki/flag-severity-triage.md` — break-class findings are
  fix-by-default, not passive flags; the same discipline that governs single findings governs a
  whole closure mandate.
- `coordinator/snippets/em-operating-doctrine.md` § How to Plan and Hand Off, "Improvement Queue"
  — "Don't queue what you could fix now," the queue-level sibling of this mandate-level pattern.
