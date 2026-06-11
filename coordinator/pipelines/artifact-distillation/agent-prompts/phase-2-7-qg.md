# Phase 2.7-QG: Haiku Coverage Gate

<!-- Naming note: `Phase 2.7-QG` avoids decimal collision with Phase 2.5 (judgment mining).
     Standardizing all QG gates to `<Phase>-QG` suffix is a future cleanup, out-of-scope here. -->

## Purpose

Phase 2.7-QG is a mechanical coverage gate that verifies every nugget assigned to a Phase 2
cluster was accounted for in that cluster's `dispositions:` output. It runs **after Phase 2
completes, before Phase 3a**, parallel by cluster (one Haiku instance per cluster).

This gate catches silent omissions — nuggets that Phase 2 neither processed nor explicitly
skipped. It does NOT check whether the synthesis was correct; it checks only that the set of
`nugget_id` values in `dispositions:` equals the set of nugget IDs assigned to the cluster.

**Model:** Haiku (parallel, one instance per cluster).
**Nature:** Purely mechanical — set membership only. No semantic interpretation.

---

## Inputs

For each cluster being verified, you receive:

1. **Phase 2 scratch file path** — the file written by the Phase 2 agent for this cluster.
   Contains a `dispositions:` YAML frontmatter block.
2. **Assigned nugget IDs** — the list of Phase 1 canonical `batch-N-M` IDs from the Clustering
   output table's `Nugget IDs` column for this cluster's System Tag row.

<!-- Review: the Staff Engineer R1 Findings 1+3+6 — assigned nugget IDs now use Phase 1 canonical batch-N-M
     (hyphen) format, matching dispositions:. The slash-vs-hyphen divergence described in the old
     prompt was the bug being fixed; both sides now use canonical Phase 1 ids. -->

**[PHASE2_SCRATCH_PATH]** — path to the Phase 2 scratch file for this cluster.
**[ASSIGNED_NUGGET_IDS]** — the nugget IDs assigned to this cluster at Clustering time,
one per line or comma-separated, format `batch-N-M` (Phase 1 canonical hyphen format).

---

## Your Task

1. **Read** the Phase 2 scratch file at `[PHASE2_SCRATCH_PATH]`.

2. **Extract** the `dispositions:` YAML frontmatter block. Parse every `nugget_id` value
   listed under `dispositions:`. This is the **emitted set**.

3. **Parse** `[ASSIGNED_NUGGET_IDS]` as the **assigned set**.

4. **Compute** the set-diff: `assigned_set − emitted_set`.
   - If the diff is **empty**: emit `PASS`.
   - If the diff is **non-empty**: emit `FAIL` and name every missing nugget ID.

5. **Write** your verdict to disk at `[VERDICT_PATH]` using the schema below. Then return a
   one-line summary confirming the file path and your verdict (PASS or FAIL).

Do NOT re-run Phase 2. Do NOT edit the Phase 2 scratch file. Do NOT interpret why nuggets
are missing — just name them. This gate is a set-diff, not a synthesis.

---

## Verdict Schema

Write a YAML file at `[VERDICT_PATH]`:

```yaml
schema_version: 1
phase: "2.7-QG"
cluster: <System Tag for this cluster>
scratch_path: <PHASE2_SCRATCH_PATH>
verdict: PASS | FAIL
missing_nugget_ids: []          # empty list on PASS; list of missing IDs on FAIL
emitted_nugget_ids: [...]       # all nugget_id values found in dispositions:
assigned_nugget_ids: [...]      # all IDs from [ASSIGNED_NUGGET_IDS]
```

**PASS example:**

```yaml
schema_version: 1
phase: "2.7-QG"
cluster: session-management
scratch_path: distill-scratch/phase2-session-management.md
verdict: PASS
missing_nugget_ids: []
emitted_nugget_ids: [batch-1-001, batch-1-002, batch-2-005]
assigned_nugget_ids: [batch-1-001, batch-1-002, batch-2-005]
```

**FAIL example:**

```yaml
schema_version: 1
phase: "2.7-QG"
cluster: session-management
scratch_path: distill-scratch/phase2-session-management.md
verdict: FAIL
missing_nugget_ids: [batch-2-005]
emitted_nugget_ids: [batch-1-001, batch-1-002]
assigned_nugget_ids: [batch-1-001, batch-1-002, batch-2-005]
```

---

## Coordinator Retry Protocol (document here for coordinator reference)

On a FAIL verdict, the coordinator dispatches at most **2 Phase 2 re-runs** for the
failing cluster, then re-runs Phase 2.7-QG after each attempt.

- **After attempt 1:** if Phase 2.7-QG returns PASS, continue pipeline normally.
- **After attempt 2 (second consecutive FAIL):** halt pipeline for this cluster. Surface
  to PM with:
  - The cluster's `missing_nugget_ids` from both FAIL verdicts
  - Both Phase 2 scratch file paths (attempt 1 and attempt 2)
  - The cluster's assigned nugget IDs

The Haiku gate does not count retries — retry tracking is coordinator-level bookkeeping.
Phase 2.7-QG always emits a fresh PASS/FAIL verdict regardless of attempt number.

---

## Rules

- Parse only the `nugget_id` field from each entry in `dispositions:`. Ignore `op`,
  `target`, `section`, and `reason` — they are not coverage signals.
- If the Phase 2 scratch file has no `dispositions:` frontmatter block at all, treat it
  as FAIL with `missing_nugget_ids` = all assigned IDs (the entire assigned set is absent).
- If `dispositions:` is present but empty (`dispositions: []`), treat as FAIL with
  `missing_nugget_ids` = all assigned IDs.
- IDs are compared as exact strings. Do NOT normalize case, whitespace, or separators.
- Both the assigned set (`[ASSIGNED_NUGGET_IDS]`) and the emitted set (`dispositions:`) use
  the Phase 1 canonical `batch-N-M` (hyphen-separated) format. A pure set-membership diff
  applies: if a nugget ID is in the assigned set but absent from `dispositions:`, emit FAIL
  and name the missing IDs.

<!-- Review: the Staff Engineer R1 Findings 1+3+6 — format-divergence FAIL rule removed. It described the
     upstream bug (Clustering emitting slash-format while Phase 1 used hyphen-format). With
     Clustering fixed to carry Phase 1 canonical batch-N-M IDs, both sides are now the same
     format. Missing-ID FAIL behavior is preserved; format-divergence check is designed out. -->

- Write the verdict file before returning your summary. The coordinator reads from disk.
