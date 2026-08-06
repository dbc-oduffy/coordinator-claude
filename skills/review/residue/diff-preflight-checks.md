---
segment_id: diff-preflight-checks
surface: diff
class: protected
order: 20
---

Three independent pre-flight checks beyond the diff freeze. Each fires or skips on its own condition; multiple can fire on the same diff.

**Check 1 — TDD compliance (self-check, no agent)**

- _Code introduces new behavior (feature, fix, refactor that changes externally observable behavior)?_
  → Verify against the TDD checklist before dispatching reviewer. If any test was written *after* the production code, surface to PM with the gap — the review will surface it anyway and a pre-review acknowledgment is cheaper than a the Staff Engineer finding.
- _Code is config-only / doc-only / generated code?_
  → Skip TDD self-check.

**Check 2 — Cited external APIs (docs-checker)**

- _Code cites C++ or Unreal Engine APIs?_
  → `docs-checker` is auto-provisioned its `assessment`-typed sidecar at spawn (`state/subagent-share/<session>/<provision_key>.md`) — no manual pre-scaffold. Dispatch it; it writes findings to its provisioned path and returns the pointer.
  → Mandatory dispatch of `docs-checker`. Other external APIs are EM judgment; in-repo-only skips.
  _See `docs/wiki/docs-checker-pre-review.md` for the full row table._

**Check 3 — Test evidence (test-evidence-parser)**

- _Diff includes **unintended** failing tests, runtime artifacts, or stack traces in the work-in-progress notes?_ (i.e., evidence of a problem the EM has not yet diagnosed — NOT verdict-bearing smoke output where a BLOCK or WARN is the expected outcome)
  → EM runs the failing test invocation and captures stdout/stderr to a file, then dispatches `test-evidence-parser` to `Read` that captured path and classify the failures. Read the structured output. Real failures block the dispatch; flakes/env failures get logged and the review proceeds.
- _Diff has clean test runs (or no test surface yet — pre-TDD scaffold)?_
  → Skip `test-evidence-parser` at pre-flight; reviewer may still call it via Worker Dispatch Recommendations.

_(EM-initiated pre-flight; the normal case is reviewer-routed dispatch via the Worker Dispatch Recommendations block at Branch B. Pre-flight loses the routing-intelligence framing, so use only when the diff already exhibits failure evidence the reviewer would otherwise stumble into cold.)_

**Phase walk (`--surface diff`).** Walks Phase 2.5 → 2.7 → 2.7b → 2.7c → 2.8, then dispatch, then Phase 3.5 → 3.7 → 4 → 5.
