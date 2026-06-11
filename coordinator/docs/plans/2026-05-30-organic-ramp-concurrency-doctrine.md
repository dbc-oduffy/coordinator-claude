---
title: Organic-Ramp Concurrency Doctrine — Replace the Undated 6-8 Hard Cap
date: 2026-05-30
scope_mode: feature
status: draft
authoring_session: work/striker/2026-05-26to30
problem_set: inline (§ Problem) — converged via PM exploration 2026-05-30
supersedes_assumption: docs/plans/2026-05-27-fan-out-default-doctrine.md §68 (the "6-8 cap is OOS-to-change" carve-out)
---

# Organic-Ramp Concurrency Doctrine

## Problem

EMs are reticent to dispatch more than 4-6 concurrent agents — observed behaviour the PM
flagged 2026-05-30. The root cause is doctrine, not hardware:

- The **"6-8 hard cap"** in `docs/wiki/dispatching-parallel-agents.md § Concurrency Budget`
  has **no recorded primary crash incident.** It is self-described as *"a heuristic calibrated
  from observed crash thresholds, not a platform-documented limit"* — but the crash event was
  never written to any lesson, decision record, or dated incident. It has been folklore-cited
  since the wiki was created (2026-05-06).
- The cap was born from **orchestrator-multiplication** fear (a wave of Opus orchestrators each
  spawning 6 sub-agents → 200+ real agents), **never from leaf-worker load and never from
  hardware.** The overwhelming common case — executors, reviewers, scouts — spawns *nothing*,
  so the original rationale does not even apply to it.
- The number is mechanically encoded as a **HARD STOP gated behind "a PM call"** (the
  `>8 chunks → WARNING → PM authorisation` machinery), which reads to EMs as *"expansion is
  forbidden territory,"* so they stop at the conservative `4-6` pilot figure and never expand.

The fix is to replace the flat numeric cap with an **organic ramp-until-degradation** model that
mirrors how the PM already governs aggregate load (spawn only as many windows as the device
comfortably runs), pushed down to the per-session wave-sizing decision.

## Converged design (PM decisions, 2026-05-30)

1. **No cap on concurrent coordinators** (top-level EM sessions/windows). The human governs
   aggregate device load organically.
2. **Each EM reasons ONLY about its own session.** No cross-session accounting, no querying what
   else is active on the device.
3. **Within a session: pure organic ramp** — launch a pilot, observe *this session's own*
   responsiveness, expand until the EM sees its own degradation. **No fixed per-session numeric cap.**
4. **Two surviving hard rules** (everything else about a flat cap and cross-session worry is deleted):
   - **(a) Ramp, don't pre-batch.** This IS the organic-governance mechanism — reframed as the
     *expected scaling path*, NOT a timidity gate.
   - **(b) Count your own fanout.** Orchestrators multiply (8 orchestrators × 6 sub-agents = a
     48-agent wave you own); leaf workers don't. This is the one piece of arithmetic that survives.
5. **The `min(16, cpu_cores - 2)` cap is real but scoped to Workflow scripts only.** It is
   **platform-enforced by the Workflow runtime** on `agent()` calls *inside a Workflow script*
   (per the Workflow tool contract), NOT something the coordinator computes and NOT something
   that applies to the manual fan-out path. The manual Agent-tool fan-out path (what
   `fan-out-dispatch.sh` / `coordinator:fan-out` drive) has **NO automatic structural backstop**
   after the HARD STOP is removed — rule (b) "count your own fanout" arithmetic + the
   cores-scaled NOTE + organic window-governance are the guards, BY DESIGN, PM-affirmed
   2026-05-30. Do NOT let the Workflow cap launder the safety story for a path it does not cover.
   <!-- the Staff Engineer F4: PM-decided — Workflow cap is real but scoped to Workflow scripts only; manual fan-out has no automatic backstop by design, PM-affirmed. -->
6. **Hardware-once-at-setup — USED for the soft ramp-reminder threshold (revised 2026-05-30 on
   PM's 60-agent datapoint).** Two distinct reasons to ramp exist, with different scaling laws:
   *blast-radius / observe-before-commit* (hardware-independent — the always-on ramp practice) and
   *overload plausibility* (hardware-dependent — "is this wave big enough that the box feels it?").
   The PM reports **60 concurrent agents ran on Striker without strain**, so a flat low threshold
   (8, or even 12) for the overload-NOTE is the timidity bug one notch up. The overload-NOTE
   threshold is therefore **derived ONCE from logical CPU cores at `coordinator:setup`** and
   written to `registry.local.toml` as `fan_out.large_wave_threshold`, read by the helper via
   `machine-local get` — exactly the *"cover hardware once at setup, don't repeat it"* pattern.
   This is a **soft NOTE trigger, never a cap.** The `min(16, cores-2)` Workflow-runtime cap (#5)
   is separate and still platform-enforced (on Workflow scripts only — not on the manual fan-out
   path; see #5 above).
   <!-- the Staff Engineer F4: reconcile with F4 — Workflow cap does not protect the manual path. -->
7. **Legibility reframe.** The mechanism's nudges all become **soft, offer-shaped NOTEs**
   ("this is large — ramp it"), never a `WARNING` HARD STOP demanding PM authorisation. The only
   HARD GATE that remains in the fan-out path is the **file-overlap collision** (a real
   correctness gate, unrelated to concurrency).

## The pinned cap-breach contract (load-bearing — read before editing any of Chunks 2-4)

The `.sh` output strings, the skill's grep, and the test assertions form one contract. Pinning it
here so the three write-disjoint chunks can be authored concurrently and verified at merge:

| Element | OLD | NEW (pinned) |
|---|---|---|
| `fan-out-dispatch.sh` threshold | `CHUNK_COUNT > 8` | `CHUNK_COUNT >= LARGE_WAVE_THRESHOLD`, where the value comes from `machine-local get fan_out.large_wave_threshold` (set once at setup, § C6), env-override `LARGE_WAVE_THRESHOLD` wins, fallback `16` when machine-local is unset/unavailable (OSS user pre-setup) — never the old `8` |
| Emit prefix | `WARNING:` | `NOTE:` (soft, offer-shaped — consistent with the existing fat-chunk `NOTE:` at `:307`) |
| Emit text | `WARNING: N chunks exceeds the 6-8 concurrency cap; a wave this size is a PM call …` | `NOTE: N concurrent agents is a large wave (≈3× cores) — a speed advisory, NOT a cap: past here CPU scheduling contention may start tapering throughput, but CPU/GPU parallelize fine, so ramp pilot→expand and watch RAM/VRAM commit more than CPU. If any chunk is an orchestrator, count its fanout. Your call, not a PM gate. See § Concurrency Budget.` (keeps the literal `large wave` substring the tests/skill match) |
| Heredoc reminder (`:318-320`) | `Concurrency cap: 6-8 concurrent … launch 4-6 agents` | Organic-ramp text: ramp pilot→expand, count fanout for orchestrators, no fixed cap; the only hard cap is the platform's `min(16, cores-2)` inside Workflow scripts. |
| Skill Step 1.5 | "Cap-Breach Gate (HARD STOP)" greps `WARNING:`, demands PM auth | "Large-Wave Ramp Reminder" — surfaces the soft `NOTE:` if present; **no HARD STOP, no PM gate**; EM ramps and proceeds. **NO executable grep logic** — the dead `grep -qF "WARNING:"` CAP_BREACH block at SKILL.md:110-112 is DELETED ENTIRELY (the large-wave NOTE is informational; Step 1.5 no longer gates on a grep). <!-- the Staff Engineer F2: dead-grep deletion pinned here. --> |
| Skill Step 2 | bands `1-6 / 7-8 / >8` | organic ramp: pilot→observe→expand; count fanout; no fixed cap |
| Test D3 (`:342`) | `_assert_stderr_contains … "6-8"` | assert stderr contains the ramp reminder (`pilot` AND `ramp`) and does NOT contain `6-8` |
| Test E (`:347-372`) | `>8 → WARNING / PM call / "9 chunks"` | Boundary test: export `LARGE_WAVE_THRESHOLD=N` (test's explicit choice, e.g. `N=12`); feed exactly N chunks → assert NOTE fires and contains `large wave`; feed N-1 chunks → assert NOTE does NOT fire. Test proves the boundary (N triggers, N-1 does not), not merely that a large number trips it. Does NOT contain `WARNING` or `PM call`. <!-- the Staff Engineer F9: boundary must be proved at N and N-1; N is self-contained, not dependent on fallback or core count. --> |

**Resolution order for the threshold** (helper reads, highest priority first): `LARGE_WAVE_THRESHOLD`
env var → `machine-local get fan_out.large_wave_threshold` (written once at setup, § C6) → fallback
`16`. The value gates a *soft NOTE*, not a dispatch — so the fallback being approximate is fine;
the setup-derived value is what makes a beefy box stop nagging at single digits. **Tests pin
`LARGE_WAVE_THRESHOLD` explicitly** so they don't depend on the runner's core count (C4).

**Env-var precedence clarification (prior-art CONFLICT #1):** `LARGE_WAVE_THRESHOLD` is a
**script-level convenience override** the helper reads *before* it calls `machine-local get` — it is
NOT a `MACHINE_LOCAL_<KEY>`-namespaced variable inside the registry reader's own resolution chain.
So putting it *above* the registry value does NOT contradict `machine-local-registry.md §4` ("ambient
env-vars rank below the deliberate .toml layers"), which governs the reader's *internal* chain. The
distinction must be stated in the C2/C6 briefs so an executor does not "fix" the precedence to match
§4: a per-invocation `LARGE_WAVE_THRESHOLD=100 bash fan-out-dispatch.sh …` is a deliberate one-shot
operator override of a soft nudge, which is exactly the semantics we want on top of the persistent
registry default.

**Setup derivation (PM-set 2026-05-30):** `fan_out.large_wave_threshold = 3 × logical_cores`. On a
24-core Striker this lands 72; on an 8-core laptop, 24. **Reframed from cap to speed-taper advisory:**
the PM clarified that core count is not a cap at all — a CPU time-slices far more than `cores` tasks,
so past `~n` agents you pay scheduling-contention tax, you don't stop. The threshold marks where
parallel *returns may start tapering*, not a ceiling. Because we optimize for speed, the target is to
*maximize* utilization; the dimension that actually degrades the machine is **memory commit (RAM/VRAM)**,
not CPU/GPU — so the cores proxy is a first cut, and a memory-commit-aware signal is its successor
(filed to the central improvement queue). The `3×` multiplier was the open knob (O1); PM set it to 3×.

SHIPPED 2026-05-30 (commit 39927cbb): the successor signal landed as `bin/probe-memory-headroom.sh`
(cross-platform best-effort RAM/VRAM read) wired into `fan-out-dispatch.sh` as a distinct
"headroom tight" NOTE that fires below an absolute RAM/VRAM floor regardless of wave size. The cores
proxy is retained as the complementary cheap always-available signal; the two NOTE phrasings are kept
disjoint so the cores-proxy regression net stays valid. Improvement-queue entry resolved.

## Surfaces & out-of-scope

**In scope** (every literal `6-8` / `4-6` / cap-breach occurrence that refers to the *general
concurrency cap*):

| # | File | Lines | What changes |
|---|---|---|---|
| C1 | `docs/wiki/dispatching-parallel-agents.md` | 19-28 (§ Concurrency Budget), 187 | Rewrite the section to organic-ramp doctrine; fix the `6–8` reference at :187 |
| C2 | `bin/fan-out-dispatch.sh` | 280-285, 294 (comment), 312-328 (heredoc) | Threshold mechanism + heredoc per pinned contract |
| C3 | `skills/fan-out/SKILL.md` | 3 (desc), 81, 105-116 (Step 1.5), 120-127 (Step 2), 179 (failure table) | Ramp-reminder semantics per pinned contract |
| C4 | `bin/fan-out-dispatch.test.sh` | 342 (D3), 347-372 (Test E) | Assertions per pinned contract |
| C5 | `README.md` | 142 | Drop "up-to-6–8"; "ramp pilot→expand" |
| C6 | `commands/setup.md` (or the setup skill) + a small helper | new step | Measure logical cores once, write `fan_out.large_wave_threshold` to `registry.local.toml` via the machine-local registry. Idempotent/reentrant (setup is re-run-safe). C2 reads it. |

**Explicitly OUT of scope** (these are *not* the general cap — leave untouched):
- `docs/wiki/dispatching-parallel-agents.md:168` — generic "a concurrency cap" as an *example* of
  a load-bearing scalar; the sentence is about pinning shared scalars, not about the value 6-8.
  Re-read at edit time; touch only if it now reads as stale. (EM judgment, default leave.)
- Per-pipeline phase-sizing tables: `architecture-survey.md:270`, `pipelines/bug-sweep/pattern-library.md:52`,
  `pipelines/artifact-distillation/PIPELINE.md:453`. These are pipeline-specific agent-count
  calibrations, NOT the general concurrency cap.
- `hooks/scripts/context-pressure-advisory.sh:125,210` — "6-8 **bytes/token**", unrelated.
- Both `CLAUDE.md` files — already cap-number-free; the coordinator HARD RULE (§ Subagent Dispatch)
  and global `~/.claude/CLAUDE.md:53` express small-and-many/ramp doctrine *without* a number.
  **No edit needed.** (Verified 2026-05-30.)
- `docs/plans/2026-05-27-fan-out-default-doctrine.md:68` — historical plan; leave as-is. Its
  "6-8 cap is OOS-to-change" carve-out is recorded as superseded in this plan's frontmatter, not
  by editing the closed plan.

## Chunks (write-disjoint — fan-out candidate)

All five chunks edit **disjoint files**. The only coupling is the **pinned contract above**
(C2 emits / C3 greps / C4 asserts) — that interface is pinned, so the chunks author concurrently
and the EM verifies at merge by running the test. Per `dispatching-parallel-agents.md`
§ Dispatch-Gate Taxonomy (Author vs. verify): pinned interface → fan out → verify at merge.

- **C1 — wiki § Concurrency Budget rewrite.** Replace lines 19-28 with organic-ramp doctrine:
  the two surviving rules, the no-cross-session-accounting principle, the `min(16,cores-2)`
  platform-backstop note (scoped to Workflow scripts — does NOT protect the manual fan-out path),
  the deletion of the flat cap and the PM-gate framing.
  - **Preserve** the existing "count your own fanout" arithmetic example currently at `:24-25`
    ("A wave of 4 orchestrators each spawning 6 sub-agents is a 24-agent wave") — it survives as
    rule (b); carry the worked example into the rewrite, don't drop it.
  - **Leaf vs. orchestrator taxonomy (qualify carefully):** When stating that leaf workers "spawn
    nothing" (rule b), apply the correct scope. Common leaf workers (executors, reviewers, simple
    file-scoped scouts) spawn nothing. BUT pipeline runners (architecture-survey, bug-sweep),
    research scouts (general-purpose / Explore doing web/codebase survey), and any deep-research
    subagent ARE orchestrators for counting purposes — apply rule (b) to them. Do NOT write
    "scouts spawn nothing" without this qualification; write instead: "most leaf workers
    (executors, reviewers, simple file-scoped scouts) spawn nothing — pipeline runners and
    research scouts are orchestrators and count."
    <!-- the Staff Engineer F6: "scouts spawn nothing" is too broad; pipeline runners and research scouts are orchestrators. -->
  - **Cite `docs/wiki/eager-agent-calibration.md`** (design-as-offers) as the doctrinal basis for
    converting the `WARNING:` HARD STOP into a soft `NOTE:` — the offer-shaped nudge is the ethos,
    not an ad-hoc choice.
  - **State plainly** that the manual fan-out path (fan-out-dispatch.sh / Agent-tool) has NO
    automatic structural backstop after the HARD STOP is removed — the NOTE + organic ramp are the
    guards BY DESIGN. Do NOT let the Workflow cap (`min(16, cores-2)`) appear to cover the manual
    path — it does not.
    <!-- the Staff Engineer F4: C1 wiki must not imply the Workflow cap protects the manual path. -->
  - **O2 NOTE rationale (reframe in the wiki):** State that on the manual fan-out path the
    cores-scaled NOTE is the SOLE hardware-legible signal between the EM and the platform ceiling
    — not redundant belt-and-suspenders but the only hardware signal available on a path that has
    no automatic backstop. Frame it accordingly (offer-shaped, not nagging), not as redundant
    confirmation of a cap that doesn't exist on this path.
    <!-- the Staff Engineer F8: NOTE is sole hardware signal on manual path, not belt-and-suspenders. -->
  - **Fix `:187`** — it currently reads verbatim *"Respects the 6–8 concurrency cap; halts and
    reports on any helper collision — never dispatches past a collision."* (shipped by the
    2026-05-27 plan). Rewrite the cap clause to the ramp model; **keep** the collision-halt clause
    (that is the real correctness gate, unrelated to concurrency). Executor: quote-match this line
    so it is not missed.
  - ~150 words of doctrine prose. Test surface: prose only — reviewed by the Staff Engineer, no automated test.
- **C2 — `fan-out-dispatch.sh`.** Implement the pinned threshold + emit-text + heredoc changes.
  Resolve the threshold in the order pinned above: `LARGE_WAVE_THRESHOLD` env var →
  `machine-local get fan_out.large_wave_threshold 2>/dev/null` → fallback **`16`** (never the old
  `8`). Test surface: C4.
- **C3 — `skills/fan-out/SKILL.md`.** Rewrite Step 1.5 (ramp reminder, no HARD STOP), Step 2
  (organic ramp), description line 3, line 81 reference, failure-table row 179. Test surface:
  the skill is prose — reviewed by the Staff Engineer; C4 indirectly covers the contract it greps.
  <!-- the Staff Engineer F2: dead-grep deletion is a REQUIRED part of the C3 executor brief. -->
  **CRITICAL — dead-grep deletion (executor must not miss this):** The current SKILL.md:110-112
  contains the following CAP_BREACH grep logic that will be a no-op after the emit changes
  (old emit was `WARNING:`, new emit is `NOTE:`):
  ```
  # Lines SKILL.md:110-112 (verbatim — executor: delete these lines entirely):
  if echo "$DISPATCH_OUTPUT" | grep -qF "WARNING:"; then
    _cap_breach_gate  # demands PM auth — HARD STOP
  fi
  ```
  **DELETE these lines ENTIRELY.** The large-wave `NOTE:` is informational; Step 1.5 no longer
  gates on any grep. If any grep is retained it MUST match the literal phrase `large wave` (NOT
  the bare `NOTE:` prefix, which would collide with the fat-chunk NOTE at fan-out-dispatch.sh:307).
  <!-- the Staff Engineer F2: executor must quote-match SKILL.md:110-112 and delete, not adapt. -->
- **C4 — `fan-out-dispatch.test.sh`.** Update D3 and Test E per the pinned contract. **This is the
  merge-gate verification: the EM runs `bash fan-out-dispatch.test.sh` after the wave and it must
  pass green.**
- **C5 — `README.md:142`.** One-line edit.
- **C6 — setup-time hardware capture (machine-local).** In the setup skill/command (alongside the
  existing `setup.md` Phase 3 machine-local writes), add an idempotent step: measure logical CPU
  cores (portable: `python3 -c 'import os; print(max(1, os.cpu_count() or 1))'` — python3 is a
  guaranteed machine-local dependency, works on macOS/Windows/Git-Bash unlike GNU-only `nproc`),
  compute `3 × cores`, and write via the **`machine-local set` primitive, guarded by a
  REGISTRY-ONLY check so a re-run never clobbers an operator's manual override** (the CLI
  self-documents `set` as "prefer over hand-editing"; do NOT hand-append TOML).
  **Amended post-review:** the guard was extracted from this inline snippet into the tested
  executable `bin/capture-fan-out-threshold.sh` (covered by `bin/capture-fan-out-threshold.test.sh`,
  14/14) so the registry-only logic cannot drift from its test; `setup.md` Step 8 now *calls* it.
  ```bash
  # VERBATIM (the logic now lives in bin/capture-fan-out-threshold.sh; this is its core)
  # Registry-only check (machine-local keys reflects only .toml layers, no env merge).
  # This ensures an operator with MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD exported at
  # setup time still gets a persistent registry entry written.
  machine-local keys | grep -qx fan_out.large_wave_threshold || \
    machine-local set fan_out.large_wave_threshold \
      "$(( 3 * $(python3 -c 'import os; print(max(1, os.cpu_count() or 1))') ))"
  ```
  <!-- the Staff Engineer F1: gate on registry-only `keys | grep -qx` not env-inclusive `has`, so an operator
       with MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD exported still gets a registry write. -->
  <!-- the Staff Engineer F5: python3 os.cpu_count() replaces GNU-only nproc; portable to macOS/Windows/Git-Bash. -->
  `fan-out-dispatch.sh` (C2) reads it via `machine-local get fan_out.large_wave_threshold 2>/dev/null`;
  the script-level `LARGE_WAVE_THRESHOLD` env var (a one-shot operator override — see the precedence
  clarification above) wins; fallback `16`. Substrate verified 2026-05-30: CLI at
  `~/.claude/bin/machine-local` exposes `get`/`has`/`set`/`keys`, registry present, `setup.md`
  already writes machine-local keys. Test surface: a small check that the helper resolves
  env → machine-local → fallback in that order (fold into C4 or a sibling test).

## Acceptance Criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|---|---|---|---|---|
| AC1 | No general-concurrency `6-8` / `4-6` cap language survives in the in-scope surfaces | `grep:` `! grep -rnE "6.?8 (concurrency\|concurrent\|hard cap)" docs/wiki/dispatching-parallel-agents.md bin/fan-out-dispatch.sh skills/fan-out/SKILL.md README.md` returns no general-cap hits | gate | pending realization |
| AC2 | `fan-out-dispatch.test.sh` passes green with the new contract | `bash:` `bash bin/fan-out-dispatch.test.sh` exits 0 | gate | pending realization |
| AC3 | The fan-out path has no count-based HARD STOP / PM-gate; the only HARD GATE is file-overlap collision; **Step 1.5 contains NO executable grep logic** (the dead-grep class is structurally impossible after C3) | `grep:` skill contains no "cap-breach … PM call" HARD STOP; `grep:` SKILL.md Step 1.5 contains no `grep -qF` or `grep -q` call; `cited:` Step 1.5 reads as a soft ramp reminder with no branch-on-output | gate | pending realization |
| AC4 | Large-wave nudge is offer-shaped (`NOTE:`, names the ramp), not mistrust-shaped (`WARNING:`/PM-auth); **emit→consume leg verified**: the phrase Step 1.5 looks for (if any surface check remains) matches what `fan-out-dispatch.sh` actually emits | `cited:` `fan-out-dispatch.sh` emit line + skill Step 1.5; `grep:` the emit string and any skill-side consumption reference use the same literal phrase | gate | pending realization |
<!-- the Staff Engineer F3: AC3 now asserts no executable grep in Step 1.5; AC4 now verifies emit→consume leg not just offer-shape. -->
| AC5 | Doctrine reads coherently for an OSS laptop operator (self-calibrating ramp, env-overridable threshold) — no Striker-specific assumption | `cited:` wiki § Concurrency Budget reviewed by the Staff Engineer for portability | advisory | pending realization |
| AC6 | The two surviving rules (ramp-don't-pre-batch, count-your-own-fanout) are stated verbatim in the wiki and the heredoc | `grep:` both phrases present in wiki + `.sh` | gate | pending realization |
| AC7 | `coordinator:setup` writes `fan_out.large_wave_threshold` (cores-scaled) to `registry.local.toml` idempotently — re-run never clobbers an existing value; **env-clobber case**: even with `MACHINE_LOCAL_FAN_OUT_LARGE_WAVE_THRESHOLD` exported at setup time, the registry key IS written (env override must not suppress the persistent write) | `bash:` `bin/capture-fan-out-threshold.test.sh` (Tests A–F: write-when-absent, no-clobber, env-clobber F7, --check-only no-mutation) — 14/14 green | gate | **realized** (capture logic extracted to tested `bin/capture-fan-out-threshold.sh`; setup.md Step 8 calls it) |
<!-- the Staff Engineer F7: env-clobber case pins F1's intended semantics — exported env must not suppress registry write. -->
| AC8 | Helper resolves threshold env-var → machine-local → fallback `16`, never the old `8`; a beefy box (machine-local set high) does NOT emit the NOTE at single-digit waves | `bash:` `fan-out-dispatch.test.sh` Test H (H1 fallback-16 boundary + never-8 floor, H2 machine-local wins over fallback, H3 env wins over registry) — 71/71 green | gate | **realized** |

## Cross-plan coordination

Scanned `docs/plans/*.md` for the in-scope file paths and the `concurrency cap` / `6-8` / `fan-out`
seams. One overlap: `docs/plans/2026-05-27-fan-out-default-doctrine.md` authored the
`fan-out-dispatch.sh` helper and the `coordinator:fan-out` skill, and at §68 declared the 6-8 cap
**out-of-scope-to-change**. This plan changes it — recorded via `supersedes_assumption` in
frontmatter. The 2026-05-27 plan is closed/shipped; per Branch C, closed plans are not edited —
the supersession note is the audit link. No live sibling plan depends on the 6-8 value. No other
overlap.

## Open Questions (surface to PM before/at review)

- **O1 — RESOLVED: multiplier is `3 × logical_cores`, and the threshold is reframed as a
  speed-taper advisory, not a cap.** The PM clarified (2026-05-30) that core count is not a cap at
  all: a CPU time-slices far more than `cores` tasks, so past `~n` agents you pay scheduling-contention
  tax, you don't stop. The NOTE marks where parallel *returns may start tapering* — advisory, watch
  throughput. Because we optimize for speed, the goal is to *maximize* utilization; the dimension that
  actually degrades the machine is **memory commit (RAM/VRAM)**, not CPU/GPU. Multiplier set to **3×**
  (24-core Striker → 72, above the proven-fine 60; 8-core laptop → 24). A **memory-commit-aware signal
  is the higher-value successor** to the cores proxy — filed to the central improvement queue.
- **O2 — does the soft NOTE earn its keep at all, or just delete the threshold mechanism? (RESOLVED: keep)**
  Decision: keep the NOTE. Rationale (updated per the Staff Engineer F8): On the manual fan-out path (which
  has NO automatic structural backstop — per Converged design #5), the cores-scaled NOTE is the
  **sole hardware-legible signal** between the EM and the platform ceiling. It is not
  belt-and-suspenders on top of a cap that doesn't exist on this path — it IS the hardware signal.
  Framed as offer-shaped (a nudge, not a gate), it gives the EM the one piece of machine-specific
  context that "ramp-don't-pre-batch" alone cannot provide. Deleting it would leave the manual
  path with no hardware awareness at all. **Not a PM question — architecture-resolved and
  consistent with the F4 resolution.**
  <!-- the Staff Engineer F8: NOTE is sole hardware signal on manual path, not redundant belt-and-suspenders; O2 self-consistent with F4. -->

## Notes
- `coordinator:fan-out` and `fan-out-dispatch.sh` percolate OUTWARD to OSS consumers via
  `publish.sh`. The organic-ramp model is *more* portable than a flat 6-8 (it self-calibrates to
  whatever machine the operator is on), so this strengthens the OSS story rather than complicating it.
- After integration, the diff edits `fan-out-dispatch.sh` + its test + the fan-out skill — re-run
  the test as the merge gate (AC2). No path moves, so no `doc-link-checker` closeout chunk.
