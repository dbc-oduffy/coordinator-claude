# `computed-skills-conversion-checklist.md` run — B1 cluster

> Purpose: the recorded outcome of running `coordinator/docs/wiki/computed-skills-conversion-checklist.md`
> (the DR-090 discharge instrument) against the three B1-converted surfaces, as AC11 of
> `docs/plans/2026-07-24-b1-ceremony-complete-computed-conversion.md` requires. Prior sweeps had
> confirmed the named tells absent by direct re-read but never recorded a run of this specific
> instrument — this file is that record.

Surfaces reviewed (current on-disk state, post B1-C3/C6/C7): `coordinator/commands/workday-complete.md`
(176 lines), `coordinator/commands/workweek-complete.md` (605 lines at review, since 611 after the
AC6 spec-backlink relocation), `coordinator/commands/autonomous.md` (44 lines).

| Checklist item | workday-complete.md | workweek-complete.md | autonomous.md |
|---|---|---|---|
| Intent + a named op only | PASS — every fence names an existing settings-home CLI | PASS | PASS — delegates to `autonomous-verb` |
| Zero command fences | PASS — 5 fenced lines, each exactly one metachar-free CLI invocation | PASS — remaining fences are PM-facing OUTPUT TEMPLATES (Surface-to-PM summary blocks), not command payloads; zero shell/python payload fences | PASS — no fences |
| Zero narrated procedures | PASS — no ordinal/"then"-joined mutation sequence; residual "then"s are dispatch-shape prose for a Sonnet worker (judgment residue, AC8), not mechanical steps | PASS — same pattern (Step 8.5 XL-entry template, version-consistency gate description) | PASS |
| Zero placeholder-by-inference | PASS — no `[choose one\|placeholder]` tokens; the one `'<json map ...>'` apply-arg shape is a genuine EM-supplied decisions map (per AC8), not an inference gap | PASS | PASS |
| Zero call-site invariants | PASS — grepped for restated guardrails; none found | PASS | PASS |
| The discharge test | PASS — every rule ties to a directive/judgment_point/gate in the assembler envelope (AC1/AC2/AC8) | PASS | PASS — sentinel toggle is the op, First-Officer doctrine relocated to `docs/wiki/autonomous-mode-first-officer-posture.md` (AC4) |
| Tutorial prose deletes, does not relocate | PASS — no archived "how to run a CLI" tutorial section | PASS | PASS |
| The completion test (shorter + loses imperative mood) | PASS — 553→176 lines (AC14) | PASS — 892→605 lines (AC14) | PASS — retains only the mechanical verb + wiki pointer |
| Push, not pull (realization #6) | PASS — grep for classification/branch vocabulary (`if classification`, `branch on`, `if a peer`, `if memo`, `if spinoff`, `Memo Branch`) returns empty | PASS — same grep, empty | PASS |
| Delivery seam exercised (realization #5) | PASS — AC15(a)/(b)/(c) live-exercised on macOS, forwarder-drift repaired (see AC15 row, C8 `close_out_macos`) | PASS — same C8 dogfood | N/A — no assembler seam for this surface (verb delegation only) |
| Ergonomics/discharge test (AC-12/AC16) | PASS — 2 compute calls + fixed JP set replaces ~15-20 self-navigated prose steps (AC16) | PASS | PASS |

**Outcome: PASS on all applicable items, all three surfaces.** No new findings — this run
confirms, via the named instrument rather than reviewer memory of DR-090's prose, what the prior
2026-07-25 AC sweep had already found by direct re-read.

Run 2026-07-25 as part of `docs/plans/2026-07-24-b1-ceremony-complete-computed-conversion.md`'s
AC11 close-out.
