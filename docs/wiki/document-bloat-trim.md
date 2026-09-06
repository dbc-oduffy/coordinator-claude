---
system: document-bloat-trim
last_updated: 2026-04-28
status: active
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

## Internals-doc extraction pattern

Command/agent files exceeding ~300 lines extract to a sibling `pipelines/<name>-internals.md` while keeping step structure + dispatch contracts inline. Examples:

| File | Before | After + sibling internals |
|---|---|---|
| `repo.md` | 481 | 340 + `repo-research-internals.md` (110) |
| `web.md` | 360 | 233 + `web-research-internals.md` (123) |
| `workday-start.md` | 320 | 239 + `workday-start-internals.md` (102) |
| `bug-sweep.md` | 314 | 251 + `pipelines/bug-sweep/pattern-library.md` |

The mechanical contract: top-level file keeps the dispatch surface (steps, names, contracts); the internals file carries elaboration the EM doesn't need on every read.

## Cookbook inlining vs link-reference for subagents

The Staff Engineer confirmed (P8): **subagents see only their dispatch prompt — bare link refs are unreachable.** Three rejected alternatives, one accepted:

(This is about a *passive* citation the subagent has no instruction to open — distinct from a brief that explicitly instructs the agent to `Read` a named path; see `coordinator/docs/wiki/dispatching-parallel-agents.md` § Agent Definitions for that case.)

- **Verbatim inlining** — kept as the substrate, but trimmed.
- **Summary + Read pointer** — rejected. Recreates the very drift hazard inlining was meant to prevent.
- **`@`-import shared file** — rejected. Untested in agent prompts.
- **Hybrid (accepted)** — keep verbatim inlining but trim cookbook to the load-bearing core. ~28 lines × 5 agents on ue-* trims; net ~50 lines saved with no behavior-change risk.

Frontmatter examples and deep-research playbook trims were deferred — frontmatter examples need careful YAML editing under structured-output dispatch examples (low risk per file, high per-error blast radius); playbooks have heavy procedural detail where condensing requires reviewer judgment, not mechanical edits.

## Memory is for cross-session pointers, not decision content

Decisions, frameworks, adoption strategies belong in plans/wikis/DRs. Memory entries exceeding a one-line pointer migrate body, leave pointer behind. Memory's value is the cross-session reachability — decisions become unfindable when buried in a memory entry that nobody knows to grep for.

## Stale doc references and plugin-bundled wiki placement

**Stale doc references: repoint when covered, create only when genuinely missing.** A dangling
`→ some-topic.md` citation is a repoint, not a license to scaffold a new file — check whether an
existing wiki already covers the topic before authoring a fresh one.

**Plugin-bundled wikis MUST live at `<plugin-root>/docs/wiki/<name>.md`.** Validate placement
with `sync-plugin-wiki.py`. A wiki authored outside that path is invisible to the plugin's live
`--plugin-dir` resolution and to OSS percolation.

## Source-of-truth doc placement

Plugin-scoped reference docs belong inside the plugin, not in project-scoped `docs/plans/`. The pattern shipped for `repo-research-internals.md` and `web-research-internals.md` resolves the broken cross-repo path in `2026-04-26-mcp-tool-agent-mapping-cleanup.md` (referenced as "source of truth" in 6 files but only resolving inside the example-game-repo source repo).

Audit-trail bug to watch: publish repos that lack `coordinator-safe-commit` silently sweep concurrent-session files under whatever subject the user types. Going forward: run `git diff --cached` before committing in any publish repo without the helper.

## Publish-repo helper distribution

The shim pattern: a 14-line `bin/safe-commit` that delegates to `$HOME/.claude/...` rather than copying the full helper + lib. No drift, low cost; makes the canonical pattern accessible from each repo without needing to remember the absolute path. Full helper copy was rejected as a drift hazard.

## Workflow-hygiene adjacencies

These aren't strictly CLAUDE.md trim rules but share the "don't pay re-cost on every session/run" framing:

- **Composed pipelines need chain invocation, not human memory.** A pipeline composed of two skills (A → B) needs a chain-invocation primitive — a calling skill that dispatches both in order, not a human-memory step. Otherwise B silently drops when the operator forgets. (queue E138)
- **Process theater on porting from prior extraction runs.** When "porting from a prior extraction run" is just lift-and-shift the prior output, don't re-run the extraction pipeline. Re-run is justified only when the input substrate has changed; otherwise lift sibling outputs. (queue E179)

## CLAUDE.md byte-limit forces wiki-first landing

CLAUDE.md has a **~39900-byte hard limit** (enforced by a PreToolUse hook). The limit is not a nuisance — it is structural enforcement of the "default fold target is wiki" rule. When the hook fires mid-edit because a behavioral default you're adding pushed CLAUDE.md over the ceiling, the correct response is to **re-author the addition wiki-first** (land the rule in the relevant wiki, leave a one-line greppable pointer in CLAUDE.md), NOT to trim unrelated content to make room. Trimming-to-fit treats the symptom; the byte-limit is telling you the content belongs in a wiki in the first place.

**Measure the headroom at plan time, not at failure.** A plan that will edit a size-gated CLAUDE.md must `wc -c` the current file *while planning* — the ceiling is close (a real instance sat at 39893/39900) and concurrent commits eat headroom between plan-write and execute. A near-full CLAUDE.md means the edit must be planned as a **compress-and-rewrite (net-neutral)**, never an append, and the executor must `wc -c <= 39900` post-edit (the `check-claude-md-size.py` hook blocks the Edit otherwise, mid-execute, where recovery is expensive). Grep the byte count as a pre-flight substrate fact, the same as any other constant a plan asserts.

## Cross-repo doctrine duplicated into project CLAUDE.md drifts from global canonical

When the same cross-repo (or any cross-cutting) doctrine appears both in the global `~/.claude/CLAUDE.md` and restated in a project-level CLAUDE.md, **suspect the project copy.** Duplicated doctrine drifts: the global canonical evolves (e.g. the cross-repo-memo single-surface ruling) while the project restatement lags, and an EM reading the stale local copy actions the old shape. Prefer a pointer (`→ global CLAUDE.md § X`) over a restatement. When you find a divergent local copy, treat it as the thing to fix, not the contract to follow.

## Verify structure-preserving compression via count invariants, not full-diff reading

When you compress a doc claiming to *preserve* structure (trim prose while keeping every header / headline / bullet / pointer), do NOT verify by reading the full diff — a full-diff read is high-effort and easy to skim past a silently-dropped pointer. Instead check **count invariants**: header count, headline count, bullet count, and outbound-pointer count before vs. after must match (or change by exactly the intended delta), plus a literal spot-check on a handful of the load-bearing lines. The count check is cheap, mechanical, and catches the dropped-section failure mode that diff-reading misses.

## Two-co-equal-rules framing beats rule-plus-carve-out when doctrine spans contexts

When a doctrine rule actually governs two distinct contexts (e.g. port-time cleanup vs. runtime discovery; sender-side vs. receiver-side), framing it as one primary rule with an exception/carve-out invites consumers to detect-then-silently-pick the wrong branch. Refactor into **two co-equal rules**, each naming its context explicitly, rather than a rule-plus-exception. (Caveat — `writing-plans.md` § preference-order: when the two rules are NOT actually co-equal but have an asymmetric preference, name the asymmetry — "registry-primary, sibling-fallback" — rather than pretending co-equality. Co-equal framing is right only when the two contexts are genuinely symmetric.)

## Durability test before pre-staging substrate for incoming work

Pre-staging substrate (directories, scaffold files, placeholder docs) in anticipation of incoming cross-repo work is short-window scaffolding — it rots the moment the incoming work's shape diverges from your guess, or never arrives. Apply the **durability test**: ship only cleanup/structure that has value *independent* of the incoming work. If the only justification for an artifact is "the incoming work will need it," it is speculative scaffolding, not durable cleanup. Build the durable half now; let the incoming work build the half that only it can specify.

## Writer-set fuzziness is a smell the artifact doesn't belong on disk

If you cannot crisply name *who writes* an on-disk artifact (one ceremony? several? any session?), that fuzziness is a signal the thing may not belong on disk as a persisted record at all. The discriminating principle is **receipt-on-disk vs. identity-via-query**: a receipt (a memo, a completion log entry, a handoff) has one writer and is a durable record; an identity (the set of active X, the current state of Y) is better derived by query at read time than persisted and kept in sync by an ambiguous writer set. When the writer set is fuzzy, prefer a live query (`bin/query-records`, a glob, a grep) over a hand-maintained on-disk list that every writer must remember to update. This is a decay-discipline principle, not a tool-boundary rule.

## `/distill` Phase 5 — Shard Apply-Agents by Volume, Not Function

*Source: project-rag-ue-addon. [universal]*

`/distill` Phase 5 "standard slicing" decomposes the apply pass by function (one agent per wiki file type, or one agent per phase of the distill pipeline). This is function-based and does not scale: a large repo with hundreds of wiki files will produce monolith agents that time out or degrade on context pressure.

**Rule.** Shard apply-agents by volume: split the wiki-file set into N chunks of roughly equal byte-count (or file-count), dispatch one apply-agent per chunk in parallel, then serialize their output via the EM commit pass. Function-based slicing is the right *design* dimension (which files an agent is allowed to touch); volume-based slicing is the right *dispatch* dimension (how many files any one agent sees). The two are orthogonal — a volume-sharded apply wave can still enforce function-scoped file permissions in the dispatch brief. Pairs with the HARD RULE in coordinator CLAUDE.md: small-remit-and-many beats large-remit-and-one.

## Compress-to-pointer requires a wiki-pointer integrity check first

Before compressing in-skill (or in-CLAUDE.md) doctrine prose down to a bare `→ docs/wiki/<name>.md § X` pointer, **verify the target wiki actually carries the rule you are about to delete.** Compression-to-pointer assumes the canonical content lives at the link destination — but if the rule was only ever stated inline (never folded to the wiki), the compression silently destroys it and leaves an orphaned pointer that resolves to a page that never mentions the rule. An orphaned pointer is *worse* than the original prose: the original at least carried the content; the pointer carries a promise the destination doesn't keep, and the next reader who follows it finds nothing.

**Rule.** The compress step is two-phase, never one: (1) confirm-or-fold — grep the target wiki for the rule; if absent, fold it there *first*; (2) only then compress the inline prose to the pointer. Pairs with § Verify structure-preserving compression via count invariants — the integrity check there is "did I drop a pointer"; the integrity check here is "does the pointer's target exist." (Source: coord-meta.)

## Consolidation method hierarchy — fold-to-wiki before dedup before prose-tightening

<!-- spec-backlink: 2026-07-22-23h55-residue / r6-008 -->

When trimming an oversized doc (CLAUDE.md-class or otherwise), work the methods in strict
priority order — don't reach for a later method before exhausting the earlier one:

1. **Fold to wiki, leave a pointer** — highest-yield, lowest-risk. Moves the bulk of the bytes
   out of the entry-point surface entirely; the pointer costs one line. This is the default move
   and should absorb most of a trim.
2. **Merge genuinely duplicated guidance** — only after confirming the redundancy is accidental,
   not deliberate. Some doc pairs restate the same rule on purpose (e.g. a floor invariant
   restated in both a project doctrine file and a linked wiki, so each is independently
   readable) — verify intent before merging, or the merge silently deletes a load-bearing
   restatement.
3. **Prose tightening** — only once (1) and (2) are exhausted. Treat any tightening pass that
   touches text a hook or tripwire pattern-matches on (e.g. a literal string a `grep`-based
   tripwire or `check-claude-md-size.py`-adjacent guard keys on) as a code change, not a wording
   change — verify the tripwire still fires post-edit.

This ordering pairs with § CLAUDE.md byte-limit forces wiki-first landing (method 1 above) and
§ Compress-to-pointer requires a wiki-pointer integrity check first (the verification gate
between methods 1 and 2 when the fold target may not yet carry the content).

## Wiki contradictions class — restated rules drift when only one instance is edited

<!-- spec-backlink: 2026-08-06-14h38 / c8-007 -->

A distinct defect class from plain duplication: the **same rule restated verbatim (or
near-verbatim) across multiple wiki files**, then only one restatement gets edited when the
rule changes. The siblings silently keep stating the old version. A 2026-07-27 sweep found
**23 instances of this class across 22 files** — the origin instance survived three review
passes before an Opus read caught it. It passed every gate this repo owns (review passes,
existing tripwires, CI) because none of them check cross-file consistency of a restated rule;
they check the file being edited in isolation.

**Why this evades review even at high scrutiny.** A reviewer reading the diff for file A sees
a coherent, correct change to file A. Nothing in that diff signals that file B or file C also
states the same rule and now disagrees with A. The defect is invisible at the diff level —
it only shows up when someone reads A and B back-to-back and notices they contradict, which is
exactly the kind of cross-file reasoning a line-scoped review pass does not do by default.

**Relationship to § Consolidation method hierarchy.** That section's method 2 ("merge
genuinely duplicated guidance") already warns that some restatements are deliberate — each
copy independently readable — and merging them can silently delete a load-bearing restatement.
This section is the mirror-image failure: when a restatement *is* deliberate and intended to
stay in sync, nothing enforces that sync. Deliberate multi-site restatement is a standing
maintenance liability unless something greps for drift.

**Mitigation direction (not yet built as of this nugget's landing):** a rule intentionally
restated in N places needs either (a) a single canonical statement + pointers from the rest
(preferred — collapses N maintenance sites to 1, per § Fold to wiki, leave a pointer), or (b)
if genuinely independent-readability is required, a lint/tripwire that flags when one
restatement changes and its siblings don't (not yet implemented — treat any wiki edit that
changes a rule known to be restated elsewhere as an occasion to check the siblings by hand
until such a tripwire exists).

## Folding a duplicated local-doctrine file into CLAUDE.md

<!-- spec-backlink: 2026-08-06-14h38 / c8-053 -->

A concrete instance of § Consolidation method hierarchy's method 2 (merge genuinely
duplicated guidance): a repo carried a separate local-doctrine file alongside `CLAUDE.md`
that substantially duplicated it across five topics. Folding the local-doctrine file into
`CLAUDE.md` collapsed the pair into a single repo-scoped boot file — one authoritative copy
per topic instead of two drifting restatements — and net-shrank the combined size
(34,174 B → 31,869 B), because the duplicated topics stopped paying twice.

**Signal to watch for.** Two boot-loaded files (both read into every session) that restate
the same topics are a merge candidate, not two independently-scoped surfaces — verify intent
per method 2 before merging (some pairs are deliberately restated for independent
readability), but a "local doctrine" file whose content is substantially the same five topics
as the project `CLAUDE.md` is the common case where merge is correct.

## Large-scale citation repoint gated on link-check, before and after

<!-- spec-backlink: 2026-08-06-14h38 / c8-055 -->

A large-scale doc-delete can repoint dozens of citations across plans, wikis, and decisions before
deleting the source file, gated on a link-check run both before and after the repoint. The raw
byte savings from the delete itself is often modest — that is not the payoff to measure.

**The real value is single-home coherence and citation-anchor consolidation, not byte count.**
When N files cite a doc that's being merged/deleted, treat the repoint as the primary work item
and the delete as its trailing step, not the reverse. Gating the link-check both pre- and
post-repoint catches two distinct failure modes: pre-check confirms you found every citation
before touching anything; post-check confirms the repoint didn't silently orphan a link (e.g. a
citation edited to point at a section header that doesn't exist at the destination).

**Rule.** For any large-scale doc consolidation touching double-digit-plus citation sites: (1)
enumerate every citation with a grep sweep, (2) run link-check pre-repoint as a baseline, (3)
repoint all citations, (4) run link-check post-repoint before deleting the source, (5) delete
only after both checks pass clean. Don't evaluate the effort by the deleted file's byte count —
evaluate it by whether every citation now resolves to a single coherent home.

## See also

- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — the helper this page references.
- `archive/handoffs/2026-04-28_222800_2fc815ec.md`, `2026-04-28_225450_5e6c9130.md` — origin handoffs.

## Decision Records

**DBT-DR-001 — Hybrid trim over `@`-import for subagent prompts**

*Problem:* ue-* agent prompts carried verbatim cookbook content. Could a link reference, summary+pointer, or `@`-import substitute?

*Decision:* Hybrid. Keep verbatim inlining (per "Agent Prompts Are Self-Contained") but trim cookbook to the load-bearing core. Frontmatter examples + deep-research playbook trims deferred — they need careful YAML editing or reviewer judgment respectively.

*Alternatives considered:* Bare link reference (rejected — the Staff Engineer P8, subagents see only the dispatch prompt). Summary + Read pointer (rejected — recreates the drift hazard). `@`-import (rejected — untested in agent prompts).

**DBT-DR-002 — `/schedule` is for remote CCR agents, not local file tasks**

*Problem:* Should the 14-day cookbook recheck use `/schedule`?

*Decision:* No. `/schedule` is for remote CCR agents that have no local file access. Pivoted to a local marker file (`tasks/cookbook-recheck-due-YYYY-MM-DD.md`) — durable, git-tracked, contains the full procedure, survives session compaction.
