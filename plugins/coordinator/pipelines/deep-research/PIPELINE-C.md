# Pipeline C: Structured Research

> Extracted from PIPELINE.md. Referenced by `/structured-research`. See PIPELINE.md for Pipelines A & B.

## Inputs and Outputs

- **Input:** A research spec file (see `spec-format.md` in this directory for the canonical format)
- **Output:** Schema-conforming structured data per subject + a JSON manifest tracking progress

## Phase Pipeline — STRICT SEQUENCE (per subject)

```
Phase 0 → [quality gates] → Phase 1 → [quality gates] → Phase 2 → [quality gates] → Phase 3
```

**Phases MUST run sequentially per subject.** Gate evaluation happens between every phase pair.

---

### Manifest Management

The manifest is a JSON file at the spec's `manifest_path`. It tracks progress across sessions.

**Per-subject fields:**
- `status` — `pending | in_progress | complete`
- `phases_completed` — array of completed phase numbers
- `phase_outputs` — map of phase number → realized file path(s) on disk
- `output_applied` — `false` until PM explicitly approves
- `last_researched` — ISO date
- `gate_retries` — map of gate name → list of topics retried
- `notes` — free text (gate annotations, PM comments)

**Top-level fields:**
- `spec_path` — path to the research spec
- `spec_hash` — SHA-256 of spec file at last run (for drift detection)
- `run_id` — format: `YYYY-MM-DD-HHhMM`

**Initialization:** On first run, all subjects start as `pending`.

**Resumability:** Resume from `last completed phase + 1`. Use `phase_outputs` (not spec path templates) to locate prior output — this is deterministic regardless of spec drift.

**Spec drift:** Compare `spec_hash` on resume. If changed, flag to PM before processing any subjects. Options: **continue** (complete subjects keep existing data) or **reset** (all subjects re-run from Phase 0).

**Incremental runs:** Batch sizing comes from the spec's `batching` config. A "run" is one invocation of Pipeline C within a session — the coordinator proposes which subjects to include based on batching config + manifest state; PM approves; that set is processed sequentially.

---

### Phase 0: Gap Analysis & Research Brief (Coordinator)

**Actor:** Coordinator (Opus). **Time:** ~5 min per subject.

1. **Read the spec** — understand subjects, topics, acceptance criteria, output schema
2. **Read known context** — existing data for this subject (from spec's `known_context` config)
3. **Identify gaps** — compare existing data against schema; note missing fields, stale sources, empty arrays
4. **Write research brief** — targeting gaps, not the full schema. Use the **Research Brief Template (Phase 0 Output)** from `agent-prompts.md`
5. **Update manifest** — `status: in_progress`, `phases_completed: [0]`, record Phase 0 output path in `phase_outputs`

**Output:** Research brief file at the spec's configured `phase_0` output path, with variable substitution applied.

---

### Phase 1: Spec-Driven Discovery (Haiku agents, parallel per topic)

**Model:** Haiku. **Dispatch:** One agent per topic area, all simultaneously.

Each agent receives:
- Topic definition from spec (search domains, focus questions — verbatim)
- Research brief excerpt for this topic (gap-targeted)
- Acceptance criteria relevant to this topic
- Subject context (name, code, any known data)

**DISPATCH:** Open `agent-prompts.md`. Copy the **Pipeline C Phase 1: Haiku Spec-Driven Discovery Prompt** template verbatim. Fill in the bracketed fields. Do NOT write a custom prompt — the template derives focus questions and search domains from the spec, enabling reproducible runs across subjects and sessions.

**Scratch path:** Spec's configured `phase_1` output path with variable substitution. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

**Output:** Sources found, unverified claims mapped to schema fields, acceptance criteria status checklist.

**Scratch verification:** Before proceeding to gates, verify all expected Phase 1 files exist. Re-dispatch once on failure; skip topic on second failure.

---

### Post-Phase 1 Quality Gates

The coordinator evaluates each gate from the spec's `gates.after_phase_1` list:

1. **Check skip conditions** — if subject matches a gate's `skip_for` list, skip that gate
2. **Evaluate rule** — read Phase 1 output, apply the gate's rule text
3. **Pass** → proceed to Phase 2
4. **Fail for specific topics** → re-dispatch the failed topic's Phase 1 agent using the SAME template, with a **"Gate Feedback"** section prepended containing the failed gate rule and specific deficiency. Output written to a `-retry` suffixed path, which REPLACES the original for downstream consumption. Manifest records the retry in `gate_retries`.
5. **Failed twice** → annotate gap in manifest `notes`, proceed. Coordinator flags the gap for Phase 2 attention.

**Hard limit:** One retry per gate per topic. No indefinite re-dispatch loops.

---

### Phase 2: Spec-Aware Verification (Sonnet agents, parallel per topic)

**Model:** Sonnet. **Dispatch:** One agent per topic area, all simultaneously.

Each agent receives:
- Phase 1 output for this topic (read from disk via `phase_outputs`)
- Schema fields relevant to this topic
- Existing data for this subject
- Acceptance criteria

**DISPATCH:** Open `agent-prompts.md`. Copy the **Pipeline C Phase 2: Sonnet Spec-Aware Verification Prompt** template verbatim. Fill in the bracketed fields. Do NOT write a custom prompt — the template embeds output schema fields so findings are structured as a schema field table, not prose.

**Output format:** Schema field table per topic:

| Field | Value | Source | Confidence | Existing Value | Change Type |
|-------|-------|--------|------------|----------------|-------------|

Change types: `CONFIRMED` (existing value verified), `UPDATED` (existing value superseded), `NEW` (no prior value), `REFUTED` (existing value contradicted). See `spec-format.md` for full taxonomy.

**Scratch path:** Spec's configured `phase_2` output path with variable substitution. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

**Scratch verification:** Before proceeding to gates, verify all expected Phase 2 files exist. Re-dispatch once on failure; skip topic on second failure.

---

### Post-Phase 2 Quality Gates

The coordinator evaluates each gate from the spec's `gates.after_phase_2` list:

- **Schema conformance check:** Phase 2 outputs must contain structured field values in table format, not prose paragraphs. If an agent returned prose without structured field values, re-dispatch once with specific feedback. If still prose on retry, coordinator extracts field values manually before Phase 3.

---

### Phase 3: Schema-Conforming Synthesis (Sonnet, single agent per subject)

**Model:** Sonnet. **Input:** All Phase 2 outputs for this subject + full output schema + existing data.

**DISPATCH:** Open `agent-prompts.md`. Copy the **Pipeline C Phase 3: Sonnet Schema-Conforming Synthesis Prompt** template verbatim. Fill in the bracketed fields. Do NOT write a custom prompt.

**Output:** A single file containing:
1. **YAML/JSON-ready structured data** conforming exactly to the output schema
2. **Annotations table** — field → source → confidence → notes (parallel to the data, not inline)
3. **Cross-topic reconciliation** — where different topics produced conflicting data for the same field
4. **Gaps remaining** — schema fields that could not be filled, with reasons

**This is NOT prose synthesis.** Structured data with prose only in annotations and reconciliation sections.

**Merge rules:** `CONFIRMED` keeps existing value. `UPDATED` replaces existing value. `NEW` adds value. `REFUTED` removes existing value with annotation explaining the contradiction.

**Scratch path:** Spec's configured `phase_3` output path with variable substitution. Instruct the agent in its prompt to use the Write tool for this. (The Agent tool has no `tools` parameter — tool guidance goes in the prompt.)

---

### Post-Phase 3: Coordinator Validation

After Phase 3 completes, the coordinator validates schema conformance:

1. **Check required fields** — all required fields in the output schema must be present
2. **Check enum values** — enum fields must use values from the schema's allowed set
3. **Check array minimums** — array fields must meet minimum counts from acceptance criteria

**Results:**
- **Conformant** → manifest: `status: complete`, record Phase 3 output path in `phase_outputs`
- **Minor gaps** (1-2 missing optional fields inferable from Phase 2 data) → coordinator edits the Phase 3 output file directly, then marks complete
- **Structural non-conformance** (prose where structured data expected, missing required fields) → re-dispatch Phase 3 once with specific feedback about what's wrong
- **`output_applied` stays `false`** until PM explicitly approves and applies the output

---

### Phase 3.5: Scratch Triage

- **Default: KEEP phase output files.** Pipeline C phase outputs serve as audit trail, and their paths are declared in the spec. Unlike Pipelines A/B where scratch is consumed by synthesis, Pipeline C outputs may be referenced by the PM during review.
- **Optional:** If the spec includes `scratch_cleanup: true`, delete intermediate phase files after Phase 3 validation passes, keeping only the Phase 3 synthesis output.

---

### Subject Batching

- **Parallel per-subject via independent orchestrators:** Each subject is dispatched to its own Opus orchestrator agent (via `/structured-research`). Orchestrators are fully independent — each owns one subject end-to-end, evaluates its own gates, and writes its own output. No cross-subject coordination needed.
- **Batch size** from the spec's `batching` config — typically per-tier "N per run" values
- **Workflow per run:**
  1. EM reads manifest, identifies pending/incomplete subjects
  2. Proposes batch to PM based on batching config and session capacity
  3. PM approves batch
  4. EM dispatches one orchestrator per subject (in parallel, background)
  5. EM processes results as orchestrators complete — updates manifest, commits
- **Within each orchestrator:** Topics are dispatched in parallel (e.g., 4 Haiku agents for Phase 1), but phases are strictly sequential per subject. Gate evaluation happens between phases.
- **Concurrency ceiling: maximum 4 orchestrators simultaneously.** Each orchestrator spawns up to T sub-agents per phase. At 4 orchestrators × 4 topics = 16 concurrent agents, which is the practical limit. Beyond this, rate limits, context thrashing, and cascading failures make the run slower than sequential. If the batch has >4 subjects, the EM dispatches in waves of 4, waiting for each wave to complete. This ceiling applies regardless of what the spec's `batching` config allows — the batching config controls *how many subjects per run*, the ceiling controls *how many run concurrently*.
- **Why 4?** Empirically determined. An attempt to dispatch 68 concurrent Opus orchestrators (each spawning Haiku and Sonnet sub-agents) caused catastrophic failure — cascading rate limits, lost context, and zero usable output. The multiplier effect is the danger: 4 orchestrators × 4 topics × 2 phases with agents = 32 agent-dispatches per wave, which is already heavy.

---

### Edge Cases

- **Partial gate failure** → re-dispatch only the failed topics, not the entire phase
- **Mid-session crash** → manifest tracks `phases_completed` and `phase_outputs`; resume from next incomplete phase
- **Spec changes between sessions** → `spec_hash` detects drift; PM decides continue or reset
- **Phase 3 non-conformance** → one re-dispatch with feedback, then escalate to PM
- **Subject already complete** → skip (manifest says `status: complete`); PM can manually reset if re-run needed

---

# Common Failure Modes (Pipeline C)

| Failure | Prevention |
|---------|------------|
| Ignoring spec, improvising prompts | Spec is the brief. Derive prompts FROM spec fields, don't rewrite. |
| Skipping quality gates | Gates evaluate between every phase pair. No "looks fine, moving on." |
| Applying output without PM review | `output_applied` stays false until PM explicitly approves. |
| Resuming without checking spec hash | Compare spec_hash on every resume. Flag drift to PM before processing any subjects. |
| Dispatching sub-agents via CLI instead of Agent tool | Use the Agent tool with `model: "haiku"` or `model: "sonnet"`. Do NOT use Bash to run `claude` CLI commands for sub-agent dispatch — the flag syntax differs and causes failures. |
| Dispatching too many orchestrators at once | **Max 4 concurrent orchestrators.** Each one spawns T×2 sub-agents across phases. 68 concurrent orchestrators caused catastrophic failure. Wave batches >4 subjects. |
| Phase 3 producing prose | Template requires schema-field output. Coordinator validates post-Phase 3. |
| Indefinite gate re-dispatch | Hard limit: one retry per gate per topic. Then annotate and proceed. |

# Cost Profile (Pipeline C)

| Pipeline | Phases | Agents | Wall-Clock |
|----------|--------|--------|------------|
| Structured (4 topics, 1 subject) | 4 (0-3) | ~4 Haiku + 4 Sonnet + 1 Sonnet | ~10-15 min |
| Structured (4 topics, 4 subjects, 1 wave) | 4 (0-3) × 4 | ~16 Haiku + 16 Sonnet + 4 Sonnet | ~15-25 min |
| Structured (4 topics, 8 subjects, 2 waves) | 4 (0-3) × 8 | ~32 Haiku + 32 Sonnet + 8 Sonnet | ~30-50 min |

**Note:** Subjects within a wave run in parallel (max 4 per wave). Wall-clock is per-wave, not per-subject. Gate retries add ~5 min each.

# Integration (Pipeline C)

- **Pipeline C:** Manifest enables cross-session campaigns — research 5 subjects today, 10 tomorrow, resume from where you left off
- **Pipeline C:** Quality gates are coordinator-evaluated between phases, not post-hoc. Gate rules and skip conditions come from the spec file
- **Pipeline C:** Spec format documented in `spec-format.md` in this directory — the canonical reference for all spec fields, variable substitution, and the change type taxonomy
