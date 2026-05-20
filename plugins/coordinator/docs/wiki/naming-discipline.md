# Naming Discipline

> When to rename a skill, agent, or doctrine surface — and when to wait. Names are cheap to change once, expensive to change twice, and very expensive to change in anticipation of occupants that never arrive.

---

## Skill names earn umbrella status by accumulating occupants, not by anticipating them

Refuse speculative umbrella renames — *"rename `foo` → `foo-suite` to leave room for siblings"*, *"rename `verify-coverage` → `coverage-tools` because we might add more checks later"*. Rename when a second occupant **actually lands**, not when one is hypothesized.

The failure mode of speculative umbrella renames:

- The anticipated siblings often don't materialize — the umbrella sits with a single occupant whose name now overpromises.
- The rename invalidates every existing reference (skill files, docs, lessons, commit messages, prior-art-checker corpus) for a benefit that may never accrue.
- When siblings *do* eventually arrive, their actual shape often doesn't fit the anticipated umbrella — the rename has to happen *again* to fit reality, costing double the churn.

The cheap path: keep the singular name. When sibling #2 lands and is a clean fit, rename once with both occupants in hand. When sibling #2 lands and *isn't* a clean fit, you've avoided a wrong-shape umbrella.

This is the naming corollary of the **instance-#3 rule** (`ceremony-calibration.md` § Pattern-extraction calibration): wait for real recurrence before codifying. Umbrellas are a structural codification — they deserve the same discipline.

## Log-field naming — name for the check, not the outcome

Log fields are contracts, not labels. A field must measure exactly one fact, named for that fact. Misnamed fields decay diagnosis: a field reporting NVML probe state but named `cuda_available` (a torch concept) confuses reviewers, operators, and agents downstream — everyone reasons from the name, not the implementation. Treat a rename to match what the field actually measures as a *fix*, not cosmetic.

Two checks at field-add time:
- **Is the name a check (the question being asked) or an outcome (the answer)?** Prefer check-shaped names (`pynvml_importable`, `vram_gate_active`) — they survive when the outcome interpretation shifts. Outcome-shaped names (`cuda_available`) lock in one interpretation and silently mislead when the underlying check changes.
- **Does the name promise more than the value delivers?** A boolean named `gpu_ready` that only checks driver presence promises a richer assertion than it makes. Narrow the name to what the value actually proves.

## Related

- `docs/wiki/ceremony-calibration.md` § Pattern-extraction calibration — instance-#3 rule for skill extraction
- `docs/wiki/implementation-standards-by-domain.md` § Observability contracts — companion rules for the log-emit shape
- `coordinator/CLAUDE.md` § Self-Improvement Loop — codify-a-stable-pattern discipline
