# Scout and Dispatch Discipline

Extensions to CLAUDE.md § Scouts and Disk-First Verification and § Subagent Dispatch. The EM's leverage comes from orchestrating delegates, not from absorbing their output back into its own context. This wiki collects the rogue-write, scout-commit, EM-as-absorber, path-translation, and namespace-prefix discipline that keeps that leverage intact.

## When this applies

Any time the EM dispatches a scout or subagent — Tier-4 investigation, fan-out enrichment, structured-output Haiku scouts, Windows-host native-tool wrappers, and any dispatch that writes new files under iterator-style directories.

## Rules

### Scout output discipline

- **Haiku scouts in structured-output mode MUST write only to the declared output path — they MUST NOT `git add` / `git commit`.** Scout-side commits race with the EM-side post-dispatch commit and corrupt the index. The dispatch contract is: write to `<output-path>`, return `DONE: <path>`. Commits are the EM's job. [E113]

- **Quarantine rogue subagent output BEFORE inspecting.** If a subagent writes outside its declared scope (file paths not in the dispatch's `scope:` block), copy the rogue output to `tasks/quarantine/<run-id>/`, then revert the working tree, then read from quarantine. Out-of-scope writes contaminate diff-based verification — every subsequent `git diff` mixes legitimate work with rogue edits, and post-hoc filtering is unreliable once a sibling commit lands on the branch. [E116]

- **Verify scout "X is missing" / "X is present" claims via cheapest probe before acting.** Research-scout briefs frequently report absence/presence of a symbol, file, or surface. Treat as hypothesis: confirm with a one-shot `Grep` or `Read` against the cited path before the finding propagates into a plan, deletion list, or follow-up dispatch. False-absence claims are common when the scout's read window missed the file; false-presence claims appear when the scout paraphrases an adjacent symbol as the queried one.

- **Default to named Haiku for any ≥3 parallel disk-first fan-out.** Haiku TEXT-ONLY hallucination rate is ~30% on 3-way parallel disk-first deliverables even with inlined recovery preamble (empirical: `/distill` 2026-05-14 first wave — 1 of 3 hallucinated, 1 partial). Named agents (`Agent({name: "haiku-batch1"})`) enable `SendMessage` resume on failure; anonymous parallel Haiku forces redispatch-from-scratch. Use named Haiku by default on any ≥3 parallel disk-first fan-out.

- **Stub-inventory recovery for idle Haiku scouts in long pipelines.** When a Pipeline B / Agent Teams Haiku scout idles or returns TEXT-ONLY hallucination instead of the expected on-disk deliverable, do NOT re-dispatch from scratch. Walk the expected output paths and write *stub inventories* enumerating what the scout was asked to find — even an empty stub with the headers in place lets the downstream synthesizer proceed without re-billing the whole upstream wave. Re-dispatch is a last resort after a single resume attempt via `SendMessage`.

- **Scout reachability claims require function-envelope evidence, not block-local snippets.** When a scout cites "the literal block at line N has no orphan check" or "this branch never executes," read the enclosing function envelope before trusting the claim. A guard one level up — early-return, caller-side wrapper, decorator — frequently invalidates the block-local reachability conclusion. Require scout briefs to quote the function signature + the conditional gate, not just the literal lines.

- **Peer-repo scouts during onboarding.** When a repo's README names sibling, upstream, or downstream repos, dispatch parallel Explore scouts against them BEFORE drafting the tracker or workstream specs. Cross-repo schema-vendoring contracts, consumer entrypoints, and ship-state of cited PRs only surface from the peer side. Cite peer `file:line` evidence in workstream specs; prose descriptions from the sending repo are insufficient.

- **Fix scout brief at instance #3, not per-directory classifier READMEs.** When scouts misread the same structural shape in 3 separate dispatches, fix the scout brief (e.g. the workstream-classification heuristic in `/workstream-start`) — do NOT write per-directory README files to correct the misread. Per-dir corrections decay in isolation and do not propagate to future dispatches; brief corrections compound across every future scout run.

- **Readiness / defer-recommendation scouts must name the unverified premise behind every defer.** "Defer X to follow-up" is a hypothesis about scope, not a verdict. The scout brief must surface each defer as a question with the premise inline: *"Defer Y assuming Z (unverified) — confirm before acting."* Defers without named premises age into mystery cuts; the next session re-investigates from zero.

### Worktree-isolated subagent caveats

- **Worktree-isolated subagents honor literal absolute Write paths.** A scout dispatched with worktree isolation that writes to an absolute path (e.g. `C:/Users/.../scratch/result.json`) lands the file in the main project tree, not the worktree. Either pass relative paths or expect main-tree writes; verify with `ls` post-completion. Polling the worktree dir for a file the scout wrote to an absolute path is a deadlock waiting to happen.

- **Resumed worktree agents can re-fire post-completion with hallucinated TEXT-ONLY runs.** Disk-first verification is load-bearing — a "DONE" reply from a resumed worktree agent does NOT mean the file was written this run. Always `ls -la`/size before accepting `DONE` on a resumed run. The hallucination signature is identical to the cold TEXT-ONLY case but appears in agents that wrote successfully on a prior run before being resumed.

- **Bound scout briefs by target output size, not just record count.** Sonnet scouts producing dense per-entry inline content can hit the 32k output cap before the final `Write`, leaving an empty file and a `DONE` reply. Specify the expected output shape in token-size terms — e.g. "≤30 records, one-line summaries, target ~5KB total" — and verify file size, not just existence, on the EM side. The failure mode is silent: scout reports `DONE`, disk has the path, file is empty or truncated. (2026-05-18, self.)

- **Sonnet/Haiku scouts on bounded-enumeration tasks hallucinate IDs not in the input list** — distinct from TEXT-ONLY hallucination. When the brief is "verify each of items [A, B, C, D]" the scout may report on items [A, B, X, Y] where X/Y were not in the input. EM-direct crossover threshold for verifier tasks may be N>50 rather than the usual N>10 — the cost of post-hoc audit against the original list exceeds the dispatch savings below that bound. Mitigation: brief MUST quote the input list verbatim in a `## Items to verify` block and instruct the scout to copy each ID from that block into its output, not regenerate from memory. (2026-05-18, project-rag-ue-addon.)

### Agent fit — tool surface beats description prose

- **Agent description prose describes calibration, not a hard capability fence.** Reading a domain agent's description as a contract for "what it can do" produces routing errors when the description trails the tool surface. The load-bearing fit check is the agent's actual `tools:` list (and, for MCP-backed agents, the MCP server's tool inventory). Description prose is useful for prioritization and tone-setting; routing decisions must Read the tool list. When in doubt, the central routing table — not domain agent prose — owns the capability map.

### Cross-task dependencies in multi-step briefs

- **Dispatch-brief task ordering must be explicit when later tasks reference earlier-task outputs.** Briefs that say "do A and B" without naming the dependency invite parallel-dispatch attempts that race on a shared output. Sequence tasks explicitly; name the output file each later task depends on; for pipeline briefs, write the dependency graph at the top: `Task 2 reads <output of Task 1>; do not start until Task 1 reports DONE`. Same rule appears in CLAUDE.md § Pre-Dispatch Verification — this wiki carries the canonical worked pattern.

### Investigation output template — separate findings from recommendations

- **Readiness scouts: name the unverified premise behind every defer recommendation.** When a readiness scout returns PARTIAL and proposes deferring a deliverable (e.g. "ship as FALLBACK, defer ACCEPT to fork-plan"), the defer rationale carries an unverified premise the scout couldn't probe — typically a dependency availability or build-cost assumption. Surface that premise as an explicit question so the PM can challenge it with domain knowledge the scout lacks. A scout that bakes an unverified premise into a recommendation hides the decision the PM actually needs to make. *(Canonical: tc-1 readiness scout deferred to FALLBACK based on assumed source-only distribution; PM had UE source path and GitHub Releases knowledge; 30 min of follow-up probing flipped the verdict to ACCEPT-with-version-pin.)*

- **Investigation scouts must separate FINDINGS (what is) from RECOMMENDATIONS (what to do).** The CLAUDE.md out-of-scope block ("Do NOT modify files, commit, or push. Read-only.") prevents the scout from acting, but does not prevent the scout from emitting recommendation-shaped text the EM then reads as authority. Require the brief's output template to carry the two sections under explicit headings — `## Findings` and `## Recommendations` — so the EM can act on the former and weigh the latter as opinion, not contract.

### EM-as-orchestrator, not absorber

- **Infrastructure-failure recovery is redispatch territory, not EM-absorbs-the-work.** When a subagent fails on a transient cause — subagent timeout, billing gate, 1M-tail error, runtime stall — the right move is to redispatch (or `SendMessage` to resume, per CLAUDE.md § Verifying Executor Output). The EM's job is orchestration; absorbing mechanical work to "just finish it" bloats EM context, breaks the leverage model, and silently shifts cost from cheap delegate tokens onto the EM's scarce context budget. If the work is genuinely small enough that dispatch overhead exceeds the work itself, that judgment belongs at plan time, not as a post-failure rescue. [E111]

### Namespace prefix audit before scaffolding

- **Before adding a new top-level namespace under an iterator-style directory (`tasks/`, `agents/`, `skills/`), grep existing prefix conventions and reuse.** Speculative-new namespaces fragment greppability for no gain — the next session looking for "the X stuff" greps the established prefix, misses the new namespace, and either duplicates work or builds on stale assumptions. If the new work is conceptually a sibling of an existing prefix, extend the prefix; only branch a new namespace when a grep-and-Read pass confirms genuine non-overlap. [E39]

### Windows path translation in dispatch context

- **Native Windows executables called from MSYS / Git Bash need path translation.** Use `C:\path` form, not `/c/path`. The MSYS shell will translate `/c/...` arguments for some calls and silently pass-through for others, depending on argument position and tool — the failure mode is `file not found` against a path that exists. Fix: use `cygpath -w "$path"` to convert before the call, or set `MSYS_NO_PATHCONV=1` for the affected invocation. Dispatches that hand a path to a scout running a native exe (e.g. UE-Cmd, MSBuild, native git on Windows) carry this hazard. [E115]

## Related

## find-and-patch waves — separate fact-finding from fix-application

For find-and-patch waves, separate fact-finding from fix-application — do not dispatch a single Sonnet executor to do both. Scout wave: dispatcher produces an inventory file on disk (paths, line numbers, current state). Fix wave: each executor reads the inventory as its brief substrate and applies fixes to its slice. Combining both in one agent produces lower-quality inventories, misses sites, and makes the fix wave harder to recover when an executor crashes mid-way. Apply: any "find all X and fix them" work → dedicate wave 1 to inventory-on-disk, wave 2 to fix-from-inventory.

- CLAUDE.md § Scouts and Disk-First Verification — the parent doctrine on disk-as-signal, TEXT-ONLY recovery, write fallback.
- CLAUDE.md § Subagent Dispatch — Haiku billing-gate carve-out, 1M-context inheritance, out-of-scope block requirement, destructive-action prohibition for autonomous-write skills.
- `tiered-context-loading.md` — Tier-4 dispatch rationale rule and exceptions.
- `scoped-safety-commits.md` — how EM-side commits coexist with sibling work on a shared branch (related: scout-side commits violate this).
- `pre-dispatch-verification.md` — substrate verification before authoring a dispatch brief.
