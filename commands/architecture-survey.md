---
name: architecture-survey
description: "Build or refresh the architecture atlas via scout, analyst, synth."
allowed-tools: ["Agent", "Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: "[--refresh]"
---

# Architecture Survey — Deep System Discovery

Builds/refreshes the architecture atlas in `docs/architecture/`. Not for weekly spot-checks
(`architecture-audit`), daily reviews (`code-health`), or one-off investigation. Occupies
~25-90 min of context — not background work. Purpose, layout, rationale, retired mechanics: wiki
(cited by name only — no path).

## Arguments

`--refresh` → refresh mode. No atlas + no flag → bootstrap. Atlas exists, no flag → ask the PM.
Announce the resolved mode before starting.

## Phase 0: Scope (YOU)

1. Read `DIRECTORY.md` if present; proceed silently if absent.
2. Discriminate scope from PM phrasing — targeted single-system / atlas-wide refresh /
   bootstrap. Classification rules: wiki.
3. Derive system boundaries and the Workflow's `censusBuckets`. Chunking rules: wiki.
4. Refresh: mark churned/stable systems from `systems-index.md`'s `Last mapped` dates.
5. Select scale tier from `counts.bucketed_total`. Threshold table: wiki.
6. Generate run ID, create the scratch dir.

Emergent-set/chunk-K detection is engine-owned. An escalation flag in the Workflow's returned
manifest → surface a re-bootstrap recommendation to the PM in the Phase 4 report; deciding it is
the PM's call, not yours.

## Phase 0.5-3: Invoke the Workflow

Invoke `coordinator/pipelines/deep-architecture-survey/survey.workflow.js` — its own header
comment documents the input shape; read it there, not a hand-copy here. It owns the whole
extraction-through-synthesis pipeline end to end — never hand-orchestrate it. Resume a
rate-limit wipe with `resumeFromRunId`. Read the returned manifest; it writes every atlas
artifact. Mechanism detail: wiki.

## Phase 4: Integration and Report (YOU)

Out of scope for every agent here: `gh pr create/merge`, `git push origin main`,
`gh release create`, any `git commit` to `main` — surface a merge question to `/merge-to-main`.

1. Verify completeness (every system has a page + index row, atlas-wide artifacts present,
   frontmatter complete).
2. RAG drift (RAG-present only): `project_subsystem_profile` vs. `systems-index.md`.
3. Flag any `last_mapped` >90 days old as narrative-drift risk.
4. Write `Last full audit` in `state/health-ledger.md` — full passes only, never the targeted
   path.
5. Atomic commit, two scoped calls, never `git add -A`:
   `git add -- docs/architecture/ state/health-ledger.md`
   `git commit -m "deep-architecture-survey: [first run|refresh] — [N] systems mapped; Last full audit bumped" -- docs/architecture/ state/health-ledger.md`
6. Rotation target:
   `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/query-completions" --since "30d" --where "nature=roadmap" --format json`
   Scoring rules: wiki.
7. Report to PM:
   ```markdown
   ## Architecture Survey Complete
   **Mode:** [first run / refresh]
   **Systems mapped:** [N] ([list])
   **Key findings:** [coupling hotspots, boundary patterns, notable design choices]
   **RAG drift:** [N mismatches: list / none detected / RAG absent — check skipped]
   **Narrative drift risk:** [systems > 90 days / all current]
   **Suggested rotation target:** [system name] (highest connectivity / oldest mapping)
   **Atlas location:** docs/architecture/
   **cartography_used:** [true / false]
   **In-scope file count:** [N] (from `counts.bucketed_total`; N/A on agentic fallback)
   **oversized_signal:** [unavailable — REQUIRED when cartography_used is true / N/A on fallback]
   ```
8. Clean scratch — only after commit succeeds:
   `rm -rf state/scratch/deep-architecture-survey/{run-id}/`.

Failure modes and every retired-mechanism detail: wiki.
