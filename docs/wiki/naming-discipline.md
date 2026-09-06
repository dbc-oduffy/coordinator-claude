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

## Flipping an identity's resolution is not renaming the identity

When you migrate what an identity *resolves to* — e.g. `claude-central-em: ~/.claude` → the DoE-claude repo — the identity NAME stays valid. Doctrine and examples that merely USE the name (`to: claude-central-em`) are NOT stale and must be left untouched; only ASSERTIONS about where the identity lives or resolves (`central = ~/.claude`) need editing.

Grep for the **assertion, not the token**. Editing every occurrence of the name is over-inclusive churn that risks "fixing" correct lines — the same speculative-blast-radius trap as an anticipatory rename, in reverse. Discriminate the two reference classes before you touch anything: a use of the name is load-bearing-as-is; only a claim about its home moves.

## Rename blast-radius spans every reference shape, not just the primary form

A rename's blast radius is not one grep — it is one grep *per reference shape*. An identifier or path lives in the corpus in several distinct forms, and each is an independent axis:

- the namespaced id (`data-science:staff-data-sci`)
- the slash-path form (`data-science/agents/staff-data-sci.md`)
- quoted strings in hardcoded consumer arrays and parity tests
- comment / prose mentions

Scanning only the primary form misses the others. A real rename scanned only the colon-namespace form and missed the slash-path form, which was load-bearing in a hardcoded consumer array (`verify-quota-self-detect-sync.py`), a parity test, and a second `SKILL.md` table — all would have silently broken post-rename (the Staff Engineer caught it in pass-2). For any identifier/path rename, grep **every** reference shape as a separate blast-radius axis, not just the one you renamed from.

## Assign a new sequential ID by scanning bodies, not just filenames

When you allocate the next number in a sequential ID space (decision records, chunk ids, anything `PREFIX-NNN`), enumerate BOTH the filename prefixes AND the in-file `id:` frontmatter across the whole directory. Picking the next fleet decision-record number from only `DR-NNN-*.md` filename prefixes misses date-named files that carry an internal `id: DR-NNN` (e.g. a `2026-07-14-*.md` file that claimed `id: DR-059`) — which caused a DR-059 collision on 2026-07-16. The filename is one index into the ID space; the frontmatter is another. Scan both before claiming the next number.

## Cite a decision-id by the namespace that minted it, not the bare number

A bare `DR-###` is ambiguous in this repo: four namespaces mint ids of that shape and mostly
collide on number. A bare id means `docs/decisions/` — that is the default and needs no
qualifier. Every other namespace is cited in a form that names it:

- a `claude-klabauter` record → repo-qualified, never a bare id that reads as ours. Two shapes
  are both correct, chosen by purpose: `` `claude-klabauter DR-210` `` (repo name + bare id) to
  cite a decision in prose; `` `claude-klabauter/docs/decisions/DR-###-<slug>.md` `` (full path)
  when the reader is being sent to open the record.
- a plan-local `DR-1`..`DR-9` → cited only inside the plan that mints it, never from outside
- a PREFIXED or document-local scheme (`SC-DR-###` in `scoped-safety-commits.md`, `DBT-DR-0##`
  in `document-bloat-trim.md`, the anchored `DR-001`..`DR-009` registry in `lesson-triage.md`,
  and any later one) → a document-local id, not a `docs/decisions/` citation, and never
  rewritten into one. This is a CLASS rule, not an enumeration: any scheme carrying its own
  prefix or scoped to one document is document-local by construction, whether or not it is
  named above. Treating this as a closed list is the failure mode this class rule guards
  against — folding document-local ids into `live-unique`, or the reverse.
- a doctrine surface that must survive re-reading cites path-qualified even when a bare id
  would happen to resolve.

Existing citations that already resolve under this convention need
no rewrite; this is a citation-form rule for new and ambiguous citations, not a license or
instruction to sweep and rewrite the corpus.

## Related

- `docs/wiki/ceremony-calibration.md` § Pattern-extraction calibration — instance-#3 rule for skill extraction
- `docs/wiki/implementation-standards-by-domain.md` § Observability contracts — companion rules for the log-emit shape
- `coordinator/docs/wiki/dogfooding-doctrine.md` § Cross-References (formerly
  `coordinator/CLAUDE.md` § Self-Improvement Loop, retired) — codify-a-stable-pattern
  discipline
