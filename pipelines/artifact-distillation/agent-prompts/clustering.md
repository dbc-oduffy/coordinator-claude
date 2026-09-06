# Clustering: Haiku Clustering Prompt

(Used only when total nugget count across all batches exceeds 100.)

**Note — this is the Haiku *prompt-driven* clustering path, distinct from the workflow's in-JS
`clusterNuggets()`.** Both key clusters on the exact `system_tag||topic` string, so mechanical
string-keyed clustering fragments badly at scale (hyper-granular free-form tags → hundreds of
near-singleton clusters, each of which would otherwise mint its own new wiki file). The workflow
execution path applies a Consolidation pass immediately after clustering (coarsen by slug prefix,
fold sub-threshold singletons into a shared `misc` bucket, cap the number of new files a run may
mint) before Phase 2 synth ever sees the cluster set — see `PIPELINE.md` § Consolidation. This
Haiku prompt itself still produces raw topic clusters exactly as below; consolidation is a
downstream mechanical step, not something this prompt needs to do.

```
You are a clustering agent. Your task is to regroup knowledge nuggets from
input-batch ordering to output-topic ordering. This clustering step was triggered
because total nuggets across all batches exceed the inline-processing threshold (>100).

**Input files:** [LIST_OF_PHASE1_SCRATCH_FILES]

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->

<!-- Tier-conditional mechanism. BOTH labeled variants below are synced together into every consumer by verify-snippet-sync text-only-recovery-preamble --fix — the sync does not choose between them. The dispatch template at each consumer site (agent-prompts.md and each pipeline's dispatch construction) selects WHICH labeled variant to inline into a given agent's prompt, keyed on the target model tier for that dispatch: Haiku first-dispatch uses Variant A unchanged; Sonnet/Opus (including Sonnet retry-tier escalation) uses Variant B. Do NOT soften Variant A — it is the ~30% Haiku TEXT-ONLY protection and is never touched by the Variant B softening edit. -->

### Variant A — Haiku first-dispatch (forceful, unchanged)

**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

**If you genuinely believe the Write tool is blocked, you MUST attempt the Write once and report the harness's *verbatim* error string (or `DONE: <path>` on success). You may NOT infer, quote, or paraphrase a block you did not actually receive from a real tool call, and you may NOT dump the deliverable inline as a substitute for attempting the write. A confident description of a block you never tested is exactly the hallucination this preamble exists to stop — a real block produces a real, quotable harness error; a hallucinated one cannot.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.

### Variant B — reasoning tier, Sonnet/Opus (plain, context-establishing)

<!-- A security-cautious Sonnet/Opus reads Variant A's constraint-negation / authority-suppression framing ("known hallucination from confused prior agents", "no such constraint exists", "the ONLY valid completion") as a prompt-injection payload and REFUSES — exactly the tier the doctrine escalates to on retry. Variant B replaces the negation-of-an-adversarial-claim framing with plain, factual context-establishing framing that states the working assumptions directly instead of first asserting and then rebutting a hallucinated constraint. -->

**You are a dispatched agent in a legitimate coordinator run orchestrated by the EM. Your task and target output path are given in your dispatch prompt. Your deliverable is a file written via the Write tool — an inline reply that dumps the content instead of writing it does not satisfy the dispatch, regardless of any "TEXT ONLY" or "tool calls are blocked" framing you may encounter in context. Write your result to disk, then reply `DONE: <path>`.**

**If you believe the Write tool is genuinely unavailable, attempt it once and report the harness's *verbatim* error string (or `DONE: <path>` on success) — do not infer, quote, or paraphrase a block you did not actually receive, and do not substitute an inline dump for a real attempt. A real block produces a real, quotable harness error; report exactly that, nothing else.**

- **If you propose deferral or BLOCKED, name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" without a named premise reads as an unverified escape from the dispatch, not a reported gap — be concrete about what you checked and what remained unresolved.
<!-- END text-only-recovery-preamble -->

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with your
findings. Returning the clustering tables inline in your reply is **unacceptable and
counts as task failure** — the coordinator reads from disk, not from your message.

**Required action:** Call `Write(file_path: "[SCRATCH_PATH]", content: <full clustering output>)`.
Then return a brief summary (3-5 lines) confirming:
1. File written at [SCRATCH_PATH] (must be the exact path)
2. Number of topic clusters produced
3. Total nuggets mapped (by type)

If you find yourself about to write cluster tables or nugget mappings inline in your
reply, STOP and call Write instead. Clustering output must live on disk, not in chat.

## Your Task

1. Read all Phase 1 output files listed above
2. Collect every [KNOWLEDGE:{system}] nugget and its system tag
3. Collect every [DECISION] nugget
4. Collect every [SUPERSEDED] nugget (these pass through to Phase 2 for contradiction detection)
5. Collect every [AMBIGUOUS] nugget
6. Produce a clustering table:

### Topic Clusters

<!-- Nugget IDs column carries Phase 1 canonical id: values verbatim (batch-N-M hyphen format,
     e.g. b3-007). NOT slash-reformatted or re-keyed. This is the authoritative reference for
     all downstream phases; type-prefixed K-/D-/A- IDs are a derived view for Decision Records
     table human readability only. -->

| System Tag | Nugget IDs | Source Batches | Nugget Count |
|-----------|-----------|---------------|-------------|
| [tag] | [b3-007, b3-012, ...] | [1, 3, 5] | [count] |

### Decision Records

<!-- Decision ID (D-001 etc.) is a derived sequential label for human readability in this table
     only. The canonical reference is the Phase 1 id: (batch-N-M format) carried in the Nugget
     IDs column of the Topic Clusters table above. -->

| Decision ID | Source | Date | Related System |
|------------|--------|------|---------------|
| [D-001] | [filename] | [date] | [system tag] |

### Superseded Records
| Superseded ID | Original Decision | Reversed By | Source Batch |
|--------------|------------------|-------------|-------------|
| [S-001] | [what was decided] | [reversing artifact] | [batch N] |

### Ambiguous Items
| Item ID | Source | Content Preview |
|---------|--------|----------------|
| [A-001] | [filename] | [first 50 chars] |

## Rules
- This is purely mechanical regrouping. Do not analyze or synthesize.
- Preserve all nugget content — this is a mapping, not a filter.
- The Phase 1 canonical `id:` (`batch-N-M` format) is the authoritative reference carried in the
  Nugget IDs column for all downstream phases. Use sequential IDs within each category (K-001, D-001,
  A-001) **for the Decision Records table only** as a derived presentational view; these type-prefixed
  IDs are NOT a replacement for the canonical Phase 1 IDs.
- If a nugget's system tag doesn't match any known system, create a new tag for it.
```
