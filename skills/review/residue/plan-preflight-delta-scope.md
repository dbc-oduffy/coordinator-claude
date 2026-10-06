---
segment_id: plan-preflight-delta-scope
surface: plan
class: protected
order: 1
---

**Trigger — `--surface plan`:** EM has a plan / design doc / RFC ready for review (outgoing), OR a plan-review's findings have landed and need processing (incoming).

**Delta-scope on re-runs.** The Pre-Dispatch Verification rule "Re-run mechanical pre-flights after material plan amendments" is a re-run trigger, NOT a re-run-everything trigger. When re-running these checks on an *amended* plan (not a first pass), scope each checker to the delta:

- **prior-art-checker** — only if the amendment changed a claim, added a subsystem, or introduced a new external reference.
- **docs-checker** — only over newly cited or changed external APIs.
- **plan-coverage-checker** — when the oracle or slate table changed; the checker renames the prior sidecar (Phase 0) and the EM diffs the new one against it.
- **plan-reviewer** (XL lane only, lens suffix `plan-review-check`) — on an amended accepted-XL plan, scoped to the amended sections, then integrate via `review-integrator` before the pre-flights. A chain reviewer, not a pre-flight; its sidecar belongs to the plan-sidecar family below. A pure wording/typo amendment re-triggers none of these.

**A delta re-run writes the canonical path, never a delta-suffixed one.** The plan-sidecar
family has exactly one path per `(plan-stem, lens)` pair — `.coordinator-local/plan-sidecars/<plan-stem>.<lens>.md`
(`<lens>` includes `plan-review-check` for `plan-reviewer`) — provisioning re-opens it idempotently. A re-run archives the prior sidecar
by inserting `.<UTC-mtime>` before its final `.md` (hyphens for colons) and
writes the fresh findings at the canonical path. A `<plan-stem>.<lens>-delta.md` name is invisible to consumers: reject it.

Name the delta in the re-dispatch brief; a full re-run is correct only when the amendment was structural enough that the prior pass's coverage fails.

Both checks below fire independently — a non-trivial plan that also cites C++/UE APIs runs both workers.

**Phase walk (`--surface plan`).** Walks Phase 2.5 → 2.7 → (2.7b ∥ 2.7d) → 2.7c → 2.8, then dispatch, then Phase 3.5 → 3.7 → 4 → 5.
