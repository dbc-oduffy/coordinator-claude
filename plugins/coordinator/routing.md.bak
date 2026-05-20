# Coordinator Routing Table

## Discovery Protocol

<!-- Review: patrik — anchor implementation reference to prevent silent staleness -->
**Implementation:** `/review` (plan artifacts) and `/review-code` (code artifacts). This document describes the algorithm; those skills implement it.

At dispatch time, `/review` or `/review-code` assembles a composite routing table:
1. Read this base routing table (universal reviewers + algorithm)
2. Scan all enabled plugins for root-level `routing.md` files
3. Merge routing fragments into composite table
4. Match signal against composite table
5. Dispatch to matched reviewer

Domain plugins register reviewers by providing a `routing.md` file at the plugin root.

## Universal Reviewers

### Patrik (staff-eng)
- **Signals:** Architectural change, new subsystem, cross-cutting (many files, new pattern), backend, security, other/unmatched
- **Model:** opus
- **Effort:** Medium (escalates to High for architectural changes)
- **Backstop:** Zolí
- **Agent file:** `agents/staff-eng.md`

### Zolí (eng-director)
- **Signals (standalone primary):** Cross-team / cross-repo seams (consumer ↔ producer, plugin ↔ host, app ↔ shared library), generic-substrate / consumer-leak risk on producer-side surfaces, architecturally-ambitious plans where DoE-altitude authority is wanted, any review the PM directs to Zolí solo
- **Signals (backstop):** Chained after Patrik on High-effort reviews to challenge under-ambition or under-authority; this is one of Zolí's roles, not his identity
- **Model:** opus
- **Effort:** Medium (escalates to High when issuing cross-team directives or resolving architectural ambition)
- **Backstop:** None (terminal — Zolí is the DoE)
- **Agent file:** `agents/eng-director.md`
- **Invocation rules:**
  - **Standalone is a first-class dispatch.** When the PM says "get a Zolí review," dispatch Zolí solo — do NOT insist on running Patrik first. Zolí is a peer of Patrik in technical rigor, not a Patrik-attached subroutine.
  - **Backstop chain is still the default for High-effort architectural Patrik reviews.** Patrik runs first, integrator applies findings, Zolí runs as backstop on the evolved artifact.
  - **For cross-repo or consumer/producer-substrate reviews, prefer Zolí standalone over Patrik+Zolí.** Patrik's EM-altitude hedging on peer-team appetite is exactly what Zolí's DoE altitude is meant to bypass.

## Fallback Rule

Any signal that does not match a domain plugin's routing fragment routes to **Patrik** at **Medium** effort.

## Sequential Review Protocol

1. Domain specialist reviews first (if signal matches a domain plugin)
2. Coordinator incorporates feedback
3. Generalist (Patrik) catches regressions (if effort >= Medium)
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
    project_type: game-dev   # general | game-dev | web-dev | data-science
    project_subtypes:        # optional free-form tags; used for engine-specific routing
      - unreal
    active_reviewers:        # optional explicit override
      - patrik
      - sid
    ---

`project_type` is a single string. `project_subtypes` is an optional list of free-form tags (e.g. `unreal`, `unity`) that enable engine-specific or stack-specific routing within the declared type. Downstream consumers do best-effort matching; unknown subtypes are silently ignored.

If no `.local.md` exists, default to core-only (Patrik + Zolí).

## Effort Calibration

The EM selects effort level based on change scope. These are defaults — the EM should override when they have context that signal-matching can't capture.

| Change Scope | Effort | Reviewers |
|-------------|--------|-----------|
| Hotfix / single-file / obvious fix | Low | 1 reviewer, domain match |
| Feature addition (2-5 files) | Medium | Domain + generalist |
| Architectural / new subsystem / cross-cutting | High | Domain + generalist + mandatory backstop |
| Maintenance/audit findings (already structured) | Medium | Domain reviewer only |
| Test-only changes | Low | 1 reviewer |
| Doc-only changes | Low | Patrik only |

## Skip Conditions

Not every change needs the full review pipeline:

- **Purely mechanical changes** (rename, format, move): `coordinator:validate` is sufficient, skip review
- **CI/CD config only**: EM self-review, no dispatch needed

## Zolí Standalone vs. Backstop — Dispatch Selection

When the PM or EM wants a Zolí review, decide which mode applies:

- **Standalone (default when in doubt):** Dispatch Zolí solo via `Agent(subagent_type=coordinator:eng-director, ...)` with `mode: "standalone"` in the prompt. Use when (a) the artifact spans repos or touches a consumer/producer seam, (b) the PM said "get a Zolí review" without naming Patrik, (c) the architectural ambition itself is what's being evaluated, or (d) Patrik would hedge on cross-team scope that Zolí has authority to set.
- **Backstop (after Patrik):** Dispatch Zolí with `mode: "backstop"` AFTER Patrik has reviewed and the integrator has applied Patrik's findings. Use when (a) Patrik returned and his recommendation reads as "conservative under AI capacity," (b) High-effort architectural reviews where doctrine requires the backstop pass, or (c) Patrik explicitly named Zolí in his findings.

An EM who responds to "get a Zolí review" with "doctrine says Zolí is a backstop, dispatching Patrik first" is misreading the doctrine. Standalone is a first-class dispatch — proceed.

## Backstop Reconciliation Protocol

When Zolí returns findings in **backstop mode** after a primary review (Patrik or domain reviewer):

- **BACKSTOP_AGREES:** Pass primary reviewer's findings to review-integrator unchanged. Zolí's agreement is noted but requires no action.
- **BACKSTOP_CHALLENGES:** The coordinator resolves the specific tension before dispatching review-integrator. Options: accept the challenge (use Zolí's suggested approach), reject the challenge (proceed with primary reviewer's recommendation), or escalate to PM if the decision has product implications. The review-integrator receives a single resolved work order, not two conflicting ones.
- **BACKSTOP_OVERRIDES:** Coordinator surfaces both perspectives to PM and blocks until resolved. Overrides are rare — "ship heading for iceberg" territory.

The review-integrator should never receive findings where the primary reviewer and Zolí disagree without the coordinator having resolved the disagreement first.

When Zolí returns findings in **standalone mode**, the verdict shape is the standard reviewer enum (`APPROVED | APPROVED_WITH_NOTES | REQUIRES_CHANGES | REJECTED`) and findings flow through the normal integrator path — no special reconciliation protocol applies.

## Post-Review Synthesis (when 2+ reviewers ran)

When an artifact has been through 2 or more reviewers, the coordinator produces a brief synthesis before proceeding:

1. **Read all review outputs** — the domain reviewer's findings, Patrik's findings, and the backstop's challenges
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

This is judgment, not rules. The routing table is a starting point.
