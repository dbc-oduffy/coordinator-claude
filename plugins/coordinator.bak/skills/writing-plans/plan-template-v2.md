---
confidence: low|medium|high
status: draft|ready|executing|done
---

# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use /execute-plan to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Status:** [prose description — mirrors frontmatter status for human readability]
**Confidence:** [Low / Medium / High] — [one-line rationale, e.g., "minimal project context" or "all key files read"]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---

## Assumptions

*(v1: list everything unverified; v2: move verified items to Verified Facts)*

- [ ] [Assumption 1]
- [ ] [Assumption 2]

## Verified Facts

*(v2 only — populated after enrichment; leave empty or omit in v1)*

- [x] [Confirmed fact with evidence — e.g., "FooClass::Bar exists at Source/Foo.h:42"]
- [~~x~~] [Gap found — e.g., "No existing SetupWidget() — must be created"]

## Open Questions (Blocking)

*(Must be resolved before execution begins. Dispatch enricher or Coordinator.)*

- [ ] [Question that blocks Phase 1]

## Open Questions (Non-blocking)

*(Can proceed to execution; resolve opportunistically)*

- [ ] [Question that informs but doesn't gate implementation]

## Risks

*(Format: [UE-specific or domain-specific context] → [what breaks] → [how to catch early])*

- **Risk — IAbilitySystemInterface include path:** [Context: path differs between UE 5.6 and 5.7] → [Failure: compile error on plugin load] → [Detection: verify include resolves in DroneSim build before merge]
- [Risk 2]: [Context] → [failure mode] → [detection method]

## Non-Goals

*(Optional. Scope exclusions — what this plan explicitly does NOT do. Distinct from Assumptions, which are beliefs-that-may-be-wrong.)*

- [Not doing X — and why that boundary exists]

## Execution Phases

### Phase 1 — [Name]

**Files:**
- Create: `exact/path/to/file.ts`
- Modify: `exact/path/to/existing.cpp:123-145`

**Steps:**

- [ ] [Step 1]
- [ ] [Step 2]
- [ ] Commit

**Gate: PM/EM approval before Phase 2.**

### Phase 2 — [Name]

...
