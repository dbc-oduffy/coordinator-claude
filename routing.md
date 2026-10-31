# Coordinator Routing Table

## Discovery Protocol

**Implementation:** `/review` implements both surfaces — `--surface plan` (plan artifacts) and `--surface diff` (code artifacts). This document describes the algorithm; that skill implements it. `/review-code` survives as a command shim that redirects to `/review --surface diff`.

At dispatch time, `/review` assembles a composite routing table:
1. Read this base routing table (universal reviewers + domain specialist reviewers + algorithm)
2. Scan all enabled plugins for root-level `routing.md` files
   *(the Data Science Reviewer, the Front-End Reviewer, and the UX Reviewer are always-registered in the coordinator base table — plugin scan adds further domain extensions. A plugin's signals come from its shipped `review-signals.json`: `coordinator/docs/wiki/planning/plugin-review-signal-overlay.md`.)*
3. Merge routing fragments into composite table
4. Match signal against composite table
5. Dispatch to matched reviewer

Domain plugins register additional reviewers by providing a `routing.md` file at the plugin root.

`contract/review-signals.json` is this file's machine projection, consumed by the composite table's automated matcher — the prose here is the source; the JSON follows it.

## Signal-Gated Pre-flight Lenses

### docs-checker
- **Signals:** A niche or version-sensitive external system the plan writes against (an API surface, an SDK, an engine), where a wrong signature is expensive
- **Model:** sonnet
- **Agent file:** `agents/docs-checker.md`

## Universal Reviewers

### the Staff Engineer (staff-eng)
- **Signals:** Architectural change, new subsystem, cross-cutting (many files, new pattern), backend, security, other/unmatched
- **Model:** opus
- **Effort:** Medium (escalates to High for architectural changes)
- **Backstop:** the Director of Engineering
- **Agent file:** `agents/staff-eng.md`

### the Director of Engineering (eng-director)
- **Signals (standalone primary):** Cross-team / cross-repo seams (consumer ↔ producer, plugin ↔ host, app ↔ shared library), generic-substrate / consumer-leak risk on producer-side surfaces, architecturally-ambitious plans where director-altitude authority is wanted, any review the PM directs to the Director of Engineering solo
- **Signals (backstop):** Chained after the Staff Engineer on High-effort reviews to challenge under-ambition or under-authority; this is one of the Director of Engineering's roles, not their identity
- **Model:** opus
- **Effort:** Medium (escalates to High when issuing cross-team directives or resolving architectural ambition)
- **Backstop:** None (terminal — the Director of Engineering is the Director of Engineering)
- **Agent file:** `agents/eng-director.md`
- **Invocation rules:**
  - **Standalone is a first-class dispatch.** When the PM says "get a the Director of Engineering review," dispatch the Director of Engineering solo — do NOT insist on running the Staff Engineer first. The Director of Engineering is a peer of the Staff Engineer in technical rigor, not a the Staff Engineer-attached subroutine.
  - **Backstop chain is still the default for High-effort architectural the Staff Engineer reviews.** the Staff Engineer runs first; the EM resolves any primary-vs-the Director of Engineering tension before the Staff Engineer applies its findings, never after — the Staff Engineer then applies the resolved work order.
  - **For cross-repo or consumer/producer-substrate reviews, prefer the Director of Engineering standalone over the Staff Engineer+the Director of Engineering.** the Staff Engineer's EM-altitude hedging on peer-team appetite is exactly what the Director of Engineering's director altitude is meant to bypass.

### Angelique (apm)
- **Trigger:** SIZE-gated, not subject-matter-signal-gated — fires on the plan's own sizing_object (frontmatter citation -> estimate.tshirt), at **XL and above**, dispatched by plan-blitz's size ladder (M and L are the Staff Engineer alone; XL and above add Angelique and the Director of Engineering). Not a `review-signals.json` entry.
- **Model:** opus
- **Effort:** Low
- **Backstop:** None — they challenge, they do not gate (`blocking_verdicts` for `coordinator:apm` is `null`, matching `coordinator:docs-checker`)
- **Agent file:** `agents/apm.md`
- **Sequencing:** Runs as the final stage of whichever tier fires — after the named reviewers apply their findings in `standard`, after `coordinator:eng-director` (the Director of Engineering) in `full`. Plan reviews are never parallelized (`skills/review/SKILL.md`); their ELI5-and-challenge pass comes last, once the technical and director-altitude passes have already shaped the plan.

## Domain Specialist Reviewers (Always-Present, Signal-Gated)

These reviewers are always registered in the coordinator routing table. They are activated by signal match — not by `project_type` or plugin enablement.

### the Data Science Reviewer (staff-data-sci)
- **Signals:** ML/AI pipeline, model serving, RAG, statistical analysis, data modeling, feature engineering, LLM fine-tuning, data preprocessing, experiment design
- **Model:** opus
- **Effort:** High
- **Backstop:** the Staff Engineer
- **Agent file:** `agents/staff-data-sci.md`

### the Front-End Reviewer (senior-front-end)
- **Signals:** Front-end, CSS, UI components, design tokens, component library, styling, responsive design, web accessibility
- **Model:** opus
- **Effort:** Medium (escalates to High when combined with architecture)
- **Backstop:** the UX Reviewer
- **Agent file:** `agents/senior-front-end.md`

### the UX Reviewer (staff-ux)
- **Signals:** UX flow, user-facing feature, trust/clarity assessment, onboarding, user interaction, form design, error states
- **Model:** opus
- **Effort:** Low (escalates to Medium for full flow reviews)
- **Backstop:** the Staff Engineer
- **Agent file:** `agents/staff-ux.md`

## Fallback Rule

Any signal that does not match a registered reviewer's signals routes to **the Staff Engineer** at **Medium** effort.

## Sequential Review Protocol

1. Domain specialist reviews first (if signal matches — the Data Science Reviewer, the Front-End Reviewer, and the UX Reviewer are always-registered signal-filtered reviewers; additional domain reviewers may come from plugins)
2. Coordinator incorporates feedback
3. Generalist (the Staff Engineer) catches regressions (if effort >= Medium)
4. Backstop challenges conservatism (if effort >= High, or Coordinator judges it warranted)

## Routing Fragment Format

Domain plugins MUST provide `routing.md` at the plugin root with this structure:

### [Reviewer Name] ([agent-name])
- **Signals:** [what triggers this reviewer]
- **Model:** [inherit | opus | sonnet]
- **Effort:** [low | medium | high]
- **Backstop:** [name — must exist in coordinator or same plugin]
- **Agent file:** `agents/[filename].md`

## Project-Type Configuration

Per-project config in `coordinator.local.md`:

    ---
    project_type: game-dev   # general | game-dev | web-dev | data-science | unreal-engine
    project_subtypes:        # optional free-form tags; used for engine-specific routing
      - unreal
    active_reviewers:        # optional explicit override
      - the Staff Engineer
      - sid
    ---

`project_type` is a single string. `project_subtypes` is an optional list of free-form tags (e.g. `unreal`, `unity`) that enable engine-specific or stack-specific routing within the declared type. Downstream consumers do best-effort matching; unknown subtypes are silently ignored.

`project_type: unreal-engine` (or `game-dev` with `project_subtypes: unreal`) selects `sid` (`game-dev:staff-game-dev`) as the default Opus reviewer for plans and code. For `project_type: unreal-engine` alone, `ue_review_signal.declares_unreal_engine` makes the `unreal` signal fire on every plan in the repo, doc-only plans included. `coordinator:docs-checker` runs on every plan and diff there, with no EM skip.

If no `.local.md` exists, default to core-only (the Staff Engineer + the Director of Engineering) for universal routing. The Data Science Reviewer, the Front-End Reviewer, and the UX Reviewer are always-registered signal-gated reviewers and activate by signal match regardless of `project_type`.

## Effort Calibration

The EM selects effort level based on change scope. These are defaults — the EM should override when they have context that signal-matching can't capture.

| Change Scope | Effort | Reviewers |
|-------------|--------|-----------|
| Hotfix / single-file / obvious fix | Low | 1 reviewer, domain match |
| Feature addition (2-5 files) | Medium | Domain + generalist |
| Architectural / new subsystem / cross-cutting | High | Domain + generalist + mandatory backstop |
| Maintenance/audit findings (already structured) | Medium | Domain reviewer only |
| Test-only changes | Low | 1 reviewer |
| Doc-only changes | Low | the Staff Engineer only |

## Skip Conditions

Not every change needs the full review pipeline:

- **Purely mechanical changes** (rename, format, move): `coordinator:validate` is sufficient, skip review
- **CI/CD config only**: EM self-review, no dispatch needed

## the Director of Engineering Standalone vs. Backstop — Dispatch Selection

When the PM or EM wants a the Director of Engineering review, decide which mode applies:

**Posture is described in the brief's prose, never passed as an argument.** `mode` is the harness `Agent` tool's own parameter — passing it to select the Director of Engineering's posture errors the dispatch. Say which posture you want in the dispatch brief itself ("standalone / director-altitude primary review", "ambition-backstop pass on the evolved artifact"); a bare "review this" defaults to standalone primary. See `agents/eng-director.md` and `skills/review/SKILL.md` § A.2 ¶ the Director of Engineering standalone vs. backstop.

- **Standalone (default when in doubt):** Dispatch the Director of Engineering solo via `Agent(subagent_type=coordinator:eng-director, ...)`, describing the standalone / director-altitude posture in the brief. Use when (a) the artifact spans repos or touches a consumer/producer seam, (b) the PM said "get a the Director of Engineering review" without naming the Staff Engineer, (c) the architectural ambition itself is what's being evaluated, or (d) the Staff Engineer would hedge on cross-team scope that the Director of Engineering has authority to set.
- **Backstop (after the Staff Engineer):** Dispatch the Director of Engineering describing the ambition-backstop posture in the brief, AFTER the Staff Engineer has reviewed and BEFORE the Staff Engineer applies its findings. Use when (a) the Staff Engineer returned and their recommendation reads as "conservative under AI capacity," (b) High-effort architectural reviews where doctrine requires the backstop pass, or (c) the Staff Engineer explicitly named the Director of Engineering in their findings.

An EM who responds to "get a the Director of Engineering review" with "doctrine says the Director of Engineering is a backstop, dispatching the Staff Engineer first" is misreading the doctrine. Standalone is a first-class dispatch — proceed.

## Backstop Reconciliation Protocol

When the Director of Engineering returns findings in **backstop mode** after a primary review (the Staff Engineer or domain reviewer):

- **BACKSTOP_AGREES:** The primary reviewer applies its findings unchanged. The Director of Engineering's agreement is noted but requires no action.
- **BACKSTOP_CHALLENGES:** The coordinator resolves the specific tension before the primary reviewer applies its findings. Options: accept the challenge (use the Director of Engineering's suggested approach), reject the challenge (proceed with primary reviewer's recommendation), or escalate to PM if the decision has product implications. The primary reviewer applies a single resolved work order, not two conflicting ones.
- **BACKSTOP_OVERRIDES:** Coordinator surfaces both perspectives to PM and blocks until resolved. Overrides are rare — "ship heading for iceberg" territory.

The primary reviewer must never apply findings where it and the Director of Engineering disagree without the coordinator having resolved the disagreement first.

When the Director of Engineering returns findings in **standalone mode**, the verdict shape is the standard reviewer enum (`APPROVED | APPROVED_WITH_NOTES | REQUIRES_CHANGES | REJECTED`) and the reviewer applies findings normally — no special reconciliation protocol applies.

## Post-Review Synthesis (when 2+ reviewers ran)

When an artifact has been through 2 or more reviewers, the coordinator produces a brief synthesis before proceeding:

1. **Read all review outputs** — the domain reviewer's findings, the Staff Engineer's findings, and the backstop's challenges
2. **Identify cross-cutting patterns** — findings that multiple reviewers flagged independently (reinforcing signal), or areas where reviewers disagree (requires judgment)
3. **Flag coverage gaps** — use each reviewer's coverage declaration to identify areas NO reviewer examined
4. **Produce a synthesis note** (3-5 bullets):
   - Reinforcing findings (2+ reviewers agree)
   - Conflicting assessments (reviewers disagree — flag for PM)
   - Uncovered areas (gaps in all coverage declarations)
   - Net assessment: does this artifact need another pass, or is it cleared?

This synthesis is lightweight — not a full re-review. The coordinator (Opus) performs it directly; no additional agent dispatch. The value is in cross-referencing, not re-examination.

**Skip when:** Only one reviewer ran, or the review was a quick spot-check at Low effort.

## EM Override Guidance

The routing table provides defaults. The EM should override when:

- They have context about the change that signal-matching can't capture
- Multiple domains are touched and one is clearly dominant
- The change is part of a larger reviewed plan (post-execution review can be lighter)
- The reviewer has already seen this code recently (diminishing returns)

## Staff-Session Roster

Doctrine-side roster data for `/staff-session` (Agent Teams collaborative planning/review).
Read fresh, server-side, by `coordinator_core.staff_session_assemble.resolve_roster()` on every
`staff-session-assemble` call — this is the single home for this data; `skills/staff-session/
SKILL.md` carries no roster tables of its own. Format is parser-load-bearing: each section is an
exact H3 heading immediately followed by a 2-column pipe table (header row + `|---|---|`
separator + data rows) — do not rename a heading or reflow a table without checking
`coordinator_core/staff_session_assemble/__init__.py`'s `_HEADING_*` constants and
`_parse_section`/`_split_pair_cell` first.

<!-- Spec backlink: docs/plans/2026-07-24-computed-skills-b5-planning-cluster.md chunk C9/AC17.
Recovered from coordinator/skills/staff-session/SKILL.md (commit c3803435 deleted them,
F1 reconciliation, PM 2026-07-24) — verbatim data, relocated home. -->

### Domain Signal -> Default Pair

| Domain Signal | Default Pair |
|---|---|
| Architecture / infrastructure | `the Staff Engineer` + `vp-product` |
| Game dev / Unreal (incl. `project_type: unreal-engine`) | `sid` + `the Staff Engineer` |
| Frontend / UI | `the Front-End Reviewer` + `the UX Reviewer` |
| Data science / ML | `the Data Science Reviewer` + `the Staff Engineer` |
| Cross-cutting / unclear | `the Staff Engineer` + `vp-product` |

Every slug in this table must resolve from the coordinator base roster alone. `sid` comes from
the `game-dev` plugin, so it appears only on the row whose domain is that plugin's — a repo
without game-dev installed never reaches it. `the Director of Engineering` can never appear here at all: the Director of Engineering is the
staff-session synthesizer, and `resolve_roster` fails loud on a `the Director of Engineering` debater slug.

### Persona Slug -> Agent File

| Slug | Agent File |
|---|---|
| `the Staff Engineer` | `coordinator/agents/staff-eng.md` |
| `sid` | `game-dev/agents/staff-game-dev.md` |
| `the UX Reviewer` | `coordinator/agents/staff-ux.md` |
| `the Front-End Reviewer` | `coordinator/agents/senior-front-end.md` |
| `the Data Science Reviewer` | `coordinator/agents/staff-data-sci.md` |
| `vp-product` | `coordinator/agents/vp-product.md` |
| `apm` | `coordinator/agents/apm.md` |

### Persona Slug -> subagent_type

| Slug | subagent_type |
|---|---|
| `the Staff Engineer` | `coordinator:staff-eng` |
| `sid` | `game-dev:staff-game-dev` |
| `the UX Reviewer` | `coordinator:staff-ux` |
| `the Front-End Reviewer` | `coordinator:senior-front-end` |
| `the Data Science Reviewer` | `coordinator:staff-data-sci` |
| `vp-product` | `coordinator:vp-product` |
| `apm` | `coordinator:apm` |

This is judgment, not rules. The routing table is a starting point.
