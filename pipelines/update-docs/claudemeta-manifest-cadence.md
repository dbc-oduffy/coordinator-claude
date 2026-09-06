---
name: update-docs/claudemeta-manifest-cadence
description: "Regenerate and commit the claudemeta keep-manifest when its --check drifts. Inlined by /update-docs Phase 11k."
version: 1.0.0
---

# claudemeta Manifest Cadence

> **Inlined by `/update-docs` Phase 11k.** DoE-specific — `state/reference/claudemeta-keep-manifest.txt`
> is this repo's own derived artifact, projecting the retrieval-priority ruling at
> `state/reference/state-subtree-retrieval-priority-index.md` for an external indexer. Not a
> generic OSS pipeline concern. No-op in any repo without the generator.

## Step 1: Check, Regenerate-and-Commit on Drift

Absent generator: skip the phase, no line in the report. Present:

```
python state/reference/generate-claudemeta-manifest.py --cadence
```

One process rather than a shell conditional — the ceremonies calling this run on Windows as often
as POSIX, and structural bash is a portability defect here. `--cadence` checks first and returns
silently at exit 0 when the manifest is already current; regeneration is skipped, not re-run.

No confirmation prompt — the PM ruled out human-in-the-loop waiting here. The pathspec is exactly
`state/reference/claudemeta-keep-manifest.txt`, never a wider one.

## Step 3: Report (EM)

Fold the generator's own stdout line ("claudemeta manifest regenerated: N files") into the Phase 14
summary as the `**claudemeta Manifest:**` line. On a clean `--check` or a missing generator: no line.
