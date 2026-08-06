---
segment_id: plan-preflight-check2-docs-api
surface: plan
class: protected
order: 3
---

**Check 2 — Cited external APIs (docs-checker)** _(runs independently of Check 1)_

| API surface cited in plan | docs-checker? |
|---|---|
| C++ or Unreal Engine APIs | **Mandatory** — run `docs-checker` regardless of EM judgment. |
| Other external library APIs | EM judgment — run if cost is justified; skip silently if not. |
| Pure prose / in-repo-only references / no cited external APIs | Skip `docs-checker`. |

When dispatching `docs-checker` (Mandatory or EM-judgment rows above): it is auto-provisioned its sidecar at spawn (`state/plan-sidecars/<plan-stem>.<lens>.md`, computed by claude-klabauter's `provision_report` — no manual pre-scaffold). Dispatch it; it writes findings to its provisioned path and returns the pointer.

_See `docs/wiki/docs-checker-pre-review.md` for full rows and sidecar consumption pattern._
