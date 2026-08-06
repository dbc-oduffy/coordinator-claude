---
segment_id: plan-preflight-check1-triviality
surface: plan
class: protected
order: 2
---

**Check 1 — Triviality (prior-art-checker)**

- _Plan covers non-trivial work?_ (design docs, RFCs, architectural plans; anything beyond a single-file fix)
  → `prior-art-checker` is auto-provisioned its sidecar at spawn (`state/plan-sidecars/<plan-stem>.<lens>.md`, computed by claude-klabauter's `provision_report` — no manual pre-scaffold). Dispatch it with the plan path; pass the provisioned sidecar path from the dispatch brief through unchanged, and read the agent's returned pointer for the sidecar it wrote. Act on buckets: **Conflicts** → surface to PM with wiki quote before continuing; **Compatible-but-relevant** → fold reference into plan's "Considered alternatives"; **Silent** → no action.
- _Plan is genuinely trivial?_ (one-line doc fix, typo, link repoint, no design content)
  → Skip `prior-art-checker`.
