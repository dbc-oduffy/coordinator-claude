# Changelog

All notable changes to coordinator-claude are documented here.

## [1.1.0] — 2026-03-31

### Deep Research — Pipeline A v2.2 (Internet Research)
- **Iterative deepening.** After Team 1 completes, the sweep agent produces a structured gap report (YAML severity scores + Gap Targets table). If significant gaps remain, the EM dispatches a smaller Team 2 (1-3 gap-specialists + merge-mode sweep) for targeted follow-up. Hard cap at 2 passes. `--shallow` flag skips the decision gate for single-pass behavior.
- **Structured gap reporting.** Sweep's gap report now includes machine-readable YAML front-matter (`deepening_recommended`, `coverage_score`, `high_severity_gaps`) and a Gap Targets table with severity, type, and suggested queries.
- **Gap-specialist prompt template.** New specialist variant for Team 2 with Prior Findings context, tighter timing (3 min floor / 8 min ceiling), D-prefixed claim IDs, and `resolves_gap` field linking claims to gap targets.
- **Merge-mode sweep.** Team 2's sweep produces a delta document (`deepening-delta.md`) instead of a full replacement. The EM merges the delta seamlessly into Team 1's synthesis.

### Deep Research — Pipeline B (Repo Research)
- **`--deeper` mode.** EM generates a dependency-weighted repomap during scoping (Phase 1.5). Language-aware import extraction (Python, JS/TS, Go, Rust, C/C++, Java) with cross-reference counting and tiered output (Tier 1/2/3). Specialists read repomap before inventories for prioritization. Graceful fallback if import graph is thin.
- **`--deepest` mode.** Two-wave pipeline: Wave 1 is the standard 7-agent team (unchanged), Wave 2 dispatches a Sonnet atlas subagent after synthesis. Produces 4 architecture atlas artifacts: file index, system map, connectivity matrix, and architecture summary. `--deepest` implies `--deeper`. Atlas failure is non-blocking.

### NotebookLM — Pipeline D v2
- **Strategist elimination.** Removed the separate Opus strategist agent. EM now scopes directly with baked-in NLM best practices, saving one agent dispatch and ~2 minutes.
- **NLM-adapted claims schema.** Workers now output structured `{letter}-claims.json` with NLM-specific fields (`transcription_suspect`, `source_type`, `nlm_citation`) alongside `{letter}-summary.md`.
- **Synthesizer → sweep rename.** Final agent renamed from "synthesizer" to "sweep" to match Pipeline A naming and reflect its actual role (adversarial coverage check + gap-filling, not just synthesis).
- **Notebook preservation (default).** Notebooks are now kept after research runs by default — they represent significant ingestion work and are valuable for follow-up queries. New `--cleanup` flag opts in to deletion.

## [1.0.0] — 2026-03-28

Initial public release. 8 plugins, 24 agents, 37 skills.
