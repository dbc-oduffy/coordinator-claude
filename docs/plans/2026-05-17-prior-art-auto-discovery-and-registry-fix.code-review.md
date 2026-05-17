---
title: Code Review — Prior-Art Auto-Discovery + Registry Fix (Implementation Fidelity)
created: 2026-05-17
reviewer: Sonnet (session-end code review, fresh session)
scope: implementation-fidelity defects only (design choices already triple-reviewed at plan stage)
plan: docs/plans/2026-05-17-prior-art-auto-discovery-and-registry-fix.md
verdict: APPROVE-WITH-REVISIONS
---

## Summary

The executor faithfully implemented Stage 1 (registry data + doctrine wiki), Stage 1.6 (script retirement), Stage 2 (agent prompt rewrite), and Stage 3 (CLAUDE.md + Phase 14) against the plan. Cross-artifact self-consistency between the registry data, doctrine wiki, and agent prompt is high — closed-enum extensions, schema field renames, two-channel discovery semantics, augment-default override, and bidirectional graph walk all converge. Two implementation-fidelity defects surfaced — both stem from the executor-flagged Stage 2 judgment call on "sidecar phrasing for unregistered project." One is a P1 (contradicts an explicit integration-pass directive from plan S2.B); the other is a P2 (plan AC2/S1.B(1) specifies an edge that is missing from the registry data, though bidirectional walk masks the symptom). Triad oracle (AC7) still passes because of the bidirectional walk in Step 4. No P0 defects.

## Findings

### P1-1 — Agent emits a separate `Auto-discovered peers: ...` header line, which the plan's A1 integration explicitly forbade

**File:** `plugins/coordinator/agents/prior-art-checker.md` (commit 53cc9d7), Step 1 and Step 2 of Bootstrap Phase 0.

**What the agent does:**
- Step 1 (registry-unreadable): "Note in the sidecar: `Auto-discovered peers: 0 — registry unreadable`."
- Step 2 (project-not-registered): "Note in sidecar header: `Auto-discovered peers: 0 — project not registered`."

**What the plan specified (S2.B(1), integration note A1):**
> Do **not** add a separate "Auto-discovered peers: N (edges: X, tags: Y)" summary line — that duplicates information already carried by the extended `Corpora consulted:` line and will produce an inconsistent sidecar format. The existing `Corpora consulted:` header is the single location for peer discovery information.

The executor's judgment call (flagged in commit message under "sidecar phrasing for unregistered project") introduced exactly the separate summary line the plan's review-integrator A1 directive forbade. The unregistered-project and registry-unreadable cases should fold their note into the `Corpora consulted:` line — for example, by omitting the `peer-wikis:` segment entirely (the existing template's `omit entire peer-wikis segment if no peers` clause already handles this) and adding the explanatory note to a DEGRADED rationale field or to the `Corpora consulted:` line itself (e.g., `peer-wikis: none — project not registered`).

**Severity:** P1. The plan's A1 directive was explicit and load-bearing (single-location-for-peer-info invariant); the executor noted the judgment call but resolved against the spec.

**Fix:** Remove the two `Auto-discovered peers: 0 — ...` notes from Step 1 and Step 2. Replace with inline annotation on `Corpora consulted:` (e.g., `peer-wikis: none — registry unreadable` / `peer-wikis: none — project not registered`). The DEGRADED clause text in the verdict block already carries the diagnostic reason; the header line should not duplicate it.

**Disposition:** applied

---

### P2-1 — Registry missing direct `ancestor` edge from `claude-unreal-holodeck` (AC2 partial-miss; bidirectional walk masks symptom)

**File:** `~/.claude/tasks/repo-registry.md` (commit 9cd29dd3), `claude-unreal-holodeck` entry, lines 99–103.

**What the registry declares (outgoing edges from holodeck):**
- `consumes-from: project-rag`
- `depends-on: coordinator-claude`

**What plan S1.B(1) specified:**
> `relationships`: edges to `project-rag` (consumes-from — engine corpus served back) and `project-rag-ue-addon` (ancestor — carved out 2026-05-13). Per CLAUDE.md ground truth quote available.

The direct outgoing edge to `project-rag-ue-addon` is missing. Bidirectional graph walk in agent Step 4 ("Also walk reverse edges: scan all other active entries for edges whose `target` is the active project's shortname") papers over this — `project-rag-ue-addon` declares `ancestor: claude-unreal-holodeck`, so the reverse walk surfaces it from holodeck's perspective. AC7 oracle (triad cross-check) therefore still passes.

**However**, there is also a semantic question in the plan body itself: an `ancestor` edge declared on holodeck pointing at project-rag-ue-addon would mean "holodeck's ancestor is the addon" per the wiki's directional definition (`Directional (A's ancestor is B; A is the descendant)`). That is reversed — the addon was carved FROM holodeck, so the addon is the descendant. The registry correctly does NOT declare such a (wrong-direction) edge from holodeck. The plan body's S1.B(1) instruction was loose; the executor reasonably interpreted ground truth from the directional semantic rather than the plan body's literal instruction. Net: the registry is semantically correct, the plan body is internally inconsistent, and AC7 still passes via bidirectional walk.

**Severity:** P2. No behavioral defect (oracle 3 passes). Documentation drift between plan body and registry; worth noting so a future reader doesn't "fix" the registry by adding a wrong-direction edge.

**Fix:** No registry change needed — registry is semantically correct. Add a one-line annotation to the plan body S1.B(1) or to the registry comment noting "holodeck has no outgoing ancestor edge; ancestor edges declare the descendant pointing at the ancestor, and the bidirectional graph walk surfaces holodeck as a peer when dispatching from either descendant." Or simply leave as-is since AC7 passes and the wiki documents the directional rule clearly.

**Disposition:** applied

---

### P2-2 — Doctrine wiki schema field documentation in registry data file is duplicated and slightly inconsistent

**File:** `~/.claude/tasks/repo-registry.md`, lines 21–22 vs `x:/coordinator-claude/docs/wiki/repo-registry.md` schema table.

Both files document the `working_wiki` / `publish_wiki` field meanings. The registry data file's "Schema" section (lines 14–24) reproduces the field semantics inline, which is fine for orientation but creates a minor SSOT question — the wiki is the canonical schema doctrine per `Schema and conventions: docs/wiki/repo-registry.md` (line 3). The inline schema in the data file should ideally be a brief pointer ("schema authoritative at `docs/wiki/repo-registry.md`") rather than a re-statement, OR the wiki should be the only place the schema lives. As-shipped, both descriptions match, so this is not a defect — but it's a future-drift risk if one is edited without the other.

**Severity:** Nitpick. Not a defect today; flagged only because the two documents are within the same plan's deliverable and the SSOT principle is what this plan elevates.

**Fix:** Optional. Leave as-is or trim the data-file schema section to a pointer in a follow-up.

**Disposition:** applied

---

### Nitpick — `corpus_source: working_wiki for all` inline consolidation hint is an executor invention

**File:** `plugins/coordinator/agents/prior-art-checker.md`, sidecar template line 168 (post-diff).

The agent's sidecar template adds:
> `[omit entire peer-wikis segment if no peers; if all peers from same source, consolidate: 'corpus_source: working_wiki for all']`

The plan only specified: "Annotate the sidecar with `corpus_source: publish_wiki_fallback` for any peer served from fallback." The "consolidate when all peers from same source" hint is an executor-added affordance, not specified. Harmless — it reduces sidecar noise when no fallback occurred — but worth noting as a small drift from spec.

**Severity:** Nitpick. Accept or trim per EM preference.

**Disposition:** applied

---

## What was implemented correctly (sampling)

- **Bidirectional graph walk** (agent Step 4) is correctly specified — "Also walk reverse edges: scan all other active entries for edges whose `target` is the active project's shortname." This is what makes AC7 oracle pass despite the registry's directional `ancestor` declarations.
- **OS-aware path normalization** (agent Step 2) — five-step normalization (~/expansion, symlink resolve, separator convert, drive-letter lowercase, trailing-slash strip) with UNC/WSL fail-loud-DEGRADED clause (h). Faithful to plan + Zolí F3.
- **Stage-gate precondition check** (agent Step 3) — hardcoded interwoven-set fail-loud check faithful to Zolí F2 Option A.
- **Augment-default override semantic** (agent Step 7) — peer_repos: augments by default, peer_repos_mode: replace overrides. Discovery reason `override` / `override:replace`. Faithful to PM F4 ruling.
- **DEGRADED clause extensions** — (f) registry-unreadable, (g) ceiling-exceeded, (h) unsupported-path-shape — extended at existing list position (line 213), not parallel structure. Faithful to A3.
- **Anti-pattern reframe in wiki** — "Bypassing the tag-cap" replaces "Bypassing the cap"; existing bullet edited rather than parallel addition. Faithful to A4.
- **CLAUDE.md tripwire entry** (Stage 3) — contact-points enumerated: agent prompt, doctrine wiki, registry data file. Faithful to A5.
- **Three-oracle smoke test referenced** in agent prompt (lines 261–267) — Oracle 1 (registry schema check), Oracle 2 (single-edge from coordinator-claude), Oracle 3 (triad cross-check). Faithful to Zolí F6 and plan Test Surface.
- **Stage 1.6 script retirement** — `bin/sync-plugin-wiki.sh`, `block-dev-side-mirror-wiki.sh`, hook registration, CLAUDE.md tripwire entry, update-docs.md Phase 11g all removed in a single commit. Rationale documented in commit message. Clean reversal point.
- **Closed-enum extensions** — `schema-lockstep`, `ancestor`, `depends-on`, `mcp-plugin` added to both wiki and data file with worked examples. `peer` narrowed to residual kind in both. Faithful to A2 and Zolí F9.

## Verdict

**APPROVE-WITH-REVISIONS** — the implementation is largely faithful; one P1 defect (sidecar separate-summary-line violates A1) and one P2 (registry/plan-body semantic question on holodeck ancestor edge, no behavioral defect) warrant pre-merge fixes. The P1 is a tradeoff-free correctness fix (revert to A1's spec). The P2 is a documentation choice — annotate or leave.

## Coverage
- **Reviewed:** implementation fidelity of all 4 in-scope commits (53cc9d7 agent prompt, 4fcb76c doctrine wiki, 9cd29dd3 registry data, 087c70a script retirement, bf9ce0c CLAUDE.md + Phase 14); cross-artifact consistency between agent prompt, registry data, doctrine wiki; AC1–AC9 spec-vs-shipped check; the two executor-flagged judgment calls
- **Not reviewed:** design choices (out of scope per dispatch — Zolí covered); the 75-file wiki layout move (mechanical); 2-line CLAUDE.md strips in 3 sister repos (mechanical); plan body itself; the doc-link-checker sidecar
- **Confidence:** HIGH on P1-1 (verbatim contradiction with A1 directive); MEDIUM-HIGH on P2-1 (semantic, bidirectional walk masks symptom); LOW on nitpicks
- **Gaps:** Did not exercise the three-oracle smoke test; the empirical-validation gap called out in the plan's status note remains (first real dispatch from a triad member will be the first end-to-end test). Not in scope to run.
