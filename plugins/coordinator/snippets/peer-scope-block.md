<!-- canonical source for the fan-out peer-scope prohibition block -->
<!-- Spec backlink: docs/plans/2026-05-27-fan-out-default-doctrine.md §Chunk 1 -->
<!--
Purpose: Template for the Out-of-scope peer-work block injected into every parallel-wave
executor prompt by bin/fan-out-dispatch.sh. Externalised from dispatching-parallel-agents.md
§ Peer-Scope Prohibition (the Staff Engineer R1/Disposition 8: repoint, no sync script — wiki is human-read)
so the helper and the wiki cite one source.

The {{peer_chunks}} placeholder is replaced at emit-time with the list of peer chunk entries,
one per line in the form:
  - <chunk-id> (files: <comma-separated file list>) — concurrent executor handles this
-->

## Out-of-scope — peer work, do NOT touch

{{peer_chunks}}

If a peer's expected output appears missing on disk, assume a peer is on it — do NOT extend scope to "fix" it, do NOT touch peer files even if your work seems blocked by their absence. If genuinely blocked, return with a blocker report.
