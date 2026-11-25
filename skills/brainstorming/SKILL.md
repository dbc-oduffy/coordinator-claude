---
name: brainstorming
description: Vague or multi-subsystem asks into requirements. Size first.
description-budget: 135
version: 1.0.0
allowed-tools: ["Read","Write","Edit","Bash","Grep","Glob","Agent","Skill","AskUserQuestion","TaskCreate","TaskUpdate","TaskGet","TaskList"]
---

# Brainstorming

Turn the PM's intent into a design spec through collaborative dialogue. The PM decides what to
build; the EM shapes feasibility, flags constraints, proposes approaches. Output: a committed spec
that feeds `coordinator:plan`.

**Announce at start:** "Using brainstorming to explore the design before we plan implementation."

**When NOT to invoke:** a well-scoped next step on a known shape goes straight to
`coordinator:plan`, or just do it if trivial. Brainstorming is for genuine ambiguity in shape —
if the request would take 2+ rounds of "what is this even?" clarifying questions, it applies.

**vs. `coordinator:shape`:** siblings, not twins. Brainstorming is for *not knowing what to
build* (produces a solution artifact). `shape` is for *converging on a problem the PM already
holds*. PM wants confirmation you understood a problem → `shape`; PM doesn't know what to build →
`brainstorming`. Both terminate in `coordinator:plan`.

<HARD-GATE>
Once started, do NOT invoke any implementation skill, write code, scaffold a project, or dispatch
an executor until the spec is written and PM-approved. The only exit is a completed spec that
transitions to `coordinator:plan`. If the PM arrived with a clear spec, skip brainstorming
entirely — but once started, see it through.
</HARD-GATE>

The design can be lightweight — a few sentences for simple work — but it must exist and be
PM-approved before implementation; "we discussed it earlier" doesn't survive context compaction,
the written spec does.

## Process

Explore project context → clarify intent with the PM (loop until clear) → propose 2-3 approaches
(loop if none fit) → present design sections, PM approving each (loop on revise) → scope check
(multi-subsystem: split into sub-specs) → write spec → self-review → PM reviews (loop on changes)
→ `coordinator:plan`.

**Terminal state:** the ONLY next step after brainstorming is `coordinator:plan`.

## Understanding Intent

<!-- BEGIN project-rag-preamble (synced from snippets/project-rag-preamble.md) -->

**Code lookup: project-rag first.** Whenever project-rag's CLI, MCP tools or registry entry is present it is the primary path: engine facts and symbol questions (definitions, callers, members) go to its tools before Grep/Glob; Grep is for literal text. Grep/Read stays available (never a prohibition); a project-rag shortfall is reported to project-rag as a gap, not silently routed around.

First action, when `mcp__project-rag__*` tools are present (they arrive deferred): `ToolSearch("select:mcp__project-rag__project_staleness_check,mcp__project-rag__project_symbol_brief,mcp__project-rag__project_lsp_definition,mcp__project-rag__project_lsp_hover,mcp__project-rag__project_code_outline,mcp__project-rag__project_symbol,mcp__project-rag__project_rag_instructions")`
Then `project_staleness_check(repo=<repos.* key>)`.
Pass `repo=<repos.* key>` on every project-rag call; its key is a `repos.` row of `machine-local keys`. An answer from the wrong repo is a miss.
Shape -> tool: symbol `project_symbol_brief(symbol_name=X, lsp=true)` first; type/location `project_lsp_definition`/`project_lsp_hover(file=, line=, name=)`; a file's symbols `project_code_outline(file=)`; exact-name identity `project_symbol(symbol_name=X)`; else `project_rag_instructions`.
Bodies and members: load `project_symbol_source` by name; a `project_symbol` stub is not "corpus can't answer".
**Enumeration is not a lookup.** "What exists?" (target list, file set, coverage count, "is X covered?") is answered by walking the filesystem, never by an index; use project-rag to understand what the walk found.
If a project-rag call errors, retry it once; retry a substring timeout by exact name.
A miss after the retry never ends your task: the failed call counts as an attempt; use Grep/Read scoped to named paths, carry on, and report the call, its output and the fallback to project-rag as a gap. The engine alone aborts a run. No project-rag CLI, MCP or registry entry at all: Grep/Read.
Executors only: an executor working from a plan's cited facts needs no fresh lookup; a new fact it needs and cannot get stops that row only.
**Every grep is scoped**: `git grep` or the Grep tool on named paths in your own repo; never search recursively from a repo root, `..`, a sibling checkout or a drive (`A-RECURSIVE-GREP-FROM-A-REPO-ROOT-STALLS-THE-BOX`). A search constraint in your brief or `em_context` binds you, even when project-rag is down.
Friction: memo `project-rag-em` / `gh issue create -R dbc-oduffy/project-rag`.
<!-- END project-rag-preamble -->

Check accumulated project knowledge first (architecture atlas, wikis, repo map) before reading
source. Clarifying questions: one per message, multiple choice when the decision space is
bounded, probing constraints rather than basics the PM has likely considered. Raise technical
concerns directly — honest counsel, not silent compliance. Independent subsystems each get their
own spec/plan/execution cycle — decompose first, then deep-dive each piece.

## Domain Language Discipline

If `CONTEXT.md` exists at the project root, read it before the first clarifying question; if
absent, proceed silently. Use its canonical terms; when the PM uses an `_Avoid_:`-listed synonym,
substitute and confirm: *"You said X — you mean &lt;canonical-term&gt;?"*

When the PM resolves a term during dialogue, update `CONTEXT.md` inline (don't batch): a `##
Terms` section, `**<Canonical term>** — one-sentence definition.` plus an `_Avoid_:` line of
synonyms actually seen. Lazily create the file on the first resolved term — never scaffold it empty.

## Exploring Approaches, Presenting the Design

2-3 approaches with trade-offs, leading with your recommendation — one sentence each on the idea,
the trade-off, and when you'd choose it; say so if one is clearly superior; flag a significant drawback even in a favored option.
Scale each design section to its complexity (a few sentences to ~300 words); ask after each
whether it looks right — incremental approval, not monolithic review. Cover as applicable: architecture, components, data flow, interfaces,
error handling, testing strategy. In existing codebases, follow established patterns.

## Writing the Spec

**Save to:** `docs/specs/YYYY-MM-DD-<topic>-design.md` (create `docs/` if absent). Must carry
enough context for a cold-start agent to implement without conversation history.

**Self-review before presenting** (fix inline): no TBD/TODO/vague requirements; no internal
contradictions; scope focused enough for a single plan (split now if not); no requirement readable
two ways; `CONTEXT.md` updated for any term resolved in dialogue.

**Commit the spec**, then:

> "Spec written and committed to `<path>`. Please review — I'll hold on implementation until you
> approve."

Wait for PM response; apply changes and re-run self-review if requested.

## Spec Template

```markdown
# [Feature Name] Design Spec

**Date:** YYYY-MM-DD
**Status:** Draft | PM-Approved
**Goal:** [One sentence]

## Context
[What exists today, what problem this solves, why now.]

## Requirements
- [Requirement 1 — concrete, testable]

### Out of Scope
- [Thing we're NOT building and why]

## Design
### Architecture
### Components
### Interfaces
### Error Handling

## Trade-offs
| Decision | Chosen | Alternative | Why |

## Testing Strategy

## Open Questions
[Should be empty before PM approval.]
```

## Transition

Once the PM approves: **REQUIRED SUB-SKILL** `coordinator:plan`, spec file as input. No other
skill is a valid next step.
