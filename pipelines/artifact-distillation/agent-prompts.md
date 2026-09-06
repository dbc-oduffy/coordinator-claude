# Artifact Distillation — Agent Prompt Templates

Per-phase prompt files. See `PIPELINE.md` for phase ordering and dispatch semantics.

Eleven templates: **Phase 1** (Haiku scanner), **Phase 1.5** (Haiku quality gate), **Clustering** (Haiku, conditional), **Phase 2** (Sonnet synthesizer), **Phase 2.5** (Sonnet judgment-mining), **Phase 3a** (Sonnet contradiction detection), **Phase 3b** (Sonnet decision-record dedup), **Phase 3d** (Sonnet deletion manifest), **Phase 3d specialist assembler** (Sonnet, converts Cross-Repo Archive Specialist Branch output into Phase 3d rows), **Phase 3d-fanout** (high-volume workflow fanout, N>500), **Phase 3-Esc** (Opus contradiction resolution + Sonnet fidelity-check — escalation path only).

**Retired:** Phase 2.7-QG (Haiku coverage-gate wave) — folded into a mechanical in-Workflow set-diff, see `commands/distill.md § Coverage gate` and `PIPELINE.md § Coverage Gate`. No agent-prompt template remains for it.

Phase 3c (DIRECTORY_GUIDE assembly) and Phase 5 (apply agents A/B/C) are coordinator-mechanical and documented in `PIPELINE.md`, not as dispatchable prompt templates.

- [Phase 1 — Haiku artifact scanner](agent-prompts/phase-1.md)
- [Phase 1.5 — Haiku quality gate](agent-prompts/phase-1-5.md)
- [Clustering — Haiku regrouping](agent-prompts/clustering.md)
- [Phase 2 — Sonnet knowledge synthesis](agent-prompts/phase-2.md)
- [Phase 2.5 — Judgment mining (dispatch prompt)](agent-prompts/phase-2-5.md)
- [Phase 2.5 — Judgment mining (full procedure)](agent-prompts/phase-2-5-judgment-mining.md)
- [Phase 3a — Contradiction detection](agent-prompts/phase-3a.md)
- [Phase 3b — Decision-record dedup](agent-prompts/phase-3b.md)
- [Phase 3d — Deletion manifest](agent-prompts/phase-3d.md)
- [Phase 3d specialist assembler — Cross-Repo Archive Specialist Branch → Phase 3d rows](agent-prompts/phase-3d-specialist-assembler.md)
- [Phase 3d — Workflow-fanout-per-cluster (high-volume mode, N>500)](agent-prompts/phase-3d-fanout.md)
- [Phase 3-Esc — Opus contradiction resolution + Sonnet fidelity-check](agent-prompts/phase-3-esc.md)
