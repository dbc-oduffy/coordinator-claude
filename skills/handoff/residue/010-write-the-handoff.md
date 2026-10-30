---
segment_id: write-the-handoff
case: shared
class: protected
order: 10
---

## Step 1: Write the Handoff

Scaffold by running `baton-assemble apply` (the apply line the entry brief rendered), which executes the whole directive set as one transaction — `d1` `coordinator-doc-new`, `d2` `lint-frontmatter`, `d4` render the tracker, `d5` `session-claim-cli` release-artifact plan, `d6` `handoff.supersede_predecessor` (fires only when the brief names a predecessor; pass `--continued-into` naming the successor when `mode='supersede'`, per § Supersession). Then fill the body per the scaffold's section skeleton (`## What Was Accomplished`, `## Current State`, `## Next Steps`, `## What I Learned`, `## Session Ledger`). **The ledger row is body text you write here — `handoff.append_session_ledger` is for a CLAIMED baton and refuses an open one.** `## What I Learned` asks what you would resent re-deriving; never leave it a placeholder. Write the file FIRST, before any git operation.

**An `## Acceptance criteria` block is a checkbox list — `- [ ]` / `- [x]`, never prose bullets.** The completeness gate counts boxes; zero returns `indeterminate`. `kind: session-handoff` needs no such block.

**Closing a `scope_mode: spec-dispatch` session**, the artifact also names (i) the scoped `code-reviewer` verdict and its integration commit; and (ii) whether the plan-reconciliation micro-step ran — ACs ticked, `status: implemented` stamped — or is deferred, naming the plan's state.
**`d5` releases, it never acquires** (`session-claim-cli release-artifact plan`, best-effort, holder-checked). Acquisition belongs only to plan authorship, `/pickup` on transfer, and `/execute-plan`'s Step 0.
