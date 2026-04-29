# Scratch Path Convention

Pipelines that dispatch sub-agents use scratch directories for intermediate output.

## Convention

```
tasks/scratch/{pipeline-name}/{run-id}/
```

- **`pipeline-name`**: matches the pipeline directory name (e.g., `weekly-architecture-audit`, `bug-sweep`)
- **`run-id`**: format `YYYY-MM-DD-HHhMM` (e.g., `2026-03-19-10h00`)
- **Lifecycle**: created at pipeline start, deleted after all phases complete successfully
- **Recovery**: if a phase fails mid-pipeline, scratch files from completed phases are preserved for re-dispatch

## Current Users

- `weekly-architecture-audit` — Haiku inventory + Sonnet analysis scratch
- `bug-sweep` — Sonnet semantic analysis + test runner scratch
- `artifact-distillation` — Haiku scanner + QG scratch, Sonnet synthesis scratch, Opus assembly scratch
- `deep-research` — managed by the `deep-research` plugin. Relay pattern scratch (decisions.md, dispatch-manifest.md, prompts/).
- `deep-research-teams` — managed by the `deep-research` plugin. Agent Teams scratch (specialist findings, synthesis).
- `deep-architecture-audit` — Haiku function inventory + Sonnet system analysis scratch
