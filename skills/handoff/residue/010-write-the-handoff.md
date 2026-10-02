---
segment_id: write-the-handoff
case: shared
class: protected
order: 10
---

## Step 1: Write the Handoff

Scaffold by running `baton-assemble apply` (run the apply line the entry brief rendered), which executes the whole directive set as one transaction — `d1` `coordinator-doc-new`, `d2` `lint-frontmatter`, `d4` render the tracker, `d5` `session-claim-cli` release-artifact plan, `d6` `handoff.supersede_predecessor` (fires only when this brief names a predecessor; the route is green — pass `--continued-into` naming the successor when `mode='supersede'`, per § Supersession below). Then fill the body per the scaffold's canonical section skeleton (`## What Was Accomplished`, `## Current State`, `## Next Steps`, `## What I Learned`, `## Session Ledger`). **The ledger row is body text you write here — `handoff.append_session_ledger` is for a CLAIMED baton and refuses an open one; that refusal is not the minter being denied its own baton.** `## What I Learned` asks what you would resent re-deriving; never leave it a placeholder. Write the file FIRST, before any git operation — it is the irreversible artifact under context pressure; everything downstream is recoverable from disk.

**An `## Acceptance criteria` block is a checkbox list — `- [ ]` / `- [x]`, never prose bullets.** The completeness gate counts boxes; zero returns `indeterminate`. `kind: session-handoff` needs no such block (the gate reads the joined plan's `status:`).

**Closing a `scope_mode: spec-dispatch` session.** When this handoff closes a session that worked from a `scope_mode: spec-dispatch` body, the artifact additionally names (i) the scoped `code-reviewer` verdict and its integration commit; and (ii) whether the plan-reconciliation micro-step ran — ACs ticked, `status: implemented` stamped — or is being explicitly deferred to the resuming session, naming the plan's state.
**`d5` releases, it never acquires.** Authoring a handoff relinquishes the plan, so `d5` runs `session-claim-cli release-artifact plan` against this session's claim — best-effort, holder-identity-checked (a non-holder no-ops to success). Where this session is not the recorded holder, `d5` writes the `claim_holder_relinquished` record instead of releasing. Acquisition is permitted only to an unambiguous live holder: plan authorship (`coordinator-doc-new --type plan`), `/pickup` on transfer, `/execute-plan`'s Step 0 — never a drive-by reader.
