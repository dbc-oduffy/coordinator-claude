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
7. Run the consume-gate script by absolute path through its interpreter, never a bareword and
   never through the settings home — `coordinator/bin/` in THIS repo carries no settings-home
   forwarder (`snippets/resolve-coordinator-bin.md` rung 3: never point a no-forwarder CLI at the
   settings home), so resolve it against the plugin root:
   `python <plugin-root>/coordinator/bin/survey-consume-gate.py`, feeding it the JSON config
   (`repo_root`, `claude_klabauter_root`, `run_id`, `census_buckets`, `mode`, `since`, `system_dirs`,
   `excluded_dirs`) on stdin. Capture its stdout verbatim and pass it straight into the
   Workflow's `INPUT.consumeGate` — a pure pass-through, do not branch on `ok`/
   `declined_reason` here. When the gate declines (or its output is absent/malformed), the
   Workflow falls back to the agentic census wave at a known higher cost — a designed path, not
   a break, when it shows up in a fallback log.

Emergent-set/chunk-K detection is engine-owned. An escalation flag in the Workflow's returned
manifest → surface a re-bootstrap recommendation to the PM in the Phase 5 report; deciding it is
the PM's call, not yours.

## Phase 0.5-3: Invoke the Workflow

Invoke `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-architecture-survey/survey.workflow.js`, passing
`INPUT.consumeGate` from Phase 0's step 7 — its own header comment documents the full input
shape; read it there, not a hand-copy here. It owns the whole extraction-through-synthesis
pipeline end to end — never hand-orchestrate it. Resume a rate-limit wipe with
`resumeFromRunId`. Read the returned manifest; it writes every atlas artifact. Mechanism
detail: wiki.

## Phase 4: Accuracy and Clarity Review (YOU)

EM-side, after the Workflow returns — its runtime has no filesystem/subprocess primitive, so
neither stage can run inside it. Why: wiki.

1. Run `python <plugin-root>/coordinator/bin/atlas-citation-check.py` over the emitted atlas
   pages. Record exit status and every listed unresolvable citation for Phase 5's report — a
   non-zero exit means the run does not report clean.
2. Dispatch `atlas-clarity-reviewer` once per page (parallel, never batched). Collect verdicts to
   the sidecar.

## Phase 5: Integration and Report (YOU)

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
6. Rotation target (Shape W, `${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`):
   `& "$env:COORDINATOR_SETTINGS_HOME\bin\query-completions.exe" --since "30d" --where "nature=roadmap" --format json`
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
   **atlas-citation-check:** [exit 0 clean / exit N — unresolvable citations listed]
   **Clarity review:** [N pages reviewed; flagged verdicts / none]
   ```
8. Clean scratch — only after commit succeeds:
   `rm -rf state/scratch/deep-architecture-survey/{run-id}/`.

Failure modes and every retired-mechanism detail: wiki.
