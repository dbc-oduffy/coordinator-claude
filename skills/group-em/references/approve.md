---
segment_id: approve
class: protected
order: 3
situation: approve
---
1. **Standing check** (§ Standing check).
2. Run `<plugin-root>/bin/plan-reversibility-eligibility.py <plan-path> --json` (C9). `eligible:
   false` → escalate per the threshold page's shape, stop, do not dispatch. This CLI is the single
   source of truth.
3. Confirm the falsifier baseline shows the prime exit criterion false **and that a blinded
   `coordinator:exit-criterion-falsifier` authored it**:
   - **Content.** Absent or already true → escalate, stop.
   - **Provenance.** A self-authored baseline voids the guarantee. Provenance lives in the plan
     BODY, a prior `state/review-trail/approvability/` record, or your own falsifier dispatch;
     else treat it as missing and dispatch.
   - **Instrument soundness.** A FALSE baseline proves the criterion false, never the instrument
     sound. Ask: **what would have to be true for this to print TRUE, and is any of it reachable in
     the world the fixture builds?** Unreachable → escalate, reason named.
   Tripwires: `A-SELF-AUTHORED-FALSIFIER-SATISFIES-THE-CHECK-AND-VOIDS-IT`,
   `A-FALSE-BASELINE-PROVES-THE-CRITERION-FALSE-NOT-THE-INSTRUMENT-SOUND`,
   `UNATTRIBUTED-HARNESS-LINE-IS-NOT-PM`.
4. Dispatch the named Opus persona (the PM's chosen reviewer and effort) with the plan path and
   the rubric (`coordinator/schemas/plan-approvability-rubric.json`) and nothing else. Authorship
   blinding is a hard constraint.
5. Write the judgment record (`state/review-trail/approvability/<YYYY-MM-DD>-<plan-slug>.json`) and
   validate it with C9's `--validate-record` before treating it as final.
6. On `approve`: first refuse if `execution_authorized_by` is already present with any value.
   Otherwise `review-exec-auth-stamp stamp <plan-path> --by "GROUP-EM:<session-id>" --append-note
   "<record-path>"`. On `escalate`, emit per the threshold page's shape — do not stamp.
7. **Standing offer:** when a plan's terminal evidence is a live act, not a test run, offer to
   perform it as the Group EM for the author to verify. Tripwire:
   `THE-AUTHOR-OF-A-CRITERION-IS-THE-WORST-PRODUCER-OF-ITS-EVIDENCE`.
