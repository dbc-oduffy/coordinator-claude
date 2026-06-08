---
title: Prior-Art Check — pickup-cross-repo-memo-fork
created: 2026-05-30
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-pickup-cross-repo-memo-fork.md`
**Verdict:** COMPATIBLE
**Claims checked:** 18
**Conflicts:** 0 | **Compatible-but-relevant:** 8 | **Silent:** 10
**Corpora consulted:** project-wikis (103+ files indexed) | global-wikis (same corpus — this IS the coordinator meta-repo) | lessons.md | improvement-queue

---

### Conflicts (plan contradicts prior art)

No conflicts found.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #2 — `/session-start` memo surfacing:** Plan states memos are "surfaced at `/session-start` § Outstanding cross-repo memos AND `/workday-start` Step 1.45, both via `workday-start-cross-repo-memo-surface.sh`."
  - **Plan covers:** This is stated as existing fact supporting the problem framing.
  - **Prior art (`skills/session-start/SKILL.md` lines 237–241):** "Run `bash ~/.claude/plugins/coordinator/bin/workday-start-cross-repo-memo-surface.sh`. Non-empty output → surface verbatim under heading `#### Outstanding cross-repo memos (DoE attention):`. Empty → skip silently. Same surface, same semantics, same helper as `/workday-start` Step 1.45"
  - **Subtype:** `cite`
  - **Suggested action:** The plan's Problem section correctly states this. No action needed — informational confirmation that the claim is accurate.

- **Claim #3 — Memo lifecycle `open → actioned`, `decision:` enum:** Plan asserts the single-surface lifecycle and `decision:` field with values `accepted | declined | partial | superseded`.
  - **Plan covers:** Used as the existing foundation for the memo-branch receipt-as-state behavior.
  - **Prior art (`schemas/cross-repo-memo.yaml` lines 62–65):** `decision:` is `optional` with `values: [accepted, declined, partial, superseded]`. The plan's C1 memo-branch encodes `decision: accepted` and `decision: declined` which are both valid enum members. `decision: partial` and `decision: superseded` are NOT used in the plan's memo branch — that is fine (they are valid values the plan doesn't invoke).
  - **Subtype:** `cite`
  - **Suggested action:** The plan's pickup-branch encoding aligns correctly with the existing schema. No action needed — informational confirmation. C3 (schema chunk) should not collide with `decision:` which is already in the schema.

- **Claim #4 — "Don't send an ack-of-ack" rule:** Plan's `ack`-is-not-a-kind negative-spec directly invokes the existing wiki rule.
  - **Plan covers:** "consistent with the existing wiki rule 'don't send an ack-of-ack when the inbound was a confirmation.'"
  - **Prior art (`docs/wiki/cross-repo-communication.md` § "Memo content is hypothesis" rule 6 and rule 8):** "But don't send an ack-of-ack when the inbound was a confirmation, not a request." and "SEND outbound when you've *unblocked* a peer (their inbound was a request gated on you). DON'T send when their inbound was a *confirmation* — the receiver-side `status` flip + git history is the audit trail; ack-of-ack is ceremony."
  - **Subtype:** `cite`
  - **Suggested action:** C5 (doctrine chunk) should cite these verbatim passages when documenting the `ack`-is-receipt-state negative-spec. Plan already points to them — the executor should be directed to cite by-section-heading not just by assertion.

- **Claim #5 — Autonomy stance doctrine already exists:** Plan states "the supporting doctrine *already exists* in `cross-repo-communication.md` (§ 'Memo-lifecycle adjudication is EM work', § 'Memo content is hypothesis — verify before acting')" and that C1/C5 should cite rather than re-author.
  - **Plan covers:** Described as the load-bearing reason the fork exists; plan claims it only wires existing doctrine.
  - **Prior art (`docs/wiki/cross-repo-communication.md` § "Memo-lifecycle adjudication is EM work"):** "When an inbound memo describes a situation, proposes an action, or asks a question — read the memo body and judge the right response yourself. Do not surface the memo contents to the PM as 'what should I do?' The PM's job is product authority; memo adjudication (what the memo says, what the right EM response is, whether the action is already done, whether the memo is superseded) is EM work. Escalate to PM only if the memo implicates a product decision — not for 'I have a memo, what do I do?'"
  - **Prior art (`docs/wiki/cross-repo-communication.md` § "Memo content is hypothesis — verify before acting"):** Verified to exist — four-clause on-receipt discipline plus on-disposition and on-sending rules.
  - **Subtype:** `cite`
  - **Suggested action:** The plan's claim is accurate. Both sections confirmed present at the locations cited. C1 and C5 executors should cite by section name (as the plan prescribes) — no duplication.

- **Claim #7 — `kind` lockstep set mirrors "four coupled path declarations" pattern:** Plan creates a new four-site lockstep for `kind` analogous to the existing four-site lockstep for inbox path.
  - **Plan covers:** "analogous to the four-coupled-path-declarations rule" — introduces a fifth pattern site on the `kind` dimension.
  - **Prior art (`docs/wiki/cross-repo-communication.md` § "Four coupled path declarations — keep in lockstep"):** "The active-memo path appears in exactly **four enforced code sites** that must stay in lockstep whenever the inbox path changes: (1) CLI write target — `cross-repo-memo:635` (`cross-repo/inbox/`), (2) Schema `applies_to` — `schemas/cross-repo-memo.yaml:2`, (3) Own-inbox guard regex — `validate-frontmatter-schema.js:385`, (4) Surface glob — `workday-start-cross-repo-memo-surface.sh:34`"
  - **Subtype:** `cite`
  - **Suggested action:** The plan's "kind lockstep set" in C5 should explicitly call out that it is a PARALLEL pattern to the existing four-path lockstep, using the same lockstep-set subsection format. The executor for C5 should cross-reference § "Four coupled path declarations" in the wiki addition. The existing four-site path-lockstep is NOT one of the sites in the plan's kind-lockstep — the plan adds 4 new sites (CLI `--kind` arg, schema `kind:` field, `schema.js` enum validator, surface-parser `kind` read). The two lockstep sets are orthogonal and both must be documented.

- **Claim #8 — Surfacing helper shared by `/session-start` and `/workday-start`:** Plan states "One change covers **both** `/session-start` and `/workday-start` (shared helper)."
  - **Plan covers:** Claimed as a feature (one fix touches both surfaces automatically).
  - **Prior art (disk verification):** Confirmed. `bin/workday-start-cross-repo-memo-surface.sh` is the shared helper. `skills/session-start/SKILL.md:239` runs it directly. `commands/workday-start.md` references it via Step 1.45. The claim is accurate — changing the helper changes both surfaces.
  - **Subtype:** `cite`
  - **Suggested action:** C4 executor description says "State this in the chunk so neither surface is missed" — this is already correct. Informational confirmation that the architecture is as the plan claims.

- **Claim #12 — Adjudicate-and-own: action/decline/surface-genuine-forks calibration:** Plan encodes "Tradeoff-free ask the EM endorses → action it; genuine product/tradeoff/architectural fork → surface to PM; disagree / wrong for this repo's consumers → `decision: declined`."
  - **Plan covers:** Described as "EM application of existing doctrine, consistent with both the PM's intent and the wiki — not a new PM decision."
  - **Prior art (`docs/wiki/cross-repo-communication.md` § "Memo-lifecycle adjudication is EM work"):** "Escalate to PM only if the memo implicates a product decision — not for 'I have a memo, what do I do?'" This matches the plan's "surface to PM only on genuine product/tradeoff/architectural fork" — the plan is applying the wiki's rule with the same calibration. The plan's three-branch encoding (action / decline / surface) is the correct concrete expansion of the wiki's abstract rule.
  - **Subtype:** `cite`
  - **Suggested action:** C5 doctrine addition "Picking up a memo — the adjudicate-and-own gate" section should use the verbatim framing from "Memo-lifecycle adjudication is EM work" as its anchor, then add the three-branch operational expansion — exactly as the plan specifies. No new stance is being invented; the exposition is correct.

- **Claim #18 — "Partial-ack memo unblocks the sender" wiki rule:** This prior-art entry is adjacent to the memo-pickup domain and slightly relevant to the plan's scope.
  - **Plan covers:** Plan explicitly excludes ack-memos from the `kind` enum (negative-spec). This wiki rule governs a different shape — sending a partial-ack as a standalone memo before work is complete.
  - **Prior art (`docs/wiki/cross-repo-communication.md` § "Partial-ack memo unblocks the sender"):** "A cross-repo memo's acknowledgement function is independent of the main deliverable's completion. When you have confirmed that you understand and accept an inbound request — even if implementation is still running — send a partial-ack memo immediately."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's ack-is-receipt-state negative-spec governs the `kind` enum (no `ack` kind). This wiki rule governs *when to send a memo* (separately). The two are compatible — the pickup-branch receipt flip is for closing an actioned memo; sending a partial-ack as a new memo (its own `ask` or `fyi` kind) for in-progress work is a distinct act. No conflict; executor for C5 may want to note the distinction in the negative-spec section to avoid a reader confusing "ack is not a kind" with "never send acknowledgement memos." Informational only.

---

### Silent areas (no prior art found)

- Claim #1 — `/pickup` 100% handoff-shaped today (zero memo awareness): no prior art documenting this gap. The plan's Problem description is the first record of this misclassification failure mode.
- Claim #6 — `kind` enum field on memo schema: confirmed ABSENT from `schemas/cross-repo-memo.yaml` (no `kind:` key in either `required:` or `optional:` blocks). Confirmed `schema.js` uses `kind` only in the context of handoff/spinoff (`spinoff-roadmap`) — no memo cross-field rules reference `kind`. Plan's claim is accurate: no prior memo-`kind` art exists.
- Claim #9 — `decision:` enum existing values `accepted | declined | partial | superseded`: confirmed in schema but no prior art *about* the decision enum shape that conflicts with plan usage. Silent as a separate claim.
- Claim #10 — CLI currently has no `--kind` flag: confirmed. Grepped `bin/cross-repo-memo` for `kind` — zero matches. The CLI has no `kind`-related code. Plan's claim is accurate.
- Claim #11 — schema.js `kind` usage confined to spinoff/handoff shapes: confirmed. All `kind` references in `schema.js` are in the spinoff/roadmap validator block (`kind: spinoff-roadmap` checks at lines ~517–557). No memo schema rules reference `kind`. Plan's claim is accurate.
- Claim #13 — Receipt-as-state (flip + commit IS the receipt; no return-memo): this is the existing wiki lifecycle (`open → actioned` in-place), but the plan's application of it to the pickup-branch is new procedure. No prior art documents pickup-as-lifecycle-driver specifically.
- Claim #14 — `ack` is NOT a `kind` (receipt state, not sender-declared kind): the ack-of-ack wiki rule establishes the anti-pattern of ack-memos, but the explicit framing of `ack` as "receipt-state, never a sender-declared kind" is plan-new vocabulary (the wiki names the behavior but not this particular encoding).
- Claim #15 — `/pickup` Step 2 globs `state/handoffs/`; Step 5 mutates `status: active → consumed`: confirmed from reading `skills/pickup/SKILL.md`. No prior art about the misapplication risk — the plan is identifying a gap, not contradicting existing doctrine.
- Claim #16 — New Step 1.5 classification fork (path + frontmatter shape): this is a new addition; no prior art for it.
- Claim #17 — Parallel fan-out C1–C5 disjoint-write architecture with C6 as merge-gate round-trip verifier: standard coordinator fan-out pattern, but no prior art specific to this feature's decomposition.

---

### Verdict logic

Zero conflicts found. All Compatible-but-relevant findings are informational confirmations or citation-alignment notes. The plan accurately cites the existing wiki sections it depends on, the `kind` field is confirmed new (no prior memo-`kind` art exists in schema.yaml, schema.js, or the wiki), and the `decision:` enum values the plan uses (`accepted`, `declined`) are confirmed valid existing members.

The plan's central claim — that it wires existing doctrine (not new stance) into the pickup procedure — is **verified accurate** against the cross-repo-communication.md corpus. Both cited sections ("Memo-lifecycle adjudication is EM work" and "Memo content is hypothesis") confirmed present and substantially match the plan's described content.

One nuance for the Opus reviewer's attention (Compatible-but-relevant #7): the plan introduces a four-site `kind` lockstep alongside the existing four-site path lockstep. The wiki currently documents only the path lockstep. C5 should add the kind-lockstep as a co-equal parallel section (not a replacement or supersession). The plan specifies this correctly; executor briefing should reinforce the co-equal framing.

**Cost estimate:** ~6K tokens (18 claims × 4 corpus reads average)
