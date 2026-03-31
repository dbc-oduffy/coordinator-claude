# Changelog

All notable changes to coordinator-claude are documented here.

## [1.1.0] — 2026-03-31

### Remember Plugin (new)
- **Temporal memory system.** New `remember` plugin adds session-scoped memory persistence. PostToolUse hooks capture key actions as they happen; SessionStart hooks inject the last N days of session history into context automatically.
- **Haiku-powered compression pipeline.** Raw session events are compressed by `claude-haiku` into structured NDC (Notable Decisions & Changes) summaries, then consolidated into daily memory files. Designed for minimal token overhead at session start.
- **Coordinator integration.** `session-end`, `update-docs`, and `workday-complete` commands now include a `/remember` step to persist session state before closing out.
- **Marketplace registration.** Plugin is registered in `marketplace.json` for one-command install.

### Deep Research — Pipeline A v2.2 (Internet Research)
- **Iterative deepening.** After Team 1 completes, the sweep agent produces a structured gap report (YAML severity scores + Gap Targets table). If significant gaps remain, the EM dispatches a smaller Team 2 (1-3 gap-specialists + merge-mode sweep) for targeted follow-up. Hard cap at 2 passes. `--shallow` flag skips the decision gate for single-pass behavior.
- **Structured gap reporting.** Sweep's gap report now includes machine-readable YAML front-matter (`deepening_recommended`, `coverage_score`, `high_severity_gaps`) and a Gap Targets table with severity, type, and suggested queries.
- **Gap-specialist prompt template.** New specialist variant for Team 2 with Prior Findings context, tighter timing (3 min floor / 8 min ceiling), D-prefixed claim IDs, and `resolves_gap` field linking claims to gap targets.
- **Merge-mode sweep.** Team 2's sweep produces a delta document (`deepening-delta.md`) instead of a full replacement. The EM merges the delta seamlessly into Team 1's synthesis.

### Deep Research — Pipeline A v2.1 (Internet Research)
- **Consolidator eliminated.** Specialists now report directly to the sweep agent, freeing one agent slot and reducing pipeline latency.
- **Adversarial specialist interaction.** Specialists are expected to challenge each other's claims via `SendMessage`. A resolution protocol is defined for contested findings.
- **Structured claims output.** Specialists produce dual output: `{letter}-claims.json` (machine-readable, typed claims with confidence scores) and `{letter}-summary.md` (human-readable).
- **Sweep phased discipline.** Sweep operates in three explicit phases: Assess (inventory specialist claims), Fill (targeted gap research), Frame (executive summary + conclusion).
- **EM scoping checklist.** Sub-question quality gates from published multi-agent research ensure scoping produces decomposable, answerable questions.

### Deep Research — Pipeline B v2.1 (Repo Research)
- **Structural orientation pass.** EM performs a codebase orientation (entry points, key directories, architecture pattern) before scoping, so focus questions are grounded in actual structure.
- **Execution-trace framing.** Specialists frame analysis around execution paths rather than file-by-file inventory, producing more actionable findings.
- **`file:line` citation enforcement.** Specialist prompts now require `file:line` citations for all claims, making findings directly navigable.
- **LLM context file discovery.** Scoping phase now surfaces `CONTEXT.md`, `CLAUDE.md`, `.cursorrules`, and similar files as high-priority reads for specialists.
- **Independent-analysis-first comparison mode.** When comparing two repos, specialists analyze each independently before cross-referencing to avoid anchoring bias.

### Deep Research — Pipeline B v2.2 (Repo Research)
- **`--deeper` mode.** EM generates a dependency-weighted repomap during scoping (Phase 1.5). Language-aware import extraction (Python, JS/TS, Go, Rust, C/C++, Java) with cross-reference counting and tiered output (Tier 1/2/3). Specialists read repomap before inventories for prioritization. Graceful fallback if import graph is thin.
- **`--deepest` mode.** Two-wave pipeline: Wave 1 is the standard 7-agent team (unchanged), Wave 2 dispatches a Sonnet atlas subagent after synthesis. Produces 4 architecture atlas artifacts: file index, system map, connectivity matrix, and architecture summary. `--deepest` implies `--deeper`. Atlas failure is non-blocking.

### NotebookLM — Pipeline D v2
- **Strategist elimination.** Removed the separate Opus strategist agent. EM now scopes directly with baked-in NLM best practices, saving one agent dispatch and ~2 minutes.
- **NLM-adapted claims schema.** Workers now output structured `{letter}-claims.json` with NLM-specific fields (`transcription_suspect`, `source_type`, `nlm_citation`) alongside `{letter}-summary.md`.
- **Synthesizer → sweep rename.** Final agent renamed from "synthesizer" to "sweep" to match Pipeline A naming and reflect its actual role (adversarial coverage check + gap-filling, not just synthesis).
- **Notebook preservation (default).** Notebooks are now kept after research runs by default — they represent significant ingestion work and are valuable for follow-up queries. New `--cleanup` flag opts in to deletion.

### Developer Ergonomics
- **Plugin command naming cleanup.** Removed redundant plugin-name prefixes from all commands: `deep-research-web.md` → `web.md`, `deep-research-repo.md` → `repo.md`, `notebooklm-research.md` → `research.md`, etc. 26 files updated, all cross-references synced.

## [1.0.0] — 2026-03-28

Initial public release. 8 plugins, 24 agents, 37 skills.

