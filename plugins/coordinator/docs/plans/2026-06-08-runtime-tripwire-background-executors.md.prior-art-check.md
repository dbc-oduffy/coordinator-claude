---
title: Prior-Art Check — 2026-06-08-runtime-tripwire-background-executors
created: 2026-06-08
author: prior-art-checker
status: implemented
kind: prior-art-check
plan: plugins/coordinator/docs/plans/2026-06-08-runtime-tripwire-background-executors.md
---

## Prior-Art Verification

**Plan:** `plugins/coordinator/docs/plans/2026-06-08-runtime-tripwire-background-executors.md`
**Verdict:** WARN
**Claims checked:** 22
**Conflicts:** 2 | **Compatible-but-relevant:** 5 | **Silent:** 15
**Corpora consulted:** project-wikis (124 files indexed) | global-wikis (35 files indexed) | lessons.md (not checked — capture queue) | improvement-queue (`~/.claude/state/coordinator-improvement-queue.md`)

---

### Conflicts (plan contradicts prior art)

- **Claim #11 — hooks.json registration: both new hooks added to the empty-matcher PostToolUse block:** The plan proposes registering both `runtime-tripwire-advisory.sh` and `runtime-tripwire-em-check.sh` in the existing empty-matcher PostToolUse block. The EM-side hook (`runtime-tripwire-em-check.sh`) reads `dispatched-agents.txt`, which is written by `track-dispatched-agents.sh`. The plan does not specify `async: false` for these hooks, and the platform-gotcha precedent requires that any hook whose output is consumed by a subsequent hook or tool must be synchronous.
  - **Plan asserts:** "Add `runtime-tripwire-advisory.sh` to the existing PostToolUse empty-matcher block ... Add `runtime-tripwire-em-check.sh` to the same block. Both `timeout: 5`. Order: after `context-pressure-advisory.sh`." No `async` field is specified.
  - **Prior art (`plugins/coordinator/docs/wiki/claude-code-platform-gotchas.md:102-106`):** "When `track-touched-files.sh` is async, the next Bash tool call (e.g. `coordinator-safe-commit` from `/handoff`) can read `touched.txt` before the hook has appended — same-session files get misclassified as orphans and rejected with 'No staged scope detected.' **Rule:** for any hook whose output is consumed by the very next tool call, keep the matcher synchronous."
  - **Prior art (`plugins/coordinator/docs/wiki/hook-best-practices.md:37-42`):** "PostToolUse hooks that produce state consumed by `coordinator-safe-commit` (touched-file lists, session-scope records) must run synchronously. Setting `async: true` means the hook process is still writing when the safe-commit helper reads — files are missed from scope detection and land outside the commit scope silently."
  - **Why this is a conflict:** `track-dispatched-agents.sh` is currently registered `async: true` (confirmed in hooks.json:300-303). The plan extends its record by adding a 4th column (`dispatched-at`). The EM-side hook reads `dispatched-agents.txt` on every PostToolUse fire. The plan's C4 spec omits an `async` field for the new hooks, leaving their default unspecified — but if the EM-side hook fires `async: true` (inheriting from no explicit setting) while `track-dispatched-agents.sh` is still writing the extended record, the EM-side hook could read a partially-written record and miss the `dispatched-at` column. Additionally, `track-dispatched-agents.sh` itself is `async: true` — if the runtime-tripwire EM check fires on the same Agent tool-result event, the dispatch-at stamp may not yet be written.
  - **Candidate directions for EM** (advisory — EM/reviewer choose):
    - `update-plan` — C4 should explicitly set `async: false` on `runtime-tripwire-em-check.sh`; assess whether the `track-dispatched-agents.sh` async setting poses a race for the EM-side hook on the same Agent event
    - `update-prior-art` — if empirical testing shows the ordering is safe (Agent PostToolUse hooks fire in hooks.json array order with each completing before the next), the wiki rule needs qualification
    - `both` — the plan should add the `async` field explicitly; the wiki should add a note about inter-hook ordering within a single event
  - **Lean:** `update-plan` is more likely — the prior art is well-established and backed by two production incidents. The C4 spec should add `async: false` to `runtime-tripwire-em-check.sh` and verify the ordering relative to `track-dispatched-agents.sh` on the Agent matcher.

---

- **Claim #9/C3 — `track-dispatched-agents.sh` extension with `dispatched-at` column:** The plan extends `track-dispatched-agents.sh` and asserts a backward-compat path for legacy 3-column records (`dispatched-at = 0`). The test suite (`test-track-dispatched-agents.sh`) currently asserts a 3-column record shape as the passing contract (T1 asserts `COL1`, `COL2`, `COL3` only; T5 seeds a "legacy bare-agentId" as the 1-column shape). The plan's backward-compat claim is correct in direction but the existing test suite will fail T1 (which expects exactly 3 columns) after the schema extension unless updated.
  - **Plan asserts (C3):** "Append `\t$(date +%s)` to the existing record line. Update file-header comment to document new column. Legacy-record read in `coordinator-safe-commit` (or wherever): missing 4th column → treat as 0."
  - **Prior art (`hooks/scripts/tests/test-track-dispatched-agents.sh:88-95`):** `COL1=$(echo "$LINE" | cut -f1)` / `COL2=$(echo "$LINE" | cut -f2)` / `COL3=$(echo "$LINE" | cut -f3)` / `if [[ "$COL1" == "$VALID_AID" && "$COL2" == "claude-opus-4-5" && "$COL3" == "executor" ]]; then / pass ...` — T1 asserts exactly the 3-column content and would pass with a 4-column record (cut -f3 still returns the 3rd column correctly), but other tests may be shape-sensitive.
  - **Why this is a conflict:** The existing test file (`test-track-dispatched-agents.sh`) does not assert the presence or absence of a 4th column, so T1 technically passes after the extension. However, the plan's C6 chunk writes NEW test scripts and cites the existing test as the "pattern shape" — if the extension does not update the existing T1-T9 test script to cover the 4-column shape, the regression net is incomplete. More critically, the plan's C3 hard constraint says "sweep `git grep -l dispatched-agents.txt` for readers and verify each gracefully handles 4-column or returns column 1 only" — this is correct, but the existing tests in `test-track-dispatched-agents.sh` are not listed as a C3 write target and will need updating.
  - **Candidate directions for EM** (advisory — EM/reviewer choose):
    - `update-plan` — add `hooks/scripts/tests/test-track-dispatched-agents.sh` to C3's write targets (update T1 to assert 4-column shape; verify T5 still works with the extended format)
    - `update-prior-art` — no wiki change needed; this is a test-coverage gap in the plan, not a doctrine conflict
  - **Lean:** `update-plan` — the test file is an existing reader of `dispatched-agents.txt` that the C3 hard constraint's own sweep would surface.

---

### Compatible-but-relevant (plan should cite or align)

- **Claim #1 — PostToolUse empty-matcher hooks fire in subagent sessions:** The plan asserts that hooks fire in subagent sessions because "hook config is inherited" and treats this as the mechanism for the agent-side nudge. The platform-gotchas wiki has a directly relevant entry on `CLAUDE_CODE_SESSION_ID` inheritance that intersects with the subagent-detect mechanism.
  - **Plan covers:** "the agent-side hook fires in *both* EM and subagent sessions (empty matcher inherited). It distinguishes by checking whether `$SESSION_ID` appears under `.git/coordinator-sessions/.agents/*/em-session-id.txt`"
  - **Prior art (`plugins/coordinator/docs/wiki/claude-code-platform-gotchas.md:33-50`):** "`CLAUDE_CODE_SESSION_ID` ... the subagent inherits the *dispatching* EM's id — exactly the cross-session linkage that the `.agents/<aid>/em-session-id.txt` back-pointer reconstructs the hard way."
  - **Subtype:** `cite`
  - **Suggested action:** The plan's subagent-detect heuristic (SESSION_ID lookup under `.agents/*/em-session-id.txt`) is the right mechanism, and the platform-gotchas entry confirms that `CLAUDE_CODE_SESSION_ID` in a subagent is the EM's session ID — which is what `em-session-id.txt` stores. The plan should cite this platform behavior in R1 (Risk 1) to strengthen its rationale, and C2/C3 specs should note which env var to read (`CLAUDE_CODE_SESSION_ID` vs `SESSION_ID` extracted from hook stdin).

---

- **Claim #7 — EM-side hook self-throttle 5 min via same pattern as `context-pressure-advisory.sh:100-115`:** Compatible — the pattern is well-established. There is one cross-cutting note about `async: true` on throttle-sentinel-using hooks.
  - **Plan covers:** "Self-throttle 5 min via `/tmp/runtime-tripwire-em-throttle-${SESSION_ID}` (same pattern as `context-pressure-advisory.sh:100-115`)"
  - **Prior art (`plugins/coordinator/docs/wiki/claude-code-platform-gotchas.md:108-112`):** "If `track-touched-files.sh` runs with `async: true`, it races against `coordinator-safe-commit`'s reads of `touched.txt`. This causes same-session files to be misclassified as orphans ... Fix: set `async: false` (default) on this hook."
  - **Subtype:** `cite`
  - **Suggested action:** The throttle pattern is sound. The plan should confirm whether the EM-side hook's `async` setting matters for the sentinel write itself (it doesn't since the sentinel is read only by the same hook instance on the next fire, not by a concurrent consumer). No change needed, but the `async` field should be explicitly stated in C4 to avoid ambiguity.

---

- **Claim #6 — Threshold defaults Opus 25 / Sonnet 15 / Haiku 10:** No conflict. The compaction-advisory's calibration note (2026-05-27) establishes that Opus/1M sessions have substantial runway vs. Sonnet/200K, which supports the asymmetric threshold design.
  - **Plan covers:** "Per-model thresholds default to Opus 25 min / Sonnet 15 min / Haiku 10 min"
  - **Prior art (`plugins/coordinator/hooks/scripts/context-pressure-advisory.sh:119-130`):** "Calibration (2026-05-18, observed on Opus 1M): auto-compaction now fires at ~60% of context window. ... Opus is the EM's primary system, and a too-large window only delays warnings (it never fires a false CRITICAL), which is the safer failure direction."
  - **Subtype:** `cite`
  - **Suggested action:** The compaction-advisory's bias-toward-Opus rationale ("too-large window only delays warnings ... safer failure direction") directly supports the plan's unknown-model → Opus default. The plan should cite this explicitly in C1's spec for the unknown-model fallback.

---

- **Claim #22 — This plan is the actuator for the "chunk-sizing failures surface as runtime tripwires (>15min wall-clock)" improvement-queue entry:** The plan's entire premise has direct prior-queue precedent.
  - **Plan covers:** (implicitly) "Make the existing 15-min executor-runtime ceiling actuator-backed"
  - **Prior art (`~/.claude/state/coordinator-improvement-queue.md:93`):** "2026-06-02 | claude-unreal-holodeck | tasks/lessons.md:58 | Fan-out aggression matches plan substrate enrichment — disjoint-write-targets is the wave-width count, not 'a manageable number of chunks'; corollary: **chunk-sizing failures surface as runtime tripwires (>15min wall-clock); EM owns the clock and re-splits without waiting for PM** | proposed target: coordinator/docs/wiki/dispatching-parallel-agents.md (Executing a Fan-Out Wave) + coordinator/CLAUDE.md § Subagent Dispatch HARD RULE"
  - **Subtype:** `cite`
  - **Suggested action:** The improvement-queue entry proposes landing this in `dispatching-parallel-agents.md` and `CLAUDE.md § Subagent Dispatch HARD RULE`. The plan addresses the CLAUDE.md pointer (AC9/C5) but does not cite `dispatching-parallel-agents.md` as a doctrine surface to update. The new `docs/wiki/runtime-tripwire.md` should cross-reference `dispatching-parallel-agents.md`, and the queue entry should be closed when this plan ships (delete the line per backlog-prune-discipline; commit subject + git log carries the audit trail).

---

- **Claim #13 — Autonomous-run detection via `/tmp/autonomous-run-${PARENT_EM_SESSION_ID}`:** Compatible pattern, directly modeled on context-pressure-advisory.sh. One prior-art note: the sentinel cleanup in `context-pressure-advisory.sh` is scoped to the current SESSION_ID to avoid cross-session deletion.
  - **Plan covers:** "Autonomous-run-aware: read `/tmp/autonomous-run-${PARENT_EM_SESSION_ID}` (looked up via the .agents back-pointer)"
  - **Prior art (`plugins/coordinator/hooks/scripts/context-pressure-advisory.sh:248-249`):** "find /tmp -maxdepth 1 `\( -name "context-pressure-*${SESSION_ID}*" -o -name "autonomous-run-*${SESSION_ID}*" \)` -mmin +1440 -delete 2>/dev/null || true" — cleanup is SESSION_ID-scoped.
  - **Subtype:** `cite`
  - **Suggested action:** C2 spec should note that the `autonomous-run-*` sentinel cleanup (stale removal after 24h) should be scoped to the subagent's own session, not a global cleanup, matching the existing pattern.

---

### Silent areas (no prior art found)

- Claim #2 — Subagent-detect via `.agents/*/em-session-id.txt` membership check: no prior art on this specific detection pattern used in hooks (the ledger structure exists but is not used by any existing hook for session-type discrimination).
- Claim #3 — Reusing `grep -m1 -oE '"model"...'` from `context-pressure-advisory.sh:154` in a new script: no prior art on cross-script library extraction of this pattern.
- Claim #4 — Full model-family case pattern exactly as in context-pressure-advisory.sh: no prior art — plan directly cites the existing script and replicates the pattern (COMPATIBLE, but not an independent prior-art topic).
- Claim #5 — Unknown-model → Opus default in the thresholds lib: no prior doctrine entry beyond the compaction advisory's inline comment cited above.
- Claim #8 — Bark-once sentinel scoped to TRANSCRIPT_HASH (agent-side): no prior art on TRANSCRIPT_HASH as sentinel scope key beyond the context-pressure-advisory use.
- Claim #10 — Legacy 3-column records parse with `dispatched-at = 0`: no prior art on backward-compat parsing for this specific schema extension.
- Claim #12 — Wrap-shape prescription text in `additionalContext`: no prior art on the specific prescribed text.
- Claim #14 — `hooks/scripts/lib/` as a shared bash library location: no prior art establishing this directory convention — it is a new convention. The plan creates it without citing prior art on the library location or the `lib/` subdirectory convention.
- Claim #15 — New `docs/wiki/runtime-tripwire.md` doctrine surface: no prior wiki on executor runtime monitoring.
- Claim #16 — CLAUDE.md pointer append (one-line): compatible with `document-bloat-trim.md` doctrine; no conflict.
- Claim #17 — `set -uo pipefail` with `|| true` guards (fail-open): compatible with context-pressure-advisory.sh header comment on `-e` omission; no independent entry needed.
- Claim #18 — Bash 3.2 / BSD coreutils portable: established doctrine (CROSS-PLATFORM-PORTABILITY tripwire); plan correctly asserts it in AC8 and C1 hard constraints.
- Claim #19 — Dispatch sequencing C1 → C2+C3+C5 parallel → C4 → C6: no prior art on sequencing; consistent with file-overlap dispatch-gate doctrine.
- Claim #20 — No auto-kill; no `Bash run_in_background` coverage: OOS framing has architectural backing per problem-set; no conflict with prior art.
- Claim #21 — C3 sweeps `git grep -l dispatched-agents.txt` readers: no prior art entry; consistent with the shared-symbol sweep doctrine in CLAUDE.md § Pre-Dispatch Verification.

---

### Verdict logic

**WARN** — two conflicts surfaced:

1. **C4 async/ordering conflict** — the plan omits `async` fields for the new hooks in hooks.json. Platform doctrine (claude-code-platform-gotchas.md + hook-best-practices.md) requires explicit `async: false` for any hook reading state written by a concurrent hook on the same event. The EM-side hook reads `dispatched-agents.txt` which is written by `track-dispatched-agents.sh` (currently `async: true`). The plan must either (a) declare `async: false` on `runtime-tripwire-em-check.sh` and verify the inter-hook ordering, or (b) confirm that the EM-side hook fires on a different event than the `track-dispatched-agents.sh` write (Agent PostToolUse vs. empty-matcher PostToolUse — the ordering on the same event within a session needs verification).

2. **C3 test-update gap** — `hooks/scripts/tests/test-track-dispatched-agents.sh` is an existing reader of `dispatched-agents.txt` not listed in C3's write targets. C3's own hard constraint mandates a sweep of all readers; the existing test file must be in scope.

Neither conflict blocks review categorically — both are `update-plan` candidates. EM should fold these into the plan before Opus reviewer dispatch.

---

**Cost estimate:** ~7,800 tokens estimated (22 claims × ~4 corpus reads average; 6 full-file reads of substantive wikis/scripts)
