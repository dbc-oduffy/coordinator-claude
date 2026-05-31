---
title: prior-art-checker pre-review doctrine
created: 2026-05-06
type: doctrine
related:
  - plugins/coordinator/agents/prior-art-checker.md
  - plugins/coordinator/snippets/prior-art-check-consumption.md
  - plugins/coordinator/docs/wiki/reviewer-pipeline.md
  - plugins/coordinator/skills/learn-lessons/SKILL.md
  - docs/wiki/docs-checker-pre-review.md
  - docs/wiki/lesson-triage.md
  - tasks/handoffs/2026-05-06_165124_wired-in-wikis-lesson-checker.md
---

# prior-art-checker Pre-Review Doctrine

## What is prior-art-checker?

prior-art-checker is a Sonnet-tier agent that cross-references a plan artifact against the coordinator's accumulated prior art before the artifact reaches an Opus reviewer. It reads the plan, enumerates its claim surface, then searches four corpora — project wikis (`docs/wiki/` recursively, including subdirectories `marketplace/`, `opensource/`, `competitors/`, and `codebase-judgment/`), global wikis (`~/.claude/docs/wiki/`), `tasks/lessons.md`, and the central improvement queue — and reports each claim as **Conflict**, **Compatible-but-relevant**, or **Silent**.

The output is a sidecar at `<plan-path>.prior-art-check.md`. The agent makes no judgments and applies no fixes; it surfaces matches with verbatim quotes for the EM to disposition.

The result: Opus reviewers receive a plan that has already been cross-referenced against captured wisdom and can focus their attention on architecture and approach instead of re-deriving lessons we have already learned.

## Why this exists — the capture-recall loop

The coordinator system captures lessons via `tasks/lessons.md` → `learn-lessons` → `docs/wiki/` and the central improvement queue. **Capture is mature; recall was broken.**

Wikis sat in `docs/wiki/` without being part of any EM's default context. The EM rarely read them at plan time. Lessons promoted to wikis silently decayed because nothing in the workflow reached for them. The fix was not more wikis — it was a process loop that consults them automatically.

prior-art-checker is the recall side of the loop. Without it, captured wikis are storage; with it, captured wikis become live doctrine that shapes plans before they ship.

## What counts as "prior art"

Two kinds, both equally in scope:

1. **Doctrine** — rules about how things should be done. Project-agnostic patterns, conventions, anti-patterns. Examples: `test-design-discipline.md`, `cleanup-sweep-hazards.md`, `round-trip-contract-tests.md`.
2. **Institutional memory** — project-specific history. What we tried, what broke, why we made the call we did. Examples: `daily-branch-discipline.md` (born of a real incident), `scoped-safety-commits.md` (born of audit-trail corruption).

Both are equally important. A plan can be doctrinally fine and still violate a project-specific decision; a plan can be project-fine and still violate doctrine. The agent checks both corpora every run.

## Role in the review pipeline

**The prior-art-checker is a recall pre-flight, not a reviewer.** It does not participate in the sequential-review HARD RULE — it runs once before any reviewer is dispatched and its output is consumed by all downstream reviewers. Running it does not satisfy the "sequential" requirement; it sits upstream of the reviewer sequence entirely.

## When does it run? — EM Decision Rules

| Artifact type | Default | EM discretion |
|---|---|---|
| **Plan documents** (`docs/plans/*.md`, `~/.claude/plans/*.md`) | **Run by default.** | Skip only when the plan is a single-file mechanical bug-fix with no architectural decision. |
| **Enriched stubs with architectural decisions** | Run when chunks introduce a new pattern, new agent, new convention, or modify cross-cutting doctrine. | Skip for stubs that are mechanical execution of a previously-checked plan. |
| **Code review (no plan artifact)** | Skip. | Run when a PR/diff lacks a plan but introduces a new pattern worth checking against doctrine. |
| **Pure prose** (lessons, postmortems, retros, strategy memos) | Skip. | None — no claim surface to cross-reference. |
| **Trivial single-file edits** | Skip. | None — overhead exceeds the benefit. |

**Special case — premise reversals.** When a plan reverses a prior decision (regenerates torn-down structure, re-introduces a pattern we previously removed), ALWAYS run the prior-art-checker. This is exactly the case where prior art most matters; per the coordinator's "Premise-pass before regenerating torn-down structure" rule, the prior-art-checker is the mechanical implementation of that premise pass.

**Skip is silent.** No flag needed, no justification required. EM judgment.

## Output format

```markdown
## Prior-Art Verification

**Plan:** <path>
**Verdict:** COMPATIBLE | WARN | BLOCKED-SURFACE-TO-PM | DEGRADED
**Claims checked:** N
**Conflicts:** X | **Compatible-but-relevant:** Y | **Silent:** Z

### Conflicts (plan contradicts prior art)
[verbatim quotes from prior art with EM-action suggestions]

### Compatible-but-relevant (plan should cite or align)
[verbatim quotes with citation suggestions]

### Silent areas (no prior art found)
[bulleted list of uncovered claims]
```

The verdict is advisory. The agent never auto-blocks; only the EM/PM may halt a review.

## Prior-art mutability — DoE-reviewer override path

*2026-05-17, project-rag.* Prior art is not immutable doctrine. When a PM-authorized DoE-tier reviewer (the Director of Engineering, or the Staff Engineer elevated by PM brief) finds that a captured wiki/lesson is outdated, vague, or wrong, they have explicit authority to override the prior-art-checker's conflict finding and direct the integrator to update the prior art rather than the plan. The integrator records the override decision and edits the wiki/lesson/queue as a first-class deliverable of the review pass — same commit, same review trail.

**When the override applies:**

- The plan deliberately reverses a captured pattern the project has since outgrown.
- The wiki entry was captured from a one-off incident and overstated as universal.
- The lesson was captured before a structural change that made it inapplicable.

**Required brief framing.** The dispatching EM MUST surface the override authority verbatim in the DoE reviewer's brief — e.g. *"You may direct the integrator to update prior art (wiki/lesson/queue) rather than the plan when the captured pattern is itself the problem. Cite the wiki entry and reason in your finding."* Without the verbatim elevation, the reviewer defaults to plan-side correction per the standard direction-of-correction enum (`update-plan` / `update-prior-art` / `both` / `override-and-document` / `PM-input-needed`).

**Companion doctrine:** `reviewer-pipeline.md § Reviewer elevation past charter` — for the mechanics of PM-authorized reviewer elevation generally.

## Verdict semantics

- **COMPATIBLE** — zero conflicts; compatible-but-relevant items are informational only. Proceed to Opus reviewer dispatch.
- **WARN** — one or more conflicts surfaced. EM (with reviewer + integrator help) picks a direction-of-correction per conflict before dispatching the Opus reviewer: `update-plan`, `update-prior-art`, `both`, `override-and-document`, or `PM-input-needed`. "WARN" does not mean "plan is wrong" — it means "two surfaces disagree; pick which to update." See § Bidirectional resolution.
- **BLOCKED-SURFACE-TO-PM** — one or more conflicts contradict load-bearing doctrine (scoped-safety-commits, daily-branch-discipline, round-trip-contract-tests, sequential-review HARD RULE, etc.) OR contradict explicit institutional memory recording a past incident. EM **must** escalate to PM before continuing. Do not dispatch the Opus reviewer until the conflict is resolved or PM authorizes override.
- **DEGRADED** — the agent ran with materially incomplete coverage. Emitted when: (a) Phase 1 capped at 30 claims and the plan has significantly more, (b) Stuck Detection fired ≥1 time, (c) a corpus was unreadable, or (d) estimated token cost exceeded 50K. Treat DEGRADED as no signal — review the plan fully against prior art as if no pre-flight ran. DEGRADED does not block; it flags unreliable coverage.

## Hard prohibitions — prior-art-checker must NOT

- Edit the plan inline. The agent writes exactly one file: the sidecar.
- Edit any wiki, lesson, or queue file (read-only against the corpus). Wiki/registry/lessons amendments arising from a Conflict are landed by the review-integrator after the EM picks a direction — not by the prior-art-checker itself.
- Apply auto-fixes of any kind. Recall is judgmental — even compatible-but-relevant findings could be wrong, and conflict resolutions need EM/PM input.
- Fabricate prior art. If a claim is silent, the agent says so. Inventing citations is worse than reporting a gap.
- WebSearch for general guidance. The agent checks **our** prior art, not the open internet's.
- Auto-block a plan. Only the EM/PM may halt a review.

## Distinction from docs-checker

The two pre-flights answer different questions:

| | docs-checker | prior-art-checker |
|---|---|---|
| **Question** | Are these external API claims factually correct? | Have we already established something relevant about this? |
| **Corpus** | Context7, LSP, project-RAG, cppreference | Project wikis, global wikis, `tasks/lessons.md`, central improvement queue |
| **Output** | Per-claim verification table (VERIFIED / UNVERIFIED / INCORRECT) | Three-bucket sidecar (Conflict / Compatible-but-relevant / Silent) |
| **Authority** | AUTO-FIX allowlist for tradeoff-free corrections | REPORT-ONLY — EM dispositions all findings |
| **Surface** | reviewer pipeline Phase 2.7 (`docs/wiki/reviewer-pipeline.md`) | reviewer pipeline Phase 2.7b (`docs/wiki/reviewer-pipeline.md`) |

They are not substitutes; they can both run on the same artifact.

## Sidecar format note

Sidecars use `kind:` rather than `type:` in their frontmatter to distinguish machine-emitted artifacts from authored docs. docs-checker sidecars should adopt the same convention when they are next revised (not in scope for this commit — surfaced as a follow-up).

## Distribution

The reviewer-side consumption block is synced via `plugins/coordinator/bin/verify-prior-art-sync.sh --fix` from `plugins/coordinator/snippets/prior-art-check-consumption.md` to all Opus reviewer prompts:

- `plugins/coordinator/agents/staff-eng.md` (the Staff Engineer)
- `plugins/coordinator/agents/eng-director.md` (the Director of Engineering)
- `plugins/game-dev/agents/staff-game-dev.md` (the Game Dev Reviewer)
- `plugins/data-science/agents/staff-data-sci.md` (the Data Science Reviewer)
- `plugins/web-dev/agents/senior-front-end.md` (the Front-End Reviewer)
- `<plugin-consumer>/game-dev/agents/staff-game-dev.md` (optional domain-plugin the Game Dev Reviewer variant)

The sync verifier is auto-discovered by `/update-docs` Phase 11b. See the tripwire in `coordinator/CLAUDE.md` — "Adding a Convention to the Coordinator System" section.

## Prior art is current best-state, not eternal law

Wikis, lessons, and registries record what we believed at last write-time. They are the corpus a new plan should align with *by default* — but they are not immutable. A plan that contradicts prior art may be the plan capitulating to the wiki, OR it may be the wiki needing revision because the plan is the corrective. Treating every conflict as "plan must yield" turns the prior-art-checker into a freeze mechanism; treating every conflict as "wiki is stale" turns it into noise. Neither is right.

The discipline: every Conflict is a **direction-of-correction question**, answered by the EM with reviewer + integrator input. The candidate directions (defined in the agent prompt) are `update-plan`, `update-prior-art`, `both`, `override-and-document`, and `PM-input-needed`. The sidecar surfaces the conflict and may offer a lean; the call is the EM's.

## Bidirectional resolution — who applies which edit

Once the EM has picked a direction per Conflict, edits land via the integrator chain after the Opus reviewer's normal pass:

| Direction | What lands | Where |
|---|---|---|
| `update-plan` | Plan amendment folding prior art in | The plan artifact |
| `update-prior-art` | Wiki/registry/lessons amendment | The cited prior-art file(s) |
| `both` | Plan amendment + prior-art amendment | Both surfaces, in one integration pass |
| `override-and-document` | One-line entry in plan's "Considered alternatives" citing prior-art quote and override rationale | The plan artifact |
| `PM-input-needed` | No edit until PM decides; then one of the above | Per PM direction |

The review-integrator agent has explicit authority to land prior-art-side edits when the EM's dispatch prompt names the direction per conflict. See `agents/review-integrator.md` § Prior-Art Conflict Resolution.

**Precedence when reviewer disagrees with EM's pre-dispatch direction.** The EM names a direction per conflict in the integrator dispatch prompt. If the Opus reviewer's findings recommend a different direction (e.g., EM pre-selected `update-plan`; reviewer's architectural read says `update-prior-art`), the integrator escalates as ASK — does NOT silently apply either direction. The EM resolves the conflict before the integration commit. The EM's dispatch-prompt direction does not auto-override a contrary reviewer recommendation; this is the structural protection against the EM short-circuiting the review's directional input.

## False-positive arbitration — feedback loop on wiki quality

The prior-art-checker is mechanical, not judgmental. It can over-match (false-flag a phrasing difference as a conflict) and under-match (miss a doctrine that applies but uses different keywords). The bidirectional resolution table above is the per-instance fix. The longer-running quality loop:

- **Repeated false-positives signal wiki revision.** When the same wiki entry produces multiple bogus conflicts across plans, that is a feedback signal — the wiki is outdated, vague, or wrong. Surface as a candidate for wiki revision (or land an `update-prior-art` direction the next time it fires). The prior-art-checker thus becomes a quality loop on the wiki corpus, not a freeze on it.
- **Repeated `update-prior-art` outcomes against the same entry** are the strong signal — two plans correcting the same wiki within a quarter means the entry is stale, not just badly phrased. Promote to a wiki-revision task at next `/workweek-complete`.

**Sidecar preservation.** Prior sidecars are never overwritten — on re-run the agent renames the existing sidecar to `<plan-path>.prior-art-check.<UTC-mtime>.md` before writing the new one. This means the arbitration history (what the first run flagged, what changed in the second run) is always available as an archived sidecar alongside the current one. The feedback-loop in rule 2 above depends on this archive existing.

**Operational hook:** during `/workweek-complete` Step 4 (improvement-queue triage), the EM scans recent `docs/plans/**/*.prior-art-check*.md` sidecars for Conflicts dispositioned as `override-and-document`, `update-prior-art`, or `both`, and flags wikis cited ≥3 times across those dispositions as candidates for revision. Repeated `update-prior-art` against the same wiki is the strongest signal — two plans correcting the same entry within a quarter means the entry is structurally stale, not just occasionally wrong. The in-flight bidirectional resolution handles individual conflicts at plan time; the weekly pass exists for cross-plan pattern detection that in-flight resolution cannot see. This is judgment-based, not automated — but the responsibility lives in weekly cadence so it doesn't drift.

## EM Disposition Prose Against a Conflict Needs Substrate Grep

**When the EM writes disposition prose against a prior-art-checker Conflict — especially a non-existence claim ("no typed X exists in this codebase") — that prose is a hypothesis until substrate-grepped, not authoritative framing.**

The prior-art-checker surfaces a Conflict; the EM responds with a disposition direction (e.g. `update-prior-art` with rationale "we don't have X"). If the rationale rests on a non-existence claim, it must be substrate-grepped before landing in the integration commit — the same no-fabrication discipline that applies to plan body assertions applies here. A disposition that convincingly argues "we have no typed Y" without a grep citation is fabrication with more prose around it.

**How to apply:** before writing an `update-prior-art` or `override-and-document` disposition that relies on a non-existence or existence claim about your codebase, run `grep -rn "<claimed identifier>" src/ tests/ plugins/ commands/` and quote a file:line result (or the zero-result) in the disposition. The sidecar body carries the rationale; the rationale is only load-bearing when it's grounded.

*Source: 2026-05-28 project-rag (tasks/lessons.md:5), companion to this wiki's § Bidirectional resolution.*

## Audit-side closure must cross-check pre-existing test signal

*2026-05-16, project-rag.* When an audit triage proposes closing a candidate as "out of scope" or "covered elsewhere," cross-check against pre-existing test failures on that candidate before closing. Convergent signal (audit says skip + existing test already red on the same surface) beats a unilateral audit-side contract-boundary assumption. The audit is reasoning forward from claim surface; the failing test is reasoning backward from observed behavior. When they disagree, the test wins until the audit explains the failure.

**Rule:** before dispositioning a prior-art match as `update-prior-art` or `override-and-document` on a candidate cited as "broken anyway," run the cited test on HEAD. A failing test that the audit was about to dismiss is the audit's blind spot, not noise.

## Tree-sitter ERROR-byte coverage interpretation

*2026-05-13, project-rag-ue-addon.* A "Tree-sitter ERROR-byte coverage %" figure cited in a plan or audit is meaningless without locus-vs-consumer-query context. ERROR bytes in regions never touched by the consumer's queries cost zero; ERROR bytes inside a query's target subtree are total failures. Coverage % aggregates both into one number, hiding the only distinction that matters.

**Rule:** when prior art cites a tree-sitter ERROR-byte percentage as evidence, demand the breakdown by consumer-query locus. "97% non-ERROR" is admissible only with "and the 3% does not overlap any of queries X, Y, Z." Without the locus split, treat the coverage figure as unverified.

## Sibling-Spinoff Pre-Commit Gate

**Plan-time spurious-spinoff drift caught by prior-art-checker is the highest-ROI pre-flight.** When a plan-writer assumes downstream infrastructure doesn't exist and authors a sibling spinoff for it, prior-art-checker's scout-artifact cross-reference catches the drift before the spinoff ships to disk.

Any sibling-spinoff handoff authored by a plan-writer MUST go through prior-art-checker before being committed — the spinoff substrate may already exist in the peer repo. The checker should search for the proposed hookspec name, dataclass name, and boot-block pattern across the peer-repo corpus (`peer_repos:` field in the checker brief).

*Canonical (2026-05-28, tc-7):* A plan-writer authored a project-rag-side spinoff for `project_rag_register_mcp_tool` hookspec, `AddonToolRegistration` dataclass, and boot-iteration block. All three already existed in project-rag's Wave-2 substrate (`core/addon_hookspecs.py:42`, `core/addon_protocol.py:190`, `mcp/project_rag_server.py:1308`, documented at `docs/wiki/addon-protocol-v1.md`). Prior-art-checker surfaced this from 3 scout artifacts within 5 minutes; spinoff was revoked, the deliverable collapsed into a ~10-line hookimpl.

**Operational trigger:** In `coordinator:plan` Branch C, when a chunk authors or commits a spinoff handoff, fire prior-art-checker with `peer_repos:` populated with the spinoff's target repo before the chunk is committed to disk.

## Cost target

Aim for under 10K tokens per plan check. The corpus is bounded (project wikis across all `docs/wiki/` subdirectories — currently ~57 files including `codebase-judgment/` entries — plus global wikis, lessons, and queue). RAG-over-wikis is a phase-2 optimization; for now, full-text reads of relevant entries is the contract.
