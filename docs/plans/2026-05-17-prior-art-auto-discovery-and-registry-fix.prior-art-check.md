---
title: Prior-Art Check — prior-art-auto-discovery-and-registry-fix
created: 2026-05-17
author: prior-art-checker
status: shipped
kind: prior-art-check
plan: docs/plans/2026-05-17-prior-art-auto-discovery-and-registry-fix.md
---

## Prior-Art Verification

**Plan:** `x:/coordinator-claude/docs/plans/2026-05-17-prior-art-auto-discovery-and-registry-fix.md`
**Verdict:** WARN
**Claims checked:** 23
**Conflicts:** 2 | **Compatible-but-relevant:** 6 | **Silent:** 15
**Corpora consulted:** project-wikis (8 files — x:/coordinator-claude/docs/wiki/) | global-wikis (47 files indexed via DIRECTORY_GUIDE.md — ~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/) | peer-wikis: coordinator-claude (x:/coordinator-claude/docs/wiki/, 8 files) | lessons.md (searched) | improvement-queue (searched)

Note: active project is claude-central (~/.claude). The bundled plugin wikis at `~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/` ARE the global-wiki corpus for this install. The peer corpus at `x:/coordinator-claude/docs/wiki/` was also consulted per the dispatch brief; it is the dev-side sibling. The bundled and peer copies of `prior-art-checker.md` and `repo-registry.md` were both read; minor prose divergences noted below but no substantive contradictions between them.

---

### Conflicts (plan contradicts prior art)

- **Claim #7 — `peer_repos:` override replaces auto-discovery:** The plan asserts that when a dispatch brief includes `peer_repos: [...]`, that list **replaces** auto-discovery (not augments).
  - **Plan asserts:** "if dispatch brief includes `peer_repos: [...]`, that list **replaces** auto-discovery (not augments). EM keeps control when they need it."
  - **Prior art (`~/.claude/tasks/coordinator-improvement-queue.md`, line ~359):** `"2026-05-16 | project-rag-ue-addon | tasks/lessons.md:113 | Prior-art-checker peer_repos block should scan docs/plans/ not just docs/wiki/ | proposed target: coordinator:prior-art-checker (extend peer_repos: corpus to include peer docs/plans/ for status:active plans) [recurring: 1]"`
  - **Why this is a conflict:** The improvement queue has a queued (recurring) item proposing that `peer_repos:` consult peer `docs/plans/` in addition to `docs/wiki/`, implying augmentation of the corpus. The plan's override-replaces-all model would satisfy one part of this queue item but the replacement semantics explicitly preclude auto-discovered peers — if the EM passes `peer_repos:` to override a *different* peer than what auto-discovery would find, auto-discovered peers are silently dropped. The queue item's intent (more coverage, not less) conflicts with the replacement-semantics choice.
  - **Suggested action for EM:** Evaluate whether "replaces" vs. "augments + overrides" is the right semantic. The queue item (`recurring: 1`) suggests the coverage-expansion direction is desired. If "replaces" is the intentional call, document it in the plan's Open Questions or Considered Alternatives, and either close or re-target the queue entry. This is a WARN, not BLOCKED — it is an architectural direction choice, not a contradiction of load-bearing doctrine.
  - **Disposition:** applied

- **Claim #14 — Sidecar `peer-wikis:` header format:** The plan adds a "Auto-discovered peers: N (edges: X, tags: Y) | Manual override: Z" discovery summary line to the sidecar header.
  - **Plan asserts:** "Discovery summary line in the header: `Auto-discovered peers: N (edges: X, tags: Y) | Manual override: Z`."
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/agents/prior-art-checker.md`, lines 128–130):** The current sidecar template specifies: `**Corpora consulted:** project-wikis (N files indexed) | global-wikis (N files indexed) | peer-wikis: <shortname1>, <shortname2> (only if peer_repos supplied; omit line otherwise) | lessons.md | improvement-queue`
  - **Why this is a conflict:** The existing `Corpora consulted:` header line already carries peer-wiki information. Adding a separate "Auto-discovered peers:" summary line duplicates the peer-wiki information at two positions in the sidecar header. The plan must decide: extend the existing `Corpora consulted:` line (e.g., tag each shortname with `(edge)` or `(tag)`), or add the new line and deprecate the peer-wiki portion of `Corpora consulted:`. Shipping both without reconciliation will make the sidecar format inconsistent.
  - **Suggested action for EM:** Fold prior art into plan — either extend `Corpora consulted:` to carry the discovery-reason annotation inline (e.g., `peer-wikis: project-rag (edge:schema-lockstep), claude-unreal-holodeck (tag:rag)`), or define the new summary line as a replacement for the current peer portion of `Corpora consulted:`. Clarify in the agent prompt edit which supersedes which. WARN severity — not load-bearing doctrine, but will produce malformed sidecars if left ambiguous.
  - **Disposition:** applied

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1/#2 — New `relationship.kind` enum values + enum extension procedure:**
  - **Plan covers:** Adding `schema-lockstep`, `ancestor`, `depends-on` as new closed-enum `relationship.kind` values; "PM judgment call — Open Question O-1."
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/repo-registry.md`, lines 74–81):** "Both `stack_tags` and `relationships.kind` are closed. Extending requires: 1. Add the new tag/kind to this wiki's table with a one-line meaning. 2. Add a worked example. 3. Update existing registry entries that should carry the new tag (or leave for next PM review pass). 4. Commit the wiki + registry changes together. **Silent additions in `tasks/repo-registry.md` without a wiki update are doctrine drift — the wiki is the contract.**"
  - **Subtype:** `cite`
  - **Suggested action:** Plan already covers S1.C wiki update (step 1), but the "worked example" requirement (step 2) is not explicitly called out. Confirm the wiki update in S1.C names at least one worked example per new kind, consistent with the extension procedure. The plan references the procedure implicitly; an explicit citation or checklist alignment would tighten the stub.
  - **Disposition:** applied

- **Claim #3 — Stage-gate sequencing:**
  - **Plan covers:** "Stage 2 does not start until Stage 1 ships — running auto-discovery against a registry that's missing edges produces silently incomplete results, which is worse than today's manual-pick."
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md`, § Plan-First Workflow):** "**Stage gates are real** — do not start Stage 2 before Stage 1 lands and the triad is in `active` block." (This is from the plan's own Hard Constraints section, echoing coordinator doctrine on stage gates.) The coordinator doctrine supporting this is: "Survey plan-substrate state before dispatching on a not-just-authored plan."
  - **Subtype:** `cite`
  - **Suggested action:** No action needed — plan already enforces the gate explicitly in the Hard Constraints section. Informational alignment only.
  - **Disposition:** applied

- **Claim #10/#23 — DEGRADED on registry-unreadable, not silent fallback:**
  - **Plan covers:** "No fallback escape hatches — if registry can't be read, sidecar must surface DEGRADED, never silently fall back to 4-corpus and pretend everything's fine."
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/agents/prior-art-checker.md`, lines 170–173):** "**DEGRADED** — the agent ran but with materially incomplete coverage. Emitted when any of the following occurred: (a)... (b)... (c) a corpus was unreadable (permission error, missing directory, truncated file), (d)... (e) `peer_repos` count exceeded the cap of 2 — peer corpora not consulted."
  - **Subtype:** `cite`
  - **Suggested action:** The plan adds "registry unreadable" as a new DEGRADED trigger, which is consistent with the existing pattern. The executor editing the agent prompt should add this alongside the existing DEGRADED clause (c) — "corpus was unreadable" — for consistency. The plan's new combined-ceiling DEGRADED trigger ("ceiling exceeded") is additive and aligns with existing clause (e). Both additions should align with the existing enum shape.
  - **Disposition:** applied

- **Claim #15 — Anti-patterns reframe ("Bypassing the cap" → tag-cap only):**
  - **Plan covers:** "Current 'Bypassing the cap' rule needs nuance... Reframe as: 'Bypassing the **tag-cap** by hand-listing more than 2 tag-only peers in `peer_repos:` overrides the cost ceiling — surface to PM.'"
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/repo-registry.md`, lines 138–141):** "**Bypassing the cap.** N=2 is a cost ceiling. If a plan genuinely needs 3+ peers, that's a signal it's too broad — surface to PM, don't extend the cap silently."
  - **Subtype:** `cite`
  - **Suggested action:** The plan directly evolves this anti-pattern entry. The reframe is compatible with the spirit of the existing rule (cost ceiling exists) but changes the scope (tag-only peers, not all peers). The executor should ensure the existing anti-pattern bullet is edited, not left alongside the new reframe as a duplicate. Flag for attention in the S1.C stub.
  - **Disposition:** applied

- **Claim #16 — CLAUDE.md tripwires list update:**
  - **Plan covers:** "Add 'Registry-self-read in prior-art-checker bootstrap' as a tripwire. Greppable contact-points: `agents/prior-art-checker.md`, `docs/wiki/repo-registry.md`."
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md`, § Adding a Convention):** "**Snippet-sync.** Edit `snippets/<name>.md` (single source), run `bin/verify-<name>-sync.sh --fix`, commit all touched files together. Never edit consumer sentinel blocks. Snippets: `project-rag-preamble`, `reviewer-calibration`, `docs-checker-consumption`, `prior-art-check-consumption`, `text-only-recovery-preamble`, `default-routing`."
  - **Subtype:** `cite`
  - **Suggested action:** The plan adds a new tripwire to CLAUDE.md's Tripwires list. Per the "Adding a Convention" doctrine, contact-points must be enumerated: `/project-onboarding`, `/session-start`, `/session-end`, relevant hook, and ≥1 canonical artifact. The plan names `agents/prior-art-checker.md` and `docs/wiki/repo-registry.md` but does not enumerate the full contact-point set required by the convention-addition procedure. The executor for S3.A should check whether `/session-start`, `/session-end`, or `/project-onboarding` need a hint about the registry-bootstrap behavior, per the convention-addition checklist.
  - **Disposition:** applied

- **Claim #20 — `project-rag-ue-addon` tagged with `mcp-server`:**
  - **Plan covers:** "`stack_tags`: `[rag, unreal-engine, python, mcp-server]` (the MCP-server tag because the addon registers tools via pluggy into project-rag's MCP)."
  - **Prior art (`~/.claude/plugins/coordinator-claude/coordinator/docs/wiki/repo-registry.md`, § `stack_tags`):** "`mcp-server` | Implements an MCP server" — the definition implies the repo hosts the server runtime, not that it registers tools into another repo's server.
  - **Subtype:** `cite`
  - **Suggested action:** The plan's rationale for the `mcp-server` tag is sound but the tag definition is "Implements an MCP server" — the addon doesn't implement the server, it contributes plugins to one. PM should confirm this is an intended extension of the tag's meaning (a docs/wiki/repo-registry.md note would help), or whether a different tag is more accurate (e.g., `rag` + `unreal-engine` + `python` may be sufficient). This is a vocabulary-alignment item, not a blocker — flag in S1.A review context.
  - **Disposition:** applied

---

### Peer prior art (coordinator-claude)

The peer corpus at `x:/coordinator-claude/docs/wiki/` is the dev-side sibling of the bundled corpus. The two copies were compared and only prose-level divergences were found (bundled copies are newer and have additional content). No findings unique to the peer corpus that aren't already covered above.

- **Claim #1 — Enum extension procedure (peer):**
  - **Peer (`coordinator-claude`):** `x:/coordinator-claude/docs/wiki/repo-registry.md` carries the same "Extending the enums" section verbatim. Confirmed: the dev-side copy is in sync with the bundled copy on this rule.
  - **Relevance:** Cross-confirms the extension procedure is current in the dev-side wiki that Stage 1 will actually edit.
  - **Suggested action:** Informational only — procedure is the same in both copies.

---

### Silent areas (no prior art found)

- Claim #4 — Two-channel discovery architecture (edges no-cap + tags-capped): no prior art in any corpus. This is net-new design.
- Claim #5 — Combined ceiling of 5 (increase from implicit 2): no prior art — the N=2 cap was per-channel, not a combined ceiling. New concept.
- Claim #6 — `pwd`-to-registry path matching as bootstrap: no prior art in any corpus.
- Claim #8 — Edges-always-consulted, no cap: no prior art. The existing doctrine is "N=2 hard cap" without channel distinction — this is an explicit evolution.
- Claim #9 — Registry no-match → manual-only mode noted in sidecar: no prior art. Current behavior is simply "4-corpus default" with no sidecar note for unregistered projects.
- Claim #11 — S1.C-pre: removing `peer_repos:` dispatch hints from repo CLAUDE.md files, atomic with registry commit: no prior art on this specific cleanup pattern.
- Claim #12 — Sidecar discovery summary line: no prior art beyond the existing `Corpora consulted:` header (see Conflict #2 above).
- Claim #13 — Per-peer `discovered_via:` annotation: no prior art in any corpus.
- Claim #17 — Phase 14 sibling-mention hint via path/shortname scanning (not `peer_repos:` CLAUDE.md field): no prior art — the plan explicitly notes this is a weaker signal because S1.C-pre removes the `peer_repos:` lines that the original design would have matched.
- Claim #18 — Atomic commit for S1.B + S1.C-pre: no prior art specific to multi-repo atomic commit requirements for this kind of registry+CLAUDE.md change.
- Claim #19 — CLAUDE.md § Pre-Review Mechanical Verification update: no prior art beyond the current wording (which is what's being changed).
- Claim #21 — `claude-unreal-holodeck` promoted from candidates to active: no prior art — this is data maintenance.
- Claim #22 — No commits inside subagent execution: prior art confirmed (Hard Constraints section matches doctrine in CLAUDE.md § Executor Dispatch); already encoded in plan; no gap.

---

### Verdict logic

**WARN.** Two conflicts surfaced:

1. **Claim #7 (override replaces vs. augments):** Conflicts with a queued improvement item (`recurring: 1`) proposing expansion of peer coverage. The plan's "replace" semantic is a defensible call — EM override mode should be precise — but it runs counter to the direction implied by the queued item. EM should disposition before Patrik dispatch: either close/retarget the queue item with a rationale note, or reconsider whether "augments but adds override priority" is a better semantic. Neither requires PM escalation; it is an EM architecture call.

2. **Claim #14 (sidecar header duplication):** The new "Auto-discovered peers:" summary line duplicates information already in `Corpora consulted:`. This is a format inconsistency that will produce ambiguous sidecars. EM should decide the reconciliation before the agent-prompt executor runs, and ensure the sidecar format section in the agent prompt is edited coherently (not having both the old peer-wiki format and the new discovery-summary format in parallel).

Neither conflict contradicts load-bearing doctrine (scoped-safety-commits, daily-branch-discipline, sequential-review HARD RULE, round-trip-contract-tests). WARN — EM disposition required before Opus reviewer dispatch.

---

**Cost estimate:** ~9,800 tokens (estimated from 23 claims × 8 targeted corpus reads: agent prompt × 1, repo-registry wiki × 2 copies, prior-art-checker wiki × 2 copies, scoped-safety-commits wiki × 1, DIRECTORY_GUIDE × 1, improvement-queue targeted grep × 1, lessons.md targeted grep × 1)
