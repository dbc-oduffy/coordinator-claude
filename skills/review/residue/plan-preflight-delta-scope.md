---
segment_id: plan-preflight-delta-scope
surface: plan
class: protected
order: 1
---

**Trigger — `--surface plan`:** EM has a plan / design doc / RFC ready for review (outgoing), OR a plan-review's findings have landed and need processing (incoming).

**Delta-scope on re-runs.** The Pre-Dispatch Verification rule "Re-run mechanical pre-flights after material plan amendments" is a re-run trigger, NOT a re-run-everything trigger. When re-running these checks on an *amended* plan (not a first pass), scope each checker to the delta:

- **prior-art-checker** — re-run only if the amendment changed a claim, added a new
  subsystem, or introduced a new external reference. A pure wording/typo amendment does
  not re-trigger it.
- **docs-checker** — re-run only over the *newly cited or changed* external APIs, not
  the full citation set already verified in the prior pass.
- **plan-coverage-checker** — re-run when the oracle or slate table changed (rows
  added/removed/edited). A prior sidecar exists; the checker renames it (Phase 0) and the
  EM diffs the new sidecar against it to see what the amendment moved.

**A delta re-run writes the canonical path, never a delta-suffixed one.** The plan-sidecar
family has exactly one path per `(plan-stem, lens)` pair — `state/plan-sidecars/<plan-stem>.<lens>.md`
— and provisioning re-opens it idempotently on re-dispatch. A re-run archives the prior sidecar
by inserting `.<UTC-mtime>` before its final `.md` (filename-safe — hyphens for colons) and
writes the fresh findings at the canonical path. A name like `<plan-stem>.<lens>-delta.md` is off
the pattern every consumer derives, so it is invisible to them: reject it, don't sanction it.

Name the delta in the re-dispatch brief ("amendment touched §X and the slate table;
scope your check to those"). A full re-run is correct only when the amendment was
structural enough that the prior pass's coverage fails to hold.

Both checks below fire independently — a non-trivial plan that also cites C++/UE APIs runs both workers.

**Phase walk (`--surface plan`).** Walks Phase 2.5 → 2.7 → (2.7b ∥ 2.7d) → 2.7c → 2.8, then dispatch, then Phase 3.5 → 3.7 → 4 → 5.
