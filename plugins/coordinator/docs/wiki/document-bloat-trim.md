---
system: document-bloat-trim
last_updated: 2026-04-28
status: living
provenance: archive/handoffs/2026-04-28_222800_2fc815ec.md + 2026-04-28_225450_5e6c9130.md
---

# Document Bloat Trim — CLAUDE.md as Link Index

> **The rule.** Entry-point docs (CLAUDE.md, `docs/README.md`, plugin READMEs) load into every session. Chars cost more there. When a section grows past a one-paragraph summary, extract to wiki/decisions/plans and link.

## Why this exists

CLAUDE.md is the surface every session reads. Inlining content there is greppable, but greppability lives equally in the linked page. The cost asymmetry is real: every char in CLAUDE.md is paid by every session, every reviewer, every dispatched agent that gets the file in context. Wiki and plan pages are pulled on demand.

"Inline so it can be grepped" is an anti-pattern when the topic has grown past a one-paragraph summary. Promote it.

## When to extract

- A section grows past a one-paragraph summary → extract to wiki.
- A decision has tradeoffs worth recording → extract to a Decision Record (DR-NNN block in the relevant wiki).
- A plan has procedural detail worth keeping → extract to `docs/plans/`.
- A subroutine of a skill has grown long enough that the SKILL.md is harder to read → extract to `pipelines/<name>-internals.md`.

## Internals-doc extraction pattern (shipped 2026-04-28)

Command/agent files exceeding ~300 lines extract to a sibling `pipelines/<name>-internals.md` while keeping step structure + dispatch contracts inline. Examples:

| File | Before | After + sibling internals |
|---|---|---|
| `repo.md` | 481 | 340 + `repo-research-internals.md` (110) |
| `web.md` | 360 | 233 + `web-research-internals.md` (123) |
| `workday-start.md` | 320 | 239 + `workday-start-internals.md` (102) |
| `bug-sweep.md` | 314 | 251 + `bug-sweep/pattern-library.md` |

The mechanical contract: top-level file keeps the dispatch surface (steps, names, contracts); the internals file carries elaboration the EM doesn't need on every read.

## Cookbook inlining vs link-reference for subagents

The Staff Engineer confirmed (P8): **subagents see only their dispatch prompt — bare link refs are unreachable.** Three rejected alternatives, one accepted:

- **Verbatim inlining** — kept as the substrate, but trimmed.
- **Summary + Read pointer** — rejected. Recreates the very drift hazard inlining was meant to prevent.
- **`@`-import shared file** — rejected. Untested in agent prompts.
- **Hybrid (accepted)** — keep verbatim inlining but trim cookbook to the load-bearing core. ~28 lines × 5 agents on ue-* trims; net ~50 lines saved with no behavior-change risk.

Frontmatter examples and deep-research playbook trims were deferred — frontmatter examples need careful YAML editing under structured-output dispatch examples (low risk per file, high per-error blast radius); playbooks have heavy procedural detail where condensing requires reviewer judgment, not mechanical edits.

## Memory is for cross-session pointers, not decision content

Decisions, frameworks, adoption strategies belong in plans/wikis/DRs. Memory entries exceeding a one-line pointer migrate body, leave pointer behind. Memory's value is the cross-session reachability — decisions become unfindable when buried in a memory entry that nobody knows to grep for.

## Source-of-truth doc placement

Plugin-scoped reference docs belong inside the plugin, not in project-scoped `docs/plans/`. The pattern shipped for `repo-research-internals.md` and `web-research-internals.md` resolves the broken cross-repo path in `2026-04-26-mcp-tool-agent-mapping-cleanup.md` (referenced as "source of truth" in 6 files but only resolving inside the holodeck source repo).

Audit-trail bug to watch: publish repos that lack `coordinator-safe-commit` silently sweep concurrent-session files under whatever subject the user types. Going forward: run `git diff --cached` before committing in any publish repo without the helper.

## Publish-repo helper distribution

The shim pattern: a 14-line `bin/safe-commit` that delegates to `$HOME/.claude/...` rather than copying the full helper + lib. No drift, low cost; makes the canonical pattern accessible from each repo without needing to remember the absolute path. Full helper copy was rejected as a drift hazard.

## See also

- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — the helper this page references.
- [`streamline-infra.md`](./streamline-infra.md) — the snippet-sync pattern for deduplicating doctrine across consumers (a different surface of the same problem).
- `archive/handoffs/2026-04-28_222800_2fc815ec.md`, `2026-04-28_225450_5e6c9130.md` — origin handoffs.

## Decision Records

**DBT-DR-001 — Hybrid trim over `@`-import for subagent prompts**

*Problem:* ue-* agent prompts carried verbatim cookbook content. Could a link reference, summary+pointer, or `@`-import substitute?

*Decision:* Hybrid. Keep verbatim inlining (per "Agent Prompts Are Self-Contained") but trim cookbook to the load-bearing core. Frontmatter examples + deep-research playbook trims deferred — they need careful YAML editing or reviewer judgment respectively.

*Alternatives considered:* Bare link reference (rejected — the Staff Engineer P8, subagents see only the dispatch prompt). Summary + Read pointer (rejected — recreates the drift hazard). `@`-import (rejected — untested in agent prompts).

**DBT-DR-002 — `/schedule` is for remote CCR agents, not local file tasks**

*Problem:* Should the 14-day cookbook recheck use `/schedule`?

*Decision:* No. `/schedule` is for remote CCR agents that have no local file access. Pivoted to a local marker file (`tasks/cookbook-recheck-due-YYYY-MM-DD.md`) — durable, git-tracked, contains the full procedure, survives session compaction.
