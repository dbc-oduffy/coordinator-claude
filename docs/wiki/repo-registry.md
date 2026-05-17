---
title: Repo Registry
created: 2026-05-07
author: EM
status: shipped
kind: wiki
---

# Repo Registry — Schema and Conventions

The repo registry (`~/.claude/tasks/repo-registry.md`) is a structured cross-repo inventory powering peer-repo prior-art lookup. This wiki documents the schema, the closed enums, and the procedure for extending either.

## Why this exists

`prior-art-checker` reads four corpora by default — active project's wikis, global `~/.claude/docs/wiki/`, project lessons, central improvement queue. Prior art established in *peer* repos (e.g., a RAG-shaped plan in `~/.claude` that should consult a peer RAG indexer) was previously invisible. The registry made peer consultation possible (via manual `peer_repos:` at dispatch time); Stage 2 of the 2026-05-17 plan makes it AUTOMATIC by having the agent walk the relationships graph itself. The EM no longer needs to remember which peers exist or which tags overlap — the registry IS the source of truth, declared once per repo.

## Consumers

- **`prior-art-checker`** — auto-discovers peers by walking the registry's relationships graph from the active project's entry (per Stage 2 of `2026-05-17-prior-art-auto-discovery-and-registry-fix`). Edges connecting the active project to active entries are consulted with no cap; `stack_tags` overlap (entries with shared tags but no edge) consulted up to N=2 additional peers. Combined ceiling: 5 → DEGRADED if exceeded. Manual `peer_repos: [shortname, ...]` in dispatch brief AUGMENTS auto-discovered set by default; `peer_repos_mode: replace` overrides to drop auto-discovery.
- **`/update-docs` Phase 14** (cwd-gated, runs only from `~/.claude`) — refreshes `last_verified`, surfaces new candidates, marks unreachable paths.
- **EM dispatch logic** (documented in `coordinator/CLAUDE.md` § Pre-Review Mechanical Verification) — most dispatches now require zero peer selection from the EM; auto-discovery handles it. Manual `peer_repos:` is an override path for edge cases (consulting a `dormant` peer, testing the agent, cross-domain plans where auto-discovery's tag-overlap is too narrow).

## Schema

```yaml
- path: <absolute-path>           # POSIX-flavored; lowercased on Windows
  shortname: <unique-id>           # referenced by peer_repos, relationships.target
  status: <enum>                   # active | dormant | unreachable | needs-pm-review
  goals:                           # PM-curated; short list
    - <human-readable goal>
  stack_tags: [<tag>, ...]         # closed enum; see below
  relationships:                   # may be empty
    - kind: <enum>                 # peer | dev-publish | consumes-from | schema-lockstep | ancestor | depends-on
      target: <shortname>          # must exist in registry
  working_wiki: <absolute-path>    # required. Canonical source-of-truth wiki; what prior-art-checker reads by default
  publish_wiki: <absolute-path>    # optional. Published mirror path; fallback when working_wiki unreachable
  last_verified: <ISO-date>        # updated by Phase 14 when path resolves
```

`working_wiki` is the source-of-truth — where humans/agents edit. `publish_wiki` is optional and populated only for repos with a separate published mirror (currently only `claude-central`, which receives the bundled coordinator wiki via percolate). When the active-project graph walk consults a peer:

1. Try `working_wiki` first.
2. If unreachable (path doesn't resolve — e.g., dev tree not mounted on this machine), fall back to `publish_wiki` if present.
3. Sidecar annotates the corpus source for traceability: `corpus_source: working_wiki` (default) or `corpus_source: publish_wiki_fallback`.

If neither resolves, the peer is skipped with a DEGRADED note.

## Closed enums

### `stack_tags` (V2 — 2026-05-17)

| Tag | Meaning | Worked example |
|---|---|---|
| `claude-plugin` | Hosts Claude Code plugin source (skills, agents, hooks) | `coordinator-claude`, `claude-unreal-holodeck` |
| `agent-orchestration` | Coordinator/EM/PM patterns, dispatch logic | `coordinator-claude` |
| `doctrine` | Wiki-heavy repo with CLAUDE.md doctrine | `coordinator-claude`, `claude-central` |
| `rag` | Retrieval-augmented generation infrastructure | `project-rag`, `project-rag-ue-addon` |
| `mcp-server` | Implements (hosts) an MCP server runtime | `project-rag`, `claude-unreal-holodeck` |
| `mcp-plugin` | Registers tools into another repo's MCP server via plugin mechanism (e.g. pluggy hookimpl). Does NOT host a server. | `project-rag-ue-addon` (registers 10 tools into `project-rag`'s MCP) |
| `unreal-engine` | UE5 game/plugin code | `claude-unreal-holodeck`, `project-rag-ue-addon` |
| `python` | Primary language is Python | `project-rag`, `project-rag-ue-addon` |
| `node` | Primary language is Node/TypeScript | — |
| `game` | Game project (any engine) | `claude-unreal-holodeck` |
| `web` | Web frontend/backend | — |
| `data-science` | ML/stats/analytics | — |

### `relationships.kind` (V2 — 2026-05-17)

| Kind | Meaning | Direction | Worked example |
|---|---|---|---|
| `peer` | **Residual** sibling stack — use ONLY when none of the more-specific kinds below apply. More-specific kind always wins. | Symmetric | `coordinator-claude` ↔ `deep-research-claude` (parallel development, no specific data-flow or schema coupling) |
| `dev-publish` | Working tree ↔ installed/published copy (development-side ↔ live-install side) | Symmetric (graph walk treats both directions equivalently) | `coordinator-claude` ↔ `claude-central` |
| `consumes-from` | One repo's outputs feed another. **Data-flow specific** — A reads/processes B's artifacts. | Directional (A consumes B; A is the consumer) | `project-rag` `consumes-from` `project-rag-ue-addon` (consumes corpus releases); `claude-unreal-holodeck` `consumes-from` `project-rag` (engine corpus served back) |
| `schema-lockstep` | Two repos share a test-enforced schema constraint. A change in one MUST trigger consultation of the other. **Strongest consult signal.** | Symmetric (declare on both sides) | `project-rag` ↔ `project-rag-ue-addon` (`structural_schema.py` constants parity-tested) |
| `ancestor` | This repo was carved/extracted from the target. Historical lineage — lessons learned during the carve-out live in the ancestor's wiki. | Directional (A's ancestor is B; A is the descendant) | `project-rag` `ancestor: claude-unreal-holodeck` (extracted 2026-04-29); `project-rag-ue-addon` `ancestor: claude-unreal-holodeck` (carved 2026-05-13) |
| `depends-on` | General dependency — repo A requires repo B to function (SDK, library, upstream tool, structural dependency). **Not** data-flow specific (that's `consumes-from`). | Directional (A depends on B) | `claude-unreal-holodeck` `depends-on: coordinator-claude` (consumes coordinator doctrine; not a data-flow consumer) |

**`peer` is the residual kind: use it only when none of `schema-lockstep`, `ancestor`, `depends-on`, `dev-publish`, `consumes-from` apply.** The more-specific kind always wins. A future EM hesitating between `peer` and `depends-on` for safety should pick `depends-on` — eroding `peer`'s precision by treating it as the default defeats the auto-discovery channel ranking.

**Symmetric vs. directional kinds and graph walk:** The agent walks the graph bidirectionally — for each edge, the relationship counts whether the active project is the source OR the target. So `ancestor` declared on `project-rag` (target: `claude-unreal-holodeck`) is also visible when auto-discovery dispatches from `claude-unreal-holodeck` looking back at its descendants. The registry need not declare inverse edges; the walk handles both directions.

## Status semantics

- **`active`** — repo is in active development; eligible as a peer for prior-art lookup.
- **`dormant`** — repo exists on disk but isn't being worked on. Eligible as peer but lower priority. Never auto-deleted in V1; pruning is a `/workweek-complete` triage decision.
- **`unreachable`** — `path` did not resolve at last Phase 14 run. Skipped by `prior-art-checker` even if listed in `peer_repos`. Kept in registry — repo may be on a disconnected drive.
- **`needs-pm-review`** — Phase 14 surfaced this candidate; PM has not yet supplied `goals`, `stack_tags`, or `relationships`. Not eligible as a peer until promoted to `active`.

## Extending the enums

Both `stack_tags` and `relationships.kind` are closed. Extending requires:

1. Add the new tag/kind to this wiki's table with a one-line meaning.
2. Add a worked example.
3. Update existing registry entries that should carry the new tag (or leave for next PM review pass).
4. Commit the wiki + registry changes together.

Silent additions in `tasks/repo-registry.md` without a wiki update are doctrine drift — the wiki is the contract.

## Phase 14 behavior (registry refresh)

Runs only when `pwd` resolves to `~/.claude`. Skipped by the `/update-docs` doc-maintenance Sonnet agent (EM-only, same pattern as Phase 12 distillation check).

1. Decode `~/.claude/projects/` dir names via `${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh` to candidate paths.
2. Diff against the active registry block. New paths → append to `<!-- BEGIN repo-registry-candidates -->` block with `status: needs-pm-review`.
3. For each existing entry: `ls <path>` to verify on-disk. Update `last_verified` if reachable; flip to `status: unreachable` otherwise (don't auto-delete).
4. End-of-phase output: "Registry has N new candidates. Edit `~/.claude/tasks/repo-registry.md` to promote."
5. Edits commit in the same Phase 9 commit cycle.

## Eligibility predicate

A registry entry is eligible for prior-art consultation when ALL three hold:

1. `status: active` (or `dormant` — still eligible, lower priority).
2. `working_wiki` field present, and the path resolves at last `last_verified`. If `working_wiki` is unreachable but `publish_wiki` resolves, the entry is eligible via fallback (sidecar annotates `corpus_source: publish_wiki_fallback`).
3. Connected to the active project by EITHER:
   - At least one `relationships` edge (graph walk finds both source and target directions), OR
   - At least one `stack_tags` overlap with the active project's tags.

Entries with `status: unreachable` or `status: needs-pm-review` are NOT eligible for auto-discovery. Manual `peer_repos:` override may still name them (audit footprint via sidecar).

## Discovery channels and caps

Prior-art-checker auto-discovery has two channels, with different cap shapes reflecting their different signal strengths:

- **Channel 1 — edges (strong signal, no cap).** Every active entry connected to the active project by ANY `relationships` edge is consulted. Edges are EM-authored ground truth; capping them defeats their purpose. The triad's three-way `schema-lockstep` + `ancestor` + `consumes-from` graph fans out to 2 peers from any vertex; the registry can grow to 4-5 edges per repo without exceeding the combined ceiling below.
- **Channel 2 — tags (weak signal, capped at N=2).** Entries with ≥1 `stack_tags` overlap with the active project AND no edge to it. Ranked by overlap count (more shared tags = higher rank); ties broken alphabetically by shortname for determinism. Cap at 2 catches "two video-game repos that share patterns" without runaway cost from many repos sharing a common tag like `python`.
- **Combined ceiling — 5 peers total.** When edges + tags would exceed 5, DEGRADED with rationale "peer count ceiling exceeded — coverage may be incomplete." The EM's remediation surface is `peer_repos: [<shortname>, ...]` with `peer_repos_mode: replace` to consult a deliberately chosen subset. The ceiling itself does not get bumped silently — that's a doctrine change requiring PM authorization.

## EM dispatch heuristic (mostly automatic; override path for edge cases)

For the common case, the EM no longer needs to select peers — auto-discovery does it:

1. Dispatch `prior-art-checker` with no `peer_repos:` in the brief.
2. The agent walks the registry from the active project's entry per the channels above.
3. The sidecar header annotates each consulted peer with `discovered_via: edge:<kind>` or `discovered_via: tag:<tagname>`.

Manual `peer_repos:` is the override path for these edge cases:

- **Consulting a `dormant` peer** (e.g., a parked repo that nonetheless has relevant prior art).
- **Cross-domain plans** where tag-overlap auto-discovery is too narrow.
- **Deliberate subset** when the combined ceiling fires and the EM wants to pick which N peers consume budget.
- **Testing the agent** against a curated peer set.

When `peer_repos:` is present:

- **Default semantic (augment):** The manual list is ADDED to auto-discovered peers (deduped by shortname). EM contributes additional knowledge; auto-discovery still fires. This is the fail-loud default — extra peers show in sidecar; the EM can see whether their hand-picked set was redundant with edges.
- **Override (`peer_repos_mode: replace`):** Manual list REPLACES auto-discovery entirely. Use for precision. Note: this is silent-data-loss-prone — if you forget that auto-discovery would have found peer X, you drop X. Reserve for cases where you genuinely want to scope to just your list.

The augment-default is calibrated to safety, not to legacy behavior. The pre-2026-05-17 behavior was "peer_repos: IS the peer list" — which silently dropped any peer the EM didn't remember to list. Augment-default inverts that fail mode.

## Sentinels self-document their refresh contract

Auto-generated sentinel blocks in the registry (and in any cross-repo doc that consumes registry data) MUST inline their refresh preconditions — generator script, input source, refresh trigger, last-refreshed timestamp. The sentinel block is the contract; siblings decay.

```markdown
<!-- BEGIN repo-registry-candidates
     Generator: ${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh
     Source: ~/.claude/projects/
     Refresh: /update-docs Phase 14 (cwd-gated, ~/.claude only)
     Last refreshed: <ISO-date>
-->
...candidates...
<!-- END repo-registry-candidates -->
```

Without inline preconditions, the block becomes an orphan auto-generated region that no maintainer knows how to regenerate. Cross-repo sentinel convention lives in the coordinator plugin's `docs/wiki/cross-repo-citation-conventions.md`.

## Sibling-output lift before re-running extraction pipelines

When a peer repo has already run an extraction, distillation, or audit pipeline against shared substrate (lessons mining, atlas extraction, prior-art harvest), **lift the sibling's output before re-running the pipeline locally**. Re-extraction over identical substrate burns tokens and produces near-duplicate output that then needs deduping against the very artifact you ignored.

Procedure:

1. Before invoking an extraction pipeline (e.g. `/learn-lessons central`, `/architecture-audit`), check peer registry entries with overlapping `stack_tags`.
2. Read each peer's most recent output (typically under `tasks/learn-lessons-*` or `docs/architecture/`).
3. Lift overlapping records as **inputs** to the local synthesizer phase, not as a separate scout.
4. Run extraction only on the local-unique delta.

Anti-pattern: dispatching a full extraction over a corpus a peer already mined yesterday, then deduping after the fact. The dedup pass is the wrong layer — the lift should happen at dispatch-time.

This is a peer-repo *output* consumption, distinct from peer-repo *wiki* consumption (which `prior-art-checker` handles). Outputs are dated artifacts; wikis are evergreen. The registry's `working_wiki` field points at the wiki; outputs are located by convention under each peer's `tasks/` tree.

## Future: per-entry opt-out

Not in V2. When a future need arises (e.g., a security-sensitive repo declining to be consulted as a peer regardless of its tags/edges), the right addition is a `consult: false` field on the registry entry — NOT a CLAUDE.md dispatch hint, NOT an environment variable. The single-source-of-truth principle established here makes the registry the canonical surface for both inclusion and exclusion signals. Adding this field will follow the closed-enum extension procedure (one-line meaning + worked example in this wiki, then registry entries gain the field).

## Anti-patterns

- **Auto-promoting candidates without PM review.** Stack tags require human judgment on goals + relationships; auto-promotion would silently shape prior-art lookups based on nothing.
- **Bypassing the tag-cap.** The N=2 cap on Channel 2 (tag-overlap peers) is a cost ceiling. Hand-listing 3+ tag-only peers in `peer_repos:` overrides it. If a plan genuinely needs 3+ tag-only peers, that's a signal scope is too broad — surface to PM. Edges (Channel 1) are uncapped by design and are NOT bypassing anything; explicit relationships are the intended channel.
- **Reading peer wikis from a non-listed repo.** The registry is the contract; ad-hoc dispatches that name unlisted paths bypass the staleness check and the closed-enum discipline.
- **Treating `last_verified` as freshness of content.** It tracks `path` resolution, not wiki freshness. Use peer wikis as recall hints, not authority.
- **Treating `peer` as the safe default.** `peer` is residual — use only when none of the more-specific kinds apply. Using `peer` for relationships that are actually `schema-lockstep` or `depends-on` erodes the channel-ranking discipline auto-discovery depends on.
- **CLAUDE.md as the prior-art-checker dispatch hint surface.** Don't declare `peer_repos: [X, Y]` in a repo's CLAUDE.md. The registry is the single source of truth; CLAUDE.md narrative about siblings is for humans/agents reading the repo, not for dispatch.

## Related

- `~/.claude/tasks/repo-registry.md` — the registry file itself
- `${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh` — projects-dir decoder used by Phase 14 (bundled with the coordinator plugin)
- `~/.claude/plugins/coordinator-claude/coordinator/agents/prior-art-checker.md` — peer_repos consumer
- `~/.claude/plugins/coordinator-claude/coordinator/commands/update-docs.md` — Phase 14 host
- `~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md` § Pre-Review Mechanical Verification — EM dispatch heuristic doctrine
