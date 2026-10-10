# Deep Research — Mechanical vs Judgment, per Leg

> Classification of every leg of the four deep-research pipelines: web (A), repo (B), structured (C), NotebookLM (D). Unit = the **leg**, never the agent: an agent is usually both. Rows are derived from the prompt templates under `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/` (16 templates; Code-Comparison Mode is not one of the four pipelines and is not classified). Citations are `file:line` inside the template named in the row.

**Mechanical** = output is a deterministic function of inputs; a script could produce it and the model adds only transcription risk. **Judgment** = output depends on weighing evidence, resolving conflict, or framing. **Hybrid** = a judgment leg with a mechanical sub-step that can be split out.

**Recommendation** vocabulary: `port` (move to engine/script), `hybrid` (split the mechanical sub-step out, keep the judgment leg), `refute` (stays a model leg; classification plus evidence is the whole answer, so its losing-options cell is empty by design).

## Legs

| # | Leg | Pipeline | Class | Evidence | Recommendation | Why the losing options lost |
|---|-----|----------|-------|----------|----------------|-----------------------------|
| 1 | Source scout | A web | judgment (cheap tier) | `scout-prompt-template.md:32-54` — WebSearch per query, WebFetch accessibility/SEO-farm check, quality filter | refute | |
| 2 | Specialist research | A web | judgment | `specialist-prompt-template.md:50-141` — deep-read, adversarial search, peer cross-pollination, converge | refute | |
| 3 | Fidelity relay | A web | judgment | `specialist-prompt-template.md:151-203` — misrepresentation check with bloat-guard discriminator | refute | |
| 4 | Gap specialist (Team 2) | A web | judgment | `gap-specialist-prompt-template.md:64-102` — targeted research on one gap target | refute | |
| 5 | Sweep / frame | A web | judgment | no template; `web-driver.md:12` — Opus reads specialist outputs, fills negative space, frames document | refute | |
| 6 | Claims merge | A web | mechanical | `web-driver.md:193-195` — `claims-emit` writes the durable pair | **ported** (live) | |
| 7 | Source scout | B repo | hybrid | inventory `repo-scout-prompt-template.md:99-117` is per-file structured extraction; comparison-file match `:31-44` is self-described "mechanical pattern-matching" | owned by the repo-scout verdict (row 24) | not derived here |
| 8 | Holistic survey | B repo | judgment | `repo-survey-prompt-template.md:31-54` — read broadly, write a senior-engineer assessment | refute | |
| 9 | Atlas sketch | B repo | mechanical | `repo-atlas-sketch-prompt-template.md:60,64-68,139-146` — "mechanical work from scout data"; file index, system map, connectivity matrix built only from inventories and repomap | hybrid: file index and connectivity counts are scriptable, the one-line system purposes are not | A full port loses the per-system purpose lines, which have no source other than the scout prose; leaving it all to a model keeps a transcription-risk leg on a 5-minute ceiling |
| 10 | Repo specialist | B repo | judgment | `repo-specialist-prompt-template.md:152-217` — assessment and optional comparison with file:line evidence | refute | |
| 11 | Fidelity relay | B repo | judgment | `repo-specialist-prompt-template.md:256-310` | refute | |
| 12 | Synthesizer | B repo | judgment | `repo-synthesizer-prompt-template.md:70-110,146-165` — cross-chunk assessment, tiered gap analysis | refute | |
| 13 | Claims merge | B repo | mechanical | `repo-driver.md:533-535` — `claims-emit`; `repo-synthesizer-prompt-template.md:305-318` forbids reporting `ran_at` | **ported** (live) | |
| 14 | Atlas refinement | B repo | hybrid | `repo-atlas-prompt-template.md:81-100` — bidirectional flow cross-validation is mechanical comparison; `:103-232` architecture summary needs specialist-level reading | hybrid: port the one-sided-connection flagging, keep the summary | Porting the whole leg drops the architecture summary (4th artifact); keeping it all as prose leaves a diff-shaped check to a model |
| 15 | Topic scout | C structured | judgment (cheap tier) | `structured-scout-prompt-template.md:29-47` — maps each finding to schema fields | refute | |
| 16 | Verifier | C structured | judgment | `structured-verifier-prompt-template.md:63-131` — verify against primary sources, schema field table, gate self-check | refute | |
| 17 | Synthesizer | C structured | hybrid | judgment: reconciliation `structured-synthesizer-prompt-template.md:73-82`; mechanical: change-type merge rules `:190-208` and gate-rule self-validation `:83-90` | hybrid: port merge-rule application and gate validation, keep contested-field resolution | Full port cannot resolve CONTESTED fields (evidence weighing, `:76-80`); no port leaves a closed rule table executed by a model |
| 18 | Claims merge | C structured | mechanical | `structured-driver.md:394` — `claims-emit` | **ported** (live) | |
| 19 | Scout | D NotebookLM | judgment (cheap tier) | `notebooklm/scout-prompt-template.md:28-48` — WebSearch plus accessibility check per notebook | refute | |
| 20 | Worker | D NotebookLM | hybrid | notebook create/tag/ingest/verify are scripted tool calls `notebooklm/worker-prompt-template.md:41-60`; claim decomposition `:61-87` is judgment | refute for now | Ingestion is MCP-tool-bound and runs through the notebooklm MCP surface, which an engine port cannot call without a new bridge; the cost of that bridge is not justified by a mechanical leg this small |
| 21 | Sweep | D NotebookLM | judgment | `notebooklm/sweep-prompt-template.md:41-44` — assess, resolve cross-notebook contradictions, frame | refute | |
| 22 | Claims merge | D NotebookLM | mechanical | `notebooklm/sweep-prompt-template.md:47` hands off to the single `claims-emit` writer; `coordinator/pipelines/deep-research/notebooklm/notebooklm.manifest.yaml` | **ported** (live) | |
| 23 | Coverage auditor | A, B, C, D | mechanical (binary cross-reference) | `coverage-auditor-prompt-template.md:29-35,77-92` — present/absent only, "not an editorial judgment"; per-pipeline blocks `:184,203,218,247` | hybrid: claim-presence matching is scriptable; the "why a reader would go deeper" sentence per absent cluster (`:94-109`) is not | A pure script can match claim ids but not paraphrase; a pure model leg spends a Sonnet dispatch on a binary check (cost floor below) |
| 24 | Repo-scout extractor | B repo | owned elsewhere | the repo-scout extraction verdict plan; plan `status:` read at writing: `draft`; its verdict document does not exist at this writing | see that plan | |

## Already answered by the tree

- **Durable claims merge — ported.** `claims-emit` is live in all four legs (rows 6, 13, 18, 22).
- **Worker-claim to `research-claim.schema.json` field mapping — consolidated** in `notebooklm/team-protocol.md` § Durable claims field mapping.

## Follow-on rows (no work in the plan that created this table)

- **F1 — `agents/repo-specialist.md` still restates the field names** it shares with the claims schema. It belongs to the repo leg; consolidation there is a later row.
- **F2 — Agent body vs prompt template duplication.** The sweep and worker legs each carry both an agent body (`agents/research-sweep.md`, `agents/research-worker.md`) and a prompt template. Open question for the family: which surface owns which instruction. Unresolved.

## Measured run cost

A **floor**, not an accounting. Reconstructed from one archived run whose durable artifacts survive: the repo pipeline run on `firstmate` (`docs/research/2026-08-30-repo-firstmate*`). Scratch files (scout inventories, specialist claims and summaries, survey, atlas) do not survive, so legs that wrote only scratch contribute template input and nothing else.

**Method.** Bytes converted at **4 characters per token** (byte count used as the character count; ASCII-dominant markdown, so the ratio is an approximation, not a tokenizer measurement). Input bytes = on-disk size of each template (an upper bound on the rendered prompt: the file includes its own wrapper prose and both tier variants) multiplied by the dispatches that run it, plus durable files the role was instructed to read. Output bytes = durable artifacts the role wrote.

| Role | Dispatches | Input bytes | Output bytes |
|------|-----------:|------------:|-------------:|
| repo scout (`repo-scout-prompt-template.md`, 9,790 B) | 2 | 19,580 | not durable |
| repo specialist (`repo-specialist-prompt-template.md`, 18,550 B) | 4 | 74,200 | not durable (merged claims counted under synthesizer) |
| repo synthesizer (`repo-synthesizer-prompt-template.md`, 20,533 B) | 1 | 20,533 + 31,684 (claims read) = 52,217 | 46,292 (assessment) + 58,238 (gap analysis) + 11,144 (advisory) + 31,684 (merged claims) = 147,358 |
| coverage auditor (`coverage-auditor-prompt-template.md`, 13,395 B) | 1 | 13,395 + 31,684 (claims read) = 45,079 | 9,495 (coverage audit) |
| **Total** | 8 | **191,076** | **156,853** |

Total bytes 347,929 / 4 = **about 87,000 tokens**, of which about 48,000 input and 39,000 output.

**What the floor excludes:** tool-call turns and tool results (file reads of the repository itself, WebFetch bodies), reasoning tokens, re-reads of the same file within a role, any retry or fidelity-relay round, the EM driver's own context, the agent-definition bodies loaded alongside each template, and the roles that wrote only scratch. The survey (`repo-survey-prompt-template.md`, 4,069 B), atlas sketch (4,855 B) and atlas refinement (8,123 B) templates are also left out: the run's flags are not recorded in the durable pair, so whether they ran is not established. The true cost is above this figure, by an unmeasured margin; no use should treat 87,000 as a total.

The one input in this table that moves with the repo is the claims file read by the synthesizer and auditor (31,684 B for 52 claims); the template bytes are fixed per role.
