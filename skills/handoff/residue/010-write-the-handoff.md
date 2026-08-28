---
segment_id: write-the-handoff
case: shared
class: protected
order: 10
---

## Step 1: Write the Handoff

Scaffold by running `baton-assemble apply` (see the assembler blurb above for the literal invocation), which executes the whole directive set as one transaction — `d1` `coordinator-doc-new`, `d2` `lint-frontmatter`, `d4` render the tracker, `d5` `session-claim-cli` release-artifact plan, `d6` `handoff.supersede_predecessor` (fires only when this brief names a predecessor — and **currently fails `-32006`**, since it dispatches the suspended `handoff.archive_transition`; `apply` returns `status: partial` having landed everything else and compensates cleanly, so treat that partial as expected and finish the flip by hand per § Supersession below). Then fill the body per the scaffold's canonical section skeleton (`## What Was Accomplished`, `## Current State`, `## Next Steps`, `## What I Learned`, `## Session Ledger`). `## What I Learned` is the one a hurried session leaves as a placeholder comment: it asks what you learned that you would resent re-deriving, and an empty one is a session's findings thrown away, not a section you were spared. Write the file FIRST, before any git operation — it is the irreversible artifact under context pressure; everything downstream is recoverable from disk.

**An `## Acceptance criteria` block is a checkbox list — `- [ ]` / `- [x]`, never prose bullets.** The completeness gate counts boxes; a heading with zero returns `indeterminate`, which reports as a quiet unverified rather than a wrong. `kind: session-handoff` needs no such block (the gate reads the joined plan's `status:` instead); every other kind has its own body counted.

**Closing a `scope_mode: spec-dispatch` session.** When this handoff closes a session that worked from a `scope_mode: spec-dispatch` body, the artifact additionally names (i) the scoped `code-reviewer` verdict and its integration commit; and (ii) whether the plan-reconciliation micro-step ran — ACs ticked, `status: implemented` stamped — or is being explicitly deferred to the resuming session, naming the plan's state. A mid-flight handoff records that deferral honestly rather than asserting a completion it does not have.

**`d5` releases, it never acquires.** Authoring a handoff relinquishes the plan, so `d5` runs `session-claim-cli release-artifact plan` against this session's claim — best-effort, holder-identity-checked (a non-holder no-ops to success). Acquisition is permitted only to an unambiguous live holder: plan authorship (`coordinator-doc-new --type plan`), `/pickup` on transfer, `/execute-plan`'s Step 0. No surface may acquire on behalf of a drive-by reader — that makes "once touched this plan" indistinguishable from "working on it right now," the exact false positive `claim-plan` exists to prevent. Lifecycle: author acquires, `/pickup` acquires on transfer, `/handoff` and close release.
