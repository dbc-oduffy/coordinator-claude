---
title: Plan Coverage Check — onboarding-install-redesign
created: 2026-05-30
author: plan-coverage-checker
status: implemented
kind: plan-coverage-check
plan: plugins/coordinator/docs/plans/2026-05-30-onboarding-install-redesign.md
---

## Plan Coverage Verification

**Plan:** `plugins/coordinator/docs/plans/2026-05-30-onboarding-install-redesign.md`
**Verdict:** COMPLETE
**Oracle items:** 8 (source: ratified problem-set `docs/problems/2026-05-30-coordinator-onboarding-install-redesign.md`, status: ratified, P1–P8)
**Architectural OOS items verified:** 3 (cherry-pick engine, kernel mini-install, UE/holodeck stack for OSS users)
**Slate items:** 8 chunks (C1–C8) + 10 AC rows (AC1–AC10)
**Missed:** 0 | **Ambiguous:** 0 | **OOS-weak:** 0 | **Hedges:** 0 | **Substrate-drift:** 1

---

### Lens 1 — Coverage (Oracle vs Slate)

#### P1 — Discovery: a cold Claude can't find the agentic install surface

**MATCHED.** Covered by C2 (owns `README.md`, "make the agentic install unmissable") and C1 (opens `agent-install.md` with explicit agentic-install framing). AC1 is the binding gate: "A cold Claude can route from README → `agent-install.md` in one hop (P1)."

#### P2 — Front-door philosophy contradicts the product

**MATCHED.** Covered by C1 (encodes logic tree, kills "express = don't think"), C3 (replaces `--non-interactive`-vs-interactive framing with unified tree), C4 (reconciles EXPRESS/CUSTOM vocabulary to unified tree). AC2 and AC8 are the binding gates.

#### P3 — "Done" is defined as scripts-ran, not partnership-entered

**MATCHED.** Covered by C1 (kills any "run install.sh = done" reading, encodes three-layer bootstrap, frames install as agentic flow with todo/mini-plan). AC2 gate: "no script-gated 'complete' line; partnership framing present." AC4 gate: "three-layer bootstrap encoded."

#### P4 — Restart gate strands the user

**MATCHED.** Covered by C1 (reframes restart as "fresh session + paste `/pickup`" with correct env-var reason, stages the handoff before the gate) and C5 (authors the `continue-onboarding-and-installation.md` handoff with `/pickup`-valid frontmatter). AC4 and AC5 are the binding gates.

#### P5 — Wrong refinement surface pointed at

**MATCHED.** Covered by C1 (embed "edit your `~/.claude`, not this clone" line), C3 (add refinement-target close to Phase 7 next-steps), C6 (add refinement-target framing to project-onboarding next-steps). AC6 is the binding gate: "refinement-target line in all three surfaces."

#### P6 — Ecosystem opacity

**MATCHED.** Covered by C1 (embed three-tier ecosystem map), C3 (make Phase 1.d remedial — offer to install deep-research, explicit status table row, honour OSS editorial principle). AC7 is the binding gate: "tier labels + deep-research status row; Phase 1.d remedial."

#### P7 — Post-install orientation aims at wrong first task

**MATCHED.** Covered by C5 (handoff body: co-write CLAUDE.md / CLAUDE.local.md as first dogfood, partnership-shape offer) and C6 (session-start fresh-install branch for the no-handoff case). AC5 is the binding gate: "continue-onboarding handoff drives co-write-CLAUDE.md first dogfood with partnership-shape offer."

#### P8 — Existing-structure users are unhandled

**MATCHED.** Covered by C7 (new `lib/detect-existing-claude-home.sh`, read-only/idempotent, emits `track=A`/`track=B`), C1 (logic tree calls the helper), C3 (wires detection in setup). AC3 is the binding gate: "Track A/B detection exists, is read-only/idempotent, Track B is minimal-honest with no cherry-pick engine."

---

### Architectural OOS verification (3 items from ratified problem-set)

All three OOS items from the ratified problem-set appear verbatim in the plan's `## Out of scope` section (plan lines 133–137). Each carries an architectural reason, not an appetite hedge:

1. **Cherry-pick/merge engine for Track B** — plan: "We support install-from-zero only." Problem-set: "Comparative extraction is unbounded judgment work we cannot stand behind as a supported path." Architectural reason present (unbounded scope of supported path). OOS-JUSTIFIED.

2. **Carving kernel into standalone pre-restart mini-install** — plan: "Carving the kernel into a standalone pre-restart mini-install (registration needs the restart; kernel is functional post-restart regardless)." Problem-set: "Architecturally unnecessary — registration requires the restart, so the kernel is functional post-restart regardless." Hard architectural reason present (plugin registration is the bottleneck; separable install would duplicate substrate for no capability gain). OOS-JUSTIFIED.

3. **UE/holodeck/game-dev stack / project-rag for generic OSS user** — plan: "Per `CLAUDE.local.md` editorial principle." Problem-set cites the same principle. Hard policy boundary (percolation polarity — holodeck-owned content flows holodeck→holodeck only). OOS-JUSTIFIED.

The plan also notes **auto-percolation is PM-gated** (C8 last bullet: "Surface 'ready to percolate to OSS coordinator-claude' to the PM at done-time"). This does not appear in the ratified problem-set OOS — it is a plan-level PM gate on a procedural action, not a scope item. Verified below under Lens 2.

---

### Missed audit items (no slate entry, no architectural OOS)

None.

---

### Ambiguous audit items

None.

---

### Weak OOS / hedges (appetite-based deferrals)

**Lens 2 hedge scan — auto-percolation PM gate (C8):**

Plan text: *"Percolation is PM-gated — this plan does NOT auto-run `publish.sh`. Surface 'ready to percolate to OSS coordinator-claude' to the PM at done-time."*

Stage 1 check: heading subtree is `### C8 — Dogfood the full flow end-to-end + closeout`. Does not match the FALSE-POSITIVE heading patterns (Considered Alternatives, Risks, etc.). Not in a blockquote.

Stage 2 check: This is NOT a scope-cut on work that should be in the plan. `publish.sh` execution is the outward-distribution step that lives after the work is validated — it is correctly PM-gated per the global CLAUDE.md (§ Plugin Architecture: "Publish/percolate/push-to-publish-repo plugin content… via `bash ~/.claude/setup/publish.sh`"). The plan correctly identifies it as a gate: the action is named (surface to PM at done-time), it is not silent deferral, and the gate owner is named (PM). This pattern is a **PM-authorization gate on an externally-visible action**, which is architecturally appropriate per First Officer Doctrine ("External-facing actions (pushing, PRs, messages) → PM asks, don't assume"). FALSE-POSITIVE — not a hedge.

No other hedge tokens found in plan body prose.

**Result: 0 hedges.**

---

### Substrate drift (in-repo paths/symbols cited that don't match disk)

#### DRIFT-1 — `.claude-plugin/marketplace.json` does not exist

**Plan citation (line 29):** *"**OSS marketplace tier** (`.claude-plugin/marketplace.json`): coordinator, web-dev, data-science, deep-research, notebooklm."*

**Disk state:** `.claude-plugin/` directory exists at `coordinator/` root and contains exactly one file: `plugin.json`. No `marketplace.json` file is present.

The plan cites `marketplace.json` as a currently existing file describing the OSS marketplace tier composition. The file does not exist on disk. Only `plugin.json` (the plugin descriptor) is present.

**Suggested action:** Amend the plan substrate citation to reflect the actual file (`plugin.json`) and clarify whether `marketplace.json` is a file to be created as part of this work, or whether the marketplace tier list is encoded elsewhere. If `marketplace.json` is a NEW file (analogous to `lib/detect-existing-claude-home.sh` and `templates/handoffs/continue-onboarding-and-installation.md` which the plan explicitly flags as NEW), it should be declared as such. Currently the plan presents it as an existing substrate.

---

#### All other cited paths — CONFIRMED

| Citation | Disk state |
|---|---|
| `commands/setup.md` | Present |
| `commands/bootstrap-repos.md` | Present |
| `skills/project-onboarding/SKILL.md` | Present |
| `skills/session-start/SKILL.md` | Present |
| `skills/pickup/SKILL.md` | Present |
| `dist/publish-repo-docs/agent-install.md` | Present |
| `dist/publish-repo-toplevel/README.md` | Present (lines 23–32 confirmed — README Quick Start matches plan description) |
| `setup.md:42-55` (Agent Teams env var section) | Confirmed — lines 40–55 are the `1b. Agent Teams env var` section |
| `setup.md:76-91` (deep-research check section) | Confirmed — lines 75–91 are the `1d. Deep research plugin` section, observational only (no install offer) |
| `bootstrap-repos.md:48-79` (EXPRESS vs CUSTOM) | Confirmed — EXPRESS/CUSTOM vocabulary present at lines 52–79 |
| `pickup/SKILL.md:69` (accepts arbitrary path) | Confirmed — line 69 is "The PM has pointed you at a specific handoff. Read it immediately and proceed." (arbitrary path via `$ARGUMENTS`) |
| `capture-fan-out-threshold.sh` in `setup.md` | Confirmed — line 328 of setup.md calls it |
| `lib/detect-existing-claude-home.sh` | Declared NEW — correct not to exist yet |
| `templates/handoffs/continue-onboarding-and-installation.md` | Declared NEW — correct not to exist yet. `templates/handoffs/` directory also does not exist; executor must create it. |

**Note on `templates/handoffs/`:** The plan says C5 owns "new `templates/handoffs/continue-onboarding-and-installation.md`" (new file). The parent directory `templates/handoffs/` does not exist on disk — only `templates/` with subdirs `bin`, `machine-local`, `setup`, and two template files. This is consistent with C5 creating a new directory + file. No drift here; surfaced for executor awareness.

---

### Verdict logic

- Zero MISSED oracle items across P1–P8.
- Zero AMBIGUOUS items.
- Zero WEAK-OOS items (auto-percolation PM gate is a legitimate PM-authorization gate, not an appetite hedge).
- Zero HEDGES.
- One SUBSTRATE-DRIFT finding: `.claude-plugin/marketplace.json` cited as existing but absent from disk. Only `plugin.json` exists in that directory.

The single substrate-drift finding is below the BLOCKED-SURFACE-TO-PM threshold (≥3 required). The drift is on a descriptive substrate citation in the `## Substrate` section (not a file that any chunk is tasked to edit), so it does not block execution — it requires a prose correction to the plan's substrate inventory. **Verdict: COMPLETE** (the drift is real and should be folded, but it is not a MISSED problem or a chunk-blocking gap).

**EM action:** Amend plan line 29 to reflect that `.claude-plugin/marketplace.json` does not currently exist — either note it as a NEW file C1 or another chunk will create, or correct the description to reference `plugin.json` (which is the actual file present). If the marketplace tier list is authored elsewhere (e.g., in `plugin.json` or in `agent-install.md`), name that location.

---

**Cost estimate:** ~6K tokens (8 oracle items × targeted substrate verifications across 10 cited paths/symbols)
