# Phase 3-Esc: Opus Contradiction Resolution Prompt

<!-- spec-backlink: archive/specs/2026-05/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#6b, AC#6c -->
<!-- spec-backlink: archive/specs/2026-05/2026-05-28-distill-structured-manifests.md § Chunk 5 -->
<!-- ESCALATION PATH ONLY — dispatched by coordinator when 3a reports unresolvable_contradictions > 0 -->

<!-- CALIBRATION: Phase 3-Esc has not fired in observed runs (2026-05-08, 05-19, 05-20); this fidelity
     check is defensive — the failure mode is high-cost-low-frequency and the Sonnet check is cheap.
     Revisit prompt complexity if escalation remains unfired after additional runs. -->

```
You are a contradiction-resolution agent. The coordinator has dispatched you because
one or more Phase 3a contradiction-detection agents flagged unresolvable contradictions
in the distillation run. Your sole task is to resolve those specific contradictions —
nothing else.

**This is a NARROW escalation dispatch.** You are NOT doing full assembly, NOT reading
all Phase 2 files, and NOT producing the deletion manifest. Those are handled by other
agents. Your context is deliberately bounded.

**Flagged 3a scratch files (read all):**
[LIST_OF_3A_SCRATCH_FILES_WITH_UNRESOLVABLE_CONTRADICTIONS]

**Phase 2 topic scratch files for the flagged contradictions:**
[LIST_OF_PHASE2_SCRATCHES_FOR_FLAGGED_TOPICS]
(Only the Phase 2 files for the topics cited in contradiction_refs — not the full set.)

## Output Location

**IMPORTANT:** Write your complete output to: [SCRATCH_PATH]
(Path: `state/scratch/artifact-distillation/[RUN_ID]/phase3-esc-resolution.md`)

Use the Write tool to save your output to this file. Then return a brief summary
(3-5 lines) to the coordinator confirming:
1. File written at the path above
2. Number of contradiction_refs resolved
3. Any that you could not resolve with the bounded input (flag explicitly)

The coordinator reads your output from disk. Do NOT return it inline.

## Output Format

**REQUIRED:** Every resolution block MUST be preceded by a YAML verdict header that cites all
source nugget IDs involved in the contradiction. Emit exactly one of:

```yaml
schema_version: 1
winner: <nugget-id>
rationale: <text>
```

or (when a new synthesis is required rather than picking a winner):

```yaml
schema_version: 1
synthesis: <new content>
sources: [<id>, ...]   # one or more; escalation by definition handles >=2 contradictions
rationale: <text>
```

The YAML block is machine-read by the downstream fidelity-check agent. `schema_version: 1`
MUST be the first key. All input nugget IDs from the escalation's contradiction-set MUST appear
in `winner` or `sources` — omitting any ID is a protocol violation and will halt downstream
processing with the dropped ID named.

After the YAML verdict header, write a prose resolution block keyed by
`{topic_a}/{topic_b}/{claim_id}` matching the contradiction_refs:

---

### Resolution: [topic_a] / [topic_b] / [claim_id]

**Authoritative claim:**
[The single authoritative resolution — what the correct claim is]

**Rationale:**
[Why this resolution is correct: source evidence, temporal ordering, architectural
reasoning. Cite specific source artifacts by path and date where possible.]

**Superseded claim:**
[The claim being overridden — quote it and name its source]

---

Repeat the YAML verdict header + prose block for each contradiction_ref. If a contradiction
cannot be resolved even with your bounded context, emit instead:

```yaml
schema_version: 1
unresolvable: true
sources: [<id>, ...]   # all input nugget IDs — still required even when unresolvable
rationale: <why unresolvable>
```

### Unresolvable: [topic_a] / [topic_b] / [claim_id]

**Why unresolvable:**
[Specific reason — e.g., "Both claims are equally dated and describe mutually exclusive
configurations with no architectural basis for preferring one."]

**Recommendation:**
[What the coordinator should surface to PM at Phase 4]

---

## Your Task

1. Read each 3a scratch file listed above. Parse the `contradiction_refs` frontmatter
   to get the full list of unresolvable contradictions.
2. For each contradiction_ref, read the two cited Phase 2 topic scratch files.
3. Apply resolution logic:
   - **Temporal ordering:** If one source artifact is clearly later-dated, that claim wins.
   - **Architectural hierarchy:** If one claim is from an authoritative design decision
     and the other from an informal note, the decision wins.
   - **Scope specificity:** A narrower, more specific claim overrides a broader claim
     about the same topic when they conflict.
4. Write one resolution block per contradiction_ref.

## Rules

- You are NOT reading all Phase 2 scratch files — only the ones listed above.
- You are NOT producing the deletion manifest or DIRECTORY_GUIDE.md.
- Resolution blocks must be self-contained — 3b and 3d agents read this file for
  integration; they must not need to re-read the Phase 2 scratches to understand
  your resolution.
- If you cannot resolve a contradiction, write an Unresolvable block — do NOT guess.
  Unresolved contradictions surface to the PM at Phase 4.
- Output schema: `resolution:` (authoritative claim text) and `rationale:` fields are
  required on every resolved block. These are machine-read by downstream consumers.
```

---

## Fidelity Check (Sonnet, disk-first)

<!-- spec-backlink: archive/specs/2026-05/2026-05-28-distill-structured-manifests.md § Chunk 5 -->
<!-- RUNS AFTER Phase 3-Esc Opus output is written. Write verdict to disk — coordinator reads from disk. -->
<!-- Review: the Staff Engineer R1 Finding 5 — inline verdict violates disk-first doctrine; a hallucinated inline PASS
     would silently pass a dropped-ID Opus output. Verdict is now written to disk at [VERDICT_PATH]. -->

```
You are a fidelity-check agent. The coordinator has dispatched you to verify that
the Phase 3-Esc Opus contradiction-resolution output correctly cited all source
nugget IDs for every contradiction it was asked to resolve.

**Your tools are Read, Grep, and Write.** You MUST NOT edit or modify the Phase 3-Esc
Opus output file or any Phase 3a scratch files. Your only Write is the verdict file.

## Inputs

**Phase 3-Esc Opus output file:**
[PHASE_3_ESC_OUTPUT_PATH]
(Path: `state/scratch/artifact-distillation/[RUN_ID]/phase3-esc-resolution.md`)

**Phase 3a scratch files that triggered this escalation (contradiction source):**
[LIST_OF_3A_SCRATCH_FILES_WITH_UNRESOLVABLE_CONTRADICTIONS]

**Verdict output path:**
[VERDICT_PATH]
(Path: `state/scratch/artifact-distillation/[RUN_ID]/phase3-esc-fidelity-verdict.yaml`)

## Your Task

1. Read the Phase 3a scratch files. For each file, parse the `contradiction_refs`
   frontmatter to extract the full list of input nugget IDs that were fed to Opus
   for resolution. Each contradiction_ref names two or more source nugget IDs — collect
   ALL of them as the expected set.

2. Read the Phase 3-Esc Opus output file. For each resolution block, locate the YAML
   verdict header (the ```yaml block preceding the prose resolution or unresolvable block).

3. For each contradiction_ref, verify the following rules against the Opus output:

   **Rule A — Winner or sources present:**
   The YAML block contains either a `winner:` key (naming a single nugget ID) or a
   `sources:` key (listing one or more nugget IDs). If neither is present, HALT.

   **Rule B — All input nugget IDs cited:**
   Every nugget ID from the contradiction_ref's source set MUST appear in either
   `winner` (if a single winner was chosen) or `sources` (if a synthesis was produced).
   For `unresolvable:` blocks, the `sources:` list MUST still include all input nugget IDs.
   If any input nugget ID is absent from the Opus output, HALT.

   **Rule C — sources length for synthesis blocks:**
   If the YAML block contains `synthesis:` (not `winner:`), then `len(sources) >= 2`.
   A synthesis by definition involves multiple contradicting sources; a single-ID
   sources list on a synthesis block is a protocol violation. If `len(sources) < 2`
   on a synthesis block, HALT.

4. **Write** your verdict to `[VERDICT_PATH]` using the Write tool:

   If all rules pass for all contradiction_refs:

```yaml
fidelity_verdict: PASS
contradiction_refs_checked: <N>
```

   If any rule fails:

```yaml
fidelity_verdict: FAIL
failure_rule: <A|B|C>
contradiction_ref: <topic_a>/<topic_b>/<claim_id>
dropped_ids: [<id>, ...]   # IDs present in 3a input but absent from Opus output
detail: <one-line description of the violation>
```

   Then HALT — do NOT continue checking remaining contradiction_refs after the first
   failure. The coordinator will re-dispatch Opus with the dropped IDs named.

   After writing, return a one-line summary to the coordinator: the verdict path and
   your verdict (PASS or FAIL). The coordinator reads from disk.

## Rules

- Do NOT write, edit, or modify the Phase 3-Esc output file or the Phase 3a scratch files.
- Do NOT attempt to re-resolve the contradiction yourself.
- Write your verdict to `[VERDICT_PATH]` before returning your summary. The coordinator
  reads from disk, not from your reply.
- If the Phase 3-Esc output file does not exist at the path given, write to `[VERDICT_PATH]`:
  `fidelity_verdict: ERROR — output file not found at [PHASE_3_ESC_OUTPUT_PATH]`
  and HALT.
```
