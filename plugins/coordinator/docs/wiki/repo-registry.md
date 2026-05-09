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

## Anti-patterns

- **Auto-promoting candidates without PM review.** Stack tags require human judgment on goals + relationships; auto-promotion would silently shape prior-art lookups based on nothing.
- **Bypassing the cap.** N=2 is a cost ceiling. If a plan genuinely needs 3+ peers, that's a signal it's too broad — surface to PM, don't extend the cap silently.
- **Reading peer wikis from a non-listed repo.** The registry is the contract; ad-hoc dispatches that name unlisted paths bypass the staleness check and the closed-enum discipline.
- **Treating `last_verified` as freshness of content.** It tracks `path` resolution, not wiki freshness. Use peer wikis as recall hints, not authority.

## Related

- `~/.claude/tasks/repo-registry.md` — the registry file itself
- `${CLAUDE_PLUGIN_ROOT}/bin/decode-claude-projects-dir.sh` — projects-dir decoder used by Phase 14 (bundled with the coordinator plugin)
- `~/.claude/plugins/coordinator-claude/coordinator/agents/prior-art-checker.md` — peer_repos consumer
- `~/.claude/plugins/coordinator-claude/coordinator/commands/update-docs.md` — Phase 14 host
- `~/.claude/plugins/coordinator-claude/coordinator/CLAUDE.md` § Pre-Review Mechanical Verification — EM dispatch heuristic doctrine
