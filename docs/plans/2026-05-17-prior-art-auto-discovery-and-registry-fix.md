---
title: Prior-Art Auto-Discovery + Registry Fix for Interwoven Triad
created: 2026-05-17
author: EM
status: shipped
kind: plan
scope_mode: feature
shipped_in: a1d38e1,f7d46fa,4fcb76c,087c70a,53cc9d7,bf9ce0c (coordinator-claude work/striker/2026-05-07); 9cd29dd3 (claude-central work/striker/2026-05-07to15); 94b25c00 (project-rag); 7507f2a3d (project-rag-ue-addon); 6e486bdb (claude-unreal-holodeck)
---

> **Status: ALL STAGES SHIPPED 2026-05-17** — 10 commits across 5 repos. See `shipped_in:` frontmatter for the commit ledger. Stage 1.B (registry data), 1.C (doctrine wiki), 1.C-pre (3 sister-repo CLAUDE.md strips), 1.5 (wiki layout move), 1.6 (wiki-mirror scripts retired), 2 (agent prompt rewrite), 3 (CLAUDE.md tripwires + Phase 14 hint) all in. Outstanding empirical question per the Director of Engineering F6/F8: the augment-default override semantic and three-oracle smoke test haven't been exercised yet — first real-world prior-art-checker dispatch from the triad will be the first end-to-end validation.

# Prior-Art Auto-Discovery + Registry Fix

## Motivation

`prior-art-checker` consults four corpora by default: project wikis, global (`~/.claude`) wikis, project lessons, central improvement queue. A fifth — peer-repo wikis — exists but requires the EM to manually pass `peer_repos: [shortname, ...]` in the dispatch brief. Three problems:

1. **EM cognitive load.** Every dispatch, the EM has to remember which peers exist and which `stack_tags` overlap with the plan's topic. PM has already authored ground truth into each repo's `CLAUDE.md` (every repo declares its peers and the exact `peer_repos:` list for prior-art-checker). The EM shouldn't be the integration point for information the system already has on disk.
2. **Registry is stale relative to ground truth.** Three repos (`project-rag`, `project-rag-ue-addon`, `claude-unreal-holodeck`) form a deeply interwoven triad — they share a schema, were carved from one monorepo, and each `CLAUDE.md` names the other two. The registry has `project-rag` with empty `relationships: []`, `claude-unreal-holodeck` stuck in `needs-pm-review` candidates, and `project-rag-ue-addon` missing entirely.
3. **Cap shape wrong for interwoven cases.** Current doctrine caps peer consultation at N=2 → DEGRADED at >2. A 3-repo triad of deeply-coupled siblings can't be checked together. The cap should govern *weak* signals (stack_tags-only matches) not *explicit* signals (declared `relationships` edges).

PM intent (this session): belt-and-suspenders — keep both discovery channels (relationship edges AND stack_tags overlap). Edges are the strong signal; tags catch "two unrelated video-game repos that share patterns" even when no edge exists.

## Sequencing

Strict two-stage. Stage 1 fixes the data + schema (registry + wiki doctrine). Stage 2 changes agent behavior. **Stage 2 does not start until Stage 1 ships** — running auto-discovery against a registry that's missing edges produces silently incomplete results, which is worse than today's manual-pick (the EM at least knows when they're picking).

## Stage 1 — Registry + Schema Fix

### S1.A — Decide enum extensions

Current `relationships.kind` enum is `{peer, dev-publish, consumes-from}`. The triad has three relationship flavors the existing enum doesn't fully capture:

- **Schema lockstep** — `project-rag` ↔ `project-rag-ue-addon` share `structural_schema.py` constants under parity tests. Strongest possible consult signal: a change to one repo's schema necessarily affects the other.
- **Ancestor / carved-out** — `claude-unreal-holodeck` is the historical monorepo that birthed both siblings. Still load-bearing for prior-art (lessons learned during the carve-out live in holodeck's wiki).
- **Read-path / write-path pair** — `project-rag-ue-addon` produces corpus releases; `project-rag` consumes them. Cleanly `consumes-from` (existing kind).
- **General dependency** — repo A requires repo B to function (SDK, library, upstream tool, structural dependency) without strictly being a data-flow consumer. The current enum has no clean home for this — `consumes-from` is data-flow specific.

**Confirmed decisions (PM approved 2026-05-17):**
- Add `schema-lockstep` as a new `relationship.kind`. Strongest signal — always consulted under auto-discovery, never DEGRADED-trimmed.
- Add `ancestor` as a new `relationship.kind`. Strong but historical — always consulted.
- Add `depends-on` as a new `relationship.kind` for general dependency edges that aren't data-flow. Always consulted under auto-discovery. (PM noted CLAUDE.md needs to express dependencies, not just peer-shape relationships.)
- `peer` and `consumes-from` retain current meaning. `consumes-from` is narrowed by the new `depends-on` to specifically mean "data-flow consumer."
- `dev-publish` (claude-central ↔ coordinator-claude) is structural mirror — also always consulted under auto-discovery.
- Add `mcp-plugin` as a new `stack_tags` enum value. Meaning: "Registers tools into another repo's MCP server via plugin mechanism (e.g. pluggy hookimpl)." Worked example: `project-rag-ue-addon` → registers tools into `project-rag`'s MCP server.

- Rename `docs_wiki:` field to `working_wiki:` (canonical source location, where humans/agents edit). Add optional `publish_wiki:` field for repos that have a separate published mirror (e.g., claude-central's bundled location). Both fields are paths; prior-art-checker reads `working_wiki:` by default, falls back to `publish_wiki:` only if `working_wiki:` is unreachable.

The alternative (collapse into `peer` + free-text `note:`) was considered and rejected — closed-enum discipline is load-bearing for auto-discovery channel logic.

### S1.B — Populate the triad

Update `~/.claude/tasks/repo-registry.md`:

1. **Promote `claude-unreal-holodeck`** from candidates → active.
   - `goals`: from CLAUDE.md — UE plugin runtime (`ClaudeUnrealHolodeck`), `holodeck-control` MCP, 3D-gen sidecars, `/holodeck:setup` + `/holodeck:doctor`.
   - `stack_tags`: `[claude-plugin, unreal-engine, mcp-server, game]`.
   - `working_wiki`: `x:/claude-unreal-holodeck/docs/wiki` (verified exists).
   - `relationships`: outgoing edges declared from holodeck: `consumes-from: project-rag` (engine corpus served back), `depends-on: coordinator-claude` (general dependency on coordinator doctrine). Ancestor edges declare the descendant pointing at the ancestor (per wiki directional rule — `A's ancestor is B; A is the descendant`), so `project-rag` and `project-rag-ue-addon` each declare `ancestor: claude-unreal-holodeck` outgoing — holodeck does NOT carry outgoing `ancestor` edges to its descendants. The bidirectional graph walk in agent Step 4 surfaces descendants as peers when dispatching from holodeck via reverse-edge scan.
   <!-- Review: code-review (Sonnet session-end) — P2-1: original text implied holodeck outgoing ancestor→ue-addon edge (wrong direction per wiki); registry is semantically correct; plan body updated to match registry actuals and clarify directional rule -->

2. **Add `project-rag-ue-addon`** as new active entry.
   - `path`: `x:/project-rag-ue-addon` (verified exists).
   - `goals`: from CLAUDE.md — UE corpus producer (scrape → chunk → structural index → GitHub Releases), no MCP runtime.
   - `stack_tags`: `[rag, unreal-engine, python, mcp-plugin]` (the addon registers tools into project-rag's MCP server via pluggy; `mcp-server` would be wrong — the addon doesn't host a server).
   - `working_wiki`: `x:/project-rag-ue-addon/docs/wiki` (verified exists).
   - `relationships`: `schema-lockstep` with `project-rag`; `ancestor` from `claude-unreal-holodeck`; `consumes-from` reverse (i.e. `project-rag` consumes-from this addon's releases).

3. **Update `project-rag` entry** — fill empty `relationships: []` with edges to both siblings. Set `working_wiki: x:/project-rag/docs/wiki/`. No `publish_wiki`.

4. **Update existing active entries for the schema rename:**
   - `coordinator-claude`: `working_wiki: x:/coordinator-claude/docs/wiki/` (post-Stage-1.5 location). No `publish_wiki` — publish target is claude-central, where wikis aren't actively maintained.
   - `claude-central`: `working_wiki: c:/users/oduffy/.claude/docs/wiki/`, `publish_wiki: c:/users/oduffy/.claude/plugins/coordinator/docs/wiki/` (stale bundled copy; prior-art-checker falls back here only if working_wiki unreachable).

5. **Stack_tags audit on existing actives** — `claude-central` and `coordinator-claude` currently have `[claude-plugin, agent-orchestration, doctrine]`. No change needed; the `dev-publish` edge already covers them.

### S1.C-pre — Remove vestigial `peer_repos:` from CLAUDE.md files

<!-- Placed before S1.C wiki update so the doctrine wiki can codify "registry is source of truth" without simultaneously contradicting live CLAUDE.md files. Renumber on review if preferred. -->


Once the registry is authoritative, the three `**Prior-art-checker:** ... peer_repos: [...]` lines in each repo's CLAUDE.md become dead weight — they only existed because the EM was the integration point. The agent walking the registry directly makes them redundant. Remove from:

- `x:/project-rag/CLAUDE.md` — line stating `peer_repos: [claude-unreal-holodeck, project-rag-ue-addon]`
- `x:/project-rag-ue-addon/CLAUDE.md` — line stating `peer_repos: [claude-unreal-holodeck, project-rag]`
- `x:/claude-unreal-holodeck/CLAUDE.md` — line stating `peer_repos: [project-rag, project-rag-ue-addon]`

The peer/sibling **narrative** in each CLAUDE.md stays — that's load-bearing context for human readers and for agents reading CLAUDE.md to understand the repo's place in the constellation. Only the *prior-art-checker dispatch hint* gets stripped. The doctrine becomes: relationships live in the registry, and the registry is the source of truth for prior-art consultation.

<!-- Review: zoli — F1: cross-repo atomicity is not achievable in git; both orderings are safe due to idempotency in both directions -->
S1.B and S1.C-pre may land in either order or as separate commits; neither produces incorrect prior-art output in isolation. Convention: land them in the same `/workday-complete` boundary (same logical session) so the registry-authority transition is observable in one changelog entry. Stage 2 does not start until both have landed.

### S1.C — Doctrine wiki update

Edit `docs/wiki/repo-registry.md` (canonical: `x:/coordinator-claude/docs/wiki/repo-registry.md`):

1. **Add new `relationship.kind` rows** to the table: `schema-lockstep`, `ancestor`, `depends-on`. Each new kind gets a one-line meaning AND a worked example in the wiki table, per the existing "Extending the enums" procedure (step 2 is mandatory — silent additions without worked examples are doctrine drift). Each new kind/tag gets a one-line meaning AND a worked example in the wiki table per the existing "Extending the enums" procedure — do not leave any new kind or tag without a worked example.
   - Also add new `stack_tags` row: `mcp-plugin` — "Registers tools into another repo's MCP server via plugin mechanism (e.g. pluggy hookimpl)." Worked example: `project-rag-ue-addon` contributes tools to `project-rag`'s MCP server.
   - `peer` is the residual kind: use it only when none of `schema-lockstep`, `ancestor`, `depends-on`, `dev-publish`, `consumes-from` apply. The more-specific kind always wins.
   <!-- Review: review-integrator — A2: explicit worked-example requirement per enum-extension procedure step 2 -->
   <!-- Review: zoli — F9: residual-kind note prevents future EMs from defaulting to `peer` out of caution and eroding the new precision -->
2. **Schema table update — rename `docs_wiki` to `working_wiki` and add `publish_wiki`.** Add the following rows to the registry schema table:

   | Field | Required? | Meaning |
   |---|---|---|
   | `working_wiki` | Required | Path to canonical source-of-truth wiki for this repo. What prior-art-checker reads. |
   | `publish_wiki` | Optional | Path to a published mirror, when the repo's wiki has a publish destination distinct from the working location. Read as fallback when `working_wiki` is unreachable. |

   All existing `docs_wiki:` entries in the registry data file must be renamed to `working_wiki:` in the same Stage 1 commit.

3. **New section: Eligibility predicate.** A registry entry is eligible for prior-art consultation when ALL hold:
   - `status: active` (or `dormant` — still eligible, lower priority).
   - `working_wiki` field present and path resolves at last `last_verified`.
   - At least one of: (a) one or more `relationships` edges to the active project, OR (b) ≥1 `stack_tags` overlap with the active project's tags.
4. **New section: Discovery channels and caps.**
   - **Channel 1 (edges, strong signal):** Every entry with a `relationships` edge connecting to the active project is consulted. **No cap.** This is the belt — explicit edges always fire.
   - **Channel 2 (tags, weak signal):** Entries with `stack_tags` overlap (but no edge) are consulted up to `N=2` (confirmed). This is the suspenders — catches "two video-game repos with similar patterns" even when nobody wired an edge.
   - **Combined ceiling:** Total peer corpus reads capped at 5 (confirmed) → DEGRADED if exceeded. Honors the existing cost discipline without strangling triads. When the combined ceiling is hit, the EM's remediation surface is `peer_repos: [...]` with `peer_repos_mode: replace` to consult a deliberately chosen subset. The ceiling itself does not get bumped silently — that's a doctrine change requiring PM authorization.
   <!-- Review: review-integrator — B3: N=2 tag cap and N=5 combined ceiling confirmed by PM 2026-05-17 -->
   <!-- Review: zoli — F5: EM remediation path when ceiling is hit was unstated; peer_repos_mode: replace is the escape valve -->
5. **Anti-patterns section update.** Current "Bypassing the cap" rule needs nuance — explicit edges aren't bypassing, they're the intended channel. **Edit the existing "Bypassing the cap" bullet** (do not add a parallel bullet alongside it): reframe as "Bypassing the **tag-cap** by hand-listing more than 2 tag-only peers in `peer_repos:` overrides the cost ceiling — surface to PM." The existing bullet is the one being updated; leaving both old and new in place creates a duplicate contradiction.
   <!-- Review: review-integrator — A4: executor edits existing bullet, not a parallel addition -->
6. **EM dispatch heuristic section update.** Auto-discovery is the default. Manual `peer_repos:` becomes an override path for: (a) plan author wants to consult a `dormant` peer, (b) plan crosses a domain the registry doesn't yet capture, (c) testing the agent against a curated peer set.

## Stage 1.5 — Wiki Layout Normalization

**Status: executed 2026-05-17 by EM-dispatched executor; staged but not committed.**

PM directive (mid-review): canonical working wiki layout is top-level `docs/wiki/` for every repo. The 8 stale dev-tree duplicates and 62 plugin-bundled wikis previously split across `x:/coordinator-claude/docs/wiki/` (8 files) and `x:/coordinator-claude/plugins/coordinator/docs/wiki/` (62 files) are consolidated at top-level. Plugin source no longer carries the doctrine wiki; consumers of the published plugin will see a stale wiki at `~/.claude/plugins/coordinator/docs/wiki/` (PM-accepted tradeoff — most percolation does not move wikis).

**What was done:**
- Audit + merge of 8 dev-tree top-level files against plugin-bundled counterparts. Result: 6 plugin-wins (newer/larger), 1 dev-tree-only (no plugin counterpart; net no-change), 1 merged-substantive (`workday-workweek-cadence.md` — unique content from both sides folded).
- 63 files moved via cp + git add + git rm (git mv failed on Windows X: drive; cp+stage gives identical git result — 55 detected as renames, 7 as M+D for merged files).
- 11 explicit-path references `plugins/coordinator/docs/wiki/X` → `docs/wiki/X` updated across 7 markdown files.
- `plugins/coordinator/docs/wiki/` directory removed.

**What still needs follow-up (flagged for Stage 1.6 or separate plan):**
- `bin/sync-plugin-wiki.sh` and `hooks/scripts/block-dev-side-mirror-wiki.sh` define `BUNDLED_WIKI="${PLUGIN_ROOT}/docs/wiki"`. Post-move, after publish, that path no longer exists in the published plugin. The scripts' core semantic ("block dev-side writes to a publish-side mirror") is now inverted: there is no bundled wiki to protect against. Both need semantic review and likely retirement or repurposing.
- The 18 user-level wikis at `~/.claude/docs/wiki/` are out-of-scope for this stage — they remain as claude-central's working wiki.

## Stage 2 — Auto-Discovery in Prior-Art-Checker

### S2.A — Agent bootstrap reads registry

Edit `agents/prior-art-checker.md` (canonical: `x:/coordinator-claude/plugins/coordinator/agents/prior-art-checker.md`):

1. **Bootstrap Phase 0** — add a step before existing corpus inventory:
   - Read `~/.claude/tasks/repo-registry.md` (the file path is fixed; the registry lives in the central install).
   - Detect active project via `pwd` matched against registry `path` field. <!-- Review: zoli — F3: case-sensitivity is only one normalization axis; symlinks, separators, drive-letter case, and ~/expansion all bite before case does --> Before comparison, normalize both `pwd` and the registry `path` field via: (a) expand `~/` against $HOME / $env:USERPROFILE, (b) resolve symlinks via realpath / Resolve-Path, (c) convert separators to forward slashes, (d) lowercase drive letters on Windows, (e) strip trailing slash. After normalization, compare case-insensitively on Windows, case-sensitively on Linux/macOS. UNC and WSL paths are explicitly unsupported; agent emits DEGRADED with reason "unsupported path shape" rather than guessing.
   - If no match, fall back to manual-only mode and note in sidecar.
   - **Stage-gate precondition check (Option A, per F2):** Read the active project's entry in the registry. If `relationships:` is empty AND the project's `path` is one of the known-interwoven set [project-rag, project-rag-ue-addon, claude-unreal-holodeck], emit DEGRADED with reason "registry interwoven-set entry has empty relationships — Stage 1 may not have landed." The hardcoded set is ugly but specific; if it's wrong, the cure is one-line.
   <!-- Review: zoli — F2: rhetorical stage-gate has no mechanism; Option A 4-line startup check provides fail-loud detection for the exact failure mode the plan names -->
2. **Walk relationships** — for each edge connecting the active project's entry to another active entry, read `working_wiki:` as the peer corpus path. If `working_wiki:` is unreachable (e.g., dev tree not mounted), fall back to `publish_wiki:` if present — but annotate the sidecar with `corpus_source: publish_wiki_fallback` for traceability. No cap on edge-discovered peers.
3. **Tag overlap** — for each active entry NOT already pulled in by an edge AND sharing ≥1 `stack_tag` with the active project, mark for consultation. Cap at 2 tag-discovered peers (rank by tag-overlap count, ties broken by alphabetical shortname for determinism).
4. **Combined ceiling** — if total peers (edges + tags) exceeds 5, DEGRADED with rationale "peer count ceiling exceeded — coverage may be incomplete." New DEGRADED triggers (registry-unreadable, combined-ceiling-exceeded) extend the existing DEGRADED clause list at its **existing position** in the agent prompt (currently lines 170–173) — do not create a parallel DEGRADED structure.
   <!-- Review: review-integrator — A3: new DEGRADED triggers extend existing list at existing position -->
5. **Override** — if dispatch brief includes `peer_repos: [...]`, that list **augments** auto-discovery by default (deduped by shortname — the EM is contributing additional knowledge on top of what the registry knows). If the dispatch brief also includes `peer_repos_mode: replace`, the manual list **replaces** auto-discovery entirely — the EM gets precise control and auto-discovered peers are excluded. Document both modes explicitly in agent prompt and dispatch contract.
   <!-- Review: zoli — F4 (PM-ruled 2026-05-17): flip to augment-default. Replace-by-default was legacy-calibrated to today's behavior; augment-default is the correct shape once the registry is authoritative. Augment-default fails observably (one extra peer in sidecar); replace-default fails invisibly (missed peer finding, discovered three weeks later). PM: replace-default is a silent-data-loss surface. -->
   <!-- Decision rationale: replace-by-default would silently drop auto-discovered peers (invisible failure mode — the surface is a missed finding three weeks later). Augment-by-default fails observably (one extra peer in sidecar header). Either way EM keeps full control via the mode flag. Decision made on the Director of Engineering's recommendation (review-stage P1) and PM ruling 2026-05-17. -->

**Queue disposition (improvement-queue item `2026-05-16 | project-rag-ue-addon | tasks/lessons.md:113`):** With augment-default now the standard behavior (per F4 PM ruling), this plan's auto-discovery IS coverage expansion — the queue item's primary intent is addressed. The item's remaining scope is narrower: extending the corpus consulted during augment-mode to include peer `docs/plans/` (active plans) in addition to `docs/wiki/`. Retarget the queue entry as: "extend augment-mode corpus to include peer docs/plans/ for status:active plans." Do not close it; update the description in the queue file as part of the Stage 2 commit.
<!-- Review: zoli — F4 queue update: with augment-default, the recurring queue item is now MORE aligned (augment-mode IS coverage expansion); docs/plans/ corpus extension is the remaining follow-up scope. -->

### S2.B — Sidecar format additions

Edit the sidecar template:

1. **Per-peer "discovery reason" annotation — inline in `Corpora consulted:`.** Each peer-wiki shortname in the existing `Corpora consulted:` header line carries an inline discovery-reason tag: e.g. `peer-wikis: project-rag (edge:schema-lockstep), claude-unreal-holodeck (tag:rag)`. For manual-override peers: `peer-wikis: claude-unreal-holodeck (override)`. Do **not** add a separate "Auto-discovered peers: N (edges: X, tags: Y)" summary line — that duplicates information already carried by the extended `Corpora consulted:` line and will produce an inconsistent sidecar format. The existing `Corpora consulted:` header is the single location for peer discovery information.
   <!-- Review: review-integrator — A1: discovery reason folded into Corpora consulted: line; separate summary line dropped to avoid header duplication -->
2. **DEGRADED reasons extended** — add "registry unreadable" and "ceiling exceeded" to the DEGRADED bucket. These extend the existing DEGRADED clause list at its existing position — not a parallel structure.
   <!-- Review: review-integrator — A3: DEGRADED extensions attach at existing list position -->

### S2.C — Backward compatibility

- Existing dispatches that pass `peer_repos: [...]` continue to work — that path becomes "override mode."
- Existing dispatches without `peer_repos:` previously fell back to 4-corpus default; they now opportunistically gain auto-discovery if the active project is registered. If the project isn't in the registry, behavior is identical to today.

## Stage 3 — Surface Updates

These are small but doctrine-grepping necessary.

### S3.A — Coordinator CLAUDE.md

1. **§ Pre-Review Mechanical Verification** — update `prior-art-checker` description: registry-driven auto-discovery is default; manual `peer_repos:` is override.
2. **§ Adding a Convention** Tripwires list — add "Registry-self-read in prior-art-checker bootstrap" as a tripwire. Greppable contact-points named so far: `agents/prior-art-checker.md`, `docs/wiki/repo-registry.md`. **Before writing the tripwire entry, audit whether `/session-start`, `/session-end`, and `/project-onboarding` need a hint about the registry-bootstrap behavior** (per the "Adding a Convention" procedure's requirement to enumerate all contact-points). If any of those surfaces need a hint, add it; if none do, document the reason in a comment in the tripwire entry. The executor decides — do not pre-skip this step.
   <!-- Review: review-integrator — A5: contact-point audit required; executor checks /session-start, /session-end, /project-onboarding before finalizing tripwire entry -->

### S3.B — /update-docs Phase 14

Phase 14 currently surfaces candidates for PM tagging. Light extension: when a candidate's `CLAUDE.md` references other registry shortnames (by `../<shortname>/` sibling path mentions or by quoted shortname), surface a "candidate has CLAUDE.md naming siblings: review and tag" notice in the candidate block. PM still confirms tags + relationship kinds — no auto-promotion, no template paste. The notice is a navigation aid, not an inference; the registry shape (kinds, lockstep, ancestor-vs-peer) requires human judgment.
<!-- Review: review-integrator — B5: lighter hint (notice, not template) confirmed; no template paste -->
<!-- Review: zoli — F10 (P3, Stage 3 stub note, not a blocker): Stage 3 stub should constrain the match to (a) sibling-path mentions of the form `../<shortname>/` or `<drive>:/<shortname>/` (filesystem-shaped), or (b) shortnames appearing in CLAUDE.md frontmatter or headings — drop bare-prose mentions. Trades recall for precision; PM signal-to-noise on Phase 14 notices is the load-bearing concern. -->

This is intentionally weaker than the original draft's "match `peer_repos:` declaration" trigger — once the agent walks the registry, those declarations don't exist in CLAUDE.md anymore (per S1.C-pre), so the trigger has to be the more general "sibling-path mention" signal.

### S3.C — Repo-registry wiki

Already covered in S1.C, but flag in plan: any wiki listing that references the old "N=2 hard cap" must update to the channel-aware cap. Grep targets:
- `docs/wiki/repo-registry.md` (canonical)
- `docs/wiki/prior-art-checker.md`
- Any `CLAUDE.md` referencing the cap.

## Acceptance Criteria

**Stage 1:**
- AC1: `~/.claude/tasks/repo-registry.md` has 5 active entries (claude-central, coordinator-claude, project-rag, project-rag-ue-addon, claude-unreal-holodeck).
- AC2: Each triad entry has non-empty `relationships:` reflecting the CLAUDE.md ground truth (cross-checkable: each repo's `peer_repos:` declaration matches the registry edges).
- AC3: `docs/wiki/repo-registry.md` documents the eligibility predicate, two-channel discovery, and channel-aware cap.
- AC4: No CLAUDE.md still cites the old "N=2 hard cap" without channel context.
- AC5: `bin/verify-registry-schema.sh` passes — YAML shape valid, all `relationship.kind` values are closed-enum members, all active `working_wiki` paths resolve (with `publish_wiki` fallback noted where applicable). Required before Stage 2 dispatch. (Promoted from optional Test Surface item per F6.)
  <!-- Review: zoli — F6: Oracle 1 promoted to required Stage 1 AC; pure registry read, no agent recursion risk -->

**Stage 2:**
- AC6: (Oracle 2) Dispatch from `coordinator-claude` with no `peer_repos:` in brief produces sidecar with `Corpora consulted:` showing `peer-wikis: claude-central (edge:dev-publish)` — single edge, single expected peer. Any deviation means agent is broken.
- AC7: (Oracle 3) Dispatch from each triad member (project-rag, project-rag-ue-addon, claude-unreal-holodeck) produces sidecar showing the other two as peers with correct discovery reasons. Pairwise symmetric — asymmetry signals broken edge in registry, not agent.
- AC8: Dispatch with `peer_repos: [claude-unreal-holodeck]` (no mode flag) produces `Corpora consulted:` showing auto-discovered peers PLUS `claude-unreal-holodeck (override)` deduped. Dispatch with `peer_repos: [claude-unreal-holodeck]` AND `peer_repos_mode: replace` produces `peer-wikis: claude-unreal-holodeck (override)` only — no auto-discovered peers.
  <!-- Review: zoli — F4 AC: exercises both augment-default and replace-override paths -->
- AC9 (Stage 2, unregistered-project): Dispatch from a repo not in the registry produces sidecar with no peer-wikis entry in `Corpora consulted:` and a note "project not registered — auto-discovery skipped" and behaves like today's 4-corpus default.

**Stage 3:**
- AC12: `coordinator/CLAUDE.md` § Pre-Review Mechanical Verification names auto-discovery as default.
- AC13: `/update-docs` Phase 14 dry-run against current candidates surfaces a "naming siblings" notice for at least `claude-unreal-holodeck` based on sibling-path mentions in its CLAUDE.md.

**Backward-compat:**
- AC11: For each of the last 5 prior-art-checker dispatches in coordinator-claude `git log` (if findable via the sidecar archive), the new agent prompt produces equivalent or strictly-greater peer coverage. If any prior dispatch's behavior would diverge, flag in the Stage 2 stub PR description. With augment-default now the standard, "I used to pass `peer_repos: [X]` and got only X; now I get X plus auto-discovery" is an expected change — pre-flag this in the stub PR description so it is not a surprise at the first user-facing sidecar.
  <!-- Review: zoli — F8: backward-compat claim "existing dispatches continue to work" was asserted not verified; with F4 augment-default, behavior does change for peer_repos users — catch it before shipping -->

## Test Surface

<!-- Review: zoli — F6: prior smoke test ("verify sidecar matches expected behavior") was circular — agent-under-test produces sidecar-under-test; replaced with oracle-shaped checks that don't require trusting the artifact being validated -->
- **Stage 1:** `bin/verify-registry-schema.sh` — REQUIRED (promoted from optional). Light shell script that validates YAML shape + enum membership + path resolution for all active entries. Must pass before Stage 2 is dispatched. This is Oracle 1 — pure registry read, no agent involvement, no recursion risk. Also promoted to Stage 1 acceptance criterion (see AC5 below).
- **Stage 2:** Three oracle-shaped checks:
  - **Oracle 2 — dry-run dispatch from coordinator-claude itself.** Active project is coordinator-claude. Expected auto-discovery: claude-central via `dev-publish` edge. Single edge, single expected peer. If the agent returns anything other than `peer-wikis: claude-central (edge:dev-publish)`, the agent is broken. 1-edge oracle — minimum complexity, maximum signal.
  - **Oracle 3 — triad cross-check.** Dispatch from each triad member (project-rag, project-rag-ue-addon, claude-unreal-holodeck); verify the other two appear in each sidecar's `Corpora consulted:`. Pairwise symmetric — if A→B works but B→A doesn't, edge symmetry is broken in the registry, not the agent.
  These are one-time validation checks, not a regression suite.
- **Stage 3:** Grep audit — confirm no stale "N=2 hard cap" references remain.

## Hard Constraints (executor-bound, when implementation begins)

- **Explicit file scope per stub** — Stage 1 stub touches only registry + repo-registry wiki; Stage 2 stub touches only prior-art-checker agent prompt + sidecar template; Stage 3 stub touches CLAUDE.md + update-docs.md.
- **No fallback escape hatches** — if registry can't be read, sidecar must surface DEGRADED, never silently fall back to 4-corpus and pretend everything's fine.
- **Stage gates are real** — do not start Stage 2 before Stage 1 lands and the triad is in `active` block.
- **No commits inside subagent execution.**

## What This Plan Does NOT Do

- Does not change the four-corpus default for unregistered projects (project wikis, global wikis, lessons, queue).
- Does not extend the registry to GitHub-based peer-repo discovery (still local-disk only — the registry path field assumes a filesystem path).
- Does not implement registry-side stack_tags auto-suggestion (V2 candidate, called out in existing wiki).
- Does not retire the manual `peer_repos:` override — it remains as the EM escape hatch.
- Does not add a per-entry opt-out field (`consult: false` or similar). When a future need arises (e.g., a security-sensitive repo declining to be consulted), the addition lives in the registry schema, not in CLAUDE.md — the single-source-of-truth principle established here makes registry the canonical surface for both inclusion and exclusion signals.
  <!-- Review: zoli — F7: future opt-out surface is registry-side, not CLAUDE.md-side; codify now so a future PM doesn't re-introduce CLAUDE.md dispatch hints to get opt-out -->

## Files-Edited (preview)

**Stage 1:**
- `~/.claude/tasks/repo-registry.md` (registry data; the *user-machine* file)
- `x:/coordinator-claude/docs/wiki/repo-registry.md` (doctrine wiki)

**Stage 2:**
- `x:/coordinator-claude/plugins/coordinator/agents/prior-art-checker.md` (agent prompt)

**Stage 3:**
- `x:/coordinator-claude/CLAUDE.md` (Pre-Review Mechanical Verification + Tripwires)
- `x:/coordinator-claude/plugins/coordinator/commands/update-docs.md` (Phase 14)
- Possibly `x:/coordinator-claude/docs/wiki/prior-art-checker.md` if it cites the old cap

Each file edited inside the stage that names it. No cross-stage edits in a single commit — clean reversal points.

## Prior-Art Cross-Check

Each repo's `CLAUDE.md` explicitly states:
- `project-rag`: `peer_repos: [claude-unreal-holodeck, project-rag-ue-addon]` for "RAG-substrate / chunker / structural-index / schema work."
- `project-rag-ue-addon`: `peer_repos: [claude-unreal-holodeck, project-rag]` for "scrape / chunk / structural-index / schema / authority-pair work."
- `claude-unreal-holodeck`: `peer_repos: [project-rag, project-rag-ue-addon]` for "RAG / chunker / structural-index / engine-corpus / schema work."

These three declarations are the ground truth this plan asserts the registry should reflect. The registry edges proposed in S1.B match these declarations symmetrically. **Once S1.B + S1.C-pre land (in either order or in the same workday boundary), these declarations are deleted from CLAUDE.md** — the registry becomes the single source of truth, and CLAUDE.md retains only the human-readable sibling narrative without prior-art-checker dispatch hints.
<!-- Review: zoli — F1: "Atomic" removed here too; S1.B and S1.C-pre may land in either order, both orderings are safe -->

Reviewed via prior-art-checker on 2026-05-17 — sidecar at `x:/coordinator-claude/docs/plans/2026-05-17-prior-art-auto-discovery-and-registry-fix.prior-art-check.md`. Verdict WARN, two conflicts dispositioned (replaces/augments semantic resolved as B6; sidecar header duplication resolved as A1), six compat folds applied (A2, A3, A4, A5, B3, B5).

Doc-link-checker on 2026-05-17 — verdict WARN, 3 path-shorthand fixes applied (plugins/coordinator/ infix); load-bearing paths now resolve.

The Director of Engineering standalone review on 2026-05-17 — review at `x:/coordinator-claude/docs/plans/2026-05-17-prior-art-auto-discovery-and-registry-fix.zoli-review.md`. Verdict APPROVE-WITH-REVISIONS, 5 P1s and 5 P2/P3s applied, F4 PM-resolved (flip to augment-default per the Director of Engineering + EM recommendation).

Stage 1.5 wiki layout move executed 2026-05-17 by EM-dispatched executor; 75 files staged, not committed. Plan body amended in third integration pass to capture the move retroactively and rename schema field docs_wiki → working_wiki + publish_wiki.

## Next Step (per coordinator:plan exit)

Prior-art-checker and the Director of Engineering standalone review both complete on 2026-05-17 — all findings integrated (see Prior-Art Cross-Check above). All open questions resolved by PM (F4 augment-default ruling).

Next: dispatch **doc-link-checker** (worker dispatch per the Director of Engineering Worker Dispatch Recommendations — verify plan's path citations before Stage 1 dispatch). Once doc-link-checker passes, dispatch Stage 1 stub for PM approval.

## Worker Dispatch Recommendations (from the Director of Engineering review)

- **doc-link-checker** — verify the plan's path citations (registry path field formats, three external CLAUDE.md paths, wiki paths) all resolve before Stage 1 dispatch. Cheap, mechanical, catches the kind of citation-rot that aged plans accumulate.
