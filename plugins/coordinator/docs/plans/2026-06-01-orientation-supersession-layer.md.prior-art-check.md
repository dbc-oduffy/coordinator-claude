---
title: Prior-Art Check — 2026-06-01-orientation-supersession-layer
created: 2026-06-01
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: docs/plans/2026-06-01-orientation-supersession-layer.md
---

## Prior-Art Verification

**Plan:** docs/plans/2026-06-01-orientation-supersession-layer.md
**Verdict:** WARN
**Claims checked:** 17
**Conflicts:** 1 | **Compatible-but-relevant:** 6 | **Silent:** 10
**Corpora consulted:** project-wikis (97 files indexed) | global-wikis (same corpus — active project IS the coordinator meta-repo) | lessons.md (not present at checked path) | improvement-queue (~/.claude/tasks/coordinator-improvement-queue.md, 72 entries scanned)

---

### Conflicts (plan contradicts prior art)

- **Claim #5 — supersedes: vocabulary reuse:** The plan asserts it is reusing the existing `supersedes:` / `superseded_by:` pointer vocabulary that is already "schema-aware" across the system (memo schema, handoff status enum, `cross-repo-communication.md` re-issue pattern).
  - **Plan asserts:** "Reuse the existing `supersedes:` / `superseded_by:` pointer vocabulary. It already exists and is schema-aware: the memo schema enforces `status: superseded ⇒ superseded_by:` required (`bin/lib/schema.js:708`), the handoff `status:` enum carries `superseded` (coordinator CLAUDE.md § Handoff Lineage), and `cross-repo-communication.md` already uses `supersedes: <old-path>` for memo re-issue."
  - **Prior art (`docs/wiki/cross-repo-communication.md`, line 302):** "Pre-2026-05-22 memos are grandfathered. Step 1.45 skips memos with `created: < 2026-05-22` by design. If a pre-cutoff memo has unfinished business, re-issue via `cross-repo-memo` with `supersedes: <old-path>`."
  - **Prior art (`bin/lib/schema.js:708–718`):** "// status: superseded requires superseded_by. { check: (fm) => { if (fm.status !== 'superseded') return null; if (!fm.superseded_by || String(fm.superseded_by).trim() === '') { return { field: 'superseded_by', error: 'required when status=superseded', hint: 'Set superseded_by to the path of the memo that supersedes this one (inverse of supersedes:).' }; } return null;"
  - **Why this is a conflict:** The existing schema-enforced `supersedes:` usage lives in the **cross-repo-memo schema** (for memo re-issue), and the `superseded_by:` cross-field rule is wired to the **memo** schema's `status: superseded` coupling — NOT to the **handoff/baton** schema. The plan's C3 default proposes adding a cross-field rule for `supersedes:` on **handoff** (baton) frontmatter, but calls this "reusing existing vocabulary." What is being reused is the **field name**, not an already-established schema-aware cross-field rule on handoffs. The plan's own text then correctly notes the memo rule "does NOT transfer verbatim" — which contradicts the framing of claim #5 as pure reuse. The divergence: the vocabulary is reused; the schema-awareness claim is overstated for the handoff domain specifically.
  - **Candidate directions for EM:**
    - `update-plan` — tighten the framing in § Design direction item 1: the field name is reused; the schema-aware cross-field rule is NEW for handoffs (not transferred from memos). The C3 "does NOT transfer verbatim" qualification already says this; just remove the overstatement in item 1.
    - `both` — clarify item 1 in the plan AND add a note to `cross-repo-communication.md` that distinguishes the memo-schema `supersedes:` usage from the forthcoming baton-schema `supersedes:` usage, to prevent future readers from conflating the two.
  - **Lean:** The plan's C3 section already resolves this correctly; the conflict is a framing gap in § Design direction item 1. `update-plan` is the likely direction — a one-line qualification in item 1 closes it.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #2 — addon-seeded baton carries `supersedes:`:** An addon-seeded `kind: spinoff` baton may carry `supersedes: <orientation-id>`.
  - **Plan covers:** The `supersedes:` field value is described as "an orientation identifier (an opaque id the superseded repo publishes, e.g. `project-rag-orientation`), not a file path."
  - **Prior art (`docs/wiki/spinoff-handoffs.md` § Frontmatter schema):** "```yaml\nkind: spinoff\nstatus: active\npredecessor: none           # always — spinoffs have no continuity ancestor\nauthoring_session: <one-line description>   # replaces predecessor link as audit trail back to origin\nworkstream: <slug>          # required, so /pickup can group them\n```\n`predecessor: none` is load-bearing."
  - **Subtype:** `cite`
  - **Suggested action:** C4 (spinoff-handoffs.md note) is already planned. However, the plan should explicitly confirm that the new `supersedes:` field in the spinoff frontmatter schema does not conflict with the existing required fields above — all required fields remain; `supersedes:` is additive optional. A note in C4 that `supersedes:` does not alter `predecessor: none` or `authoring_session:` requirements would close this alignment gap.

- **Claim #3 — no new `kind`:** Orientation rides existing `kind: spinoff`; no new `kind: orientation` is introduced.
  - **Plan covers:** Explicitly stated in § Design direction item 2.
  - **Prior art (`docs/wiki/agent-install-contract.md` § Install-spinoff layer):** "There is **no new folder and no new convention**: a downstream repo's whole obligation is 'drop a `kind: spinoff` baton (carrying `install_chain_order:`) into `~/.claude/tasks/handoffs/`.' The `install_chain_order:` tag is what distinguishes an install leg from the coordinator onboarding handoff in the same folder."
  - **Prior art (`docs/wiki/agent-install-contract.md`, Install-spinoff layer):** "> Do **not** invent a `tasks/spinoffs/` (or `tasks/install-chain/`) directory: no coordinator machinery scans it, so a baton dropped there is invisible to `/pickup`, `query-records`, and `/workday-start`. The standard `tasks/handoffs/` folder is the only surface all three already read."
  - **Subtype:** `cite`
  - **Suggested action:** The plan already aligns; cite these passages in C1 to show the no-new-kind choice is consistent with the no-new-folder / no-new-convention ethos already enshrined in the layer this plan extends.

- **Claim #6 — CONDITIONAL+LIVE vs UNCONDITIONAL+TERMINAL semantic seam:** The new supersession is conditional+live; existing supersession (handoff `status: superseded`) is unconditional+terminal.
  - **Plan covers:** Described in § Design direction item 4 as "the single distinction that prevents a naive copy of the terminal semantics."
  - **Prior art (coordinator CLAUDE.md § Handoff Lineage):** "**Frontmatter `status`: `active | consumed | superseded`** (`shipped` rejected — use `consumed` + `shipped_in:`). [...] `/pickup` flips to `in_flight`, mutates frontmatter in place at `tasks/handoffs/`"
  - **Prior art (`docs/wiki/spinoff-handoffs.md` § Deployment_state lifecycle for spinoffs):** "Column states refer to `deployment_state:` frontmatter, NOT `status:`. The `status:` enum is `active | consumed | superseded` (per coordinator CLAUDE.md § Handoff Lineage); `shipped` is not a valid `status:` value"
  - **Subtype:** `cite`
  - **Suggested action:** The plan correctly avoids stamping `status: superseded` on the superseded orientation baton. C4's spinoff-handoffs.md note should explicitly state that `supersedes:` on a live baton does NOT trigger the `status: superseded` lifecycle transition — it is a separate spine-build-time preference mechanism. This makes the semantic seam greppable from the schema doc.

- **Claim #9 — coordinator agnosticism:** Coordinator hardcodes no orientation, no addon, no order; resolution rule is generic.
  - **Plan covers:** § Design direction item 5: "Coordinator stays agnostic. It hardcodes no orientation, no addon, no order."
  - **Prior art (`docs/wiki/agent-install-contract.md` § Install-spinoff layer — The two roles):** "**Coordinator STITCHES + DRIVES.** Post-reboot, `continue-onboarding-and-installation.md` Step 0 greps `tasks/handoffs/` for `install_chain_order:` legs, writes a lightweight install-chain spine listing every leg found, and drives each to conclusion via `/pickup`. This is the durability a vanilla session lacked — and it is agnostic: it tracks whatever spinoffs are present, asserting no fixed set."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's C3 spine-builder rule should carry an explicit "agnostic" comment (or comment block) in the template matching the language of the existing agnosticism guarantee — so the resolution rule is greppably agnostic, not just incidentally so.

- **Claim #15 — downstream conformance guidance separates what-we-call from what-others-should-do:** The plan's "teach the other side in a wiki" split.
  - **Plan covers:** C2 "Guidance for conforming repos" section explicitly invokes this principle: "Reaffirm the 'teach the other side in a wiki, don't code their ceremony' split."
  - **Prior art (`docs/wiki/cross-repo-communication.md` § When lifting a cross-repo primitive):** "Ship what makes sense for OUR install surface; teach how OTHERS should handle theirs in a wiki — never code both sides from our repo. [...] *Source: 2026-05-28 install-divergence lift; PM crystallized rule when EM was about to wire holodeck's install ceremony from coordinator publish surface.*"
  - **Prior art (`docs/wiki/agent-install-contract.md` § Guidance for conforming repos):** "This is the 'teach the other side in a wiki, don't code their ceremony' half of the contract (per `cross-repo-communication.md` § When lifting a cross-repo primitive)."
  - **Subtype:** `cite`
  - **Suggested action:** Already cited in-plan; no additional action needed beyond the existing cross-references. Informational only.

- **Claim #17 — no ack-of-ack memo after accepted memo:** Plan states "per `cross-repo-communication.md` no ack-of-ack memo is sent."
  - **Plan covers:** § Notes / coordinator-side only: "per `cross-repo-communication.md` no ack-of-ack memo is sent."
  - **Prior art (`docs/wiki/cross-repo-communication.md` § Memo content is hypothesis, item 8):** "A cross-repo reply can be superseded by a sibling memo from the same correspondent — grep the archive before acting on its recommendation. [...] DON'T send when their inbound was a *confirmation* — the receiver-side `status` flip + git history is the audit trail; ack-of-ack is ceremony."
  - **Prior art (`docs/wiki/cross-repo-communication.md` § Don't re-nag the PM):** "Once the receiver path has been handed to the PM at send time, the sender's job is done."
  - **Subtype:** `cite`
  - **Suggested action:** Already correctly applied. Informational only.

---

### Peer prior art

No `peer_repos` supplied in the dispatch brief. Section omitted.

---

### Silent areas (no prior art found)

- Claim #1 — absence of orientation/supersession semantics in the install-spinoff layer: no prior art (expected — this is the gap the plan fills).
- Claim #4 — spine-builder Step 0 resolution rule as the one new surface: no prior art on this specific mechanic.
- Claim #7 — superseded orientation never stamped `status: superseded` to preserve its default-when-absent liveness: no prior art (novel semantic distinction; plan introduces it).
- Claim #8 — `superseded_by:` back-pointer NOT written on the superseded baton: no prior art directly covering this omission-as-design.
- Claim #10 — `supersedes:` value is an opaque orientation id (not a file path): no prior art on this naming convention.
- Claim #11 — `bin/lib/schema.js` validator is permissive (targeted cross-field, not strict-unknown-reject) for handoff schema: covered by reading schema.js directly; no prior art contradicts this — plan's substrate claim is factually verified.
- Claim #12 — proposed light cross-field rule gating `supersedes:` to `kind: spinoff` only (not `spinoff-roadmap`): no prior art; this is a new rule modeled after the existing graph-fields gate.
- Claim #13 — C1+C2 are one executor because of write-overlap on `agent-install-contract.md`: no prior art — this is executor-scoping doctrine applied correctly, no contradiction found.
- Claim #14 — plan extends "no new folder, no new convention" ethos: compatible with and consistent with prior art (Claim #3 compatible-but-relevant entry covers this); no conflict.
- Claim #16 — yielding half (project-rag orientation yielding) is OOS: no prior art specifically addresses this boundary; consistent with "teach the other side in a wiki, don't code their ceremony" doctrine.

---

### Verdict logic

One conflict surfaced (Claim #5). The conflict is a **framing gap** in § Design direction item 1: the plan accurately describes the terminal `supersedes:`/`superseded_by:` schema-aware coupling for the **memo** schema, then calls the new baton-side usage "reuse" of vocabulary that is already "schema-aware" — but the schema-awareness on the handoff domain is NEW (C3 introduces it; the memo-schema rule explicitly does not transfer). The plan's own C3 section already contains the correct qualification ("the memo rule does NOT transfer verbatim"), making this a presentation-layer discrepancy rather than a substantive architectural error.

**WARN** — the conflict is a framing gap in one paragraph, not a load-bearing design divergence. The EM should tighten § Design direction item 1 before Opus reviewer dispatch (or delegate to the review-integrator post-review). No PM-altitude call required.

---

**Cost estimate:** ~8K tokens (17 claims × 5 corpus reads average; 4 wiki files read in full, schema.js targeted grep, improvement-queue scanned)
