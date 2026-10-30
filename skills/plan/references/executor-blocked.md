---
segment_id: executor-blocked
class: protected
order: 1
situation: executor-blocked
---
## Branch D — Executor BLOCKED on substrate drift

_Condition: a dispatched executor returns BLOCKED citing substrate differing from what the plan asserted (path moved, helper renamed, framework changed, contract field absent, schema column missing)._

- _Default: amend the plan or write a successor; do NOT silently expand executor scope to absorb the drift._
  → Re-invoke `coordinator:plan` to amend (small drift) or compose a successor (larger drift or shape change). Re-run the pipeline from substrate verification; that invariant is shared; which chain discharges it is selected by the lane. `plan`: prior-art-checker → named Opus persona (`review-findings-ledger verify`). `spec-dispatch`: re-run **Branch B** over the drifted paths, amend the light body, re-fire the light terminal (its scoped `code-reviewer` pass still binds). **Do not hand the S lane the full lane's chain.**
- _Product-risk findings during BLOCKED inspection (privacy, permission-default change, external contract shift)?_
  → Even under `/autonomous`, surface them via `AskUserQuestion` before amending.
