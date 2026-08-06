<!-- canonical source for the fan-out peer-scope prohibition block -->
<!--
Purpose: Template for the Out-of-scope peer-work block injected into parallel-wave prompts.
Externalised into this one snippet so every caller shares a single source rather than each
re-deriving its own peer-scope prohibition text.

Used by two callers with different entry shapes for the {{peer_chunks}} placeholder:

  bin/fan-out-dispatch.py (executor wave):
    - <chunk-id> (files: <comma-separated file list>) — concurrent executor handles this

  bin/fan-out-integrator.py (integrator wave):
    - <slice-id> (sidecar: <sidecar-path>, files: <comma-separated file list>) — peer integrator
      is running RIGHT NOW in parallel; do NOT wait for it, do NOT collate its findings with yours,
      your scope is yours alone
-->

## Out-of-scope — peer work, do NOT touch

{{peer_chunks}}

If a peer's expected output appears missing on disk, assume a peer is on it — do NOT extend scope to "fix" it, do NOT touch peer files even if your work seems blocked by their absence. If genuinely blocked, return with a blocker report.
