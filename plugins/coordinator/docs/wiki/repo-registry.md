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

`prior-art-checker` reads four corpora by default — active project's wikis, global `~/.claude/docs/wiki/`, project lessons, central improvement queue. Prior art established in *peer* repos (e.g., a RAG-shaped plan in `~/.claude` that should consult a peer RAG indexer) was previously invisible. The registry gives the EM a structured way to nominate peers at dispatch time.

## Consumers

- **`prior-art-checker`** — accepts optional `peer_repos: [shortname, ...]` in dispatch brief. Reads each peer's `docs_wiki` as a 5th corpus. Hard cap N=2; >2 → DEGRADED.
- **`/update-docs` Phase 14** (cwd-gated, runs only from `~/.claude`) — refreshes `last_verified`, surfaces new candidates, marks unreachable paths.
- **EM dispatch logic** (documented in `coordinator/CLAUDE.md` § Pre-Review Mechanical Verification) — matches plan claim topics to `stack_tags`, picks up to 2 peers.

## Schema

```yaml
- path: <absolute-path>           # POSIX-flavored; lowercased on Windows
  shortname: <unique-id>           # referenced by peer_repos, relationships.target
  status: <enum>                   # active | dormant | unreachable | needs-pm-review
  goals:                           # PM-curated; short list
    - <human-readable goal>
  stack_tags: [<tag>, ...]         # closed enum; see below
  relationships:                   # may be empty
    - kind: <enum>                 # peer | dev-publish | consumes-from
      target: <shortname>          # must exist in registry
  docs_wiki: <absolute-path>       # path to docs/wiki/ — what prior-art-checker reads
  last_verified: <ISO-date>        # updated by Phase 14 when path resolves
```

## Closed enums

### `stack_tags` (V1)

| Tag | Meaning |
|---|---|
| `claude-plugin` | Hosts Claude Code plugin source (skills, agents, hooks) |
| `agent-orchestration` | Coordinator/EM/PM patterns, dispatch logic |
| `doctrine` | Wiki-heavy repo with CLAUDE.md doctrine |
| `rag` | Retrieval-augmented generation infrastructure |
| `mcp-server` | Implements an MCP server |
| `unreal-engine` | UE5 game/plugin code |
| `python` | Primary language is Python |
| `node` | Primary language is Node/TypeScript |
| `game` | Game project (any engine) |
| `web` | Web frontend/backend |
| `data-science` | ML/stats/analytics |

### `relationships.kind` (V1)

| Kind | Meaning | Example |
|---|---|---|
| `peer` | Sibling stack — same domain, parallel development | `coordinator-claude` ↔ `deep-research-claude` |
| `dev-publish` | Working tree ↔ installed/published copy | `coordinator-claude` ↔ `claude-central` |
| `consumes-from` | One repo's outputs feed another | `<your-app>` `consumes-from` `<your-rag-indexer>` |

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

## EM dispatch heuristic (peer_repos)

When dispatching `prior-art-checker` for a plan:

1. Read claim topics from the plan body.
2. Compare against `stack_tags` of `active` registry entries.
3. Pick up to 2 peers with the strongest overlap. Skip the active project's own entry.
4. Pass as `peer_repos: [<shortname>, ...]` in the dispatch brief; include each peer's `docs_wiki` path.
5. Justify the choice in a one-line comment in the dispatch comment for telemetry.

If plan stack is unclear or multi-domain, omit `peer_repos` — the 4-corpus default is the safe fallback.

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

1. Before invoking an extraction pipeline (e.g. `/learn-lessons central`, `/architecture-survey`), check peer registry entries with overlapping `stack_tags`.
2. Read each peer's most recent output (typically under `tasks/learn-lessons-*` or `docs/architecture/`).
3. Lift overlapping records as **inputs** to the local synthesizer phase, not as a separate scout.
4. Run extraction only on the local-unique delta.

Anti-pattern: dispatching a full extraction over a corpus a peer already mined yesterday, then deduping after the fact. The dedup pass is the wrong layer — the lift should happen at dispatch-time.

This is a peer-repo *output* consumption, distinct from peer-repo *wiki* consumption (which `prior-art-checker` handles). Outputs are dated artifacts; wikis are evergreen. The registry's `docs_wiki` field points at the wiki; outputs are located by convention under each peer's `tasks/` tree.

## Anti-patterns

- **Auto-promoting candidates without PM review.** Stack tags require human judgment on goals + relationships; auto-promotion would silently shape prior-art lookups based on nothing.
- **Bypassing the cap.** N=2 is a cost ceiling. If a plan genuinely needs 3+ peers, that's a signal it's too broad — surface to PM, don't extend the cap silently.
- **Reading peer wikis from a non-listed repo.** The registry is the contract; ad-hoc dispatches that name unlisted paths bypass the staleness check and the closed-enum discipline.
- **Treating `last_verified` as freshness of content.** It tracks `path` resolution, not wiki freshness. Use peer wikis as recall hints, not authority.

## Periodic cross-repo summaries

At workday-start in any registered repo, the EM can enumerate sibling repos and query each for recent roadmap completions — producing a one-screen "what shipped in sibling repos this week" view.

### Invocation pattern

```bash
for repo in $(awk '/<!-- BEGIN repo-registry -->/,/<!-- END repo-registry -->/' \
    ~/.claude/tasks/repo-registry.md \
    | grep -E '^\s*path:' | awk '{print $2}'); do
  (cd "$repo" && query-completions --since "7d" --where "nature=roadmap" --format markdown-list)
done
```

This yields a per-repo markdown list of roadmap-tagged completion records from the last 7 days. Adjust `--since` and `--where` to taste (e.g., `nature=shipped` for cross-repo release summaries).

### Schema mismatch warning — do NOT use yq

`tasks/repo-registry.md` is a **markdown file** with YAML-list blocks inside HTML comment sentinels (`<!-- BEGIN repo-registry -->` / `<!-- END repo-registry -->`). It is NOT a top-level YAML document. `yq '.repos[].path'` will silently return nothing or error — do not use it for registry parsing.

The sentinel-bounded `awk` pattern above is the canonical extraction method. It respects the sentinel boundaries and is safe to run on any machine in the coreutils dependency surface (DR-016 — `yq` is explicitly excluded from the coreutils surface).

### Invocation context

- **When:** `/workday-start` if the EM wants cross-repo situational awareness before planning. Also useful before dispatching `prior-art-checker` — a recent sibling completion in the same domain may have established art the plan should reference.
- **Scope:** runs only against `status: active` entries; `unreachable` paths will cause `cd` to fail — wrap in `if [ -d "$repo" ]` guard if the registry may contain unreachable entries.
- **Cost:** one `query-completions` call per active repo. Cheap — `query-completions` reads `archive/completed/` frontmatter, no LLM calls. Skip if no completions log is present in a sibling (query will return empty; that's fine).

## Related

- `~/.claude/tasks/repo-registry.md` — the registry file itself
- `${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh` — projects-dir decoder used by Phase 14 (bundled with the coordinator plugin)
- `~/.claude/plugins/coordinator/agents/prior-art-checker.md` — peer_repos consumer
- `~/.claude/plugins/coordinator/commands/update-docs.md` — Phase 14 host
- `~/.claude/plugins/coordinator/CLAUDE.md` § Pre-Review Mechanical Verification — EM dispatch heuristic doctrine
