---
title: Plan Coverage Check — pickup-cross-repo-memo-fork
created: 2026-05-30
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md`
**Verdict:** COMPLETE
**Oracle items:** 4 (source: `## Problem` section, four numbered sub-problems)
**Slate items:** 6 (C1–C6)
**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 1 (precision note — within tolerance)

---

### Missed audit items (no slate entry, no architectural OOS)

None.

---

### Ambiguous audit items (signal-partial — informational only)

None.

---

### Weak OOS / hedges (appetite-based deferrals)

None identified.

The only conditional language in the plan body is in the `## Doubt-check (B.0)` section: "If the reviewer rules against a new field, Chunks C2/C3/C4 (CLI flag, schema, surfacing-priority) collapse." This section is framing about reviewer scope boundaries — Stage 1 FALSE-POSITIVE applies (alternative-framing context, not body-prose scope-cut). No hedge finding emitted.

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

#### SD-1 — `_compose_frontmatter` does not yet have a `kind` parameter (pre-implementation state — within tolerance)

**Plan citation (C2):**
> `_compose_frontmatter`: emit `kind: <value>` when provided (quoted via `_yaml_quote` for consistency, though enum values are slug-safe).

**Plan citation (§ Pinned interface / kind lockstep set, item 1):**
> CLI writer — `cross-repo-memo` `_compose_frontmatter` (emits `kind:` when `--kind` given)

**Disk state:** `bin/cross-repo-memo` at line 461 defines `_compose_frontmatter` with signature:
```python
def _compose_frontmatter(
    *,
    title: str,
    to: str,
    topic: str,
    body: str,
    self_receipt: bool = False,
    decision: str | None = None,
    supersedes: str | None = None,
    summary: str | None = None,
) -> str:
```
No `kind` parameter is present. The emitted frontmatter block (lines 514–529) does not include a `kind:` line.

**Assessment:** This is the expected pre-implementation state. The plan correctly describes `kind` as a new addition (C2 adds it). This is NOT a plan-vs-disk contradiction; the plan is specifying work to be done. Classified as a precision note for the reviewer rather than a blocking drift finding. The plan's description of what `_compose_frontmatter` "does" is prospective (describing post-implementation behavior), which is correct plan-writing practice.

**Action:** No amendment needed. Reviewer should note this is the expected substrate state for a pre-execution plan.

---

### Oracle-vs-Slate cross-reference (Lens 1)

**Sub-problem 1: No memo ingest procedure**

Oracle text: "/pickup needs a form-classification fork (handoff / spinoff / memo) with read-before-reasoning as the first act of the memo branch."

Slate match: **C1** — "New Step 1.5 (Classify the artifact) before the existing handoff flow: read the artifact first (read-before-reasoning, stated explicitly as the anti-confabulation gate), then classify by path + frontmatter shape." Shared noun phrases: `form-classification fork`, `read-before-reasoning`, memo branch. Signal (c) confirmed. Classification: **MATCHED**.

Disk verification: `skills/pickup/SKILL.md` confirmed on disk. Current file is 100% handoff-shaped (Steps 1–6 operate on `state/handoffs/` only, mutate `status: active → consumed`, no memo awareness). The plan's characterization of the current state is accurate.

---

**Sub-problem 2: Memos don't self-declare their shape**

Oracle text: "A new sender-declared `kind:` frontmatter field (proposed enum `ask | consult | fyi`) lets the pickup fork branch deterministically."

Slate matches:
- **C2** — "`--kind {ask,consult,fyi}` argparse arg" + `_compose_frontmatter` emits `kind:` when provided.
- **C3** — "`cross-repo-memo.yaml` `optional:` block: add `kind` as `{type: enum, values: [ask, consult, fyi]}`" + `schema.js` memo cross-field rules: validate `kind` ∈ enum when present.

Shared identifier: `` `kind` ``, enum values `ask | consult | fyi`. Signal (b) confirmed across both chunks. Classification: **MATCHED**.

Disk verification: `schemas/cross-repo-memo.yaml` has `optional:` block (lines 47–74) — confirmed. `kind` is genuinely absent from the schema — confirmed new addition. `status` and `decision` enums are present in the schema as described. `bin/lib/schema.js` cross-repo-memo rules start at line 649; `decision` enum validation shape is at lines 674–689 — within ±50 of cited "lines ~663–700." The plan's mirror-this-shape description is accurate.

---

**Sub-problem 3: A memo-ask is a peer hypothesis, not a command**

Oracle text: "the receiving EM adjudicates and owns the disposition for this repo's customers/consumers — weighs it, may action it, may decline with a logged rationale, may propose."

Slate matches:
- **C1** — Memo branch step 3: "adjudicate-and-own per the autonomy stance (cite `cross-repo-communication.md` § 'Memo-lifecycle adjudication is EM work'): weigh against this repo's customers/consumers; then either action (→ `decision: accepted`), decline (→ `decision: declined` + rationale), or — only on a genuine product/tradeoff/architectural fork — surface to PM."
- **C5** — "New § 'Picking up a memo — the adjudicate-and-own gate': a short section that points to the existing § 'Memo-lifecycle adjudication is EM work'... State the calibrated stance (action tradeoff-free / decline-with-rationale / surface only genuine forks) and the 'ask = peer hypothesis, not command' framing."

Shared noun phrase: `adjudicate-and-own`, `peer hypothesis`. Signal (c) confirmed. Classification: **MATCHED**.

---

**Sub-problem 4: Receipt-as-state, not ack-memos**

Oracle text: "The receiver marks the memo `open → actioned` in place (with `decision:` + note), or it ages out to `cross-repo/archive/`. The sender just looks at the receiver's inbox/archive... No two-sided protocol, no ack-memo sent back."

Slate matches:
- **C1** — "Receipt-as-state: the flip + commit IS the receipt; sender reads it on the same machine. No return-memo (negative-spec, cite the ack-of-ack rule)."
- **C4** — "One change covers both `/session-start` and `/workday-start` (shared helper). State this in the chunk so neither surface is missed." — Surfacing drives the open→actioned lifecycle visibility.

Shared phrase: `open → actioned`, `No return-memo` / `no ack-memo`. Signal (c) confirmed. Classification: **MATCHED**.

Disk verification of the "shared helper" claim: Both `skills/session-start/SKILL.md` (line 239) and `commands/workday-start.md` (line 210) invoke `workday-start-cross-repo-memo-surface.sh` verbatim — the same binary. The plan's claim that "one change covers both" is factually accurate on disk.

---

### Substrate verification summary (Lens 3)

| Citation | Disk state | Finding |
| --- | --- | --- |
| `bin/cross-repo-memo` `_compose_frontmatter` exists | EXISTS at line 461 | `kind` parameter absent — pre-implementation state (SD-1, within tolerance) |
| `schemas/cross-repo-memo.yaml` has `optional:` block | CONFIRMED lines 47–74 | `kind` genuinely absent — correct pre-implementation state |
| `schemas/cross-repo-memo.yaml` `status` enum | CONFIRMED line 39 | values: [open, actioned, reviewed, action_taken, closed, superseded] |
| `schemas/cross-repo-memo.yaml` `decision` enum | CONFIRMED line 65 | values: [accepted, declined, partial, superseded] |
| `bin/lib/schema.js` cross-repo-memo rules ~663–700 | CONFIRMED lines 649–730 | `decision`/`status: action_taken` validation shape present; no `kind` validator yet — pre-implementation |
| `bin/workday-start-cross-repo-memo-surface.sh` filters `status: open` | CONFIRMED line 115: `if status != "open": sys.exit(0)` | `kind` not yet parsed — pre-implementation |
| `skills/pickup/SKILL.md` handoff-shaped, no memo awareness | CONFIRMED | Steps 1–6 operate on `state/handoffs/`, mutate `status: active → consumed` / `deployment_state` only |
| Both `/session-start` and `/workday-start` use same helper | CONFIRMED | `session-start/SKILL.md:239` and `commands/workday-start.md:210` both invoke `workday-start-cross-repo-memo-surface.sh` |

---

### Verdict logic

- Zero MISSED oracle items (all four sub-problems have signal-confirmed slate entries).
- Zero AMBIGUOUS items.
- Zero weak-OOS / appetite-based deferrals.
- Zero hedge tokens firing on body prose.
- One substrate precision note (SD-1) — within ±50-line tolerance; pre-implementation state is the correct substrate state for an unexecuted plan. Does not gate INCOMPLETE.

**Verdict: COMPLETE.**

Plan is clear for named-reviewer dispatch.

---

**Cost estimate:** ~3,800 tokens (4 oracle items × 6 substrate verifications × targeted reads)
