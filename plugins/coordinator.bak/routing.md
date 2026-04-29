# Coordinator Routing Table

## Discovery Protocol

<!-- Review: patrik — anchor implementation reference to prevent silent staleness -->
**Implementation:** `/review-dispatch` command. This document describes the algorithm; the command implements it.

At dispatch time, `/review-dispatch` assembles a composite routing table:
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

### Zolí (ambition-advocate)
- **Signals:** N/A — backstop only, never primary
- **Model:** opus
- **Effort:** Medium
- **Backstop:** None (terminal backstop)
- **Agent file:** `agents/ambition-advocate.md`
- **Invocation rule:** Mandatory at High effort, optional at Medium, skip at Low

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
    project_type:            # list of types — all matching domain agents are active
      - unreal               # values: unreal | game-docs | web | data-science | meta
      - data-science
    active_reviewers:        # optional explicit override
      - patrik
      - sid
    ---

Single values are also accepted for backwards compatibility:

    ---
    project_type: web
    ---

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

## Backstop Reconciliation Protocol

When the backstop (Zolí) returns findings after a primary review (Patrik or domain reviewer):

- **BACKSTOP_AGREES:** Pass primary reviewer's findings to review-integrator unchanged. Zolí's agreement is noted but requires no action.
- **BACKSTOP_CHALLENGES:** The coordinator resolves the specific tension before dispatching review-integrator. Options: accept the challenge (use Zolí's suggested approach), reject the challenge (proceed with primary reviewer's recommendation), or escalate to PM if the decision has product implications. The review-integrator receives a single resolved work order, not two conflicting ones.
- **BACKSTOP_OVERRIDES:** Coordinator surfaces both perspectives to PM and blocks until resolved. Overrides are rare — "ship heading for iceberg" territory.

The review-integrator should never receive findings where Patrik and Zolí disagree without the coordinator having resolved the disagreement first.

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
