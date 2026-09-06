---
title: independent-coverage-auditor-pattern
created: 2026-05-30
type: doctrine
related:
  - plugins/coordinator/docs/wiki/plan-coverage-checker.md
  - plugins/coordinator/docs/wiki/reviewer-pipeline.md
  - plugins/coordinator-claude/global-doctrine/CLAUDE.md
  - plugins/coordinator/snippets/em-operating-doctrine.md
  - plugins/deep-research/agents/coverage-auditor.md
  - docs/plans/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md
---

<!-- spec-backlink: archive/specs/2026-05/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md § C8, § AC13 -->

# Independent Post-Hoc Coverage Auditor Pattern

## The pattern

A **fresh-eyes, independent agent** is dispatched *after* a synthesis or artifact is complete. It
audits output coverage — did the synthesis carry the inputs? — and emits a **sidecar** recording
what is present-with-pointer, what is absent, and where a reader could go deeper. It never edits
the artifact it audits.

The governing principle, inherited from `plan-coverage-checker.md:93`:

> **The author's own confidence is the failure mode.** An agent that believes its output is
> comprehensive is in exactly the highest-risk state for a coverage gap. The agent that made the
> synthesis cannot audit its own completeness; the pattern exists to catch what author confidence
> masks.

Three requirements define a conforming instantiation:

1. **Fresh eyes.** A new, independent agent — not the synthesizer, not any specialist whose content
   was in scope. Dispatch-point: after synthesis completes, before archive/cleanup.
2. **Sidecar-only output.** The auditor emits one artifact: a coverage-audit sidecar adjacent to
   the synthesis output. It **never writes the synthesis output path**. This is the no-edit/no-bloat
   contract, upstream, enforced directly in `coordinator/agents/parallel-review-synthesizer.md` and `coordinator/agents/research-synthesizer.md` (not in coordinator/CLAUDE.md, which does not carry a § Synthesis Discipline section — that would have been a pure duplicate):
   > "Synthesizers don't rewrite — they assess, fill, and frame. … Never re-author specialist
   > content."
3. **Non-teammate Agent.** Dispatched as a plain `Agent(...)` — spawned outside any team context.
   This is the established non-teammate-subagent pattern for inter-phase pipeline steps:
   `claude-code-platform-gotchas.md:333` ("dispatch it as a regular subagent — not a teammate"),
   `staff-sessions.md:113` ("scouts (N teammates) → EM dispatches subagent for inter-phase work →
   specialists (M teammates); total teammates: N + M, staying within 7").

Coverage classification is **binary**: `present-with-pointer` or `absent`. "Under-represented" is
a judgment call beyond a Sonnet cross-reference task. The closed-world input universe is scoped to
specialist/worker claim records only — synthesizer-authored additions (e.g. `[SWEEP ADDITION]`
content) have no upstream claim record and are excluded from the denominator; including them causes
false-absent noise.

**Always-on, no EM opt-out.** The pattern is skill-internal (see each instantiation's wiring
point). An opt-out by a confident author re-instantiates the failure mode it exists to prevent —
the same logic as plan-coverage-checker's no-opt-out (`plan-coverage-checker.md:93`, OD-3 in the
deep-research plan).

## Two named instantiations

### Instantiation 1 — deep-research `coverage-auditor`

**Agent file:** `deep-research/agents/coverage-auditor.md`
**Spec:** `docs/plans/2026-05-30-deep-research-synthesis-fidelity-coverage-audit.md`

The coverage auditor for the four deep-research pipelines (A web, B repo, C structured, D
notebooklm). It is dispatched by the EM at the pipeline driver's "On Completion Notification"
step — after the synthesis is written, before archive/cleanup (the team auto-cleans on session exit).

**Input universe:** specialist/worker claim records per pipeline:
- A (web), B (repo): `*-claims.json`, `*-assessment.md`
- C (structured): `*-findings.md` + `synthesis-annotations.md` as drop-justification oracle (OD-1 —
  structured has no prose synthesis to distort; relay is OOS; the auditor checks that every
  verifier finding mapped to a field or was dropped-with-annotation)
- D (notebooklm): `{letter}-claims.json` as primary + notebooklm MCP tools (`notebook_query`) for
  notebook-level verification — **documented divergence**, because on-disk claims files are a lossy
  extraction of the actual notebook content. Degrades gracefully to claims-only if MCP unavailable,
  with an explicit sidecar note.

**Sidecar format** (`{output-path minus .md}-coverage-audit.md`): two structured sections —
(1) **Coverage Pointers** — binary claim-by-claim cross-reference (present-with-pointer / absent);
(2) **Completeness Map** — distilled-out topics with source pointers for readers who need depth.

**Two-artifact reader contract** (must be stated in the sidecar spec):

| Artifact | Question answered | Owner | Drives |
|---|---|---|---|
| `gap-report.md` | "Did we research enough?" (input coverage) | Synthesizer | Web deepening gate |
| `-coverage-audit.md` | "Did the synthesis carry the research?" (output coverage) | Auditor | Reader completeness |

The synthesizer's Phase 1 `gap-report.md` is preserved unchanged — the auditor does not supersede
it. The auditor owns the output-vs-input question; the gap-report owns the input-coverage question.
The synthesizer's `[UNFILLED GAP]` inline markers remain in synthesis prose (reader-facing, per
`research-synthesizer.md:89`); the auditor's Completeness Map supersedes and consolidates the
scattered free-prose meta-observations paragraph, referencing the inline markers rather than
deleting them.

**Per-pipeline applicability matrix:**

| Pipeline | Coverage Auditor | Fidelity Relay |
|---|---|---|
| A (web) | Always-on | Yes (Team-1 phase, gated on gap-report signal) |
| B (repo) | Always-on | Yes (Team-1 phase, gated on `--deepest` flag) |
| C (structured) | Reduced (drop-annotation check; oracle: `synthesis-annotations.md`) | OOS (no prose synthesis to distort; CONTESTED pre-empts) |
| D (notebooklm) | Always-on (documented divergence: MCP tools + cleanup-deferred ordering) | OOS (no depth tier; structurally cannot gate — revisit if D gains depth concept) |

### Instantiation 2 — coordinator `comprehensiveness-auditor-DRAFT`

**Agent file:** does not yet exist (DRAFT)
**Spec:** `docs/wiki/reviewer-pipeline.md § Phase 2.4`

A DRAFT Sonnet-tier auditor for the coordinator plan-review pipeline. PM has approved the concept;
implementation has not landed. When it ships, it will run between plan-draft and prior-art-check —
`plan.write → comprehensiveness-auditor → docs-checker → prior-art-checker → Opus reviewer →
integrator` — because gap findings often reshape the plan body (adding Rollback, Migration sections)
and the downstream checks should run on the amended body.

Its audit question is structural: "does the plan address canonical coverage areas (rollback,
migration, observability, security boundary, error paths, test surface, concurrency, docs impact)?"
Output sidecar at `state/review-findings/{timestamp}-comprehensiveness.md`. Non-empty Silent column
blocks downstream reviewer dispatch until the EM fills or annotates N/A.

## Shared doctrine; disjoint implementations

These two instantiations **share the doctrine above** but do NOT share an agent file or prompt
template. Their input universes are structurally disjoint:

- Deep-research auditor: research synthesis + specialist claim records (`*-claims.json`, etc.) —
  the output of a multi-agent research pipeline.
- Coordinator comprehensiveness-auditor: coordinator plans and their coverage against canonical
  engineering concerns (rollback, migration, etc.) — the input to a plan-review pipeline.

Combining them into a shared agent would require a generic cross-domain input parser that is more
fragile and harder to tune than two domain-specific prompts. Doctrine is the shared layer;
instantiation is necessarily per-domain. This follows `coordinator/docs/wiki/ceremony-calibration.md § Pattern-extraction calibration` (formerly `coordinator/CLAUDE.md § Self-Improvement Loop`):

> "Codify a stable pattern before running new instances under it. Wait for instance #3 before
> extracting into a skill."

With two named instantiations (one shipped, one DRAFT), the pattern is now codified at the wiki
level. The third instantiation — whichever domain it lands in — should evaluate whether to extract
into a shared base template, or remain domain-specific for the same disjoint-input-universe reason.

## Contact points

Per `coordinator/docs/wiki/coordinator-tripwires.md § Adding a Convention to the Coordinator System` — conventions decay
unless greppable from surfaces agents encounter:

**Deep-research instantiation:**
- `plugins/deep-research/agents/coverage-auditor.md` — agent body
- `pipelines/deep-research/coverage-auditor-prompt-template.md` — per-pipeline field set
- `commands/research.md` — driver contact point
- `plugins/deep-research/CLAUDE.md` — plugin-level convention surface
- `deep-research/pipelines/team-protocol.md` (and repo/structured variants) — protocol contact points
- This wiki entry — canonical pattern doc

**Coordinator instantiation (when it ships):**
- `agents/comprehensiveness-auditor.md` (to be created)
- `skills/review/SKILL.md` Phase 2.4 (to be wired)
- This wiki entry — canonical pattern doc

No tripwire registration is required for the auditor pattern itself — it is a dispatch convention,
not a static-grep rule. The deep-research driver wiring contact-points above are the greppable
surfaces; see `coordinator/docs/wiki/coordinator-tripwires/` for the registry if a static-grep tripwire is
introduced in a future chunk.

## Lineage

The independent post-hoc coverage auditor pattern is the post-synthesis analog of
`plan-coverage-checker.md` — "the author's confidence is the failure mode" (`plan-coverage-checker.md:93`).
plan-coverage-checker applies it pre-synthesis, at the plan-review seam. This pattern applies it
post-synthesis, at the output-verification seam. Both share the same no-opt-out rationale.
