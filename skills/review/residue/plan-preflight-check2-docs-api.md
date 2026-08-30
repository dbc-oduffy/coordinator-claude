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

`docs-checker` is auto-provisioned its sidecar at spawn, same as Check 1's — no manual pre-scaffold. Dispatch it; it writes findings there and returns the pointer.

_See `${CLAUDE_PLUGIN_ROOT}/docs/wiki/docs-checker-pre-review.md` for full rows and sidecar consumption pattern._
