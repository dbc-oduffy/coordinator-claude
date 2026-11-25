<!-- canonical source for subagent-box-guards — edit here; injected via `contract_blocks:`, not paste-governed. -->

## Box Guards You Will Meet

- **pytest is the EM's and `coordinator:test-runner`'s.** A subagent's own `pytest` is denied; finish the edit, then name the exact test command in your report for the EM to run.
- **Every `python`/`pytest` spawn carries all five thread caps on the same command**: `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, each a positive integer within the box cap (the denial names it). Put them as a leading `KEY=n ` prefix on each command itself; an `export`, even earlier in the same call, does not satisfy the guard.
- **A guard-denied compound command runs none of its parts.** Re-issue the non-denied parts (`mkdir`, a file write) as separate calls and confirm they landed.
- **`rm -rf` is guarded.** Leave your scratch in place and name its path in your report for the EM.
