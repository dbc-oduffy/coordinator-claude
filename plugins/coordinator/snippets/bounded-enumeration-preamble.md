# Bounded-Enumeration Preamble

Inline this verbatim into Sonnet or Haiku dispatches whose deliverable is a verdict-per-item table over a **bounded input list** (verify-this-list-of-IDs, classify-these-N-entries, audit-these-paths, expand-these-summary-rows). Without it, scouts empirically hallucinate IDs not present in the input — fabricating verdicts for items that don't exist, which silently corrupts downstream waves that trust the table by ID.

---

**Bounded-enumeration preamble (paste verbatim into the dispatch brief):**

> The input list below is the COMPLETE set of items you may produce verdicts for. Do NOT add rows for items not in the input list. Do NOT infer related items from context, file structure, or recalled prior knowledge. Do NOT expand a single input row into multiple output rows unless the input row explicitly contains multiple file:line citations (in which case fan-out is allowed per cited file:line).
>
> Output schema:
> - One row per input item, in input order.
> - Row count MUST equal input count (or input citation count, for explicit fan-out). Verify before writing the file.
> - Each row's ID column MUST be the verbatim ID from the input. No new IDs, no renamings, no abbreviations.
>
> Before writing the deliverable file, run a self-check: `wc -l` the output table body and compare to the input count. If they differ and you have not explicitly fanned out a multi-citation row, STOP and re-read the input list — you have either hallucinated rows or skipped rows. Inline the count check at the top of your reply: `Input items: N. Output rows: M. Reconciled: <reason if M != N>`.

---

## When to inline

- Any chunk-verify Haiku dispatch over a bounded backlog (`/bug-blitz` Phase 1, `/bug-sweep` triage, queue-classification waves).
- Any executor whose input is "verify these N file:line entries" or "classify these N items."
- Any audit whose schema is "one verdict row per input row."

## When NOT to inline

- Open-ended enumeration ("find all X in the codebase") — bounded preamble would suppress discovery.
- Schema-driven generation ("emit a row per gameplay tag the indexer found") — bound is the indexer's output, not a passed-in list.
- Single-item dispatches — count check is trivial.

## Companion

Pair with `text-only-recovery-preamble.md` for high-parallel waves (>5 fan-outs) where Haiku/Sonnet may also hallucinate inline text-only output. Pair with `project-rag-preamble.md` when the verification step involves code-shaped lookups.

## Provenance

Encoded 2026-05-18 after `/bug-blitz` Phase 1 Haiku scouts on a backlog of ~47 items produced 3 rows for IDs not in the input list (BS-XX-* fabrications). Wiki coverage of the general scout-hallucination class lives in `docs/wiki/scout-and-dispatch-discipline.md`; this snippet is the specific bounded-enumeration variant.
